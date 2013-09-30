import os
import contextlib

from os.path import join as mkpath

from sh import which



def resource(path):
  from pkg_resources import resource_filename, Requirement

  return resource_filename(Requirement.parse('dazzle'), mkpath('resources', path))



def checkrc(func):
  def __(*args, **kwargs):
    try:
      func(*args, **kwargs)
      return True

    except Exception:
      return False

  return __



@contextlib.contextmanager
def cd(new_path):
  old_path = os.getcwd()
  os.chdir(new_path)

  yield

  os.chdir(old_path)



@checkrc
def ping(host):
  sh.ping('-c3',
          '-i0.2',
          host.l3addr)



@checkrc
def ssh(host, *args, **kwargs):
  sh.ssh('-q',
         '-o UserKnownHostsFile=/dev/null',
         '-o StrictHostKeyChecking=no',
         '-l root',
         host.l3addr,
         *args,
         **kwargs)
