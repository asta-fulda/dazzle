import socket
import collections
import argparse
import logging
import threading
import paramiko
import ConfigParser as configparser

from dazzle.task import Task



class Host(object):
  ''' A host definition.
  '''
  
  def __init__(self, label, mac, ip):
    self.__label = label
    
    self.__mac = mac
    
    # Resolve the hostname to an IP address
    self.__ip = socket.gethostbyname(ip)


  @property
  def label(self):
    return self.__label


  @property
  def mac(self):
    return self.__mac


  @property
  def ip(self):
    return self.__ip


  def __str__(self):
    return self.__label



class HostList(object):
  ''' Manager for the host list.
      
      The host list is read from the config file using an .ini format parser
      upon startup.
      
      Each host is accessable by its label and its defined group.
  '''
  
  def __init__(self, path = '/etc/dazzle.conf'):
    parser = configparser.SafeConfigParser()
    parser.read(path)

    self.__hosts = {}
    self.__groups = collections.defaultdict(lambda: [])
    
    # Loop over all sections - one section per host
    for label in parser.sections():
      try:
        # Create a host entry
        host = Host(label = label,
                    mac = parser.get(label, 'mac'),
                    ip = parser.get(label, 'ip'))

      except Exception as e:
        logging.warn('Ignoring host: %s (%s)', label, e)

      else:
        # Remember host definition
        self.__hosts[label] = host
        
        # Check if host is assigned to one or more groups and add host to list
        # of host for each group
        if parser.has_option(label, 'group'):
          for group in parser.get(label, 'group').split(','):
            self.__groups[group.strip()].append(host)


  def get(self, label):
    ''' Returns a list of for the given label.
        
        If the label starts with an '@', the group with the name matching the
        label is returned. If the group name is empty, the whole set of defined
        hosts is returned.
    '''
    
    if label == '@':
      # Return all defined hosts
      return self.__hosts.itervalues()

    if label.startswith('@') and label[1:] in self.__groups:
      # Returns the hosts of the specified group
      return iter(self.__groups[label[1:]])

    if label in self.__hosts:
      # Returns the host with the specified label
      return iter([self.__hosts[label]])

    raise KeyError()
    

'''
class HostTask(Task):
  def __init__(self, parent, host):
    Task.__init__(self,
                  parent = parent,
                  element = host)

    self.__host = host

    self.__ssh_client = paramiko.SSHClient()
    self.__ssh_client.load_system_host_keys()
    self.__ssh_client.set_missing_host_key_policy(paramiko.WarningPolicy())
    self.__ssh_client.connect(self.host.ip)


  def __del__(self):
    self.__ssh_client.close()


  @property
  def host(self):
    return self.__host


  def do(self, command):
    session = self._transport.open_session()
    session.exec_command(command)

    return session.makefile('rb')



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
    def __init__(self, parent, hosts, **kwargs):
      Task.__init__(self,
                    parent = parent)

      self.__hosts = hosts

      self.__tasks = [taskcls(parent = self,
                              host = host,
                              **kwargs)
                      for host
                      in hosts]


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
'''