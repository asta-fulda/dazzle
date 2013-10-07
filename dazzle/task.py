from abc import ABCMeta, abstractmethod, abstractproperty
from enum import Enum

import inspect
import threading
import collections
import pkg_resources
import blessings
import contextlib
import traceback
import os
import sh



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
  __metaclass__ = ABCMeta


  def __init__(self, message = None):
    self.__message = message


  @abstractproperty
  def name(self):
    pass


  @property
  def message(self):
    return self.__message



JobState.States = Enum('Checking',

                       'PreRunning',
                       'Running',
                       'PostRunning',

                       'Finished',
                       'Skipped',
                       'Failed',

                       value_type = lambda enum, i, key: type('JobState%s' % key,
                                                              (JobState,),
                                                              {'name' : property(lambda self: key)}))



class Job(object):

  def __init__(self):
    self.__state = None
    self.__progress = None

    object.__init__(self)


  @property
  def state(self):
    return self.__state


  @state.setter
  def state(self, value):
    assert type(value) in JobState.States

    self.__state = value
    self.__progress = None

    JobManager.instance.update(self)


  @property
  def progress(self):
    return self.__progress


  @progress.setter
  def progress(self, value):
    self.__progress = value

    JobManager.instance.update(self)


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

    job.state = JobState.States.Failed(message.decode('utf-8'))

  except Exception:
    message = traceback.format_exc()

    job.state = JobState.States.Failed(message.decode('utf-8'))



@contextlib.contextmanager
def job(title, element = None):
  class ContextJob(Job):
    title = property(lambda self: title)
    element = property(lambda self: element)

  job = ContextJob()

  with job_error_handler(job):
    job.state = JobState.States.Running()

    yield job

    # Jobs can set their state on it's own - don't mess around with it if it was
    # changed from the running state to something else
    if type(job.state) == JobState.States.Running:
      job.state = JobState.States.Finished()



class JobManager(object):

  state_format = {
    JobState.States.Checking: terminal.bold_yellow(' .. '),
    JobState.States.PreRunning: terminal.bold_cyan('>>') + terminal.cyan('> '),
    JobState.States.Running: terminal.cyan('>') + terminal.bold_cyan('>>') + terminal.cyan('>'),
    JobState.States.PostRunning: terminal.cyan(' >') + terminal.bold_cyan('>>'),
    JobState.States.Finished: terminal.bold_green(' OK '),
    JobState.States.Skipped: terminal.bold_blue(' ** '),
    JobState.States.Failed: terminal.bold_red('!!!!'),
  }


  def __init__(self):
    object.__init__(self)

    self.__jobs = list()


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
      for i in range(0, len(line), width):
        self.__print_line(terminal.bold_white('       | ') + \
                          line[i:i + width])


  def update(self, updated_job):
    with terminal_lock:
      terminal.stream.write('\r')

      if updated_job not in self.__jobs:
        # New job
        self.__jobs.append(updated_job)

        self.__print_reset(0)
        self.__print_job(updated_job)

      elif type(updated_job.state) in [JobState.States.Finished,
                                       JobState.States.Skipped]:
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

      elif type(updated_job.state) == JobState.States.Failed:
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


JobManager.instance = JobManager()



class Task(Job):
  __metaclass__ = ABCMeta


  def __init__(self):
    self.__title = inspect.getdoc(self).split('\n')[0].strip()

    Job.__init__(self)


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
        self.state = JobState.States.PreRunning()
        for task in saveiter(pre):
          task()

      # Check if task must run
      self.state = JobState.States.Checking()
      excuse = self.check()

      # Run the task if it's required
      if excuse is None:
        self.state = JobState.States.Running()
        self.run()

      # Run post task(s)
      post = self.post
      if post is not None:
        self.state = JobState.States.PostRunning()
        for task in saveiter(post):
          task()

      # Update the status
      if excuse is None:
        self.state = JobState.States.Finished()

      else:
        self.state = JobState.States.Skipped(excuse)


  def __str__(self):
    return '<%s(%s) @ %s>' % (self.__class__.__name__,
                             self.title,
                             self.element)
