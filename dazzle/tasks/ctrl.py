from dazzle.host import HostTask, HostGroupMixin
from dazzle.task import parallelize
from dazzle.utils import *



@parallelize(HostGroupMixin, 'hosts', 'host')
class Wakeup(HostTask):
  ''' Waking up host '''


  def check(self):
    return not ping(self.host)


  def run(self):
    while not ping(self.host):
      sh.etherwake(self.host.l2addr)



@parallelize(HostGroupMixin, 'hosts', 'host')
class Shutdown(HostTask):
  ''' Shutting down host '''


  def check(self):
    return ping(self.host)


  def run(self):
    ssh(self.host, 'poweroff')
