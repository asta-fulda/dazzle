from dazzle.utils import *

import sh
from sh import (
  ErrorReturnCode,
  cp,
  rm,
  mkdir,
  ln,
#   curl,
#   make,
#   find,
#   cpio,
#   tar,
#   gzip,
#   ldd,
#   sed,
#   dropbearkey,
#   printf,
#   ssh,
#   ping,
#   arp,
#   udp_sender,
#   udp_receiver
)

try:
  from sh import etherwake
except:
  from sh import ether_wake as etherwake

from shutil import (
  rmtree
)

from tempfile import (
  mkdtemp
)



# Make the comandos more error resistent
mkdir = mkdir.bake('-p')
cp = cp.bake('-pL')
rm = rm.bake('-fR')
ln = ln.bake('-f')



def cp_script(src, dst):
  cp(src, dst)
  sh.chmod('+x', src)



def cp_exec(src, dst):
  with cd(dst):
    cp_lib(src, dst)

    for line in sh.ldd(src):
      lib = sh.sed('-e',
                   r''' /\//!d;
                        /linux-gate/d;
                        /=>/ {s/.*=>[[:blank:]]*\([^[:blank:]]*\).*/\1/};
                        s/[[:blank:]]*\([^[:blank:]]*\) (.*)/\1/
                  ''',
                  _in = line[:-1])
      if lib:
        cp_lib(str(lib), dst)



def cp_lib(src, dst):
  with cd(dst):
    cp(src, src[1:])
