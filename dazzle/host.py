import socket
import collections
import argparse
import logging
import threading
import ConfigParser as configparser

from dazzle.task import Task



class Host(object):
  def __init__(self, label, l2addr, l3addr):
    self.__label = label

    self.__l2addr = l2addr
    self.__l3addr = l3addr

    self.__l3addr = socket.gethostbyname(self.__l3addr)


  @property
  def label(self):
    return self.__label


  @property
  def l2addr(self):
    return self.__l2addr


  @property
  def l3addr(self):
    return self.__l3addr


  def __str__(self):
    return self.__label



class HostList(object):
  def __init__(self, path):
    parser = configparser.SafeConfigParser()
    parser.read(path)

    self.__hosts = {}
    self.__groups = collections.defaultdict(lambda: [])

    for label in parser.sections():
      try:
        host = Host(label = label,
                    l2addr = parser.get(label, 'l2addr'),
                    l3addr = parser.get(label, 'l3addr'))

      except Exception as e:
        logging.warn('Ignoring host: %s (%s)', label, e)

      else:
        self.__hosts[label] = host

        if parser.has_option(label, 'group'):
          for group in parser.get(label, 'group').split(','):
            self.__groups[group.strip()].append(host)


  def get(self, label):
    if label == '@':
      return self.__hosts.itervalues()

    if label.startswith('@'):
      return self.__groups[label[1:]]

    if label in self.__hosts:
      return [self.__hosts[label]]

    raise KeyError()



class HostTask(Task):
  def __init__(self, host):
    self.__host = host

    Task.__init__(self)


  @property
  def element(self):
    return self.host


  @property
  def host(self):
    return self.__host



class HostSetAction(argparse.Action):
  def __call__(self, parser, namespace, values, option = None):
    namespace.hosts = set()

    for value in values:
      try:
        for host in namespace.__hostlist__.get(value):
          namespace.hosts.add(host)

      except KeyError:
        raise argparse.ArgumentError(self, 'Invalid host: %s' % value)



class HostSetMixin(object):

    @staticmethod
    def argparser(parser):
      parser.add_argument('-l', '--list',
                          dest = '__hostlist__',
                          metavar = 'HOSTLIST',
                          type = HostList,
                          required = True,
                          help = 'the host list file')

      parser.add_argument(dest = 'hosts',
                          metavar = 'HOST',
                          type = str,
                          nargs = '+',
                          action = HostSetAction,
                          help = 'the hosts to run the task on')



def group(taskcls):
  # Ensure given class is a host task class
  assert issubclass(taskcls, HostTask)

  class Wrapped(Task, HostSetMixin):
    def __init__(self, hosts, **kwargs):
      self.__hosts = hosts

      self.__tasks = [taskcls(host = host,
                              **kwargs)
                      for host
                      in hosts]

      Task.__init__(self)


    @property
    def hosts(self):
      return self.__hosts


    @property
    def tasks(self):
      return self.__tasks


    @property
    def element(self):
      return '[%s]' % ', '.join(str(task.element)
                                for task
                                in self.tasks)


    def run(self):
      threads = [threading.Thread(target = task)
                 for task
                 in self.tasks]

      for thread in threads:
        thread.start()

      for thread in threads:
        thread.join()


    @staticmethod
    def argparser(parser):
      HostSetMixin.argparser(parser)

      # Check if subclass has arguments defined and attach it to the wrapper
      if hasattr(taskcls, 'argparser'):
        taskcls.argparser(parser)

  # Copy meta data to wrapper class
  Wrapped.__doc__ = taskcls.__doc__
  Wrapped.__name__ = '@%s' % taskcls.__name__

  return Wrapped
