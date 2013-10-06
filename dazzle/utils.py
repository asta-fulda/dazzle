import os
import contextlib

from os.path import join as mkpath

import sh



def resource(path):
  from pkg_resources import resource_filename, Requirement

  return resource_filename(Requirement.parse('dazzle'), mkpath('resources', path))



def checkrc(func):
  def __(*args, **kwargs):
    try:
      func(*args, **kwargs)
      return True

    except Exception as ex:
      return False

  return __



@contextlib.contextmanager
def cd(new_path):
  old_path = os.getcwd()
  os.chdir(new_path)

  yield

  os.chdir(old_path)



@checkrc
def ping(host,
         timeout = 3):
  sh.ping('-c', '3',
          '-i', '0.2',
          '-w', timeout,
          host.l3addr)



def ssh(host, *args, **kwargs):
  sh.ssh('-q',
         '-o', 'UserKnownHostsFile=/dev/null',
         '-o', 'StrictHostKeyChecking=no',
         '-o', 'PasswordAuthentication=no',
         '-l root',
         host.l3addr,
         *args,
         **kwargs)
