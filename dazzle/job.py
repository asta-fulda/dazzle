import traceback
import contextlib
import dazzle



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



BornJobState = type('BornJobState', (JobState,), {})
BornJobState.antecedent = []

CheckingJobState = type('CheckingJobState', (ActiveJobState,), {})
CheckingJobState.antecedent = [BornJobState]

PreRunningJobState = type('PreRunningJobState', (ActiveJobState,), {})
PreRunningJobState.antecedent = [BornJobState,
                                 CheckingJobState]

RunningJobState = type('RunningJobState', (ActiveJobState,), {})
RunningJobState.antecedent = [BornJobState,
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
               presenter,
               parent,
               title):
    # Create a node representing this job on the server
    self.__node = presenter.create(parent = parent.__node if parent is not None else None,
                                   title = title)


  def state(self, state):
    ''' Update the jobs state. '''
    
    self.__node.set_state(state)


  def progress(self, value):
    ''' Update the jobs progress. '''
    
    self.__node.set_progress(value)



@contextlib.contextmanager
def job(presenter, parent, title, *args):
  ''' A context manager for creating inline jobs.
      
      The context manager can be used to execute code in a sub-job using a with
      block.
  '''
  
  job = Job(presenter = presenter,
            parent = parent,
            title = title % args)

  try:
    running_state = job.state(RunningJobState)

    yield job

  except:
    traceback.print_exc()
    
    # Jobs can set their state on it's own - don't mess around with it if it was
    # changed from the running state to something else
    if job.state == running_state:
      job.state(SuccessJobState)
