"""Core functionalities of the application.

Handles access to the database and provides high-level interfaces for all operations.
__all__ exports:
    - BuchSchlossBaseError: the error raised in this module.
        Instances come with a nice description of what exactly failed.
    - misc_data: provide easy access to data stored in Misc by attribute lookup
    - login: to get a LoginContext for a user
    - Book, Person, Borrow, Member, Library, Group, Script: namespaces for functions
        dealing with the respective objects
    - ScriptPermissions: flag enum of script permissions
"""
import functools
import inspect
import itertools
import string
import textwrap
from hashlib import pbkdf2_hmac
from functools import wraps, partial
from datetime import timedelta, date
from os import urandom
import sys
import warnings
import operator
import enum
import logging
import logging.handlers

try:
    # noinspection PyPep8Naming
    import typing as T
except ImportError:
    T = None

import peewee

from . import config
from . import utils
from . import models
from . import lua

__all__ = [
    'BuchSchlossBaseError', 'misc_data',
    'Person', 'Book', 'Member', 'Borrow', 'Library', 'Script',
    'login', 'ScriptPermissions',
]

log_conf = config.core.log
if log_conf.file:
    if log_conf.rotate.how == 'none':
        handler = logging.FileHandler(log_conf.file)
    elif log_conf.rotate.how == 'size':
        handler = logging.handlers.RotatingFileHandler(
            log_conf.file,
            maxBytes=2 ** 10 * log_conf.rotate.size,
            backupCount=log_conf.rotate.copy_count,
        )
    elif log_conf.rotate.how == 'time':
        handler = logging.handlers.TimedRotatingFileHandler(
            log_conf.file,
            when=log_conf.interval_unit,
            interval=log_conf.interval_value,
        )
    else:
        raise ValueError('config.core.log.rotate.how had an invalid value')
else:
    handler = logging.StreamHandler(sys.stdout)
# noinspection PyArgumentList
logging.basicConfig(level=getattr(logging, config.core.log.level),
                    format='{asctime} - {levelname}: {msg}',
                    datefmt='%Y-%m-%d %H:%M:%S',
                    style='{',
                    handlers=[handler],
                    )
del handler, log_conf


class ScriptPermissions(enum.Flag):
    """permissions scripts can have

    - AUTH_GRANTED: execute functions that require a password when
      executed with a MEMBER LoginContext
    - REQUESTS: access the internet, confined to configured URLs and HTTP methods
    - STORE: store data
    """
    AUTH_GRANTED = enum.auto()
    REQUESTS = enum.auto()
    STORE = enum.auto()


class LoginType(enum.Enum):
    MEMBER = 'Member[{name}]({level})'
    GUEST = 'Guest'
    SCRIPT = 'Script[{name}]({level})<-{invoker}'
    INTERNAL = 'SYSTEM({level})'


class LoginContext:
    """data about a logged in user"""

    def __init__(self, login_type: LoginType, level: int, **data):
        self.type = login_type
        self.level = level
        for k, v in data.items():
            setattr(self, k, v)

    def __str__(self):
        return self.type.value.format(**self.__dict__)


class MiscData:
    """Provide an easy interface for the Misc table."""

    def __getattr__(self, item):
        try:
            conn = models.db.connect(True)
            try:
                return models.Misc.get_by_id(item).data
            finally:
                if conn:
                    models.db.close()
        except models.Misc.DoesNotExist as e:
            raise AttributeError('%s has no attribute %s' % (repr(self), item)) from e

    def __setattr__(self, key, value):
        conn = models.db.connect(True)
        try:
            m = models.Misc.get_by_id(key)
        except models.Misc.DoesNotExist as e:
            raise AttributeError('Can only set database columns, not %s' % (key,)) from e
        else:
            m.data = value
            m.save()
        finally:
            if conn:
                models.db.close()


class BuchSchlossBaseError(Exception):
    """Error raised in this module"""

    def __init__(self, title, message, *sink):
        if sink:
            warnings.warn('BuchSchlossBaseError.__init__ got unexpected arguments')
        self.title = title
        self.message = message

    def __str__(self):
        return '{0.title}: {0.message}'.format(self)

    @classmethod
    def template_title(cls, template_title):
        """return a subclass that will %-format the given template title
            with the one given at creation

            *args are passed along, making this work well with BuchSchlossError
        """

        class BuchSchlossTemplateTitleError(cls):
            def __init__(self, title, message, *args):
                super().__init__(template_title % title, message, *args)

        return BuchSchlossTemplateTitleError

    @classmethod
    def template_message(cls, template_message):
        """return a subclass that will %-format the given template message
            with the one given at creation

            *args are passed, making this work well with BuchSchlossError
        """

        class BuchSchlossTemplateMessageError(cls):
            def __init__(self, title, message, *args):
                super().__init__(title, template_message % message, *args)

        return BuchSchlossTemplateMessageError


class BuchSchlossError(BuchSchlossBaseError):
    """a subclass that will use utils.get_name

        The title will be passed through utils.get_name normally

        The message will be passed through utils.get_name and .format will
        be called with an optional tuple (unpacked) given

        'error::' will be prepended to both title and message
    """

    def __init__(self, title, message, *message_args, **message_kwargs):
        super().__init__(utils.get_name('error::' + title),
                         utils.get_name('error::' + message)
                         .format(*message_args, **message_kwargs))


class BuchSchlossPermError(BuchSchlossBaseError):
    """use utils.get_name for level and message name"""

    def __init__(self, level):
        super().__init__(utils.get_name('no_permission'),
                         utils.get_name('must_be_{}').format(
                             utils.level_names[level]))


class BuchSchlossNotFoundError(BuchSchlossError.template_title('%s_not_found')
                               .template_message('no_%s_with_id_{}')):
    def __init__(self, model: str, pk):
        super().__init__(model, model, pk)


class BuchSchlossExistsError(BuchSchlossError.template_title('%s_exists')
                             .template_message('%s_with_id_{}_exists')):
    def __init__(self, model: str, pk):
        super().__init__(model, model, pk)


class Dummy:  # TODO: move this out to misc
    """Provide a dummy object

    special attributes:
        _default: a default item to be returned when the requested one is not set
        _str: the string representation of self
        _call: a callable to call (default: return self)
        _bool: value to return when __bool__ is called
        _items: mapping or sequence to delegate __getitem__ to.
            _default will be returned on Key, Index or AttributeError
    """

    def __init__(self, _bool=True, _call=lambda s, *a, **kw: s, **kwargs):
        """Set the attributes given in kwargs."""
        self._bool = _bool
        self._call = _call
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __str__(self):
        """return self._str if set, else '-----'"""
        try:
            return self._str
        except AttributeError:
            return '-----'

    def __call__(self, *args, **kwargs):
        return self._call(self, *args, **kwargs)

    def __bool__(self):
        return self._bool

    def __getattr__(self, item):
        """return self._default if set, else self"""
        if item == '_default':
            return self
        elif item in ('_str', '_items'):  # _bool and _call are always set
            raise AttributeError
        else:
            return self._default

    def __getitem__(self, item):
        try:
            return self._items[item]
        except (KeyError, IndexError, AttributeError):
            return self._default


def pbkdf(pw, salt, iterations=config.core.hash_iterations[0]):
    """return pbkdf2_hmac('sha256', pw, salt, iterations)"""
    return pbkdf2_hmac('sha256', pw, salt, iterations)


def from_db(*arguments: T.Type[models.Model], **keyword_arguments: T.Type[models.Model]):
    """Wrap functions taking IDs of database objects.

    convert all arguments to wrapper_arg.get_by_id(func_arg)
    arguments may be given be position or by keyword;
    they are converted independently of how they were passed to the wrapper
    raise a BuchSchlossBaseError with an explanation if the object does not exist
    """

    def wrapper_maker(f):
        signature = inspect.signature(f)
        pos_names = signature.parameters.keys()
        for name, model in zip(pos_names, arguments):
            keyword_arguments[name] = model

        @wraps(f)
        def wrapper(*args: T.Any, **kwargs):
            bound = signature.bind(*args, **kwargs)
            with models.db.atomic():
                for k, m in keyword_arguments.items():
                    arg = bound.arguments[k]
                    if isinstance(arg, DataNamespace):
                        bound.arguments[k] = arg.data
                    elif not isinstance(arg, m):
                        try:
                            bound.arguments[k] = m.get_by_id(arg)
                        except m.DoesNotExist:
                            raise BuchSchlossNotFoundError(m.__name__, arg)
            with models.db.atomic():
                return f(*bound.args, **bound.kwargs)

        return wrapper

    return wrapper_maker


def check_level(login_context, level, resource):
    """check if the currently logged in member has the given level.
        otherwise, raise a BuchSchlossBaseError and log"""
    if login_context.level < level:
        logging.info('{} was denied access to {} (level)'
                     .format(login_context, resource))
        raise BuchSchlossPermError(level)


def auth_required(f):
    """require the currently logged member's password for executing the function
    raise a BuchSchlossBaseError if not given or wrong"""

    @wraps(f)
    def auth_required_wrapper(*args,
                              login_context: LoginContext,
                              current_password: str = None,
                              **kwargs):
        status = None
        if login_context.type is LoginType.INTERNAL:
            if not login_context.level:
                status = 'unprivileged_login_context'
        elif login_context.type is LoginType.SCRIPT:
            perms = (models.Script.select(models.Script.permissions)
                     .where(name=login_context.name).get().permissions)  # noqa -- scritp LC has name
            if ScriptPermissions.AUTH_GRANTED not in perms:
                status = 'no_script_perms'
        elif login_context.type is LoginType.MEMBER:
            if current_password is None:
                raise TypeError('when called with a MEMBER login context, '
                                '``current_password`` must be given')
            # noinspection PyUnresolvedReferences
            login_member = models.Member.get_by_id(login_context.name)
            if not authenticate(login_member, current_password):
                status = 'wrong_password'
        else:
            status = 'unknown_auth_category'
        if status is None:
            logging.info('{} was granted access to {} (auth)'
                         .format(login_context, f.__qualname__))
            return f(*args, login_context=login_context, **kwargs)
        else:
            logging.info('{} was denied access to {} (auth)'
                         .format(login_context, f.__qualname__))
            raise BuchSchlossError('no_permission', status)

    last_doc_line = f.__doc__.splitlines()[-1]
    if last_doc_line.isspace():
        doc_indent = last_doc_line
    else:
        doc_indent = last_doc_line[:-len(last_doc_line.lstrip())]
    auth_required_wrapper.__doc__ += '\n\n' + textwrap.indent(textwrap.dedent("""
    When called with a MEMBER LoginContext,
    this function requires authentication in form of
    a ``current_password`` argument containing the currently
    logged in member's password.
    It is not callable by GUEST and unprivileged SYSTEM
    LoginContexts as well as SCRIPT LoginContexts without
    the AUTH_GRANTED permission.
    """), doc_indent)
    return auth_required_wrapper


def authenticate(m, password):
    """Check if the given password corresponds to the hashed one.
    Update the hash if newer iteration number present"""
    password = password.encode()
    for old, iterations in enumerate(config.core.hash_iterations):
        if m.password == pbkdf(password, m.salt, iterations):
            if old:
                close_db = models.db.connect(reuse_if_open=True)
                m.password = pbkdf(password, m.salt)
                m.save()
                if close_db:
                    models.db.close()
            return True
    return False


def login(name: str, password: str):
    """attempt to login the Member with the given name and password.

    :return LoginContext: on success

    Try all iterations specified in the configuration
    and update to newest (first) one where applicable

    :raise BuchSchlossBaseError: on failure
    """
    try:
        with models.db:
            m = models.Member.get_by_id(name)
    except models.Member.DoesNotExist:
        raise BuchSchlossNotFoundError('Member', name)
    if authenticate(m, password):
        logging.info(f'login success {m}')
        return LoginContext(LoginType.MEMBER, m.level, name=m.name)
    else:
        logging.info(f'login fail {m}')
        raise BuchSchlossError('login', 'wrong_password')


class ActionNamespace:
    """common stuff for the Book, Person, Member,
    Library, Group, Borrow and Script namespaces"""
    model: T.ClassVar[models.Model]
    required_levels: T.Any
    # view_ns hacked in later because it uses 'view' permissions
    actions: 'T.ClassVar[frozenset[str]]' = frozenset(('new', 'edit', 'search'))
    namespaces: 'T.ClassVar[list[str]]' = []
    _model_fields: T.ClassVar[set]
    _format_fields: T.ClassVar[set]

    def __init_subclass__(cls, extra_actions: dict = {}):  # noqa
        """add the _model_fields and required_levels attributes"""
        if extra_actions is None:
            extra_actions = dict()
        cls.namespaces.append(cls.__name__)
        cls.model = getattr(models, cls.__name__)
        cls._model_fields = {
            k for k in dir(cls.model)
            if isinstance(getattr(cls.model, k), (peewee.Field, peewee.BackrefAccessor))
        }
        if not hasattr(cls, '_format_fields'):
            cls._format_fields = utils.get_format_fields(f'{cls.model.__name__}::repr')

        def level_required(level, f):
            """due to scoping, this has to be a separate function"""
            @wraps(f)
            def wrapper(*args, login_context: LoginContext, **kwargs):
                checker(login_context)
                return f(*args, login_context=login_context, **kwargs)

            checker = partial(check_level, level=level, resource=f.__qualname__)
            return wrapper

        extra_actions['view_ns'] = 'view'  # see ``actions = ...`` above
        cls.actions |= extra_actions.keys()
        cls.required_levels = getattr(config.core.required_levels, cls.__name__)
        for name in cls.actions:
            if (cls.__name__, name) == ('Member', 'change_password'):
                req_level = 0
            else:
                req_level = cls.required_levels[extra_actions.get(name) or name]
            func = getattr(cls, name)
            setattr(cls, name, level_required(req_level, func))

    @classmethod
    def format_object(cls, obj: peewee.Model):
        """Wrap utils.get_name to format the ::repr with matching arguments"""
        attrs = {k: getattr(obj, k) for k in cls._format_fields}
        return utils.get_name(cls.__name__ + '::repr', **attrs)

    @staticmethod
    def new(*, login_context, **kwargs):
        """Create a new record"""

    @staticmethod
    def edit(id_, *, login_context, **kwargs):
        """Edit an existing record"""

    @classmethod
    def view_ns(cls, id_: T.Union[int, str], *, login_context):
        """Return a namespace of information"""
        try:
            r = DataNamespace(cls, cls.model.get_by_id(id_), login_context, True)
        except cls.model.DoesNotExist:
            raise BuchSchlossNotFoundError(cls.model.__name__, id_)
        else:
            logging.info(f'{login_context} viewed {r}')
            return r

    @classmethod
    def check_view_permissions(cls, login_context, data_ns=None):
        """Check whether the login context has viewing permission and log"""
        check_level(login_context, cls.required_levels.view, cls.__name__ + '.view_ns')
        if data_ns is not None:
            logging.info(f'{login_context} viewed {data_ns}')

    @classmethod
    def search(cls, condition: tuple, *, login_context):
        """search for records.

        :param condition: is a condition tuple.

        Condition tuples are tuples of the form ``(a, op, b)`` or ``(func, c)``.
        They may also be empty.

        In the first case, ``op`` may be either a logical operation
        ("and" or "or"), in which case ``a`` and ``b`` are condition tuples,
        or a comparison operation ("contains", "eq", "ne", "gt", "ge", "lt" or "le"),
        in which case ``a`` is a (possibly dotted) path to the field to test
        and ``b`` is the value to test against.

        In the second case, ``func`` is "not" or "exists".
        This function is applied to the condition tuple ``c``.

        An empty condition tuple results in no change to the query state.
        If the top-level condition tuple is empty, all existing values are returned.
        """
        def follow_path(path, q):
            def handle_many_to_many():
                through = fv.through_model.alias()
                cond_1 = (getattr(cur, cur.pk_name)
                          == getattr(through, fv.model.__name__.lower() + '_id'))
                cond_2 = (getattr(through, mod.__name__.lower() + '_id')
                          == getattr(mod, mod.pk_name))
                return q.join(through, on=cond_1).join(mod, on=cond_2)

            *path, end = path.split('.')
            cur = mod = cls.model
            for fn in path:
                fv = getattr(mod, fn)
                mod = fv.rel_model.alias()
                if isinstance(fv, peewee.ManyToManyField):
                    q = handle_many_to_many()
                elif isinstance(fv, peewee.BackrefAccessor):
                    q = q.join(mod, on=(getattr(cur, cur.pk_name)
                                        == getattr(mod, fv.field.name)))
                else:
                    q = q.join(mod, on=(fv == getattr(mod, mod.pk_name)))
                cur = mod
            fv = getattr(mod, end)
            if isinstance(fv, peewee.ManyToManyField):
                mod = fv.rel_model
                q = handle_many_to_many()
                fv = getattr(mod, mod.pk_name)
            elif isinstance(fv, peewee.BackrefAccessor):
                mod = fv.rel_model.alias()
                q = q.join(mod, on=(getattr(cur, cur.pk_name)
                                    == getattr(mod, fv.field.name)))
                fv = getattr(mod, mod.pk_name)
            return fv, q

        def handle_condition(cond, q):
            if len(cond) == 2:
                func, c = cond
                if func == 'not':
                    c, q = handle_condition(c, q)
                    return ~c, q
                elif func == 'exists':
                    sub_q = cls.model.alias().select(0)
                    c, sub_q = handle_condition(c, sub_q)
                    return peewee.fn.EXISTS(sub_q.where(c)), q
                else:
                    raise ValueError('`func` must be "not" or "exists"')
            a, op, b = cond
            if op in ('and', 'or'):
                if not a:
                    return handle_condition(b, q)
                elif not b:
                    return handle_condition(a, q)
                else:
                    a, q = handle_condition(a, q)
                    b, q = handle_condition(b, q)
                    return getattr(operator, op + '_')(a, b), q
            else:
                a, q = follow_path(a, q)
                if op in ('eq', 'ne', 'gt', 'lt', 'ge', 'le'):
                    return getattr(operator, op)(a, b), q
                elif op == 'in':
                    return a << b, q
                elif op == 'contains':
                    return a.contains(b), q
                else:
                    raise ValueError('`op` must be "and", "or", "eq", "ne", "gt", "lt" '
                                     '"ge", "le" or "contains"')

        query = cls.model.select_str_fields(cls._format_fields).distinct()
        if condition:
            condition, query = handle_condition(condition, query)
            query = query.where(condition)
        logging.info(f'{login_context} searched {cls.__name__}')
        return (DataNamespace(cls, value, login_context, True) for value in query)


class Book(ActionNamespace,
           extra_actions={'get_all_genres': 'view', 'get_all_groups': 'view'},
           ):
    """Namespace for Book-related functions"""
    @staticmethod
    def new(*, isbn: int, author: str, title: str, language: str, publisher: str,  # noqa
            year: int, medium: str, shelf: str, series: T.Optional[str] = None,
            series_number: T.Optional[int] = None,
            concerned_people: T.Optional[str] = None,
            genres: T.Iterable[str] = (), groups: T.Iterable[str] = (),
            library: str = 'main', login_context: LoginContext) -> int:
        """Attempt to create a new Book with the given arguments and return the ID

        :raise BuchSchlossBaseError: on failure

        See models.Book.__doc__ for details on arguments
        """
        with models.db:
            try:
                b = models.Book.create(
                    isbn=isbn, author=author, title=title, language=language,
                    publisher=publisher, year=year, medium=medium,
                    shelf=shelf, series=series, series_number=series_number,
                    concerned_people=concerned_people,
                    library=models.Library.get_by_id(library),
                )
            except models.Library.DoesNotExist:
                raise BuchSchlossNotFoundError('Library', library)
            for g in groups:
                models.Group.create(book=b, name=g)
            for g in genres:
                models.Genre.create(book=b, name=g)
            logging.info(f'{login_context} created {b}')
        return b.id

    @classmethod
    @from_db(book=models.Book)
    def edit(cls, book: T.Union[int, models.Book], *, login_context, **kwargs):
        """Edit a Book based on the arguments given.

        See models.Book.__doc__ for more information on the arguments.

        :raise BuchSchlossBaseError: if the Book isn't found
            or the new library does not exist
        """
        if not set(kwargs.keys()) <= cls._model_fields - {'id'}:
            raise TypeError('unexpected kwarg')
        lib = kwargs.pop('library', None)
        if lib is not None:
            try:
                book.library = models.Library.get_by_id(lib)
            except models.Library.DoesNotExist:
                raise BuchSchlossNotFoundError('Library', lib)
        for k in {'genres', 'groups'} & kwargs.keys():
            model: peewee.Model = getattr(models, k[:-1].capitalize())
            values = kwargs.pop(k, ())
            model.delete().where(model.book == book, model.name.not_in(values)).execute()
            for v in values:
                try:
                    model.create(book=book, name=v)
                except peewee.IntegrityError as e:
                    if not str(e).startswith('UNIQUE'):
                        raise
        for k, v in kwargs.items():
            setattr(book, k, v)
        book.save()
        logging.info(f'{login_context} edited {book}')

    @staticmethod
    def get_all_genres(login_context):
        """return all known genres in the database"""
        logging.info(f'{login_context} viewed all genres')
        return tuple(g.name for g in models.Genre.select(models.Genre.name).distinct())

    @staticmethod
    def get_all_groups(login_context):
        """return all known groups in the database"""
        logging.info(f'{login_context} viewed all groups')
        return tuple(g.name for g in models.Group.select(models.Group.name).distinct())

    @staticmethod
    def get_all_series(login_context):
        """return all known series names in the database"""
        logging.info(f'{login_context} viewed all series names')
        return tuple(b.series for b in
                     models.Book.select(models.Book.series).distinct()
                     .where(models.Book.series != None))  # noqa


class Person(ActionNamespace):
    """Namespace for Person-related functions"""
    @staticmethod
    def new(*, id: int, first_name: str, last_name: str, class_: str,  # noqa
            max_borrow: int = 3, libraries: T.Iterable[str] = ('main',),
            pay: bool = None, borrow_permission: date = None,
            login_context):
        """Attempt to create a new Person with the given arguments.

        :raise BuchSchlossBaseError: on failure

        Silently ignore nonexistent libraries.

        See models.Person.__doc__ for details on arguments.

        If ``pay`` is True and ``borrow_permission`` is None,
        set the borrow_permission to ``today + 52 weeks``.
        """
        if borrow_permission is None and pay:
            borrow_permission = date.today() + timedelta(weeks=52)
        p = models.Person(id=id, first_name=first_name, last_name=last_name,
                          class_=class_, max_borrow=max_borrow,
                          borrow_permission=borrow_permission)
        p.libraries = libraries
        try:
            p.save(force_insert=True)
        except peewee.IntegrityError as e:
            if str(e).startswith('UNIQUE'):
                raise BuchSchlossExistsError('Person', id)
            else:
                raise
        else:
            logging.info(f'{login_context} created {p} '
                         f'with borrow_permission={borrow_permission}')

    @classmethod
    @from_db(person=models.Person)
    def edit(cls, person: T.Union[int, models.Person], *, login_context, **kwargs):
        """Edit a Person based on the arguments given.

        :raise BuchSchlossBaseError: if the Person isn't found or a library doesn't exist.

        See Person.__doc__ for more information on the arguments.

        If ``pay`` is True, ``borrow_permission`` will be incremented
        by 52 weeks. (assuming a value of today if None)
        """
        if not set(kwargs.keys()) - {'pay'} <= cls._model_fields - {'id'}:
            raise TypeError('unexpected kwarg')
        if kwargs.pop('pay', False):
            if 'borrow_permission' in kwargs:
                raise TypeError(
                    '``pay`` and ``borrow_permission`` may not be given together')
            kwargs['borrow_permission'] = ((person.borrow_permission or date.today())
                                           + timedelta(weeks=52))
        errors = set()
        if 'libraries' in kwargs:
            lib_names = kwargs.pop('libraries')
            libs = models.Library.select().where(models.Library.name << lib_names)
            if libs.count() != len(lib_names):
                not_found = set(lib_names) - {lib.name for lib in libs}
                raise BuchSchlossNotFoundError('Library', next(iter(not_found)))
            person.libraries.add(lib_names, clear_existing=True)
        for k, v in kwargs.items():
            setattr(person, k, v)
        person.save()
        msg = f'{login_context} edited {person}'
        if 'borrow_permission' in kwargs:
            msg += f' setting borrow_permission to {kwargs["borrow_permission"]}'
        logging.info(msg)
        return errors


class Library(ActionNamespace):
    """Namespace for Library-related functions"""
    @staticmethod
    def new(name: str, *,  # noqa
            books: T.Sequence[int] = (),
            people: T.Sequence[int] = (),
            pay_required: bool = True,
            login_context):
        """Create a new Library with the specified name and add it to the specified
            people and books.

            :param books: and
            :param people: are sequences of the IDs of
              the people and books to gain access / be transferred to the new library
            :param pay_required: indicates whether people need to have paid
              in order to borrow from the library

            :raise BuchSchlossBaseError: if the Library exists
        """
        with models.db:
            try:
                lib = models.Library.create(name=name, pay_required=pay_required)
            except peewee.IntegrityError as e:
                if str(e).startswith('UNIQUE'):
                    raise BuchSchlossExistsError('Library', name)
                else:
                    raise
            else:
                lib.people = people
                models.Book.update({models.Book.library: lib}
                                   ).where(models.Book.id << books).execute()

    @staticmethod
    @from_db(models.Library)
    def edit(lib: T.Union[models.Library, str], *,
             pay_required: bool = None,
             login_context,
             ):
        """Set restriction status of a library

            :param lib: is the name of the Library to modify
            :param pay_required: will set the Library's payment
              requirement to itself if not None

            :raise BuchSchlossBaseError: if the Library doesn't exist
        """
        if pay_required is not None:
            lib.pay_required = pay_required
            lib.save()
        logging.info(f'{login_context} edited {lib}')


class Borrow(ActionNamespace):
    """Namespace for Borrow-related functions"""
    _format_fields_back = utils.get_format_fields('Borrow::repr-back')
    _format_fields_not_back = utils.get_format_fields('Borrow::repr-not-back')
    _format_fields = _format_fields_not_back | _format_fields_back | {'is_back'}

    @classmethod
    def format_object(cls, obj: models.Borrow):
        """differentiate between returned and not returned borrows"""
        if obj.is_back:
            attrs = {k: getattr(obj, k) for k in cls._format_fields_back}
            return utils.get_name('Borrow::repr-back', **attrs)
        else:
            attrs = {k: getattr(obj, k) for k in cls._format_fields_not_back}
            return utils.get_name('Borrow::repr-not-back', **attrs)

    @classmethod
    @from_db(book=models.Book, person=models.Person)
    def new(cls, book, person, weeks, *, override=False, login_context):
        """Borrow a book.

        :param book: is the ID of the Book begin borrowed
        :param person: is the ID of the Person borrowing the book
        :param weeks: is the time to borrow in weeks.
        :param override: may be specified to ignore some issues (b, c, e)

        :raise BuchSchlossBaseError: if

            a) the Person or Book does not exist
            b) the Person has reached their limit set in max_borrow
            c) the Person is not allowed to access the library the book is in
            d) the Book is not available
            e) the Person's borrow_permission has expired

        The maximum amount of time a book may be borrowed for is defined
        in the configuration settings.
        """
        if not book.is_active or book.borrow.where(models.Borrow.is_back == False).count():  # noqa
            raise BuchSchlossError('Borrow', 'Borrow::{}_not_available', book)
        if override:
            check_level(login_context, cls.required_levels.override, 'Borrow.new.override')
        else:
            if book.library not in person.libraries:
                raise BuchSchlossError(
                    'Borrow', 'Borrow::{person}_not_in_{library}',
                    person=person, library=book.library)
            if (book.library.pay_required
                    and (person.borrow_permission or date.min) < date.today()):
                raise BuchSchlossError(
                    'Borrow', 'Borrow::Library_{}_needs_payment', book.library)
            n_borrowed = person.borrows.where(models.Borrow.is_back == False).count()  # noqa
            if n_borrowed >= person.max_borrow:
                raise BuchSchlossError('Borrow', 'Borrow::{}_reached_max_borrow', person)
        rdate = date.today() + timedelta(weeks=weeks)
        models.Borrow.create(person=person, book=book, return_date=rdate)
        logging.info(f'{login_context} borrowed {book} to {person} until {rdate}'
                     + override * ' with override=True')


    @staticmethod
    @from_db(models.Borrow)
    def edit(borrow, *,
             login_context,
             is_back: bool = None,
             return_date: date = None,
             weeks: int = None,
             ):
        """Edit a Borrow

        :param borrow: is either a Borrow DataNS or a Borrow ID
        :param is_back: whether the book was returned
        :param return_date: the date on which the book has to be returned
        :param weeks: the number of weeks to extend borrowing time (from today on)

        :raise BuchSchlossBaseError: if ``borrow`` is a Book DataNS whose .borrow is None

        ``weeks`` and ``return_date`` may not be given together
        """
        if return_date is not None and weeks is not None:
            raise TypeError('``return_date`` and ``weeks`` may not both be given')
        if weeks is not None:
            return_date = date.today() + timedelta(weeks=weeks)
        if return_date is not None:
            borrow.return_date = return_date
        if is_back is not None:
            borrow.is_back = is_back
        logging.info(f'{login_context} edited {borrow}')
        borrow.save()


class Member(ActionNamespace, extra_actions={'change_password': None}):  # special-cased
    """namespace for Member-related functions"""
    @classmethod
    def format_object(cls, obj: models.Member):
        """Wrap utils.get_name to format the ::repr with matching arguments"""
        attrs = {k: getattr(obj, k) for k in cls._format_fields}
        if 'level' in attrs:
            attrs['level'] = utils.level_names[obj.level]
        return utils.get_name('Member::repr', **attrs)

    @staticmethod
    @auth_required
    def new(name: str, password: str, level: int, *, login_context):
        """Create a new Member

        :param name: must be unique among members and is case-sensitive
        :param level: must be between 0 and 4, inclusive
        """
        salt = urandom(config.core.salt_length)
        pass_hash = pbkdf(password.encode(), salt)
        with models.db:
            try:
                m = models.Member.create(name=name, password=pass_hash,
                                         salt=salt, level=level)
            except peewee.IntegrityError as e:
                if str(e).startswith('UNIQUE'):
                    raise BuchSchlossExistsError('Member', name)
                else:
                    raise
        logging.info(f'{login_context} created {m}')

    @staticmethod
    @auth_required
    @from_db(models.Member)
    def edit(member, *, login_context, **kwargs):
        """Edit the given member.

        Set the given attributes on the given Member.
        As of now, only the level can be set.

        If the editee is currently logged in, a new level
        applies to all future actions immediately

        .. warning::

            DO NOT change password with this function.
            Use ``Member.change_password`` instead
        """
        old_str = str(member)
        if not set(kwargs.keys()) <= {'level'}:
            raise TypeError('unexpected kwarg')
        for k, v in kwargs.items():
            setattr(member, k, v)
        member.save()
        logging.info(f'{login_context} edited {old_str} to {member}')

    @classmethod
    @auth_required
    @from_db(member=models.Member)
    def change_password(cls, member, new_password, *, login_context):
        """Change a Member's password

        Editing a password requires having the configured level or being the editee.
        If the editee is currently logged in, the new password
        needs to be used for authentication immediately.
        """
        req_level = cls.required_levels.change_password
        if (login_context.level < req_level
                and (login_context.type is not LoginType.MEMBER
                     or login_context.name != member.name)):
            raise BuchSchlossError('no_permission', 'Member::must_be_{}_or_editee',
                                   utils.level_names[req_level])
        member.salt = urandom(config.core.salt_length)
        member.password = pbkdf(new_password.encode(), member.salt)
        member.save()
        logging.info(f"{login_context} changed {member}'s password")


class Script(ActionNamespace, extra_actions={'execute': None}):
    """namespace for Script-related functions"""
    allowed_chars = set(string.ascii_letters + string.digits + ' _-')
    callbacks = None

    @staticmethod
    def _transform_permissions(perms):
        """create a ScriptPermissions form an iterable of names"""
        return functools.reduce(
            operator.or_,
            (ScriptPermissions[p] for p in perms),
            ScriptPermissions(0),
        )

    @classmethod
    @auth_required
    def new(cls, *,
            name: str,
            code: str,
            setlevel: T.Optional[int],
            permissions: T.Iterable[str],
            login_context: LoginContext):
        """create a new script with the given arguments

        raise a BuchSchlossError if a script with the names name already exists
        see models.Script for details on arguments
        """
        permissions = cls._transform_permissions(permissions)
        if not name:
            raise ValueError('Name is empty')
        if not set(name) <= cls.allowed_chars:
            raise ValueError("Name contains illegal characters {}"
                             .format(''.join(set(name) - cls.allowed_chars)))
        if setlevel is not None:
            check_level(login_context, setlevel, 'Script.new.setlevel')
        try:
            new = models.Script.create(
                name=name, code=code, setlevel=setlevel,
                permissions=permissions, storage={})
        except peewee.IntegrityError as e:
            if str(e).startswith('UNIQUE'):
                raise BuchSchlossExistsError('Script', name)
            else:
                raise
        else:
            logging.info(f'{login_context} created {new}')

    @classmethod
    @auth_required
    @from_db(script=models.Script)
    def edit(cls, script: T.Union[str, models.Script], *, login_context, **kwargs):
        """edit a script"""
        if not set(kwargs) <= cls._model_fields or 'name' in kwargs:
            raise TypeError('unexpected kwarg')
        if 'permissions' in kwargs:
            kwargs['permissions'] = cls._transform_permissions(kwargs['permissions'])
        for k, v in kwargs.items():
            setattr(script, k, v)
        script.save()
        logging.info(f'{login_context} edited {script}')

    @classmethod
    @from_db(script=models.Script)
    def execute(cls,
                script: T.Union[str, models.Script],
                function: T.Optional[str] = None,
                *,
                callbacks=None,
                login_context):
        """Execute a script

        :param script: is a script name
        :param function: is optionally a name of a function in the
            script that takes no arguments. The function will be called.
        :param callbacks: may be an alternative UI callback
            dictionary to the default one
        """
        if script.setlevel is None:
            script_lc_level = login_context.level
        else:
            script_lc_level = script.setlevel
        script_lc = LoginContext(
            LoginType.SCRIPT, script_lc_level, name=script.name, invoker=login_context)
        ui_callbacks = callbacks or cls.callbacks
        get_name_prefix = f'script-data::{script.name}::'
        script_config = config.scripts.lua.get(script.name).mapping
        if ScriptPermissions.STORE in script.permissions:
            edit_func = partial(Script.edit, script.name, login_context=internal_priv_lc)
            add_storage = (
                lambda: Script.view_ns(script.name, login_context=internal_priv_lc)['storage'],
                lambda data: edit_func(storage=data),
            )
        else:
            add_storage = None
        runtime = lua.prepare_runtime(
            script_lc,
            add_ui=(ui_callbacks and (ui_callbacks, get_name_prefix)),
            add_storage=add_storage,
            add_requests=(ScriptPermissions.REQUESTS in script.permissions),
            add_config=script_config,
        )
        try:
            ns = runtime.execute(script.code)
            if function is not None:
                ns[function]()
        except BuchSchlossBaseError:
            raise
        except Exception as e:
            if config.debug:
                raise
            logging.error('error executing script function: ' + str(e))
            display = script.name
            if function is not None:
                display += ':' + function
            raise BuchSchlossError('Script::execute', 'script_{}_exec_problem', display)


class DataNamespace(T.Mapping[str, T.Any]):
    """class for data namespaces returned by view_ns"""
    def __init__(self,
                 ans: T.Type[ActionNamespace],
                 raw_data: T.Any,
                 login_context: LoginContext,
                 verified=False,
                 ):
        """initialize this namespace with data from the database"""
        self.verified = verified
        self.data = raw_data
        self.ans = ans
        self.handlers = self.data_handling[ans]
        self.attributes = frozenset.union(*map(frozenset, self.handlers.values()))
        self.login_context = login_context
        self.string = ans.format_object(raw_data)

    def __eq__(self, other):
        if isinstance(other, DataNamespace):
            return self.data == other.data
        elif isinstance(other, type(self['id'])):
            return self['id'] == other
        else:
            return NotImplemented

    def __len__(self):
        return len(tuple(self))

    def __iter__(self):
        return iter({'id', *itertools.chain.from_iterable(self.handlers.values())})

    def __hash__(self):
        return hash(self['id'])

    def __str__(self):
        return str(self.data)

    def __getitem__(self, item):
        if not self.verified:
            self.ans.check_view_permissions(self.login_context, self)
            self.verified = True
        if item == 'id':
            # Not making the same mistake twice
            return getattr(self.data, type(self.data).pk_name)
        elif item in self.attributes:
            obj = getattr(self.data, item)
        else:
            raise KeyError(f"DataNamespace of {self.ans!r} has no key '{item}'")
        if item in self.handlers.get('transform', {}):
            obj = self.handlers['transform'][item](obj)
        if item in self.handlers.get('wrap_iter', {}):
            new_dns = partial(type(self),
                              self.handlers['wrap_iter'][item],
                              login_context=self.login_context)
            return tuple(map(new_dns, obj))
        elif item in self.handlers.get('wrap_dns', {}):
            if obj is None:
                return None
            else:
                return type(self)(
                    self.handlers['wrap_dns'][item],
                    obj,
                    login_context=self.login_context,
                )
        else:  # allow + transform without wrapping
            return obj

    data_handling: T.Mapping[T.Type[ActionNamespace], T.Mapping] = {
        Book: {
            'allow': ('isbn author title series series_number language publisher '
                      'concerned_people year medium shelf is_active').split(),
            'transform': {
                'genres': lambda gs: [g.name for g in gs],
                'groups': lambda gs: [g.name for g in gs],
                'borrow': lambda bs:
                    next(iter(bs.where(models.Borrow.is_back == False).limit(1)), None),
            },
            'wrap_dns': {'library': Library, 'borrow': Borrow},
        },
        Person: {
            'allow': 'first_name last_name class_ max_borrow borrow_permission'.split(),
            'transform': {'borrows': lambda bs: bs.where(models.Borrow.is_back == False)},  # noqa
            'wrap_iter': {'libraries': Library, 'borrows': Borrow},
        },
        Library: {
            'allow': ('name', 'pay_required'),
            'wrap_iter': {'books': Book, 'people': Person},
        },
        Borrow: {
            'allow': ('id', 'return_date', 'is_back'),
            'wrap_dns': {'book': Book, 'person': Person},
        },
        Member: {
            'allow': ('name', 'level'),
        },
        Script: {
            'allow': ('name', 'code', 'setlevel', 'storage'),
            'transform': {
                'permissions': lambda ps: [p.name for p in ScriptPermissions if p in ps],
            },
        },
    }


internal_priv_lc = LoginContext(LoginType.INTERNAL, config.MAX_LEVEL)
internal_unpriv_lc = LoginContext(LoginType.INTERNAL, 0)
guest_lc = LoginContext(LoginType.GUEST, 0)
misc_data = MiscData()

logging.info('core operational')
