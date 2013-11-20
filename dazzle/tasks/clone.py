from dazzle.host import HostTask, HostSetMixin, group
from dazzle.task import Task, JobState, job
from dazzle.commands import *
from dazzle.utils import *

from dazzle.tasks.ctrl import Wakeup, Shutdown

import re
import threading
import humanize




class Acquire(Wakeup):
  ''' Boot host in maintenance mode '''

  def check(self):
    if Wakeup.check(self) is None:
      return None

    try:
      ssh(self.host).cat('/etc/maintenance')

    except:
      return None

    else:
      return 'Host is already in maintenance mode'


  @property
  def pre(self):
    return Shutdown(self,
                    host = self.host)


  def run(self):
    ip = ''.join('%02X' % int(i)
               for
               i in self.host.l3addr.split('.'))

    template = '/srv/tftp/pxelinux.cfg/maintenance'
    config = '/srv/tftp/pxelinux.cfg/%s' % ip

    with job(self, 'Enable maintenance config', self.host) as j:
      if not os.path.exists(template):
        j.status = JobState.Failed('Maintenance TFTP config template is missing: %s' % template)

      if os.path.exists(config):
        j.status = JobState.Failed('Client specific TFTP config file already exists: %s' % config)

      ln(template,
         config)

    try:
      Wakeup.run(self)

    finally:
      with job(self, 'Disable maintenance config', self.host) as j:
        rm(config)



class Receive(HostTask):
  ''' Receive data on host '''

  udp_receiver_stat_re = re.compile(r'''
    ^
    bytes=\ *(?P<tran>
      (([0-9]{1,3})
      |([0-9]{1,3})\ ([0-9]{1,3})
      |([0-9]{1,3})\ ([0-9]{1,3})\ ([0-9]{1,3}))
      (\ |M|K)
    )
    \ *\(\ *
      (?P<mbps>
        (\d+(\.\d+)?)
      )\ +Mbps
    \)
    \ *.*
    $
  ''', re.VERBOSE)


  def __init__(self, parent, host, dst):
    HostTask.__init__(self,
                      parent = parent,
                      host = host)

    self.__dst = dst

    self.__event_ready = threading.Event()
    self.__event_recvy = threading.Event()


  @property
  def event_ready(self):
    return self.__event_ready


  @property
  def event_recvy(self):
    return self.__event_recvy


  @property
  def pre(self):
    return Acquire(self,
                   host = self.host)


  @property
  def post(self):
    return Shutdown(self,
                    host = self.host)


  def run(self):
    stream = ssh(self.host)('udp-receiver',
                            '--mcast-rdv-address', '224.0.0.1',
                            '--nokbd',
                            '--file', self.__dst,
                            '--pipe', '"/usr/bin/lzop -dc"',
                            _err_bufsize = 0,
                            _iter = 'err')

    def stream_lines(eol = '\n'):
      line = ''
      for x in stream:
        if x == eol:
          yield line
          line = ''

        else:
          line += x

    # Wait for ready state and notify about it
    for line in stream_lines():
      if line.startswith('Compressed UDP receiver'): break

    self.progress = 'Ready'
    self.__event_ready.set()

    # Wait for receiving state and notify about it
    for line in stream_lines():
      if line.startswith('Connected as'): break

    self.progress = 'Connected'
    self.__event_recvy.set()

    # Get transfer status and update process
    for line in stream_lines(eol = '\r'):
      stats = self.udp_receiver_stat_re.match(line.strip())

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

  udp_sender_stat_re = re.compile(r'''
    ^
    bytes=\ *(?P<tran>
      (([0-9]{1,3})
      |([0-9]{1,3})\ ([0-9]{1,3})
      |([0-9]{1,3})\ ([0-9]{1,3})\ ([0-9]{1,3}))
      (\ |M|K)
    )
    \ *.*
    $
  ''', re.VERBOSE)

  def __init__(self, parent, hosts, src, dst):
    Task.__init__(self,
                  parent = parent,
                  element = '[%s]' % ', '.join(str(host)
                                               for host
                                               in hosts))

    self.__hosts = hosts

    self.__src = src
    self.__dst = dst


  def run(self):
    threads = {receiver: threading.Thread(target = receiver)
               for receiver
               in [Receive(parent = self,
                           host = host,
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
                           '--min-receivers', len(threads),
                           '--mcast-data-address', '224.0.0.1',
                           '--max-bitrate', '500m',
                           '--file', self.__src,
                           '--pipe', '/usr/bin/lzop',
                           _iter = 'err')

    for line in stream:
      stats = self.udp_sender_stat_re.match(line.strip())

      if stats:
        tran = stats.group('tran').replace(' ', '')

        if tran[-1] == 'M':
          tran = int(tran[:-1]) * 1024 * 1024

        elif tran[-1] == 'K':
          tran = int(tran[:-1]) * 1024

        else:
          tran = int(tran)

        self.progress = '%s/s' % humanize.naturalsize(tran,
                                                      binary = True,
                                                      gnu = True)

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
