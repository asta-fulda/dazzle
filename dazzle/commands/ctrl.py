import time

from dazzle.task import HostTask, SimpleCommandTask
from dazzle.job import FailedJobState



def ping(host, timeout = None):
  ''' Helper function to ping a host.
      
      The given host must be an instance of Host.
      
      The method returns True if the host was pinged successfully, False
      otherwise.
  '''
   
  import ping
  
  if not timeout:
    timeout = 1
  
  return ping.do_one(host.ip,
                     timeout = timeout,
                     psize = 56) is not None



class WakeupTask(HostTask):
  ''' Waking up host '''
  
  from awake import wol


  def check(self):
    if ping(self.host):
      return 'Host is already up'


  def execute(self):
    # Try 120 times to wake the host up
    for x in xrange(0, 120):
      # Update task's progress
      self.job.progress('Try %02d / 120' % (x + 1))

      # Send out wake up packets
      WakeupTask.wol.send_magic_packet(self.host.mac)

      # Check if the host is up
      if ping(self.host,
              timeout = 1):
        break

    else:
      self.job.state(FailedJobState('Host does not wake up in time'))



class ShutdownTask(HostTask):
  ''' Shutting down host '''


  def check(self):
    if not ping(self.host):
      return 'Host is already down'


  def execute(self):
    result = self.rsh('/sbin/poweroff')
    if result.status != 0:
      self.job.state(FailedJobState(result.output))
    
    # Try 120 times to shut the host down
    for x in xrange(0, 120):
      
      # Update task's progress
      self.job.progress('Try %02d / 120' % (x + 1))
      
      # Check if the host is up
      if not ping(self.host,
                  timeout = 1):
        break
      
      # Give the host a chance to shut down
      time.sleep(1)
      
    else:
      self.job.state(FailedJobState('Host does not shut down in time'))



class ExecuteTask(HostTask):
  ''' Execute given command on host '''


  def __init__(self, parent, host, command):
    HostTask.__init__(self,
                     parent = parent,
                     host = host)

    self.__command = command


  @property
  def command(self):
    return self.__command


  def check(self):
    if not ping(self.host):
      return 'Host is not reachable'


  def execute(self):
    self.progress(self.command)

    return self.sh(self.command)


  @staticmethod
  def argparser(parser):
    parser.add_argument(dest = 'command',
                        metavar = 'COMMAND',
                        type = str,
                        help = 'the command to run on the remote host(s)')



WakeupCommand = SimpleCommandTask(WakeupTask)
ShutdownCommand = SimpleCommandTask(ShutdownTask)
ExecuteCommand = SimpleCommandTask(ExecuteTask)
