"""Get configuration settings"""

import os
import sys
import datetime
import json
import base64
import binascii
from collections.abc import Mapping
import configobj
from configobj import validate

MODULE_DIR = os.path.split(__file__)[0]
config_data = None


def is_timedelta(value):
    """create timedeltas"""
    if isinstance(value, (int, float)):
        return datetime.timedelta(days=value)
    elif isinstance(value, str):
        if value.count(':') > 2:
            raise validate.VdtValueError(value)
        try:
            items = [(n, float(x)) for n, x in zip(
                ('days', 'hours', 'minutes'), value.split(':'))]
        except ValueError:
            raise validate.VdtTypeError(value)
        return datetime.timedelta(**dict(items))
    else:
        raise validate.VdtTypeError(value)


def is_optionlist(value, *options):
    """check whether all list items are in ``options``"""
    try:
        if not all(isinstance(v, str) for v in options):
            raise validate.VdtParamError(options, value)
    except TypeError as e:
        raise validate.VdtParamError(str(e), value)
    val = validator.check('force_list', value)
    if not all(v in options for v in val):
        raise validate.VdtValueError(value)
    return val


def is_task_list(value, _tasks=('backup', 'web_backup', 'late_books')):
    """check whether the value is a list of tasks"""
    # TODO: make ``_tasks`` a mapping directly to the functions
    return validator.check('optionlist{}'.format(_tasks), value)


def is_file(value):
    """check whether the value is a valid file system path"""
    if not isinstance(value, str):
        raise validate.VdtTypeError(value)
    if not os.path.isfile(value):
        raise validate.VdtValueError(value)
    return value


def is_base64bytes(value, length=None):
    """check whether the value is ``length`` base64-encoded bytes

        if ``length`` is not given, allow any length
    """
    if not isinstance(value, str):
        raise validate.VdtTypeError(value)
    try:
        data = base64.b64decode(value)
    except binascii.Error:
        raise validate.VdtValueError(value)
    if length is not None and len(data) != length:
        raise validate.VdtValueError(value)
    return data


validator = validate.Validator({
    'timedelta': is_timedelta,
    'optionlist': is_optionlist,
    'task_list': is_task_list,
    'file': is_file,
    'base64bytes': is_base64bytes,
})


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
        return self.mapping.get(item, fallback)

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
        config = configobj.ConfigObj(filename,
                                     configspec=os.path.join(MODULE_DIR, 'configspec.cfg'),
                                     file_error=True
                                     )
    except (configobj.ConfigObjError, IOError) as e:
        raise Exception('error reading {}: {}'.format(filename, e))
    val = config.validate(validator)
    if isinstance(val, Mapping):  # True if successful, dict if not
        print('--- ERROR IN CONFIG FILE FORMAT ---\n')

        def pprint_errors(errors, nesting=''):
            """display errors"""
            for k, v in errors.items():
                if isinstance(v, dict):
                    print(nesting+'\\_', k)
                    pprint_errors(v, nesting+' |')
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
            config['utils']['names'] = name_data

        # multiline defaults aren't allowed (AFAIK)
        if config['gui2']['intro']['text'] is None:
            config['gui2']['intro']['text'] = 'Buchschloss\n\nhttps://github.com/mik2k2/buchschloss'

        if ((config['utils']['email']['smtp']['username'] is None)
                ^ (config['utils']['email']['smtp']['password'] is None)):
            raise Exception('smtp.username and smtp.password must both be given or omitted')
        if noisy_success:
            print('YAY, no configuration errors found')
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
