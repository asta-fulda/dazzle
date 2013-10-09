import argparse

from dazzle.task import find_tasks, job_manager
from dazzle.host import HostList



parser = argparse.ArgumentParser()

subparsers = parser.add_subparsers(title = 'tasks',
                                   help = 'the task to execute')

for task in find_tasks(entry_point_group = 'dazzle.tasks'):
  task_parser = subparsers.add_parser(name = task._task_name,
                                      help = task._task_help)

  task_grp_parser = task_parser.add_argument_group()

  if hasattr(task, 'argparser'):
    task.argparser(task_grp_parser)

  task_parser.set_defaults(task = task,
                           task_args = [action.dest
                                        for action
                                        in task_grp_parser._group_actions
                                        if not (action.dest.startswith('__') and
                                                action.dest.endswith('__'))])



def main():
  args = parser.parse_args()

  task_args = {name : getattr(args, name)
               for name
               in args.task_args}

  task = args.task(parent = job_manager.root,
                   **task_args)
  task()



if __name__ == '__main__':
    main()
