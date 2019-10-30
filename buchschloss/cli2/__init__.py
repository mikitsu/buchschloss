"""Entry point"""

import sys
import traceback
import getpass
import shlex
import inspect
import itertools

import misc

from .. import core
from .. import utils
from .. import config
from . import interpreter
from .objects import BookStr
from . import compiler


def get_extra_cmds():
    if getattr(config, 'DEBUG', False):
        def pdb(**kwargs):
            """Call the builtin berakpoint()"""
            breakpoint()

    def stack(_stack, **kwargs):
        """Print a Python repr of the left-over stack"""
        print(repr(_stack))

    def help(item=None, **kwargs):
        """Dispaly help for the given item or general help in None is given"""
        def show_args(func):
            spec = inspect.getfullargspec(func)
            no_default = object()
            return ', '.join(reversed([
                (name+'='+repr(val) if val is not no_default else name)
                for name, val in itertools.zip_longest(
                    reversed(spec.args), reversed(spec.defaults or ()),
                    fillvalue=no_default)
                if not name.startswith('_')]))

        if item is None:
            print('This is the Buchschloss cli2 REPL')
            print('Next to cli2 standard syntax, some extra commands are supported.')
            print('If a command takes arguments, they are given positional-only'
                  ' following a space after the command.'
                  ' They are processed by shlex.split, i.e. arguments are'
                  ' separated by spaces and space-containing arguments'
                  ' are enclosed by quotes.')
            print('These are the extra commands:')
            misc.show_table({'command name': tuple(commands.keys()),
                             'arguments': [show_args(v) or '---'
                                           for v in commands.values()],
                             'description': [v.__doc__.split('\n')[0]
                                             for v in commands.values()]})
        else:
            print('no help on', item, 'available (yet)')

    def login(username, **kwargs):
        """Log in with Buchschloss credentials"""
        password = getpass.getpass()
        try:
            core.login(username, password)
        except core.BuchSchlossBaseError as e:
            print('error', e.title, e.message)
        else:
            print('logged in as', username)

    def logout(**kwargs):
        """Logout of Buchschloss"""
        core.logout()

    def curlogin(**kwargs):
        """Display the currently logged in Member"""
        print(core.current_login)

    commands = {'%'+k: v for k, v in locals().items() if not k.startswith('_')}
    return commands


def repl(prompt='-> '):
    """Start a REPL for cli2. Raise an EOFError on exit by user"""
    global_vars = {'exit': BookStr('input EOF to exit'),
                   'EOF': BookStr('use the EOF character to exit'),
                   'help': BookStr('use "%help" for help'),
                   }
    stack = []
    extra_commands = get_extra_cmds()
    while True:
        cmd = input(prompt)
        if cmd.startswith('%'):
            xcmd, params = (cmd+' ').split(' ', 1)
            params = shlex.split(params)
            try:
                extra_commands[xcmd](*params, _stack=stack, _globals=global_vars)
            except KeyError:
                print('unknown %-command. Use "%help"')
            continue
        try:
            bc = compiler.book_compile(cmd)
        except compiler.CompilingError as e:
            print('error reading:', str(e).split('\n')[0])
        else:
            # noinspection PyBroadException
            try:
                stack = interpreter.interpret(bc, global_vars, global_vars)
            except Exception:
                traceback.print_exc()
                print(utils.get_name('unexpected_error'))
            else:
                for v in reversed(stack):
                    print(v.book_str().value)


def start():
    if not getattr(config, 'DEBUG', False):
        sys.stderr = core.DummyErrorFile()
    try:
        repl()
    except EOFError:
        pass
