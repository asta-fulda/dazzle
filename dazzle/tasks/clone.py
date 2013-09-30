from dazzle.host import HostTask, HostGroupMixin
from dazzle.task import parallelize
from dazzle.commands import *
from dazzle.utils import *

from dazzle.tasks.ctrl import Wakeup, Shutdown



def ip2hex(host):
  return ''.join('%02X' % int(i)
                 for
                 i in host.l3addr.split('.'))



@parallelize(HostGroupMixin, 'hosts', 'host')
class Acquire(HostTask):
  ''' Enable maintenance mode '''

  def check(self):
    return not ssh(self.host, 'cat', '/etc/maintenance')


  @property
  def pre(self):
    return Shutdown(self.host)


  def run(self):
    ln('/srv/tftp/pxelinux.cfg/maintenance',
       '/srv/tftp/pxelinux.cfg/%s' % ip2hex(self.host))


  @property
  def post(self):
    return Wakeup(self.host)



@parallelize(HostGroupMixin, 'hosts', 'host')
class Release(HostTask):
  ''' Disable maintenance mode '''

  def check(self):
    return ssh(self.host, 'cat', '/etc/maintenance')


  def run(self):
    rm('/srv/tftp/pxelinux.cfg/%s' % ip2hex(self.host))


  @property
  def post(self):
    return Shutdown(self.host)



@parallelize(HostGroupMixin, 'hosts', 'host')
class Receive(HostTask):
  ''' Run data retrieval on host '''

  @property
  def pre(self):
    return Acquire(self.host)


  @property
  def post(self):
    return Release(self.host)


  def run(self):
    ssh(self.host,
        'udp-receiver',
        '--mcast-rdv-address 224.0.0.1',
        '--nokbd',
        '--file /dev/sda')
