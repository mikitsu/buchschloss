"""Get configuration settings"""

import os
import sys
import datetime
import json
import contextlib
from collections.abc import Mapping
import pprint
import typing as T

import configobj

from .validation import validator

MODULE_DIR = os.path.dirname(__file__)
INCLUDE_NAME = 'include'  # I'd love to make this configurable...
config_data = None
ExceptSpec = T.Union[T.Type[BaseException], T.Tuple[T.Type[BaseException], ...]]
ActuallyPathLike = T.Union[bytes, str, os.PathLike]


class ConfigError(Exception):
    """configuration error"""


class DummyErrorFile:
    """Revert errors to log.

    Attributes:
        error_happened: True if write() was called
        error_file: the log file name
        error_texts: list of the error messages wrote to the log file for later use
            e.g. display, email, ..."""

    def __init__(self, error_file='error.log'):
        self.error_happened = False
        self.error_texts = []
        self.error_file = 'error.log'
        with open(error_file, 'a', encoding='UTF-8') as f:
            f.write('\n\nSTART: ' + str(datetime.datetime.now()) + '\n')

    def write(self, msg):
        self.error_happened = True
        self.error_texts.append(msg)
        while True:
            try:
                with open(self.error_file, 'a', encoding='UTF-8') as f:
                    f.write(msg)
            except OSError:
                pass
            else:
                break


class AttrAccess:
    """Provide attribute access to mappings, supporting nesting"""
    EMPTY_INST = type('', (), {'__repr__': lambda s: 'AttrAccess.EMPTY_INST'})()

    def __init__(self, mapping):
        self.mapping = mapping

    def get(self, item, fallback=EMPTY_INST):
        """return ``item`` if present, otherwise the given fallback
            (an empty AttrAccess instance by default)"""
        if fallback is self.EMPTY_INST:
            fallback = type(self)({})
        val = self.mapping.get(item, fallback)
        if isinstance(val, Mapping):
            val = type(self)(val)
        return val

    def __getitem__(self, item):
        return self.mapping[item]

    def __getattr__(self, item):
        val = self.mapping[item.replace('_', ' ')]
        if isinstance(val, Mapping):
            val = type(self)(val)
        return val


def load_file(path: ActuallyPathLike,
              loader: T.Callable[[T.TextIO], T.MutableMapping] = configobj.ConfigObj,
              load_error: ExceptSpec = configobj.ConfigObjError,
              ) -> T.Tuple[configobj.ConfigObj, T.Set[ActuallyPathLike]]:
    """recursively load a file as ConfigObj. Return (<ConfigObj>, <set of invalid paths>)

        The invalid paths returned may be nonexistent or unparseable
        ``loader`` specifies how to load the file
        ``load_error`` is used to catch exceptions while loading the file
    """
    def include_config(section: configobj.Section):
        """recursively read included files and merge"""
        for k, v in section.items():
            if k == INCLUDE_NAME:
                if isinstance(v, str):
                    v = [v]
                elif isinstance(v, configobj.Section):
                    continue  # could also raise an error or add some filename to errors
                del section[k]
                for new_file in v:
                    new_section, new_errors = load_file(new_file, loader, load_error)
                    section.merge(new_section)
                    errors.update(new_errors)
            elif isinstance(v, configobj.Section):
                include_config(v)

    errors = set()
    try:
        f = open(path)
    except OSError:
        return configobj.ConfigObj({}), {path}
    try:
        config = loader(f)
    except load_error:
        return configobj.ConfigObj({}), {path}
    finally:
        f.close()
    if not isinstance(config, configobj.ConfigObj):
        config = configobj.ConfigObj(config)
    include_config(config)
    return config, errors


def load_names(name_file: ActuallyPathLike,
               name_format: str
               ) -> T.Mapping:
    """Load the name file with inclusions ignoring errors"""
    def convert_name_data(data):
        if isinstance(data, str):
            return data
        elif isinstance(data, T.Mapping):
            return {k.lower(): convert_name_data(v) for k, v in data.items()}
        else:
            return ''

    loaders = {
        'json': (json.load, json.JSONDecodeError),
        'configobj': (configobj.ConfigObj, configobj.ConfigObjError),
    }
    name_data, __ = load_file(name_file, *loaders[name_format])
    # special case the only list
    level_list = name_data.pop('level names', ())
    if not isinstance(level_list, T.Sequence) or len(level_list) != 5:
        level_list = ['level_{}'.format(i) for i in range(5)]
    processed_data = convert_name_data(name_data)
    processed_data['level names'] = level_list
    return processed_data


def start(noisy_success=True):
    """load the config file specified in the BUCHSCHLOSS_CONFIG environment variable
        and validate the settings"""
    try:
        filename = os.environ['BUCHSCHLOSS_CONFIG']
    except KeyError:
        raise ConfigError('environment variable BUCHSCHLOSS_CONFIG not found') from None
    config, invalid_files = load_file(filename)
    config = configobj.ConfigObj(
        config, configspec=os.path.join(MODULE_DIR, 'configspec.cfg'))
    val = config.validate(validator)
    if isinstance(val, Mapping):  # True if successful, dict if not
        with contextlib.redirect_stdout(sys.stderr):
            print('--- ERROR IN CONFIG FILE FORMAT ---\n')

            def pprint_errors(errors, nesting=''):
                """display errors"""
                for k, v in errors.items():
                    if isinstance(v, dict):
                        print(nesting + '\\_', k)
                        pprint_errors(v, nesting + ' |')
                    else:
                        print(nesting, k, 'OK' if v else 'INVALID')

            pprint_errors(val)
            print('\n\nSee the confspec.cfg file for information on how the data has to be')
            if invalid_files:
                print('\nThe following configuration files could not be loaded:')
                print('\n'.join(invalid_files))
        sys.exit(1)
    else:
        config['utils']['names'] = load_names(
            config['utils']['names']['file'], config['utils']['names']['format'])
        # multiline defaults aren't allowed (AFAIK)
        if config['gui2']['intro']['text'] is None:
            config['gui2']['intro']['text'] = \
                'Buchschloss\n\nhttps://github.com/mik2k2/buchschloss'

        if ((config['utils']['email']['smtp']['username'] is None)
                ^ (config['utils']['email']['smtp']['password'] is None)):
            raise ConfigError(
                'smtp.username and smtp.password must both be given or omitted')
        if noisy_success:
            print('YAY, no configuration errors found')
        if invalid_files:
            with contextlib.redirect_stdout(sys.stderr):
                print('\nThe following configuration files could not be loaded:')
                print('\n'.join(invalid_files))
                print()
        if (config['debug']
                and noisy_success
                and input('Do you want to see the current settings? ')
                .lower().startswith('y')):
            pprint.pprint(config)
        if not config['debug']:
            sys.stderr = DummyErrorFile()
        return config


def __getattr__(name):
    global config_data
    if config_data is None:
        config_data = AttrAccess(start(False))
    val = getattr(config_data, name)
    globals()[name] = val
    return val


if sys.version_info < (3, 7):
    # pre-3.7 don't support module-level __getattr__
    # get configuration now and assign top-level structures
    config_data = AttrAccess(start(False))
    for k, v in config_data.mapping.items():
        globals()[k] = AttrAccess(v)
    debug = config_data['debug']
