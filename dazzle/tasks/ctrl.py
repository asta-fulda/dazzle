from dazzle.host import HostTask, group
from dazzle.task import JobState

from dazzle.utils import *
from dazzle.commands import *

import re



class Wakeup(HostTask):
  ''' Waking up host '''

  ip_route_get_re = re.compile(r'''
    ^
    (?P<dst>
      ([\d\.]+)
    )
    \ +dev\ +(?P<dev>
      (\w+)
    )
    \ +src \ +(?P<src>
      ([\d\.]+)
    )
    $
  ''', re.VERBOSE)


  def __init__(self, host):
    try:
      self.__etherwake = sh.etherwake

    except:
      self.__etherwake = sh.ether_wake

    HostTask.__init__(self, host)


  def check(self):
    if ping(self.host):
      return 'Host is already up'


  def run(self):
    # Find the interface to send the wake up packet from
    for line in sh.ip.route.get(self.host.l3addr):
      route = self.ip_route_get_re.match(line.strip())

      if route and route.group('dst') == self.host.l3addr:
        device = route.group('dev')
        break

    else:
      self.state = JobState.States.Failed('Can\'t find interface for host: %s' % self.host.l3addr)


    # Try 60 times to wake the host up
    for x in xrange(0, 60):
      # Update task's progress
      self.progress = 'Poke %02d / 60' % (x + 1)

      # Send out wake up packets
      self.__etherwake(self.host.l2addr,
                       '-i', device)

      # Check if the host is up
      if ping(self.host,
              timeout = 1):
        break

    else:
      self.state = JobState.States.Failed('Host does not wake up in time')



class Shutdown(HostTask):
  ''' Shutting down host '''


  def check(self):
    if not ping(self.host):
      return 'Host is already down'


  def run(self):
    ssh(self.host, 'poweroff',
        _ok_code = [0, 255])



class Execute(HostTask):
  ''' Execute given command on host '''


  def __init__(self, host, command):
    HostTask.__init__(self, host)

    self.__command = command


  @property
  def command(self):
    return self.__command


  def check(self):
    if not ping(self.host):
      return 'Host is not reachable'


  def run(self):
    self.progress = self.command

    return ssh(self.host, self.command)


  @staticmethod
  def argparser(parser):
    parser.add_argument(dest = 'command',
                        metavar = 'COMMAND',
                        type = str,
                        help = 'the command to run on the remote host(s)')



WakeupGroup = group(Wakeup)
ShutdownGroup = group(Shutdown)
ExecuteGroup = group(Execute)
