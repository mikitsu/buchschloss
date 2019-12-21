"""Get configuration settings"""

import os
import datetime
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
        try:
            items = [(n, float(x)) for n, x in zip(
                ('days', 'hours', 'minutes'), value.split(':'))]
        except ValueError:
            raise validate.VdtTypeError(value)
        return datetime.timedelta(**dict(items))
    else:
        raise validate.VdtTypeError(value)


def is_optionlist(value, *options):
    """check whether all list items"""
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


validator = validate.Validator({
    'timedelta': is_timedelta,
    'optionlist': is_optionlist,
    'task_list': is_task_list,
})


class AttrAccess:
    """Provide attribute access to mappings, supporting nesting"""
    def __init__(self, mapping):
        self._mapping = mapping

    def __getattr__(self, item):
        val = self._mapping[item.replace('_', ' ')]
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
        # multiline defaults aren't allowed (AFAIK)
        if config['gui2']['intro']['text'] is None:
            config['gui2']['intro']['text'] = 'Buchschloss\n\nhttps://github.com/mik2k2/buchschloss'
        if noisy_success:
            print('YAY, no configuration errors found')
        return config


def __getattr__(name):
    global config_data
    if config_data is None:
        config_data = AttrAccess(start(False))
    return getattr(config_data, name)
