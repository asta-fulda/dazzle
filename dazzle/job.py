import sh
import os
import time
import logging
import blessings
import threading
import multiprocessing
import multiprocessing.managers
import traceback
import contextlib



class JobState(object):
  antecedent = []



class ActiveJobState(JobState):
  def __init__(self):
    JobState.__init__(self)
  
  
  def __str__(self):
    return '%s' % type(self)



class FinishedJobState(JobState):
  def __init__(self, message = None):
    JobState.__init__(self)

    self.__message = message


  @property
  def message(self):
    return self.__message
  
  
  def __str__(self):
    return '%s(%s)' % (type(self), self.__message)



CheckingJobState = type('CheckingJobState', (ActiveJobState,), {})
CheckingJobState.antecedent = [type(None)]

PreRunningJobState = type('PreRunningJobState', (ActiveJobState,), {})
PreRunningJobState.antecedent = [type(None),
                                 CheckingJobState]

RunningJobState = type('RunningJobState', (ActiveJobState,), {})
RunningJobState.antecedent = [type(None),
                              CheckingJobState,
                              PreRunningJobState]

PostRunningJobState = type('PostRunningJobState', (ActiveJobState,), {})
PostRunningJobState.antecedent = [RunningJobState]

SuccessJobState = type('SuccessJobState', (FinishedJobState,), {})
SuccessJobState.antecedent = [RunningJobState,
                              PostRunningJobState]

SkippedJobState = type('SkippedJobState', (FinishedJobState,), {})
SkippedJobState.antecedent = [CheckingJobState]

FailedJobState = type('FailedJobState', (FinishedJobState,), {})
FailedJobState.antecedent = [CheckingJobState,
                             PreRunningJobState,
                             RunningJobState,
                             PostRunningJobState]



class Job(object):
  def __init__(self,
               manager,
               parent,
               title):
    logging.debug('Creating job: title="%s", parent="%s", manager="%s" (in %s)', title, parent, manager, os.getpid())
    
    self.__node = manager.create(parent = parent.__node if parent is not None else None,
                                 title = title)


  def state(self, state):
    ''' Update the jobs state. '''
    
    logging.debug('Changed job state: %s -> %s', self, state)
    self.__node.set_state(state)


  def progress(self, value):
    ''' Update the jobs progress. '''
    
    logging.debug('Changed progress: "%s" -> "%s"', self, value)
    self.__node.set_progress(value)



@contextlib.contextmanager
def job(parent, title, element = None):
  job = Job(parent = parent,
            title = title,
            element = element)

  try:
    running_state = job.state = JobState.Running()

    yield job

  except:
    traceback.print_exc()
    
    # Jobs can set their state on it's own - don't mess around with it if it was
    # changed from the running state to something else
    if job.state == running_state:
      job.state = JobState.Success()



class JobManager(multiprocessing.managers.BaseManager):
  terminal = blessings.Terminal()
  terminal_lock = threading.Lock()
  
  state_format = {
    CheckingJobState: [terminal.bold_white('[ ') + terminal.bold_yellow('.') + terminal.yellow('.') + terminal.bold_yellow('.') + terminal.yellow('.') + terminal.bold_white(' ]'),
                        terminal.bold_white('[ ') + terminal.yellow('.') + terminal.bold_yellow('.') + terminal.yellow('.') + terminal.bold_yellow('.') + terminal.bold_white(' ]')],

    PreRunningJobState: [terminal.bold_white('[ ') + terminal.bold_cyan('>') + terminal.cyan('>> ') + terminal.bold_white(' ]'),
                          terminal.bold_white('[ ') + terminal.bold_cyan('>>') + terminal.cyan('> ') + terminal.bold_white(' ]'),
                          terminal.bold_white('[ ') + terminal.cyan('>') + terminal.bold_cyan('>> ') + terminal.bold_white(' ]'),
                          terminal.bold_white('[ ') + terminal.cyan('>>') + terminal.bold_cyan('> ') + terminal.bold_white(' ]')],

    RunningJobState: [terminal.bold_white('[ ') + terminal.bold_cyan('>') + terminal.cyan('>>>') + terminal.bold_white(' ]'),
                       terminal.bold_white('[ ') + terminal.bold_cyan('>>') + terminal.cyan('>>') + terminal.bold_white(' ]'),
                       terminal.bold_white('[ ') + terminal.cyan('>') + terminal.bold_cyan('>>') + terminal.cyan('>') + terminal.bold_white(' ]'),
                       terminal.bold_white('[ ') + terminal.cyan('>>') + terminal.bold_cyan('>>') + terminal.bold_white(' ]'),
                       terminal.bold_white('[ ') + terminal.cyan('>>>') + terminal.bold_cyan('>') + terminal.bold_white(' ]')],

    PostRunningJobState: [terminal.bold_white('[ ') + terminal.bold_cyan(' >') + terminal.cyan('>>') + terminal.bold_white(' ]'),
                           terminal.bold_white('[ ') + terminal.bold_cyan(' >>') + terminal.cyan('>') + terminal.bold_white(' ]'),
                           terminal.bold_white('[ ') + terminal.cyan(' >') + terminal.bold_cyan('>>') + terminal.bold_white(' ]'),
                           terminal.bold_white('[ ') + terminal.cyan(' >>') + terminal.bold_cyan('>') + terminal.bold_white(' ]')],

    SuccessJobState: terminal.bold_white('[ ') + terminal.bold_green(' OK ') + terminal.bold_white(' ]'),
    SkippedJobState: terminal.bold_white('[ ') + terminal.bold_blue(' ** ') + terminal.bold_white(' ]'),
    FailedJobState: terminal.bold_white('[ ') + terminal.bold_red('!!!!') + terminal.bold_white(' ]'),
    
    type(None): terminal.bold_white('       :'),
  }
  
  
  class Node(object):
    def __init__(self,
                 manager,
                 parent,
                 title):
      self.__manager = manager
      
      self.__parent = parent
      
      self.__title = title
      self.__state = None
      self.__progress = None
      
      self.__children = []
      
      if self.__parent is not None:
        self.__parent.__children.append(self)
    
    
    @property
    def title(self):
      return self.__title
    
    
    def get_state(self):
      return self.__state
    
    
    def set_state(self, new_state):
      logging.debug('Changed node state: %s -> %s', self, new_state)
      
      assert type(self.__state) in type(new_state).antecedent
    
      old_state = self.__state
      self.__state = new_state
    
      self.__progress = None
    
      self.__manager.update(self,
                            old_state = old_state,
                            new_state = new_state)
    
    
    state = property(get_state,
                     set_state)
    
    
    def get_progress(self):
      return self.__state
      
      
    def set_progress(self, value):
      logging.debug('Changed progress: "%s" -> "%s"', self, value)
      
      self.__progress = value
  
      self.__manager.update(self,
                            old_state = self.state,
                            new_state = self.state)
    
    progress = property(get_progress,
                        set_progress)
    
    
    @property
    def children(self):
      return self.__children
    
    
    @property
    def level(self):
      if self.__parent is None:
        return 0
      
      else:
        return self.__parent.level + 1
    
    
    def __str__(self):
      return 'Node[%s]' % self.__title

  
  def __init__(self):
    multiprocessing.managers.BaseManager.__init__(self)
    
    self.register('create',
                  callable = self.__create)
    
    self.start(self.__init)
    

  def __init(self):
    # Initialize the set of active nodes
    self.__active_nodes = set()
    
    self.__root = JobManager.Node(manager = self,
                                  parent = None,
                                  title = None)
    
    # Initialize the animation
    self.__animation_thread = threading.Thread(target = self.__animate)
    self.__animation_thread.daemon = True
    self.__animation_shutdown = threading.Event()
    self.__animation_ticks = 0

    # Print the initial line
    #JobManager.terminal.stream.write('-' * (JobManager.terminal.width if JobManager.terminal.is_a_tty else 80))

  
  def __create(self,
               parent,
               title):
    logging.debug('Creating node [parent=%s, title="%s"] (in %s)', parent, title, os.getpid())
    
    if parent is None:
      parent = self.__root
    
    node = JobManager.Node(manager = self,
                           parent = parent,
                           title = title)
    
    self.update(node,
                None,
                None)
    
    return node
  

  def shutdown(self):
    ''' Shuts the job manager down.
    '''
    
    # self.__animation_shutdown.set()
    # self.__animation_thread.join()


  @staticmethod
  def __print_backlog(job):
    # Prefix the job line with its file state marker
    prefix = JobManager.state_format[type(job.state)]
      
    # Calculate the maximal with of the title
    width = JobManager.terminal.width if JobManager.terminal.is_a_tty else 80
    width -= len(prefix)
    
    # Trim the title length to avoid line wrapping
    title = JobManager.ellipsis(job.title, width)

    # Print the job line
    JobManager.terminal.stream.write('%s %s\n' % (prefix,
                                                  title))
    JobManager.terminal.stream.write(JobManager.terminal.clear_eol)
    
    # The jobs state is definitly FinishedJobState here
    assert isinstance(job.state, FinishedJobState)
    if job.state.message:
      
      # Prefix the message lines
      prefix = JobManager.state_format[type(None)]
      
      # Calculate the maximal with of the message
      width = JobManager.terminal.width if JobManager.terminal.is_a_tty else 80
      width -= len(prefix)
      
      # Split the message in lines and print the lines indented
      for line in job.state.message.split('\n'):
        line = line.rstrip()
        for i in range(0, len(line), width - 1):
          JobManager.terminal.stream.write('%s %s\n' % (prefix,
                                                        line[i:i + width]))
          JobManager.terminal.stream.write(JobManager.terminal.clear_eol)


  def update(self, updated_node, old_state, new_state):
    logging.debug('Updated node: "%s" (%s -> %s)', updated_node, old_state, new_state)
    
    def __(node):
      logging.debug('  %sShow node: "%s" (children=%s, state=%s, progress=%s)', '  ' * node.level, node.title, node.children, node.state, node.progress)
      
      for child in node.children:
        __(child)
    
    __(self.__root)
    

  def __update(self, updated_node, old_state, new_state):
    with JobManager.terminal_lock:
      # Unwind active block
      JobManager.terminal.stream.write('\r')
      JobManager.terminal.stream.write(JobManager.terminal.move_up * len(self.__active_nodes))

      if (type(old_state) == type(None) and
          type(new_state) != type(None)):
        # New node started
        self.__active_nodes.add(updated_node)

      if type(new_state) in [JobState.Success,
                             JobState.Skipped]:
        # Node finished
        self.__print_backlog(updated_node)

      if type(new_state) in [JobState.Success,
                             JobState.Skipped,
                             JobState.Failed]:
        # Node ended
        self.__active_nodes.remove(updated_node)

      # Progress or state update - redraw active block
      def print_childs(parent):
        for node in parent.children:
          if node.state is None or node not in self.__active_nodes:
            continue
          
          # Get the animation frames for the nodes state
          frames = JobManager.state_format[type(node.state)]
          
          # Prefix the node line with its state marker
          prefix = frames[self.__animation_ticks % len(frames)]
          
          # Prefix the node line with some indention
          prefix += '  ' * (node.level - 1)
          
          # Calculate the progress and the node title
          title = '%s' % node.title if node.title is not None else ''
          progress = '(%s)' % node.progress if node.progress is not None else ''
          
          # Calculate the maximal title length
          width = JobManager.terminal.width if JobManager.terminal.is_a_tty else 80
          width -= len(prefix)
          width -= len(progress)
          
          # Trim the title length to avoid line wrapping
          title = JobManager.ellipsis(title, width)

          JobManager.terminal.stream.write('%s %s %s\n' % (prefix,
                                                           title,
                                                           progress))
          JobManager.terminal.stream.write(JobManager.terminal.clear_eol)

          print_childs(node)
      
      # Print the active block
      print_childs(self.__root)

      if type(new_state) == JobState.Failed:
        # Node failed
        self.__print_backlog(updated_node)

        # Hard exiting of the process
        #os._exit(1)


  def __animate(self):
    while self.__animation_shutdown.is_set():
      time.sleep(1)

      self.__animation_ticks += 1

      self.update(updated_node = None,
                  old_state = None,
                  new_state = None)
  
  
  @staticmethod
  def ellipsis(text, width):
    if len(text) > width:
      return text[:width - 3] + '...'
    
    else:
      return text
