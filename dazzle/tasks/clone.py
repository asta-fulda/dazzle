from dazzle.host import HostTask, group

from dazzle.commands import *
from dazzle.utils import *
from dazzle.task import JobState

from dazzle.tasks.ctrl import Wakeup, Shutdown

import re
import threading
import humanize



def ip2hex(host):
  return ''.join('%02X' % int(i)
                 for
                 i in host.l3addr.split('.'))



class Acquire(HostTask):
  ''' Enable maintenance mode '''

  def check(self):
    try:
      ssh(self.host, 'cat', '/etc/maintenance')

    except:
      return True

    else:
      return False


  @property
  def pre(self):
    return Shutdown(host = self.host)


  def run(self):
    src = '/srv/tftp/pxelinux.cfg/maintenance'
    dst = '/srv/tftp/pxelinux.cfg/%s' % ip2hex(self.host)

    if not os.path.exists(src):
      self.status = JobState.States.Failed('Maintenance TFTP config is missing: %s' % src)

    if os.path.exists(dst):
      self.status = JobState.States.Failed('Client specific TFTP config already exists: %s' % dst)

    ln(dst, src)


  @property
  def post(self):
    return Wakeup(self.host)



class Release(HostTask):
  ''' Disable maintenance mode '''

  def check(self):
    try:
      ssh(self.host, 'cat', '/etc/maintenance')

    except:
      return False

    else:
      return True


  def run(self):
    rm('/srv/tftp/pxelinux.cfg/%s' % ip2hex(self.host))


  @property
  def post(self):
    return Shutdown(self.host)



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
    return Release(self.host)


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
ReleaseGroup = group(Release)
ReceiveGroup = group(Receive)
