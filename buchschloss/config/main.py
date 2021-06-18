"""Get configuration settings"""
import os
import sys
import datetime
import json
import contextlib
import pathlib
from collections.abc import Mapping
import typing as T

import configobj

from .validation import validator, MAX_LEVEL

CONFIG_FILE_ENV = 'BUCHSCHLOSS_CONFIG'
DEFAULT_INTRO_TEXT = """Buchschloss

https://github.com/mik2k2/buchschloss"""
MODULE_DIR = os.path.dirname(__file__)
INCLUDE_NAME = 'include'  # I'd love to make this configurable...
UI_SECTIONS = ('lua', 'gui2')
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
                    file_path = file_dir / new_file
                    new_section, new_errors = load_file(file_path, loader, load_error)
                    section.merge(new_section)
                    errors.update(new_errors)
            elif isinstance(v, configobj.Section):
                include_config(v)

    file_dir = pathlib.Path(path).parent
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
               ) -> dict:
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
    processed_data = convert_name_data(name_data)
    # problems here break gui2's level selection widget
    # TODO: this is not very nice.
    #   is there a way to make sure the keys are valid without going berserk
    #   if something unexpected happens?
    level_names = processed_data.get('level_names')
    if not isinstance(level_names, dict):
        level_names = {}
    for k, v in level_names.copy().items():
        try:
            new_k = int(k)
        except ValueError:
            pass
        else:
            if 0 <= new_k <= MAX_LEVEL and isinstance(v, str):
                level_names[new_k] = v
        del level_names[k]
    if len(level_names) < 2:
        # gui2 needs at least two
        if level_names and 0 not in level_names:
            level_names[0] = '-----'
        else:
            sys.stderr.write('ATTENTION: filling default values for level names\n')
            level_names = {i: 'level_' + str(i) for i in range(MAX_LEVEL + 1)}
    processed_data['level names'] = level_names
    return processed_data


def get_config():
    """get configuration data as an AttrAccess object"""
    try:
        filename = os.environ[CONFIG_FILE_ENV]
    except KeyError:
        raise ConfigError('environment variable BUCHSCHLOSS_CONFIG not found') from None

    config, invalid_files = load_file(filename)
    config = configobj.ConfigObj(
        config, configspec=os.path.join(MODULE_DIR, 'configspec.cfg'))
    for f in pre_validation:
        f(config)
    val = config.validate(validator)
    if isinstance(val, Mapping):
        config_error(val, invalid_files)
        sys.exit(1)
    else:
        if invalid_files:
            with contextlib.redirect_stdout(sys.stderr):
                print('\nThe following configuration files could not be loaded:')
                print('\n'.join(invalid_files))
                print()
        for f in post_validation:
            f(config)
        return AttrAccess(config)


def config_error(error_spec, invalid_files):
    """print error information to STDERR"""
    def pprint_errors(errors, nesting=''):
        """display errors"""
        for k, v in errors.items():
            if isinstance(v, dict):
                print(nesting + '\\_', k)
                pprint_errors(v, nesting + ' |')
            else:
                print(nesting, k, 'OK' if v else 'INVALID')

    with contextlib.redirect_stdout(sys.stderr):
        print('--- ERROR IN CONFIG FILE FORMAT ---\n')
        pprint_errors(error_spec)
        print('\n\nSee the confspec.cfg file for information on how the data has to be')
        if invalid_files:
            print('\nThe following configuration files could not be loaded:')
            print('\n'.join(invalid_files))


def merge_ui(config):
    """merge the [ui] section into each UI section"""
    if 'ui' in config:
        for ui_sec in UI_SECTIONS:
            sec = config.setdefault(ui_sec, {})
            sec.merge(config['ui'])
        del config['ui']


def flatten_gui2_actions(config):
    """flatten the nested actions/subactions"""
    def flatten_one_layer(prefix, layer):
        r = {}
        for k, v in layer.items():
            if isinstance(v, dict):
                r.update(flatten_one_layer(prefix + (k,), v))
            else:
                r['::'.join(prefix + (k,))] = v
        return r
    flat = flatten_one_layer((), config.get('gui2', {}).get('actions', {}))
    config.get('gui2', {})['actions'] = flat


def insert_name_data(config):
    """load name data into [utils][names]"""
    name_data = load_names(
        config['utils']['names']['file'], config['utils']['names']['format'])
    name_data['date'] = config['utils']['names']['date format']
    # without unrepr=True, this gets converted to a Section
    # which fails with numeric keys (level representations)
    config['utils'].__setitem__('names', name_data, unrepr=True)


def apply_ui_intro_text_default(config):
    """insert the newline-including default for [<ui>][intro][text]"""
    for ui_sec in UI_SECTIONS:
        sec = config[ui_sec]
        # multiline defaults aren't allowed (AFAIK)
        if sec['intro']['text'] is None:
            sec['intro']['text'] = DEFAULT_INTRO_TEXT


def check_smtp_auth_data(config):
    """check SMTP auth data"""
    # once optional sections are supported, this can go away
    if ((config['utils']['email']['smtp']['username'] is None)
            != (config['utils']['email']['smtp']['password'] is None)):
        raise ConfigError(
            'smtp.username and smtp.password must both be given or omitted')


def redirect_stderr(config):
    """redirect STDERR to error.log when not debugging"""
    if not config['debug']:
        sys.stderr = DummyErrorFile()


def apply_permission_level_defaults(config):
    """apply default values for permission levels"""
    conf = config['core']['required levels']
    for k in ('Book', 'Person', 'Library', 'Member', 'Script'):
        if conf[k]['search'] is None:
            conf[k]['search'] = conf[k]['view']
        if conf[k]['edit'] is None:
            conf[k]['edit'] = conf[k]['new']

    special_replacements = (
        (('Borrow', 'search'), ('Borrow', 'view')),
        (('Borrow', 'override'), ('Person', 'edit')),
        (('Member', 'change password'), ('Member', 'edit')),
    )
    for (dest_1, dest_2), (src_1, src_2) in special_replacements:
        if conf[dest_1][dest_2] is None:
            conf[dest_1][dest_2] = conf[src_1][src_2]

    return config


pre_validation = (
    merge_ui,
    flatten_gui2_actions,
)
post_validation = (
    insert_name_data,
    apply_ui_intro_text_default,
    apply_permission_level_defaults,
    check_smtp_auth_data,
    redirect_stderr,
)
