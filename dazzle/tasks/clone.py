from dazzle.host import HostTask, HostSetMixin, group
from dazzle.task import Task, JobState, job
from dazzle.commands import *
from dazzle.utils import *

from dazzle.tasks.ctrl import Wakeup, Shutdown

import re
import sys
import threading
import humanize



class MaintenanceConfigManager(object):

  def __init__(self, host):
    self.__host = host

    ip = ''.join('%02X' % int(i)
                 for
                 i in host.l3addr.split('.'))

    self.__template = '/srv/tftp/pxelinux.cfg/maintenance'
    self.__config = '/srv/tftp/pxelinux.cfg/%s' % ip


  @property
  def template(self):
    return self.__template


  @property
  def config(self):
    return self.__config


  def create(self):
    with job('Enable maintenance config', self.__host) as j:
      if not os.path.exists(self.template):
        j.status = JobState.States.Failed('Maintenance TFTP config template is missing: %s' % self.template)

      if os.path.exists(self.config):
        j.status = JobState.States.Failed('Client specific TFTP config file already exists: %s' % self.config)

      ln('-s',
         self.template,
         self.config)


  def remove(self):
    with job('Disable maintenance config', self.__host) as j:
      if not os.path.exists(self.config):
        self.status = JobState.States.Skipped('Client specific TFTP config file does not exists: %s' % self.config)

      rm(self.config)



class Acquire(Wakeup):
  ''' Boot host in maintenance mode '''

  def __init__(self, host):
    Wakeup.__init__(self, host)

    self.__maintenance_mgr = MaintenanceConfigManager(host = self.host)



  def check(self):
    if Wakeup.check(self) is None:
      return None

    try:
      ssh(self.host, 'cat', '/etc/maintenance')

    except:
      return None

    else:
      return 'Host is already in maintenance mode'


  @property
  def pre(self):
    return Shutdown(host = self.host)


  def run(self):
    self.__maintenance_mgr.create()

    try:
      Wakeup.run(self)

    finally:
      self.__maintenance_mgr.remove()



class Receive(HostTask):
  ''' Run data retrieval on host '''

  udp_receiver_stat_re = re.compile(r'''
    ^
    bytes=\ *(?P<tran>
      (([0-9]{1,3})
      |([0-9]{1,3})\ ([0-9]{1,3})
      |([0-9]{1,3})\ ([0-9]{1,3})\ ([0-9]{1,3}))
      (\ |M|K)
    )
    \ +\(
      (?P<mbps>
        (\d+(\.\d+)?)
      )\ +Mbps
    \)
    $
  ''', re.VERBOSE)


  def __init__(self, host, dst):
    self.__dst = dst

    self.__event_ready = threading.Event()
    self.__event_recvy = threading.Event()

    HostTask.__init__(self, host)


  @property
  def event_ready(self):
    return self.__event_ready


  @property
  def event_recvy(self):
    return self.__event_recvy


  @property
  def pre(self):
    return Acquire(self.host)


  @property
  def post(self):
    return Shutdown(self.host)


  def run(self):
    stream = ssh(self.host,
                 'udp-receiver',
                 '--mcast-rdv-address', '224.0.0.1',
                 '--nokbd',
                 '--file', self.__dst,
                 _err_bufsize = 0,
                 _iter = 'err')

    def stream_lines(eol = '\n'):
      line = ''
      for x in stream:
        if x != eol:
          line += x

        else:
          yield line
          line = ''

    # Wait for ready state and notify about it
    for line in stream_lines():
      if line.startswith('UDP receiver'): break

    self.progress = 'Ready'
    self.__event_ready.set()

    # Wait for receiving state and notify about it
    for line in stream_lines():
      if line.startswith('Connected as'): break

    self.progress = 'Connected'
    self.__event_recvy.set()

    # Get transfer status and update process
    for line in stream_lines(eol = '\r'):
      stats = self.udp_receiver_stat_re.match(line)

      if stats:
        tran = stats.group('tran').replace(' ', '')

        if tran[-1] == 'M':
          tran = int(tran[:-1]) * 1024 * 1024

        elif tran[-1] == 'K':
          tran = int(tran[:-1]) * 1024

        else:
          tran = int(tran)

        tran = humanize.naturalsize(tran,
                                    binary = True)

        mbps = stats.group('mbps')

        self.progress = '%(tran)s @ %(mbps)s MB/s' % {'tran' : tran,
                                                       'mbps' : mbps}


  @staticmethod
  def argparser(parser):
    parser.add_argument('--dst',
                        dest = 'dst',
                        metavar = 'DEV',
                        required = True,
                        type = str,
                        help = 'the device to copy to')



class Clone(Task, HostSetMixin):
  ''' Clone to hosts '''

  def __init__(self, hosts, src, dst):
    self.__hosts = hosts

    self.__src = src
    self.__dst = dst

    Task.__init__(self)


  @property
  def element(self):
    return '[%s]' % ', '.join(str(host)
                              for host
                              in self.__hosts)


  def run(self):
    threads = {receiver: threading.Thread(target = receiver)
               for receiver
               in [Receive(host = host,
                           dst = self.__dst)
                   for host
                   in self.__hosts]}

    # Start receiver tasks
    for receiver in threads.itervalues():
      receiver.start()

    # Wait for all task be ready
    for receiver in threads.iterkeys():
      receiver.event_ready.wait()

    stream = sh.udp_sender('--mcast-rdv-address', '224.0.0.1',
                           '--nokbd',
                           '--interface', 'virbr0',
                           '--min-receivers', len(threads),
                           '--file', self.__src,
                           _iter = 'err')

    for line in stream:
      self.progress = line[:-1]

    # Wait for all task finish
    for receiver in threads.itervalues():
      receiver.join()


  @staticmethod
  def argparser(parser):
    parser.add_argument('--src',
                        dest = 'src',
                        metavar = 'DEV',
                        required = True,
                        type = str,
                        help = 'the device to copy from')
    parser.add_argument('--dst',
                        dest = 'dst',
                        metavar = 'DEV',
                        required = True,
                        type = str,
                        help = 'the device to copy to')

    HostSetMixin.argparser(parser)



AcquireGroup = group(Acquire)
ReceiveGroup = group(Receive)
