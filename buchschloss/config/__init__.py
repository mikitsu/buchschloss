"""Provide attribute access to configuration settings"""
import sys as _sys
import pprint as _pprint
from . import main as _main

_config_data = _main.get_config()


def start():
    """provide config feedback to STDOUT"""
    print('No configuration errors found.')
    if (_config_data.debug
            and input('Do you want to see the current settings? ')
            .lower().startswith('y')):
        _pprint.pprint(_config_data.mapping)


def __getattr__(name):
    val = getattr(_config_data, name)
    globals()[name] = val
    return val


if _sys.version_info < (3, 7):
    # pre-3.7 don't support module-level __getattr__
    # get configuration now and assign top-level structures
    for k, v in _config_data.mapping.items():
        globals()[k] = _main.AttrAccess(v)
