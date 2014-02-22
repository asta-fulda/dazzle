
def saveiter(thing):
  ''' Helper method returning a save iterator.
      
      If the passed value is None, an empty iterator is returned.
      If the passed value is an iterable, the passed value is returned as-is.
      Everything else is wrapped in an iterator yielding only the passed value.
  '''
  
  import collections
  
  if thing is None:
    return iter([])

  if not isinstance(thing, collections.Iterable):
    return iter([thing])

  return iter(thing)



def check_exc(func):
  ''' Function wrapper for checking for exceptions.
      
      The wrapped function is called in a try-expect-block. If the function
      throws any exception, the exception is catched and False is returned,
      otherwise True is returned. The return value of the wrapped function is
      ignored.
  '''
  
  def __(*args, **kwargs):
    try:
      func(*args, **kwargs)
      return True
 
    except Exception:
      return False
 
  return __

