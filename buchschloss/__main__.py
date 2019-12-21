"""Run the desired interface after importing it.

run `utils.run()` if wished by user """

from argparse import ArgumentParser
from importlib import import_module
from threading import Thread
import sys
import os

try:
    from . import config
except ImportError:
    raise ImportError('config not found. make sure it exists and BuchSchloss'
                      ' is run with the -m switch')

parser = ArgumentParser(description='Launcher for Buchschloss Interfaces')
parser.add_argument('interface', help='The interface type to run',
                    choices=('cli', 'gui2', 'cli2', 'config'))
parser.add_argument('--no-tasks', action='store_false', dest='do_tasks',
                    help="Don't run tasks specified in config")
args = parser.parse_args()

os.chdir(config.core.working_directory)
mod = import_module('.'+args.interface, __package__)
if args.do_tasks:
    from . import utils
    Thread(target=utils.run).start()
mod.start()
sys.exit()
