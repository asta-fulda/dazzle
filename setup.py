import setuptools


version = open('VERSION').read().strip().split(' ')

setuptools.setup(
  license = 'GNU GPLv3',

  name = 'dazzle',
  version = version[0],

  author = 'Dustin Frisch',
  author_email = 'fooker@lab.sh',

  url = 'http://www.opendesk.net/dazzle',

  description = 'Task based host controll system',
  long_description = open('README').read(),
  keywords = 'dazzle tasks host clone mirror',

  packages = setuptools.find_packages(),

  namespace_packages = [
    'dazzle'
  ],

  install_requires = [
    'blessings >= 1.5.0',
    'sh >= 1.0',
    'humanize >= 0.5',
    'recordtype >= 1.0',
    'paramiko >= 1.12.2',
    'ping >= 0.2',
    'awake >= 1.0'
  ],

  entry_points = {
    'dazzle.commands' : [
      'wakeup = dazzle.commands.ctrl:WakeupCommand',
      'shutdown = dazzle.commands.ctrl:ShutdownCommand',
      'execute = dazzle.commands.ctrl:ExecuteCommand',

      'acquire = dazzle.commands.clone:AcquireCommand',
      'receive = dazzle.commands.clone:ReceiveCommand',

      'clone = dazzle.commands.clone:CloneCommand',
    ],

    'console_scripts' : [
      'dazzle = dazzle.__main__:main'
    ]
  },
)
