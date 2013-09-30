from abc import abstractmethod, abstractproperty

import urllib

from dazzle.task import Task, job
from dazzle.utils import *
from dazzle.commands import *



class BuildTask(Task):

  element = property(lambda self: None)


  def __init__(self):
#     self.__workdir = mkdtemp(prefix = 'dazzle-kernel-')
    self.__workdir = mkpath('/tmp/dazzle', type(self).__name__)
    mkdir(self.__workdir)

    self.__log = open(self.__workdir + '.log', 'wa')

    Task.__init__(self)


  @property
  def log(self):
    return self.__log


  @property
  def workdir(self):
    return self.__workdir


  def __del__(self):
    self.__log.close()

#     with job('Cleaning up'):
#       rmtree(self.__workdir)

    self.__workdir = None



class CompileTask(BuildTask):

  def __init__(self, target):
    BuildTask.__init__(self)

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
  def project(self):
    pass


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

    def reporthook(blocknum, blocksize, size):
      j.progress = '%05.2f %%' % round(float(blocknum * blocksize) * 100.0 / float(size), 2)

    urllib.urlretrieve(url = self.url,
                       filename = archive_file,
                       reporthook = reporthook)


  def extract(self, j):
    archive_file, archive_algo = self.archive

    def reporthook(line):
      j.progress = '%s %%' % int(line.strip())

    sh.tar(sh.pv(archive_file,
                 '-n',
                 _piped = True,
                 _err = reporthook),
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
      with job('Download %s source' % self.project) as j:
        self.download(j)

      with job('Extracting %s source' % self.project) as j:
        self.extract(j)

      with job('Compile %s' % self.project) as j:
        self.compile(j)

      with job('Install %s' % self.project) as j:
        self.install(j)


  @staticmethod
  def argparser(parser):
    parser.add_argument(dest = 'target',
                        metavar = 'TARGET',
                        type = str,
                        help = 'the installation target')



class Kernel(CompileTask):
  ''' Download and compile kernel '''

  def __init__(self, target):
    CompileTask.__init__(self, target)


  @property
  def project(self):
    return 'kernel'


  @property
  def url(self):
    return 'https://www.kernel.org/pub/linux/kernel/v3.x/linux-3.11.1.tar.xz'


  def compile(self, j):
    with cd(self.workdir_src):
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

  def __init__(self, target):
    CompileTask.__init__(self, target)


  @property
  def project(self):
    return 'busybox'


  @property
  def url(self):
    return 'http://www.busybox.net/downloads/busybox-1.21.1.tar.bz2'


  def compile(self, j):
    with cd(self.workdir_src):
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

  def __init__(self, target):
    CompileTask.__init__(self, target)


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
            '--enable-bundled-libtom')

      sh.make('thisclean',
              _out = self.log)

      sh.make('STATIC=1',
              'all',
              '-j4',
              _out = self.log)


  def install(self, j):
    with cd(self.workdir_dst):
      sh.make('install',
              'DESTDIR=%s' % self.target,
              _out = self.log)

    with job('Create host keys'):
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



class UDPCast(CompileTask):
  ''' Download and build udpcast '''

  def __init__(self, target):
    CompileTask.__init__(self, target)


  @property
  def project(self):
    return 'udpcast'


  @property
  def url(self):
    # return 'http://www.udpcast.linux.lu/download/udpcast-20120424.tar.gz'
    return 'http://pkgs.fedoraproject.org/repo/pkgs/udpcast/udpcast-20120424.tar.gz/b9b67a577ca5659a93bcb9e43f298fb2/udpcast-20120424.tar.gz'


  def compile(self, j):
    with cd(self.workdir_dst):
      sh.sh('%s/configure' % self.workdir_src,
            '--prefix', '/usr')

      sh.make('clean',
              _out = self.log)

      sh.make('all',
              'LDFLAGS=--static',
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
  ''' Download, compile and install maintenance boot image '''

  def __init__(self, target):
    self.__target = target

    BuildTask.__init__(self)

    self.__kernel = Kernel(target = self.workdir)
    self.__busybox = Busybox(target = self.workdir)
    self.__dropbear = Dropbear(target = self.workdir)
    self.__udpcast = UDPCast(target = self.workdir)


  @property
  def target(self):
    return self.__target


  @property
  def pre(self):
    return [self.__kernel,
            self.__busybox,
            self.__dropbear,
            self.__udpcast]


  def run(self):
    with cd(self.workdir):
      with job('Create base layout'):
        for d in [
            'etc',
            'dev', 'dev/pts',
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

      with job('Create root user'):
        with open('etc/passwd', 'w') as f:
          f.write('root::0:0:root:/root:/bin/sh\n')

        with open('etc/group', 'w') as f:
          f.write('root::0:root\n')

        mkdir('root/')
        mkdir('root/.ssh/')

      with job('Configure boot scripts'):
        ln('bin/busybox', 'init')
        ln('bin/busybox', 'sh')

        mkdir('etc/init.d/')
        cp_script(resource('rcS'), 'etc/init.d/rcS')

      with job('Create initamfs'):
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

      with job('Create boot image'):
        self.__kernel.create(initramfs = mkpath(self.workdir, initramfs),
                             target = self.target)


  @staticmethod
  def argparser(parser):
    parser.add_argument(dest = 'target',
                        metavar = 'TARGET',
                        type = str,
                        help = 'the installation target')
