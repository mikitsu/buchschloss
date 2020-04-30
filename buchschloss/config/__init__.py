"""Get configuration settings"""

import os
import sys
import datetime
import json
from collections.abc import Mapping
import pprint

import configobj

from .validation import validator

MODULE_DIR = os.path.split(__file__)[0]
config_data = None


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


def start(noisy_success=True):
    """load the config file specified in the BUCHSCHLOSS_CONFIG environment variable
        and validate the settings"""
    try:
        filename = os.environ['BUCHSCHLOSS_CONFIG']
    except KeyError:
        raise Exception('environment variable BUCHSCHLOSS_CONFIG not found') from None
    try:
        config = configobj.ConfigObj(
            filename, configspec=os.path.join(MODULE_DIR, 'configspec.cfg'),
            file_error=True)
    except (configobj.ConfigObjError, IOError) as e:
        raise Exception('error reading main config file {}: {}'
                        .format(filename, e)) from None
    val = config.validate(validator)
    if isinstance(val, Mapping):  # True if successful, dict if not
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
        raise Exception
    else:
        # since this can get quite large, it is an external file
        name_format = config['utils']['names']['format']
        try:
            with open(config['utils']['names']['file']) as f:
                if name_format == 'json':
                    name_data = json.load(f)
        except (OSError, json.JSONDecodeError):
            raise Exception('error reading name file')
        else:
            def convert_name_data(data):
                if isinstance(data, str):
                    return data
                else:
                    return {k.lower(): convert_name_data(v) for k, v in data.items()}

            name_data = convert_name_data(name_data)
            config['utils']['names'].update(name_data)

        # multiline defaults aren't allowed (AFAIK)
        if config['gui2']['intro']['text'] is None:
            config['gui2']['intro']['text'] = \
                'Buchschloss\n\nhttps://github.com/mik2k2/buchschloss'

        if ((config['utils']['email']['smtp']['username'] is None)
                ^ (config['utils']['email']['smtp']['password'] is None)):
            raise Exception('smtp.username and smtp.password must both be given or omitted')
        if noisy_success:
            print('YAY, no configuration errors found')
            if (config['debug']
                    and input('Do you want to see the current settings? ')
                    .lower().startswith('y')):
                pprint.pprint(config)
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
