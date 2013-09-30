from abc import ABCMeta, abstractmethod, abstractproperty
from enum import Enum

import sys
import inspect
import threading
import collections
import functools
import pkg_resources
import blessings
import traceback
import contextlib
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
                       'Aborted',
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
    return self.__title


  @abstractproperty
  def element(self):
    pass



@contextlib.contextmanager
def job(title, element = None):
  class ContextJob(Job):
    title = property(lambda self: title)
    element = property(lambda self: element)

  job = ContextJob()


  try:
    job.state = JobState.States.Running()

    yield job

    job.state = JobState.States.Finished()

  except sh.ErrorReturnCode as ex:
    job.state = JobState.States.Failed(ex.stderr or ex.stderr)

  except Exception as ex:
    job.state = JobState.States.Failed(str(ex))



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
    terminal.stream.write('%s%s\n' % (line.decode("utf8"),
                                      terminal.clear_eol))

  def __print_skip(self):
    terminal.stream.write('\n')


  def __print_job(self, job):
    line = '[ %s ] ' % JobManager.state_format[type(job.state)]

    if job.title is not None: line += '%s' % job.title
    if job.element is not None: line += ': %s' % job.element
    if job.progress is not None: line += ' (%s)' % job.progress

    self.__print_line(line)


  def update(self, job):
    with terminal_lock:
      terminal.stream.write('\r')

      if job not in self.__jobs:
        # New job
        self.__jobs.append(job)

        self.__print_reset(0)
        self.__print_job(job)

      elif type(job.state) in [JobState.States.Finished,
                             JobState.States.Skipped,
                             JobState.States.Failed]:
        # Leaving job
        self.__jobs.remove(job)

        self.__print_reset(len(self.__jobs) + 1)
        self.__print_job(job)

        for j in self.__jobs:
          self.__print_job(j)

        if type(job.state) == JobState.States.Failed:
          # Failing job

          self.__print_line()
          self.__print_job(job)
          self.__print_line(job.state.message)

          traceback.print_exc()

          sys.exit(1)

      else:
        # Updated job
        self.__print_reset(len(self.__jobs))

        for j in self.__jobs:
          if j == job:
            self.__print_job(j)

          else:
            self.__print_skip()


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
    return True


  @property
  def pre(self):
    pass


  @property
  def post(self):
    pass


  def __call__(self):
    try:
      if self.pre:
        self.state = JobState.States.PreRunning()
        for task in saveiter(self.pre):
          task()

      self.state = JobState.States.Checking()
      run = self.check()

      if run:
        self.state = JobState.States.Running()
        self.run()

      if self.post:
        self.state = JobState.States.PostRunning()
        for task in saveiter(self.post):
          task()

      if run:
        self.state = JobState.States.Finished()
      else:
        self.state = JobState.States.Skipped()

    except sh.ErrorReturnCode as ex:
      job.state = JobState.States.Failed(ex.stderr or ex.stderr)

    except Exception as ex:
      self.state = JobState.States.Failed(str(ex))


  def __str__(self):
    return '<%s(%s) @ %s>' % (self.__class__.__name__,
                             self.title,
                             self.element)




class GroupTask(Task):
  def __init__(self, tasks):

    self.__tasks = tasks

    Task.__init__(self)


  @property
  def tasks(self):
    return self.__tasks



class SerializedGroupTask(GroupTask):

  def run(self):
    for task in self.tasks:
      task()



class ParallelizedGroupTask(GroupTask):

  def run(self):
    threads = [threading.Thread(target = task)
               for task
               in self.tasks]

    for thread in threads:
      thread.start()

    for thread in threads:
      thread.join()



def group(groupcls, mixincls, plur, sing):
  assert issubclass(groupcls, GroupTask)

  def wrapper(taskcls):
    assert issubclass(taskcls, Task)

    def __init__(self, **kwargs):
      groupcls.__init__(self, tasks = [taskcls(**dict(kwargs.items() +
                                                      [(sing, element)]))
                                       for element
                                       in kwargs.pop(plur)])

    wrapped = type('Grouped' + taskcls.__name__,
                    (groupcls, mixincls),
                    {'__init__': __init__,
                     'element': property(lambda self: ', '.join(str(task.element) for task in self.tasks))})

    wrapped.__doc__ = taskcls.__doc__
    wrapped.__module__ = taskcls.__module__

    return wrapped

  return wrapper



serialize = functools.partial(group, SerializedGroupTask)
parallelize = functools.partial(group, ParallelizedGroupTask)
