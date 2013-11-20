from abc import ABCMeta, abstractmethod

import inspect
import threading
import collections
import pkg_resources
import blessings
import contextlib
import traceback
import time
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
  antecedent = []



class ActiveJobState(JobState):
  def __init__(self):
    JobState.__init__(self)



class FinishedJobState(JobState):
  def __init__(self, message = None):
    JobState.__init__(self)

    self.__message = message


  @property
  def message(self):
    return self.__message



JobState.Checking = type('Checking', (ActiveJobState,), {})
JobState.Checking.antecedent = [type(None)]

JobState.PreRunning = type('PreRunning', (ActiveJobState,), {})
JobState.PreRunning.antecedent = [type(None),
                                  JobState.Checking]

JobState.Running = type('Running', (ActiveJobState,), {})
JobState.Running.antecedent = [type(None),
                               JobState.Checking,
                               JobState.PreRunning]

JobState.PostRunning = type('PostRunning', (ActiveJobState,), {})
JobState.PostRunning.antecedent = [JobState.Running]

JobState.Success = type('Success', (FinishedJobState,), {})
JobState.Success.antecedent = [JobState.Running,
                               JobState.PostRunning]

JobState.Skipped = type('Skipped', (FinishedJobState,), {})
JobState.Skipped.antecedent = [JobState.Checking]

JobState.Failed = type('Failed', (FinishedJobState,), {})
JobState.Failed.antecedent = [JobState.Checking,
                              JobState.PreRunning,
                              JobState.Running,
                              JobState.PostRunning]



class Job(object):

  def __init__(self,
               parent,
               title,
               element = None):
    self.__parent = parent
    self.__childs = []

    self.__title = title

    self.__element = element

    self.__state = None
    self.__progress = None

    self.__listeners = set()

    if parent is not None:
      parent.childs.append(self)
      parent.__notify()

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
  def state(self, new_state):
    assert type(self.__state) in type(new_state).antecedent

    old_state = self.__state
    self.__state = new_state

    self.__progress = None

    self.manager.update(self,
                        old_state = old_state,
                        new_state = new_state)


  @property
  def progress(self):
    return self.__progress


  @progress.setter
  def progress(self, value):
    self.__progress = value

    self.manager.update(self,
                        old_state = self.state,
                        new_state = self.state)


  @property
  def listeners(self):
    return self.__listeners


  def __notify(self):
    for listener in self.listeners:
      listener(self)


  @property
  def title(self):
    return self.__title


  @property
  def element(self):
    return self.__element



@contextlib.contextmanager
def job_exception_handler(job):
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
  job = Job(parent = parent,
            title = title,
            element = element)

  with job_exception_handler(job):
    running_state = job.state = JobState.Running()

    yield job

    # Jobs can set their state on it's own - don't mess around with it if it was
    # changed from the running state to something else
    if job.state == running_state:
      job.state = JobState.Success()



class JobManager(threading.Thread):

  state_format = {
    JobState.Checking: [terminal.bold_yellow('.') + terminal.yellow('.') + terminal.bold_yellow('.') + terminal.yellow('.'),
                        terminal.yellow('.') + terminal.bold_yellow('.') + terminal.yellow('.') + terminal.bold_yellow('.')],

    JobState.PreRunning: [terminal.bold_cyan('>') + terminal.cyan('>> '),
                          terminal.bold_cyan('>>') + terminal.cyan('> '),
                          terminal.cyan('>') + terminal.bold_cyan('>> '),
                          terminal.cyan('>>') + terminal.bold_cyan('> ')],

    JobState.Running: [terminal.bold_cyan('>') + terminal.cyan('>>>'),
                       terminal.bold_cyan('>>') + terminal.cyan('>>'),
                       terminal.cyan('>') + terminal.bold_cyan('>>') + terminal.cyan('>'),
                       terminal.cyan('>>') + terminal.bold_cyan('>>'),
                       terminal.cyan('>>>') + terminal.bold_cyan('>')],

    JobState.PostRunning: [terminal.bold_cyan(' >') + terminal.cyan('>>'),
                           terminal.bold_cyan(' >>') + terminal.cyan('>'),
                           terminal.cyan(' >') + terminal.bold_cyan('>>'),
                           terminal.cyan(' >>') + terminal.bold_cyan('>')],

    JobState.Success: terminal.bold_green(' OK '),
    JobState.Skipped: terminal.bold_blue(' ** '),
    JobState.Failed: terminal.bold_red('!!!!'),
  }


  class RootJob(Job):
    def __init__(self, manager):
      Job.__init__(self,
                   parent = None,
                   title = None,
                   element = None)

      self.__manager = manager


    @property
    def manager(self):
      return self.__manager


  def __init__(self):
    threading.Thread.__init__(self)

    self.__root = JobManager.RootJob(manager = self)

    self.__active_jobs = set()

    self.__animation_ticks = 0

    self.daemon = True
    self.start()

    terminal.stream.write('-' * (terminal.width if terminal.is_a_tty else 80))

  @property
  def root(self):
    return self.__root


  @staticmethod
  def __print_backlog(job):
    line = terminal.bold_white('[ ') + \
           JobManager.state_format[type(job.state)] + \
           terminal.bold_white(' ] ')

    line += job.title

    if job.element is not None:
      line += ': %s' % job.element

    terminal.stream.write('%s%s\n' % (line,
                                      terminal.clear_eol))

    if job.state.message:
      width = (terminal.width - 9) if terminal.is_a_tty else 71

      for line in job.state.message.split('\n'):
        line = line.rstrip()
        for i in range(0, len(line), width - 1):
          terminal.stream.write('%s%s%s\n' % (terminal.bold_white('       : '),
                                              line[i:i + width],
                                              terminal.clear_eol))


  def update(self, updated_job, old_state, new_state):
    with terminal_lock:
      # Unwind active block
      terminal.stream.write('\r')
      terminal.stream.write(terminal.move_up * len(self.__active_jobs))

      if (type(old_state) == type(None) and
          type(new_state) != type(None)):
        # New job started
        self.__active_jobs.add(updated_job)

      if type(new_state) in [JobState.Success,
                             JobState.Skipped]:
        # Job finished
        self.__print_backlog(updated_job)

      if type(new_state) in [JobState.Success,
                             JobState.Skipped,
                             JobState.Failed]:
        # Job ended
        self.__active_jobs.remove(updated_job)

      # Progress or state update - redraw active block
      def print_childs(parent):
        for job in parent.childs:
          if job.state is None or job not in self.__active_jobs:
            continue

          frames = JobManager.state_format[type(job.state)]

          line = terminal.bold_white('[ ') + \
                 frames[self.__animation_ticks % len(frames)] + \
                 terminal.bold_white(' ] ')

          line += '  ' * (job.level - 1)

          if job.title is not None: line += '%s' % job.title
          if job.element is not None: line += ': %s' % job.element
          if job.progress is not None: line += ' (%s)' % job.progress

          terminal.stream.write('%s%s\n' % (line,
                                            terminal.clear_eol))

          print_childs(job)

      print_childs(self.root)

      if type(new_state) == JobState.Failed:
        # Job failed
        self.__print_backlog(updated_job)

        # Hard exiting of the process
        os._exit(1)


  def run(self):
    while True:
      time.sleep(1)

      self.__animation_ticks += 1

      self.update(updated_job = None,
                  old_state = None,
                  new_state = None)


job_manager = JobManager.instance = JobManager()



class Task(Job):
  __metaclass__ = ABCMeta


  def __init__(self,
               parent,
               title = None,
               element = None):
    Job.__init__(self,
                 parent = parent,
                 title = title or inspect.getdoc(self).split('\n')[0].strip(),
                 element = element)


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
    with job_exception_handler(self):

      # Check if task must run
      self.state = JobState.Checking()
      excuse = self.check()

      if excuse is not None:
        self.state = JobState.Skipped(excuse)
        return

      # Run pre task(s)
      pre = self.pre
      if pre is not None:
        self.state = JobState.PreRunning()
        for task in saveiter(pre):
          task()

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
      self.state = JobState.Success(message)
