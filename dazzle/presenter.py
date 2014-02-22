import time
import blessings
import threading
import multiprocessing.managers

from dazzle.job import BornJobState, CheckingJobState, PreRunningJobState, RunningJobState, PostRunningJobState, SuccessJobState, SkippedJobState, FailedJobState, FinishedJobState
import contextlib



class Node(object):
  ''' The server side representation of a job.
      
      The nodes are organized in a tree.
  '''
  
  def __init__(self,
               presenter,
               parent,
               title):
    self.__presenter = presenter
    
    self.__parent = parent
    
    self.__title = title
    self.__state = BornJobState()
    self.__progress = None
    
    self.__children = []
    
    if self.__parent is not None:
      self.__parent.__children.append(self)
  
  
  @property
  def title(self):
    return self.__title
  
  
  def get_state(self):
    return self.__state
  
  
  def set_state(self, state):
    assert type(self.__state) in type(state).antecedent
    
    with self.__presenter.update():
      self.__state = state
      self.__progress = None
  
  
  state = property(get_state,
                   set_state)
  
  
  def get_progress(self):
    return self.__progress
    
    
  def set_progress(self, value):
    with self.__presenter.update():
      self.__progress = value
  
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



class Presenter(multiprocessing.managers.BaseManager):
  ''' A presenter for jobs.
      
      The presenter spawns a server process for rendering the job states.
      For each job created, a Node is created on the server.
      
      To allow animations, the server spawns a thread updating the animation
      ticker each second and updates the the screen on each animation or state
      change.
  '''
  
  terminal = blessings.Terminal()
  
  
  state_marker = {
    BornJobState: [terminal.bold_white('[ ') + terminal.bold_black('----') + terminal.bold_white(' ]')],
    
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
 
  
  def __init__(self):
    multiprocessing.managers.BaseManager.__init__(self)
    
    self.register('create',
                  callable = self.__create)
    
    self.start(self.__init)
    

  def __init(self):
    # Create the lock used to serialize updates
    self.__lock = multiprocessing.Lock()
    
    # Initialize the set of active nodes
    self.__active_nodes = []
    
    # Build the root node
    self.__root = Node(presenter = self,
                       parent = None,
                       title = None)
    
    # Initialize and start the animation
    self.__animation_thread = threading.Thread(target = self.__animate)
    self.__animation_thread.daemon = True
    
    self.__animation_shutdown = threading.Event()
    
    self.__animation_ticks = 0

    self.__animation_thread.start()

  
  def __create(self,
               parent,
               title):
    if parent is None:
      parent = self.__root
    
    with self.update():
      node = Node(presenter = self,
                  parent = parent,
                  title = title)
      
      self.__active_nodes.append(node)
    
    return node


  @staticmethod
  def __print_backlog(job):
    # Prefix the job line with its file state marker
    prefix = Presenter.state_marker[type(job.state)]
      
    # Calculate the maximal with of the title
    width = Presenter.terminal.width if Presenter.terminal.is_a_tty else 80
    width -= len(prefix)
    
    # Trim the title length to avoid line wrapping
    title = Presenter.ellipsis(job.title, width)

    # Print the job line
    Presenter.terminal.stream.write('%s %s' % (prefix,
                                               title))
    Presenter.terminal.stream.write(Presenter.terminal.clear_eol + '\n')
    
    # The jobs state is definitly FinishedJobState here
    assert isinstance(job.state, FinishedJobState)
    if job.state.message:
      
      # Prefix the message lines
      prefix = Presenter.state_marker[type(None)]
      
      # Calculate the maximal with of the message
      width = Presenter.terminal.width if Presenter.terminal.is_a_tty else 80
      width -= len(prefix)
      
      # Split the message in lines and print the lines indented
      for line in job.state.message.split('\n'):
        line = line.rstrip()
        for i in range(0, len(line), width - 1):
          Presenter.terminal.stream.write('%s %s' % (prefix,
                                                      line[i:i + width]))
          Presenter.terminal.stream.write(Presenter.terminal.clear_eol + '\n')

  
  @contextlib.contextmanager
  def update(self):
    ''' Context manager for code updating a node.
        
        The context is synchronized by a presenter wide node and updates the
        presentation after the node was updated.
    '''
    
    # Serialize updates
    with self.__lock:
      
      # Execute the context
      yield
      
      # Remove all finished nodes from the list of active nodes
      for node in self.__active_nodes:
        if type(node.state) in [SuccessJobState,
                                SkippedJobState,
                                FailedJobState]:
          # Print backlog for finished node
          self.__print_backlog(node)
          
          # Remove from list of active ones
          self.__active_nodes.remove(node)
  
      # Print the active block
      def print_childs(parent):
        # Doing an off-by-one-recusion to skip root node
        for node in parent.children:
          # Ignore all non-active nodes
          if node not in self.__active_nodes:
            continue
          
          # Get the animation frames for the nodes state marker
          frames = Presenter.state_marker[type(node.state)]
          
          # Prefix the node line with its state marker
          prefix = frames[self.__animation_ticks % len(frames)]
          
          # Prefix the node line with some indention
          prefix += '  ' * (node.level - 1)
          
          # Calculate the progress and the node title
          title = '%s' % node.title if node.title is not None else ''
          progress = '(%s)' % node.progress if node.progress is not None else ''
          
          # Calculate the maximal title length
          width = Presenter.terminal.width if Presenter.terminal.is_a_tty else 80
          width -= len(prefix)
          width -= len(progress)
          
          # Trim the title length to avoid line wrapping
          title = Presenter.ellipsis(title, width)
          
          # Print the node line
          Presenter.terminal.stream.write('%s %s %s' % (prefix,
                                                        title,
                                                        progress))
          Presenter.terminal.stream.write(Presenter.terminal.clear_eol + '\n')
          
          # Recursice draw child nodes
          print_childs(node)
      
      print_childs(self.__root)
      
      # Unwind active block
      Presenter.terminal.stream.write('\r')
      Presenter.terminal.stream.write(Presenter.terminal.move_up * len(self.__active_nodes))


  def __animate(self):
    ''' Worker method for animation thread.
        
        The animation thread updates the the animation ticker each second and
        then calls update without changing any node.
    '''
    
    while not self.__animation_shutdown.is_set():
      time.sleep(1)
      
      # Increase animation ticks
      with self.update():
        self.__animation_ticks += 1
      
  
  
  @staticmethod
  def ellipsis(text, width):
    ''' Utitlity method to trim the given string to the given width.
        
        If the strings length is grater than the given width, the string is
        trimmed to the given width but an ellipsis is appended.
    '''
    
    if len(text) > width:
      return text[:width - 3] + '...'
    
    else:
      return text
