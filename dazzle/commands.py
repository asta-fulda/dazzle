from dazzle.utils import *

import sh
from sh import (
  ErrorReturnCode,
  cp,
  rm,
  mkdir,
  ln
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



def cp_lib(src, dst):
  with cd(dst):
    mkdir(os.path.dirname(src[1:]))
    cp(src, src[1:])
