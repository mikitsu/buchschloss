"""Run the desired interface after importing it.

run `utils.run()` if wished by user """

from argparse import ArgumentParser
from importlib import import_module
from threading import Thread
import sys
import os

os.chdir(os.environ.get('BUCHSCHLOSS_DIR', '.'))

parser = ArgumentParser(description='Launcher for Buchschloss Interfaces')
parser.add_argument('interface', help='The interface type to run',
                    choices=('cli', 'gui2', 'lua', 'config'))
parser.add_argument('--no-tasks', action='store_false', dest='do_tasks',
                    help="Don't run tasks specified in config")
args = parser.parse_args()

try:
    mod = import_module('.' + args.interface, __package__)
except ImportError:
    raise ImportError("interface couldn't be located. Did you run with the -m flag?")

if args.do_tasks:
    from . import utils
    Thread(target=utils.get_runner()).start()
mod.start()
sys.exit()
