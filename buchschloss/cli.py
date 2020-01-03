"""CLI for buchschloss"""

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
    import readline
except ImportError:
    pass

from . import core
from . import utils
from . import config


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
    try:
        f_args = inspect.signature(func).parameters.keys()
    except (TypeError, ValueError):
        pass
    else:
        if func.__name__ in core.auth_required.functions:
            kwargs['current_password'] = getpass.getpass(utils.get_name('current_password'))
        for i, name in enumerate(f_args):
            if 'password' in name:
                passwd = getpass.getpass(utils.get_name(name)+': ')
                args.insert(i, passwd)
    try:
        return func(*args, **kwargs)
    except core.BuchSchlossBaseError as e:
        raise ExecutionError('{0.title}: {0.message}'.format(e))
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
eval_val.last_result = None


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
            print(data.cmd, 'is not a valid command')
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


def start():
    """Entry point. Provide a REPL"""
    if not config.debug:
        sys.stderr = core.DummyErrorFile()
    print(config.gui2.intro.text, end='\n\n')  # TODO: have a separate config section
    try:
        while True:
            try:
                ui = read_input('{} -> '.format(core.current_login))
                handle_user_input(ui)
            except Level8Error as e:
                print(e.__class__.__name__, e)
    except ExitException:
        if not config.debug and sys.stderr.error_happened:
            if input(utils.get_name('send_error_report')+'\n')[0] in 'yYjJ':
                try:
                    utils.send_mailgun('Error in Schuelerbuecherei', '\n\n\n'.join(sys.stderr.error_texts))
                except utils.requests.RequestException as e:
                    print('\n'.join((utils.get_name('error_while_sending_error_msg'), str(e))))
            sys.exit()


"Specific actions"


def help(name=None):
    """Display help for an action.

    If "commands" is passed, list possible commands.
    If no action is given, display general help."""
    print('+++ Attention: passwords are *never* taken directly as parameters +++')
    print('+++ Achtung: Passwörter *nie* direkt als Parameter angeben +++\n\n')
    
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
            n, getsig(f), (inspect.getdoc(f) or 'No docstring').split('\n\n')[0]
            ) for n, f in COMMANDS.items() if callable(f)))
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


COMMANDS = {
    'login': core.login,
    'logout': core.logout,
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
    'restitute': core.Borrow.restitute,
    'view_borrow': core.Borrow.view_str,
    'search_borrow': core.Borrow.search,
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
variables = {}


parser = MyArgumentParser('', add_help=False)
parser.add_argument('action', help='The name of the function to call',
                    choices=COMMANDS)
parser.add_argument('args', nargs='*', help='The arguments to use. '
                    'Will be evaluated as Python literals or, '
                    'on failure, as strings. '
                    'Stored values may be used by putting the '
                    'name between <angle brackets>. '
                    'Pass positional arguments at their position. '
                    'Pass keyword arguments as `key`=`model`, '
                    'where `key` is the argument name (string) and '
                    '`model` its model (evaluated as Python literal or, '
                    'if that fails, as string')
parser.add_argument('--store', help='Store the result of this call in '
                    'a variable with the name. The model may be '
                    'retrieved by putting the name in <angle brackets>')
parser.add_argument('-c', '--cmd', help='Invoke the given command '
                    'with the result of the execution as sole '
                    'positional argument.')
