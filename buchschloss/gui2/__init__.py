"""entry point"""

from .. import utils
from . import main

start = main.app.launch
utils.late_handlers.append(main.late_hook)
