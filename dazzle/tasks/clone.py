from dazzle.host import HostTask, group

from dazzle.commands import *
from dazzle.utils import *
from dazzle.task import JobState, job

from dazzle.tasks.ctrl import Wakeup, Shutdown

import re
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
    bytes=(?P<bytes>
      (([0-9]{1,3})\ +)+
    )
    \ +\(
      (?P<mbps>
        (\d+(\.\d+)?)
      \ +Mbps)
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
    self.__event_ready


  @property
  def event_recvy(self):
    self.__event_recvy


  @property
  def pre(self):
    return Acquire(self.host)


  @property
  def post(self):
    return Shutdown(self.host)


  def run(self):
    stream = ssh(self.host,
                 'udp-receiver',
                 '--mcast-rdv-address 224.0.0.1',
                 '--nokbd',
                 '--file', self.__dst,
                 _iter = 'err')

    # Wait for ready state and notify about it
    for line in stream:
      if line.startswith('UDP receiver'): break

    self.__event_ready.set()

    # Wait for receiving state and notify about it
    for line in stream:
      if line.startswith('Connected as'): break

    self.__event_recvy.set()

    # Get transfer status and update process
    for line in stream:
      stats = self.udp_receiver_stat_re.match(line)

      if stats:
        self.progress = '%(bytes)s @ %(mbps)s MB/s' % {'bytes' : humanize.naturalsize(stats.group('bytes'),
                                                                                      binary = True),
                                                       'mbps' : stats.groupd('mbps')}


  @staticmethod
  def argparser(parser):
    parser.add_argument('--dst',
                        dest = 'dst',
                        metavar = 'DEV',
                        required = True,
                        type = str,
                        help = 'the device to copy to')



AcquireGroup = group(Acquire)
ReceiveGroup = group(Receive)
