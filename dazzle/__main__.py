
import logging
import argparse
import itertools

from dazzle.task import CommandTask
from dazzle.job import JobManager
from dazzle.host import HostList



logging.basicConfig(level = logging.DEBUG)



# Define the argument parser
parser = argparse.ArgumentParser(prog = 'dazzle')

# Add a subparser group for the available tasks
subparsers = parser.add_subparsers(title = 'task',
                                   help = 'the task to execute')

# Add an argument for the hosts to execute the task on
parser.add_argument('hosts',
                    metavar = 'HOST',
                    nargs = '+',
                    help = 'the hosts to execute the task on')

# Add all tasks to the subparser group
for command_task_cls in CommandTask:
  # Build a subparser for the task
  task_parser = subparsers.add_parser(name = command_task_cls.task_name,
                                      help = command_task_cls.task_help)
  
  # Add an agrument group for the tasks arguments
  task_grp_parser = task_parser.add_argument_group()
  
  # Delegate the agrument group population to the task if it is able to do so
  if hasattr(command_task_cls, 'argparser'):
    command_task_cls.argparser(task_grp_parser)
  
  
  task_parser.set_defaults(command_cls = command_task_cls,
                           command_args = [action.dest
                                           for action
                                           in task_grp_parser._group_actions
                                           if not (action.dest.startswith('__') and
                                                   action.dest.endswith('__'))])



def main():
  # Parse the command line arguments
  args = parser.parse_args()
  
  # Build the argument map for calling the task
  command_args = {name : getattr(args, name)
                  for name
                  in args.command_args}
  
  # Build a list of hosts
  host_list = HostList()
  hosts = set(itertools.chain(*(host_list.get(host)
                                for host
                                in args.hosts)))
  
  # Create and start the job manager
  job_manager = JobManager()
  
  # Build the task instance to execute
  task = args.command_cls(manager = job_manager,
                          hosts = hosts,
                          **command_args)
  
  # Execute the task
  task()
  
  # Shut down the job manager
  job_manager.shutdown()



if __name__ == '__main__':
    main()
