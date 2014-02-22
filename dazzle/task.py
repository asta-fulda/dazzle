from abc import ABCMeta, abstractmethod

import os
import inspect
import traceback
import paramiko
import pkg_resources
import multiprocessing

from dazzle.job import Job, CheckingJobState, PreRunningJobState, PostRunningJobState, RunningJobState, SkippedJobState, SuccessJobState, FailedJobState
from dazzle.utils import saveiter



class Task(object):
  def __init__(self,
               presenter,
               parent,
               title):
    self.__job = Job(presenter = presenter,
                     parent = parent.__job if parent is not None else None,
                     title = title)
    


  def check(self):
    ''' Checks if the task must run.
        
        Each task can deny its own executing by returning a excuse from this
        methods implementation.
    '''
    return None


  @property
  def pre(self):
    ''' Returns the tasks running pre this job.
        
        A task implementation can return a task or a list of tasks which
        must be executed pre this task itself is running.
    '''
    return None
  
  
  @abstractmethod
  def execute(self):
    ''' Executes this task. '''
    pass


  @property
  def post(self):
    ''' Returns the tasks running post this job.
        
        A task implementation can return a task or a list of tasks which
        must be executed post this task itself is running.
    '''
    return None


  def __call__(self):
    try:
      # Check if job must run
      self.job.state(CheckingJobState())
      excuse = self.check()
      
      # Exit early, if the job has en excuse not to run
      if excuse is not None:
        self.__job.state(SkippedJobState(excuse))
        return

      # Run pre job(s)
      pre = self.pre
      if pre is not None:
        self.job.state(PreRunningJobState())
        for task in saveiter(pre):
          task()
          
      # Run the job
      self.job.state(RunningJobState())
      message = self.execute()

      # Run post job(s)
      post = self.post
      if post is not None:
        self.job.state(PostRunningJobState())
        for task in saveiter(post):
          task()

      # Update the status
      self.job.state(SuccessJobState(message))
    
    except:
      traceback.print_exc()
      
      message = traceback.format_exc()

      self.job.state(FailedJobState(message.decode('utf-8')))
  
  
  @property
  def job(self):
    return self.__job



class HostTask(Task):
  def __init__(self,
               presenter,
               parent,
               host):
    Task.__init__(self,
                  presenter = presenter,
                  parent = parent,
                  title = '%s: %s' % (inspect.getdoc(self).split('\n')[0].strip(),
                                      host.label))
    
    self.__host = host
    
    self.__ssh = paramiko.SSHClient()
    self.__ssh.load_system_host_keys()
    self.__ssh.set_missing_host_key_policy(paramiko.WarningPolicy())


  @property
  def host(self):
    return self.__host


  def sh(self, command):
    pass
  
  
  def rsh(self, command):
    # Connect to the host
    self.__ssh.connect(self.host.ip,
                       username = 'root',
                       password = 'root')
    
    # Open a channel
    channel = self.__ssh.get_transport().open_session()
    
    # Execute the command on remote
    channel.exec_command(command)
    
    # Get stderr and stdout
    stdout = channel.makefile('rb', -1).read()
    stderr = channel.makefile_stderr('rb', -1).read()
    
    # Get return code
    status = channel.recv_exit_status()
    
    # Close the connection
    self.__ssh.close()
    
    # Return stdout on success, stderr otherwise
    if status == 0:
      return stdout
    
    else:
      return stderr
    
    self.__ssh.close()



class CommandTask(Task):
  class __metaclass__(ABCMeta):
    def __iter__(self):
      ''' Searches for all task implementations.
        
          The entry point group is searched for all registered, non-abstract
          classes.
      '''
      
      for entry_point in pkg_resources.iter_entry_points(group = 'dazzle.commands'):
        command_cls = entry_point.load()
        
        assert issubclass(command_cls, CommandTask)
        assert not inspect.isabstract(command_cls)
        
        command_cls.task_name = entry_point.name
        command_cls.task_help = inspect.getdoc(command_cls)
    
        yield command_cls
  
  
  def __init__(self,
               presenter,
               hosts):
    Task.__init__(self,
                  presenter,
                  parent = None,
                  title = '%s: [%s]' % (inspect.getdoc(self).split('\n')[0].strip(),
                                        ', '.join(host.label
                                                  for host
                                                  in hosts)))
    
    self.__presenter = presenter
    
    self.__hosts = hosts


  @abstractmethod
  def create_task(self, host):
    ''' Creates the task to execute for the given host.
        
        A task implementation can return a task for the given job. If no job
        should be executed, None can be returned.
    '''
    pass
  
  
  def execute(self):
    processes = {task: multiprocessing.Process(target = task)
                 for task
                 in (self.create_task(host)
                     for host
                     in self.__hosts)
                 if task is not None}
    
    for process in processes.itervalues():
      process.start()
    
    for process in processes.itervalues():
      process.join()


  @property
  def hosts(self):
    return self.__hosts
  
  
  @property
  def presenter(self):
    return self.__presenter
    


def SimpleCommandTask(host_task_cls):
  ''' Decorator to transform a HostTask into a CommandTask.
      
      The decorator can be used to transform a class implementing a HostTask
      into a class implementing a CommandTask and make it able to be used as
      directly executable task.
      
      For each host passed to the task, an instance of the class is created
      respectively.
      
      The wrapped class is preserved and accessable by the wrappings class .task
      property
  '''
  
  class Wrapper(CommandTask):
    task = host_task_cls
    
    def __init__(self,
                 presenter,
                 hosts,
                 **kwargs):
      
      CommandTask.__init__(self,
                           presenter = presenter,
                           hosts = hosts)
      
      self.__kwargs = kwargs


    def create_task(self, host):
      return host_task_cls(presenter = self.presenter,
                           parent = self,
                           host = host,
                           **self.__kwargs)
    
    
    @staticmethod
    def argparser(parser):
      # Check if wrapped class defines an argument parser and forward to it
      if hasattr(host_task_cls, 'argparser'):
        host_task_cls.argparser(parser)
  
  # Face the wrappers name and documentation
  Wrapper.__name__ = '@%s' % host_task_cls.__name__
  Wrapper.__doc__ = host_task_cls.__doc__
  
  return Wrapper
