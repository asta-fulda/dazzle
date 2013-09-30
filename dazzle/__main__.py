import argparse
import logging

from dazzle.task import find_tasks
from dazzle.host import HostList



logging.basicConfig(level = logging.INFO)



parser = argparse.ArgumentParser()
parser.add_argument('-v', '--verbose',
                    action = 'store_true',
                    default = False,
                    help = 'enable verbose messages')

parser.add_argument('-l', '--list',
                    dest = 'hostlist',
                    metavar = 'HOSTLIST',
                    type = HostList,
                    required = True,
                    help = 'the host list file')

subparsers = parser.add_subparsers(title = 'tasks',
                                   help = 'the task to execute')

for task in find_tasks(entry_point_group = 'dazzle.tasks'):
  logging.debug('Load argument parser for task: %s' % task._task_name)

  task_parser = subparsers.add_parser(name = task._task_name,
                                      help = task._task_help)

  task_grp_parser = task_parser.add_argument_group()

  if hasattr(task, 'argparser'):
    task.argparser(task_grp_parser)

  task_parser.set_defaults(task = task,
                           args = [action.dest
                                   for action
                                   in task_grp_parser._group_actions])



def main():
  args = parser.parse_args()

  if args.verbose:
    logging.root.setLevel(level = logging.DEBUG),

  task = args.task(**{name : getattr(args, name)
                      for name
                      in args.args})

  logging.debug('Executing task: %s' % task)
  task()



if __name__ == '__main__':
    main()
