import setuptools


version = open('VERSION').read().strip()

setuptools.setup(
  license = 'GNU GPLv3',

  name = 'dazzle',
  version = version,

  author = 'Dustin Frisch',
  author_email = 'fooker@lab.sh',

  url = 'http://www.opendesk.net/dazzle',

  description = 'Task based host controll system',
  long_description = open('README').read(),
  keywords = 'dazzle tasks host clone mirror',

  packages = setuptools.find_packages(),

  package_data = {
    'resources': ['*']
  },

  namespace_packages = [
    'dazzle'
  ],

  install_requires = [
    'blessings >= 1.5.0',
    'enum >= 0.4',
    'sh >= 1.0'
  ],

  entry_points = {
    'dazzle.tasks' : [
      'wakeup = dazzle.tasks.ctrl:Wakeup',
      'shutdown = dazzle.tasks.ctrl:Shutdown',

      'acquire = dazzle.tasks.clone:Acquire',
      'release = dazzle.tasks.clone:Release',

      'receive = dazzle.tasks.clone:Receive',

      'kernel = dazzle.tasks.bootimg:Kernel',
      'busybox = dazzle.tasks.bootimg:Busybox',
      'dropbear = dazzle.tasks.bootimg:Dropbear',
      'udpcast = dazzle.tasks.bootimg:UDPCast',

      'bootimg = dazzle.tasks.bootimg:Image',
    ],

    'console_scripts' : [
      'dazzle = dazzle.__main__:main'
    ]
  },
)
