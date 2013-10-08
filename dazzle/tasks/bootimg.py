from abc import abstractmethod, abstractproperty

from dazzle.task import Task, job, JobState
from dazzle.utils import *
from dazzle.commands import *

import urllib
import itertools
import re



class BuildTask(Task):

  element = property(lambda self: None)


  def __init__(self, parent, workspace = None):
    if workspace is None:
      self.__workspace = mkdtemp(prefix = 'dazzle-kernel-')
      self.__workspace_tmp = True

    else:
      self.__workspace = workspace
      self.__workspace_tmp = False

    mkdir(self.__workspace)

    self.__log = open(self.workdir + '.log', 'wa')

    Task.__init__(self,
                  parent = parent)


  @property
  def log(self):
    return self.__log


  @property
  def workspace(self):
    return self.__workspace


  @property
  def workspace_tmp(self):
    return self.__workspace_tmp


  @abstractproperty
  def project(self):
    pass


  @property
  def workdir(self):
    return mkpath(self.workspace, self.project)


  @abstractmethod
  def target(self):
    pass


  def __del__(self):
    self.__log.close()

    if self.workspace_tmp:
      with job(self, 'Cleaning up'):
        rmtree(self.__workspace)

    self.__workspace = None


  @staticmethod
  def argparser(parser):
    parser.add_argument('--workspace',
                        dest = 'workspace',
                        metavar = 'DIR',
                        default = None,
                        type = str,
                        help = 'reuse an existing build environment')



class CompileTask(BuildTask):

  def __init__(self, parent, workspace, target):
    BuildTask.__init__(self,
                       parent = parent,
                       workspace = workspace)

    self.__workdir_src = mkpath(self.workdir, 'src')
    self.__workdir_dst = mkpath(self.workdir, 'dst')

    self.__target = target


  @property
  def workdir_src(self):
    return self.__workdir_src


  @property
  def workdir_dst(self):
    return self.__workdir_dst


  @property
  def target(self):
    return self.__target


  @abstractproperty
  def url(self):
    pass


  @property
  def archive(self):
    archive_file = self.url.split('/')[-1]
    archive_algo = archive_file.rsplit('.')[-1]

    if archive_algo == 'bz2':
      archive_algo = 'bzip2'

    return archive_file, archive_algo


  def download(self, j):
    archive_file, _ = self.archive

    if not self.workspace_tmp and os.path.exists(mkpath(self.workdir, archive_file)):
      j.state = JobState.Skipped(('Using existing file: %s' % mkpath(self.workdir, archive_file)))
      return

    def report(blocknum, blocksize, size):
      j.progress = '%05.2f %%' % round(float(blocknum * blocksize) * 100.0 / float(size), 2)

    urllib.urlretrieve(url = self.url,
                       filename = archive_file,
                       reporthook = report)


  def extract(self, j):
    archive_file, archive_algo = self.archive

    def report(line):
      j.progress = '%s %%' % int(line.strip())

    sh.tar(sh.pv(archive_file,
                 '-n',
                 _piped = True,
                 _err = report),
           '--strip-components=1',
           '--%s' % archive_algo,
           extract = True,
           verbose = True,
           directory = self.workdir_src,
           _out = self.log)


  @abstractmethod
  def compile(self, j):
    pass


  @abstractmethod
  def install(self, j):
    pass


  def run(self):
    mkdir(self.workdir_src)
    mkdir(self.workdir_dst)

    with cd(self.workdir):
      with job(self, 'Download %s source' % self.project) as j:
        self.download(j)

      with job(self, 'Extracting %s source' % self.project) as j:
        self.extract(j)

      with job(self, 'Compile %s' % self.project) as j:
        self.compile(j)

      with job(self, 'Install %s' % self.project) as j:
        self.install(j)



class Kernel(CompileTask):
  ''' Download and compile kernel '''

  @property
  def project(self):
    return 'kernel'


  @property
  def url(self):
    return 'https://www.kernel.org/pub/linux/kernel/v3.x/linux-3.11.1.tar.xz'


  def compile(self, j):
    with cd(self.workdir_src):
      if self.workspace_tmp:
        sh.make('O=%s' % self.workdir_dst,
                'clean',
                _out = self.log)

      sh.cp(resource('kernel.config'),
            mkpath(self.workdir_dst, '.config'))

      sh.make('O=%s' % self.workdir_dst,
              'vmlinux',
              'modules',
              '-j4',
              _out = self.log)


  def install(self, j):
    with cd(self.workdir_src):
      sh.make('O=%s' % self.workdir_dst,
              'modules_install',
              _env = {'INSTALL_MOD_PATH': self.target},
              _out = self.log)


  def create(self, initramfs, target):
    with cd(self.workdir_src):
      sh.make('O=%s' % self.workdir_dst,
              'bzImage',
              '-j4',
              _out = self.log)

    with cd(self.workdir_dst):
      cp('arch/x86/boot/bzImage',
         'arch/x86/boot/bzImage.bak')

    with cd(self.workdir_src):
      sh.make('O=%s' % self.workdir_dst,
              'CONFIG_INITRAMFS_SOURCE=%s' % initramfs,
              'bzImage',
              '-j4',
              _out = self.log)

    with cd(self.workdir_dst):
      cp('arch/x86_64/boot/bzImage',
         target)



class Busybox(CompileTask):
  ''' Download and build busybox '''

  @property
  def project(self):
    return 'busybox'


  @property
  def url(self):
    return 'http://www.busybox.net/downloads/busybox-1.21.1.tar.bz2'


  def compile(self, j):
    with cd(self.workdir_src):
      if self.workspace_tmp:
        sh.make('O=%s' % self.workdir_dst,
                'clean',
                _out = self.log)

      sh.cp(resource('busybox.config'),
            mkpath(self.workdir_dst, '.config'))

      sh.make('O=%s' % self.workdir_dst,
              'busybox',
              '-j4',
              _out = self.log)


  def install(self, j):
    with cd(self.workdir_src):
      sh.make('O=%s' % self.workdir_dst,
              'CONFIG_PREFIX=%s' % self.target,
              'install',
              _out = self.log)

    with cd(self.target):
      mkdir('etc/udhcpc/')
      cp_script(resource('udhcpc'), 'etc/udhcpc/default.script')



class Dropbear(CompileTask):
  ''' Download and build dropbear '''

  @property
  def project(self):
    return 'dropbear'


  @property
  def url(self):
    return 'https://matt.ucc.asn.au/dropbear/releases/dropbear-2012.55.tar.bz2'


  def compile(self, j):
    with cd(self.workdir_dst):
      sh.sh('%s/configure' % self.workdir_src,
            '--prefix', '/usr',
            '--disable-zlib',
            '--enable-bundled-libtom',
            _out = self.log)

      if self.workspace_tmp:
        sh.make('thisclean',
                _out = self.log)

      with cd(self.workdir_src):
        sh.sed('-i',
               's' \
               '|#define DEFAULT_PATH "/usr/bin:/bin"' \
               '|#define DEFAULT_PATH "/usr/sbin:/sbin:/usr/bin:/bin"' \
               '|g',
               'options.h')

      sh.make(# 'STATIC=1',
              'all',
              '-j4',
              _out = self.log)


  def install(self, j):
    with cd(self.workdir_dst):
      sh.make('install',
              'DESTDIR=%s' % self.target,
              _out = self.log)

    with job(self, 'Create host keys'):
      with cd(self.target):
        # Generate host keys
        mkdir('etc/dropbear/')

        dropbearkey = sh.Command(mkpath(self.workdir_dst, 'dropbearkey'))

        rm('etc/dropbear/dropbear_rsa_host_key')
        dropbearkey('-t', 'rsa',
                    '-f', 'etc/dropbear/dropbear_rsa_host_key',
                    _out = self.log)

        rm('etc/dropbear/dropbear_dss_host_key')
        dropbearkey('-t', 'dss',
                    '-f', 'etc/dropbear/dropbear_dss_host_key',
                    _out = self.log)


class XZUtils(CompileTask):
  ''' Download and build xz utils '''

  @property
  def project(self):
    return 'xz'


  @property
  def url(self):
    return 'http://tukaani.org/xz/xz-5.0.5.tar.xz'


  def compile(self, j):
    with cd(self.workdir_dst):
      sh.sh('%s/configure' % self.workdir_src,
            '--prefix', '/usr',
            '--disable-lzma-links',
            '--disable-lzmadec',
            '--disable-lzmainfo',
            '--disable-scripts',
            '--disable-threads',
            '--disable-xzdec',
            '--disable-shared',
            _out = self.log)

      if self.workspace_tmp:
        sh.make('clean',
                _out = self.log)

      sh.make('all',
#               'LDFLAGS=--static',
              '-j4',
              _out = self.log)


  def install(self, j):
    with cd(self.workdir_dst):
      # We don't need most of the stuff xz would install - so do it manually
      sh.install('-d',
                 mkpath(self.target, 'usr/bin'))
      sh.install('-m755',
                 'src/xz/xz',
                 mkpath(self.target, 'usr/bin'))



class UDPCast(CompileTask):
  ''' Download and build udpcast '''

  @property
  def project(self):
    return 'udpcast'


  @property
  def url(self):
    return 'http://pkgs.fedoraproject.org/repo/pkgs/udpcast/udpcast-20120424.tar.gz/b9b67a577ca5659a93bcb9e43f298fb2/udpcast-20120424.tar.gz'


  def compile(self, j):
    with cd(self.workdir_dst):
      sh.sh('%s/configure' % self.workdir_src,
            '--prefix', '/usr',
            _out = self.log)

      if self.workspace_tmp:
        sh.make('clean',
                _out = self.log)

      sh.make('all',
#               'LDFLAGS=--static',
              '-j4',
              _out = self.log)


  def install(self, j):
    with cd(self.workdir_dst):
      # Can't use the standard make install because of a bug during out of tree
      # builds - copy the two programs manually
      # sh.make('install',
      #         'DESTDIR=%s' % self.target,
      #         _out = self.log)
      sh.install('-d',
                 mkpath(self.target, 'usr/sbin'))
      sh.install('-m755',
                 'udp-sender',
                 'udp-receiver',
                 mkpath(self.target, 'usr/sbin'))



class Image(BuildTask):
  ''' Create maintenance boot image '''

  ldconfig_re = re.compile(r'''
    ^
    \s+
    (?P<name>
      libnss_(files
             |dns
             ).so.2
    )
    \ \((?P<spec>
      .*
    )\)
    \ =>
    \ (?P<path>
      .+
    )
    $
  ''', re.VERBOSE)

  ldd_re = re.compile(r'''
    ^
    \s+(
      linux-(vdso|gate).so.1
    |
      (
        (\S+\ =>\ )?
        (?P<path>/\S+)
      )
    )
    \ \(0x[0-9a-f]+\)
    $
  ''', re.VERBOSE)


  def __init__(self, parent, workspace, target):
    BuildTask.__init__(self,
                       parent = parent,
                       workspace = workspace)

    self.__kernel = Kernel(parent = parent, workspace = workspace, target = self.workdir)
    self.__busybox = Busybox(parent = parent, workspace = workspace, target = self.workdir)
    self.__dropbear = Dropbear(parent = parent, workspace = workspace, target = self.workdir)
    self.__xzutils = XZUtils(parent = parent, workspace = workspace, target = self.workdir)
    self.__udpcast = UDPCast(parent = parent, workspace = workspace, target = self.workdir)

    self.__target = target


  @property
  def target(self):
    return self.__target


  @property
  def project(self):
    return 'image'


  @property
  def pre(self):
    return [self.__kernel,
            self.__busybox,
            self.__dropbear,
            self.__udpcast,
            self.__xzutils]


  def run(self):
    with cd(self.workdir):

      if self.workspace_tmp:
        rm('*')

      with job(self, 'Create base layout'):
        for d in [
            'etc',
            'dev', 'dev/pts',
            'var', 'var/run',
            'lib',
            'proc',
            'sys',
        ]: mkdir(d)

        # Create initial device nodes
        for name, major, minor in [
            ('mem    ', 1, 1),
            ('kmem   ', 1, 2),
            ('null   ', 1, 3),
            ('port   ', 1, 4),
            ('zero   ', 1, 5),
            ('full   ', 1, 7),
            ('random ', 1, 8),
            ('urandom', 1, 9),
            ('tty    ', 5, 0),
            ('console', 5, 1),
        ]:
          path = mkpath('dev', name)
          rm(path)
          sh.mknod(path,
                   'c',
                   major,
                   minor)

      with job(self, 'Copy NSS libraries'):
        libs = []
        for line in sh.Command('/sbin/ldconfig')('-p'):
          lib = self.ldconfig_re.match(line)
          if lib:
            libs.append(lib.groupdict())

        for lib in (sorted(libs, key = lambda lib: len(lib['spec'].split(',')))[-1]
                    for _, libs
                    in itertools.groupby(libs, lambda lib: lib['name'])):
          cp_lib(lib['path'],
                 self.workdir)

      with job(self, 'Create root user'):
        with open('etc/passwd', 'w') as f:
          f.write('root::0:0:root:/root:/bin/sh\n')

        with open('etc/group', 'w') as f:
          f.write('root::0:root\n')

        mkdir('root/')
        mkdir('root/.ssh/')

        try:
          cp('/root/.ssh/id_dsa.pub',
             'root/.ssh/authorized_keys')

        except:
          cp('/root/.ssh/id_rsa.pub',
             'root/.ssh/authorized_keys')

        sh.chmod('0600', 'root/.ssh/authorized_keys')

      with job(self, 'Copy system config files'):
        cp(resource('nsswitch.conf'),
           'etc')

      with job(self, 'Configure boot scripts'):
        ln('bin/busybox', 'init')
        ln('bin/busybox', 'sh')

        mkdir('etc/init.d/')
        cp_script(resource('rcS'),
                  'etc/init.d/rcS')

        cp_script(resource('inittab'),
                  'etc/inittab')

      with job(self, 'Copy required libraries'):
        for prog in sh.find(self.workdir,
                            '-type', 'f',
                            '-executable',
                            _iter = True):
          try:
            for line in sh.ldd(prog[:-1], _iter = True):
              lib = self.ldd_re.match(line)
              if lib and lib.group('path'):
                cp_lib(lib.group('path'),
                       self.workdir)

          except:
            pass


      with job(self, 'Create initamfs'):
        initramfs = 'initramfs.cpio'

        sh.cpio(sh.find('.',
                        '-not', '-path', './%s' % initramfs,
                        _piped = True),
                create = True,
                format = 'newc',
                verbose = True,
                _piped = True,
                _out = initramfs,
                _err = self.log)

      with job(self, 'Create boot image'):
        self.__kernel.create(initramfs = mkpath(self.workdir, initramfs),
                             target = self.target)


  @staticmethod
  def argparser(parser):
    BuildTask.argparser(parser)

    parser.add_argument('target',
                        metavar = 'TARGET',
                        default = 'srv/tftp/maintenance',
                        type = str,
                        help = 'the path of the boot image to create')
