"""CLI for buchschloss"""
import collections
import shlex
import argparse
import ast
import builtins
import getpass
import sys
import pprint
import traceback
import inspect
import operator
import datetime
try:
    # on linux (all? some?), importing will make arrow keys usable
    import readline  # noqa
except ImportError:
    pass

from . import core
from . import utils
from . import config
from .config.main import DummyErrorFile


class MyArgumentParser(argparse.ArgumentParser):
    """Raise a ParsingError when parsing fails"""
    def error(self, message):
        raise ParsingError(message)


class Level8Error(Exception):
    """Error by user"""
    pass


class ParsingError(Level8Error):
    """Invalid command format"""
    pass


class ExecutionError(Level8Error):
    """Error while executing the given command"""
    pass


class VariableNameError(Level8Error):
    """Invalid variable name"""
    pass


class ExitException(Exception):
    """raised to exit"""
    @classmethod
    def throw(cls, *si, **nk):
        raise cls()


def execute(command, args, kwargs):
    """execute the given command with the given arguments

        get passwords with getpass
        display encountered errors
    """
    func = COMMANDS[command]
    if command in EXTERNAL_COMMANDS:
        kwargs['login_context'] = current_login
    try:
        f_args = inspect.signature(func).parameters.keys()
    except (TypeError, ValueError):
        pass
    else:
        if func.__qualname__ in core.auth_required.functions:
            kwargs['current_password'] = getpass.getpass(
                utils.get_name('interactive_question::current_password'))
        for i, name in enumerate(f_args):
            if 'password' in name:
                passwd = getpass.getpass(utils.get_name(
                    'interactive_question::' + name) + ': ')
                args.insert(i, passwd)
    try:
        return func(*args, **kwargs)
    except core.BuchSchlossBaseError as e:
        raise ExecutionError(str(e))
    except ExitException:
        raise
    except Exception:
        traceback.print_exc()
        raise ExecutionError(utils.get_name('unexpected_error'))


def parse_args(arg_list):
    """filter out keyword-arguments"""
    args = []
    kwargs = {}
    for arg in arg_list:
        if '=' in arg:
            try:
                kw, val = arg.split('=')
            except ValueError:
                raise ParsingError('malformed input: "{!r}"'.format(arg))
            kwargs[kw] = eval_val(val)
        else:
            args.append(eval_val(arg))
    return args, kwargs


def eval_val(val):
    """evaluate a given argument:

        if enclosed in <>, get the variable
        if a date in %Y-%m-%d format, use it
        if a valid Python literal, use it
        treat as a string
    """
    if val == '<>':
        return eval_val.last_result
    elif val.startswith('<') and val.endswith('>'):
        try:
            return variables[val[1:-1]]
        except KeyError as e:
            raise VariableNameError('variable {} does not exist'.format(e))
    else:
        try:
            return datetime.datetime.strptime(val, '%Y-%m-%d').date()
        except ValueError:
            pass  # avoid deep nesting
        try:
            return ast.literal_eval(val)
        except Exception:
            return val
eval_val.last_result = None  # noqa


def read_input(prompt):
    """get the user input. Split it with shlex.split"""
    try:
        return shlex.split(input(prompt))
    except ValueError as e:
        raise ParsingError(str(e))
    except KeyboardInterrupt:
        sys.exit()


def do_execution(data, args, kwargs):
    """perform the execution of a command with arguments"""
    r = execute(data.action, args, kwargs)
    if data.cmd in COMMANDS:
        class NS:
            action = data.cmd
            store = data.store
            cmd = None
        do_execution(NS, (r,), {})
    else:
        if data.cmd:
            print(utils.get_name('cli::{}_is_invalid_command').format(data.cmd))
        if r is not None:
            pprint.pprint(r)
            eval_val.last_result = r
        if data.store:
            variables[data.store] = r


def handle_user_input(ui):
    """read input, parse arguments and execute the command"""
    ns = parser.parse_args(ui)
    args, kwargs = parse_args(ns.args)
    do_execution(ns, args, kwargs)


def ask(question):
    """Ask a yes/no question"""
    r = ''
    valid_answers = config.cli.answers.yes + config.cli.answers.no
    while not r or r.lower() not in valid_answers:
        r = input(question).lower()
    return r.lower() in config.cli.answers.yes


def start():
    """Entry point. Provide a REPL"""
    print(config.cli.intro.text, end='\n\n')
    for script_spec in config.cli.startup_scripts:
        utils.get_script_target(script_spec, login_context=core.internal_unpriv_lc)()
    try:
        while True:
            try:
                ui = read_input('{} -> '.format(current_login))
                handle_user_input(ui)
            except Level8Error as e:
                print(e.__class__.__name__, e)
    except (ExitException, EOFError) as e:
        if isinstance(e, EOFError):
            # make the terminal prompt go onto a new line
            print()
        if isinstance(sys.stderr, DummyErrorFile) and sys.stderr.error_happened:
            if ask(utils.get_name('cli::interactive_question::send_error_report') + ' '):
                try:
                    utils.send_email(utils.get_name('error_in_buchschloss'),
                                     '\n\n\n'.join(sys.stderr.error_texts))
                except Exception as e:
                    print('\n'.join((utils.get_name('error::error_while_sending_error_msg'),
                                     str(e))))
            sys.exit()


"Specific actions"


def login(name, password):
    """wrap around core.login"""
    global current_login
    current_login = core.login(name, password)


def logout():
    """forget the current login"""
    global current_login
    current_login = core.guest_lc


def help(name=None):
    """Display help for an action.

    If "commands" is passed, list possible commands.
    If no action is given, display general help."""
    print('+++ Attention: passwords are *never* taken directly as parameters +++')
    print(utils.get_name('cli::dont_give_passwords'), '\n\n')

    def getsig(func):
        try:
            return str(inspect.signature(func))
        except (ValueError, TypeError):
            return '(<?>)'

    if name is None:
        parser.print_help()
        return
    elif name == 'commands':
        print('\n\n'.join('{}{}: {}'.format(
            n, getsig(f), (inspect.getdoc(f) or 'No docstring').split('\n\n')[0])
            for n, f in COMMANDS.items() if callable(f)))
        return
    elif name in COMMANDS:
        obj = COMMANDS[name]
    else:
        obj = name  # it gets passed through eval-val before
    builtins.help(obj)


def lsvars():
    print(*['{} = {!r}'.format(k, v) for k, v in variables.items()], sep='\n')


def setvar(name, value):
    variables[name] = value


def foreach(iterable):
    """Iterate over the given iterable.

        execute the following commands for each element in the iterable
        the element is accessible as <> in the first instruction
    """
    inputs = []
    ui = read_input('... ')
    while ui:
        inputs.append(ui)
        ui = read_input('... ')
    for val in iterable:
        eval_val.last_result = val
        for ui in inputs:
            handle_user_input(ui)


def get_lua_data(data_spec):
    val_funcs = {
        'str': input,
        'int': lambda p: int(input(p)),
        'bool': ask,
    }
    r = {}
    for k, name, val_type in data_spec:
        while True:
            try:
                v = val_funcs[val_type](name + ': ')
            except ValueError:
                continue
            break
        r[k] = v  # noqa
    return r


core.Script.callbacks = {
    'ask': ask,
    'alert': print,
    'display': pprint.pprint,
    'get_data': get_lua_data,
}


EXTERNAL_COMMANDS = {
    'new_person': core.Person.new,
    'edit_person': core.Person.edit,
    'view_person': core.Person.view_str,
    'search_person': core.Person.search,
    'new_book': core.Book.new,
    'edit_book': core.Book.edit,
    'view_book': core.Book.view_str,
    'search_book': core.Book.search,
    'new_library': core.Library.new,
    'edit_library': core.Library.edit,
    'new_group': core.Group.new,
    'edit_group': core.Group.edit,
    'activate_group': core.Group.activate,
    'new_member': core.Member.new,
    'edit_member': core.Member.edit,
    'change_password': core.Member.change_password,
    'view_member': core.Member.view_str,
    'search_member': core.Member.search,
    'borrow': core.Borrow.new,
    'view_borrow': core.Borrow.view_str,
    'search_borrow': core.Borrow.search,
}
INTERNAL_COMMANDS = {
    'login': login,
    'logout': logout,
    'help': help,
    'list': lambda x: tuple(x),
    'build_list': lambda *a: a,
    'print': pprint.pprint,
    'attr': getattr,
    'item': operator.getitem,
    'exit': ExitException.throw,
    'set': setvar,
    'vars': lsvars,
    'foreach': foreach,
}
COMMANDS = collections.ChainMap(EXTERNAL_COMMANDS, INTERNAL_COMMANDS)
variables = {}
current_login = core.guest_lc


parser = MyArgumentParser('', add_help=False)
parser.add_argument('action', help=utils.get_name('cli::help::action'),
                    choices=COMMANDS)
parser.add_argument('args', nargs='*', help=utils.get_name('cli::help::args'))
parser.add_argument('--store', help=utils.get_name('cli::help::store'))
parser.add_argument('-c', '--cmd', help=utils.get_name('cli::help::cmd'))
