"""Run the desired interface after importing it.  TODO: do we really need this??!?!

Handle special requests TODO headless
run `mod.utils.run()` if wished by user """

from argparse import ArgumentParser
from importlib import import_module
from threading import Thread
import sys
import os

try:
    from buchschloss import config
except ImportError:
    try:
        from . import config
    except ImportError:
        try:
            import v2.config as config
        except ImportError:
            raise ImportError("Couldn't find config anywhere")

# TODO: make/is case-insensitive?
parser = ArgumentParser(description='Launcher for Buchschloss Interfaces')
parser.add_argument('interface', help='The interface type to run',
                    choices=('gui', 'cli', 'gui2', 'cli2'))
parser.add_argument('--no-tasks', action='store_false', dest='do_tasks',
                    help="Don't run tasks specified in config")
args = parser.parse_args()

try:
    os.chdir(config.WORKING_DIR)
    mod = import_module('.'+args.interface, __package__)
except ImportError:
    raise ImportError('To properly import, this must be run with the -m flag')
if args.do_tasks:
    Thread(target=mod.utils.run).start()
mod.start()
sys.exit()
