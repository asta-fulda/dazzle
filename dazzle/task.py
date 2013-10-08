from abc import ABCMeta, abstractmethod, abstractproperty
from enum import Enum

import inspect
import threading
import collections
import pkg_resources
import blessings
import contextlib
import traceback
import recordtype
import os
import sh
import functools
import enum



def saveiter(thing):
  if thing is None:
    return iter([])

  if not isinstance(thing, collections.Iterable):
    return iter([thing])

  return iter(thing)



def find_tasks(entry_point_group):
  for entry_point in pkg_resources.iter_entry_points(group = entry_point_group):
    taskcls = entry_point.load()

    assert not inspect.isabstract(taskcls)

    taskcls._task_name = entry_point.name
    taskcls._task_help = inspect.getdoc(taskcls)

    yield taskcls



terminal = blessings.Terminal()
terminal_lock = threading.Lock()



class JobState(object):
  pass



class FinishedJobState(JobState):
  def __init__(self, message = None):
    JobState.__init__(self)

    self.__message = message


  @property
  def message(self):
    return self.__message



JobState.New = type('New', (JobState,), {})

JobState.Checking = type('Checking', (JobState,), {})

JobState.PreRunning = type('PreRunning', (JobState,), {})
JobState.Running = type('Running', (JobState,), {})
JobState.PostRunning = type('PostRunning', (JobState,), {})

JobState.Success = type('Success', (FinishedJobState,), {})
JobState.Skipped = type('Skipped', (FinishedJobState,), {})
JobState.Failed = type('Failed', (FinishedJobState,), {})



class Job(object):

  def __init__(self, parent):
    self.__parent = parent
    self.__childs = []

    if parent is not None:
      parent.childs.append(self)
      parent.__notify()

    self.__state = JobState.New
    self.__progress = None

    self.__listeners = set()

    object.__init__(self)


  @property
  def manager(self):
    return self.__parent.manager


  @property
  def parent(self):
    return self.__parent


  @property
  def childs(self):
    return self.__childs


  @property
  def level(self):
    if self.parent is None:
      return 0

    return self.parent.level + 1


  @property
  def state(self):
    return self.__state


  @state.setter
  def state(self, value):
    self.__state = value
    self.__progress = None

    self.manager.update(self)


  @property
  def progress(self):
    return self.__progress


  @progress.setter
  def progress(self, value):
    self.__progress = value

    self.manager.update(self)


  @property
  def listeners(self):
    return self.__listeners


  def __notify(self):
    for listener in self.listeners:
      listener(self)


  @abstractproperty
  def title(self):
    pass


  @abstractproperty
  def element(self):
    pass



@contextlib.contextmanager
def job_error_handler(job):
  try:
    yield

  except sh.ErrorReturnCode as ex:
    if ex.stderr:
      message = ex.stderr[:-1]

    elif ex.stdout:
      message = ex.stdout[:-1]

    else:
      message = traceback.format_exc()

    job.state = JobState.Failed(message.decode('utf-8'))

  except Exception:
    message = traceback.format_exc()

    job.state = JobState.Failed(message.decode('utf-8'))



@contextlib.contextmanager
def job(parent, title, element = None):
  class ContextJob(Job):
    title = property(lambda self: title)
    element = property(lambda self: element)

  job = ContextJob(parent = parent)

  with job_error_handler(job):
    running_state = job.state = JobState.Running()

    yield job

    # Jobs can set their state on it's own - don't mess around with it if it was
    # changed from the running state to something else
    if job.state == running_state:
      job.state = JobState.Success()



class JobManager(object):

  state_format = {
    JobState.New: terminal.bold_black(' .. '),
    JobState.Checking: terminal.bold_yellow(' ?? '),
    JobState.PreRunning: terminal.bold_cyan('>>') + terminal.cyan('> '),
    JobState.Running: terminal.cyan('>') + terminal.bold_cyan('>>') + terminal.cyan('>'),
    JobState.PostRunning: terminal.cyan(' >') + terminal.bold_cyan('>>'),
    JobState.Success: terminal.bold_green(' OK '),
    JobState.Skipped: terminal.bold_blue(' ** '),
    JobState.Failed: terminal.bold_red('!!!!'),
  }


  class RootJob(Job):
    title = None
    element = None

    def __init__(self, manager):
      self.__manager = manager

      Job.__init__(self, parent = None)

    @property
    def manager(self):
      return self.__manager


  def __init__(self):
    object.__init__(self)

#     self.__finished_jobs = set()
#     self.__active_jobs = set()

    self.__root = JobManager.RootJob(manager = self)
#     self.__root.listeners += self.update()

    self.__jobs = []


  @property
  def root(self):
    return self.__root

  def __print_reset(self, n):
    terminal.stream.write('\r')
    terminal.stream.write(terminal.move_up * n)


  def __print_line(self, line = ''):
    terminal.stream.write('%s%s\n' % (line,
                                      terminal.clear_eol))


  def __print_skip(self):
    terminal.stream.write('\n')


  def __print_job(self, job):
    line = terminal.bold_white('[ ') + \
           JobManager.state_format[type(job.state)] + \
           terminal.bold_white(' ] ')

    if job.title is not None: line += '%s' % job.title
    if job.element is not None: line += ': %s' % job.element
    if job.progress is not None: line += ' (%s)' % job.progress

    self.__print_line(line)


  def __print_sep(self):
    self.__print_line(terminal.bold_black('-' * terminal.width))


  def __print_message(self, message):
    width = terminal.width - 9

    for line in message.split('\n'):
      line = line.rstrip()
      for i in range(0, len(line), width - 1):
        self.__print_line(terminal.bold_white('       | ') + \
                          line[i:i + width])


  def update(self, updated_job):
    with terminal_lock:
      if updated_job not in self.__jobs:
        # New job
        self.__jobs.append(updated_job)

        self.__print_reset(0)
        self.__print_job(updated_job)

      elif type(updated_job.state) in [JobState.Success,
                                       JobState.Skipped]:
        # Leaving job
        self.__jobs.remove(updated_job)

        # Print the finished job topmost
        self.__print_reset(len(self.__jobs) + 1)
        self.__print_job(updated_job)

        # Print the message if it exists
        if updated_job.state.message is not None:
          self.__print_message(updated_job.state.message)

        # Print remaining jobs
        for job in self.__jobs:
          self.__print_job(job)

      elif type(updated_job.state) == JobState.Failed:
        # Failing job
        self.__print_sep()
        self.__print_job(updated_job)

        # Check if we have message and print it
        if updated_job.state.message is not None:
          self.__print_message(updated_job.state.message)

        # Hard exiting of the process
        os._exit(1)

      else:
        # Updated job
        self.__print_reset(len(self.__jobs))

        for job in self.__jobs:
          # Test if we have to reprint the line - and skip it if not
          if job != updated_job:
            self.__print_skip()
            continue

          self.__print_job(job)


job_manager = JobManager.instance = JobManager()



class Task(Job):
  __metaclass__ = ABCMeta


  def __init__(self, parent):
    self.__title = inspect.getdoc(self).split('\n')[0].strip()

    Job.__init__(self,
                 parent = parent)


  @property
  def title(self):
    return self.__title


  @abstractproperty
  def element(self):
    pass


  @abstractmethod
  def run(self):
    pass


  def check(self):
    pass


  @property
  def pre(self):
    pass


  @property
  def post(self):
    pass


  def __call__(self):
    with job_error_handler(self):

      # Run pre task(s)
      pre = self.pre
      if pre is not None:
        self.state = JobState.PreRunning()
        for task in saveiter(pre):
          task()

      # Check if task must run
      self.state = JobState.Checking()
      excuse = self.check()

      # Run the task if it's required
      if excuse is None:
        self.state = JobState.Running()
        message = self.run()

      # Run post task(s)
      post = self.post
      if post is not None:
        self.state = JobState.PostRunning()
        for task in saveiter(post):
          task()

      # Update the status
      if excuse is None:
        self.state = JobState.Success(message)

      else:
        self.state = JobState.Skipped(excuse)


  def __str__(self):
    return '<%s(%s) @ %s>' % (self.__class__.__name__,
                             self.title,
                             self.element)
