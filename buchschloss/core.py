"""Core functionalities of the application.

Handles access to the database and provides high-level interfaces for all operations.
__all__ exports:
    - BuchSchlossBaseError: the error raised in this module.
        Instances come with a nice description of what exactly failed.
    - DummyErrorFile: a dummy error file (for sys.stderr) that writes errors to log
        and provides access to them e.g. for display or ending
    - misc_data: provide easy access to data stored in Misc by attribute lookup
    - login, logout: to log  user in or out
    - Book, Person, Borrow, Member, Library, Group: namespaces for functions
        dealing with the respective objects
    - ComplexSearch: for very complex search queries
"""

import inspect
from hashlib import pbkdf2_hmac
from functools import wraps, partial
from datetime import datetime, timedelta, date
from os import urandom
import sys
import warnings
import operator
import re
import enum
import abc
import builtins
import traceback
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

__all__ = [
    'BuchSchlossBaseError', 'DummyErrorFile', 'misc_data', 'ComplexSearch',
    'Person', 'Book', 'Member', 'Borrow', 'Library', 'Group',
    'login',
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
del log_conf
logging.basicConfig(level=getattr(logging, config.core.log.level),
                    format='{asctime} - {levelname} - {funcName}: {msg}',
                    datefmt='%Y-%m-%d %H:%M:%S',
                    style='{',
                    handlers=[handler],
                    )


class LoginType(enum.Enum):
    MEMBER = 'Member[{name}]({level})'
    GUEST = 'Guest'
    SCRIPT = 'Script[{name}]({level})'
    INTERNAL = 'SYSTEM-{name}'


class LoginContext:
    """data about a logged in user"""

    def __init__(self, login_type: LoginType, name: str, level: int):
        self.type = login_type
        self.name = name
        self.level = level

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
    """

    def __init__(self, title, message, *message_format):
        super().__init__(utils.get_name(title),
                         utils.get_name(message).format(*message_format))


class BuchSchlossPermError(BuchSchlossBaseError):
    """use utils.get_name for level and message name"""

    def __init__(self, level):
        super().__init__(utils.get_name('no_permission'),
                         utils.get_name('must_be_{}').format(
                             utils.get_level(level)))


class BuchSchlossNotFoundError(BuchSchlossError.template_title('%s_not_found')
                               .template_message('no_%s_with_id_{}')):
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
            f.write('\n\nSTART: ' + str(datetime.now()) + '\n')

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


class LibraryGroupAction(enum.Enum):
    ADD = 'add'
    REMOVE = 'remove'
    DELETE = 'delete'
    NONE = 'none'


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
            with models.db:
                for k, m in keyword_arguments.items():
                    arg = bound.arguments[k]
                    if not isinstance(arg, m):  # allow direct passing
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
        logging.info('access to {} denied to {}'
                     .format(resource, login_context))
        raise BuchSchlossPermError(level)


def level_required(level):
    """require the given level for executing the wrapped function.
    raise a BuchSchlossBaseError when requirement not met."""

    def wrapper_maker(f):
        checker = partial(check_level, level=level, resource=f.__qualname__)

        @wraps(f)
        def level_required_wrapper(*args, login_context: LoginContext, **kwargs):
            checker(login_context)
            return f(*args, **kwargs)

        return level_required_wrapper

    return wrapper_maker


def auth_required(f):
    """require the currently logged member's password for executing the function
    raise a BuchSchlossBaseError if not given or wrong"""

    @wraps(f)
    def auth_required_wrapper(*args, login_context: LoginContext, current_password: str, **kwargs):
        if login_context.type is not LoginType.MEMBER:
            raise BuchSchlossError('auth_failed', 'not_logged_in')
        login_member = Member.view_ns(login_context.name, login_context=internal_lc).password
        if authenticate(login_member, current_password):
            logging.info('{} passed authentication for {}'.format(
                current_login, f.__name__))
            return f(*args, **kwargs)
        else:
            logging.info('{} failed to authenticate for {}'.format(
                current_login, f.__name__))
            raise BuchSchlossError('auth_failed', 'wrong_password')

    auth_required_wrapper.__doc__ += (
        '\n\nThis function requires authentication in form of\n'
        'a `current_password` argument containing the currently\n'
        "logged in member's password\n")
    auth_required.functions.append(f.__qualname__)
    return auth_required_wrapper
auth_required.functions = []  # noqa


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

    Return a LoginContext on success

    Try all iterations specified in config.HASH_ITERATIONS
        and update to newest (first) one where applicable
    raise a BuchSchlossBaseError on failure
    """
    try:
        with models.db:
            m = models.Member.get_by_id(name)
    except models.Member.DoesNotExist:
        raise BuchSchlossError('login', 'no_Member_with_id_{}', name)
    if authenticate(m, password):
        logging.info('login success {}'.format(m))
        return LoginContext(LoginType.MEMBER, m.name, m.level)
    else:
        logging.info('login fail {}'.format(m))
        raise BuchSchlossError('login', 'wrong_password')


def _update_library_group(lg_model: T.Type[models.Model],
                          libgr: peewee.ManyToManyQuery,
                          new: T.Set[str]):
    errors = set()
    old = set(lg.name for lg in libgr)
    for add in new.difference(old):
        try:
            libgr.add(lg_model.get(name=add))
        except lg_model.DoesNotExist:
            errors.add(BuchSchlossNotFoundError(lg_model.__name__, add).message)
    for rem in old.difference(new):
        # these are the ones we just read from the database,
        # if we get an error here it's bad, so let it crash
        libgr.remove(lg_model.get(name=rem))
    return errors


class ActionNamespace(abc.ABC):
    """Abstract base class for the Book, Person Member, Library, Group and Borrow namespaces"""
    model: T.ClassVar[models.Model]
    view_level: T.ClassVar[int] = 0

    @classmethod
    @abc.abstractmethod
    def new(cls, *, login_context, **kwargs):
        """Create a new record"""
        raise NotImplementedError

    @classmethod
    @abc.abstractmethod
    def view_str(cls, id_: T.Union[int, str], *, login_context) -> dict:
        """Return information in a dict"""
        raise NotImplementedError

    @classmethod
    def view_ns(cls, id_: T.Union[int, str], *, login_context):
        """Return a namespace of information"""
        check_level(login_context, cls.view_level, cls.__name__ + '.view_ns')
        try:
            return cls.model.get_by_id(id_)
        except cls.model.DoesNotExist:
            raise BuchSchlossNotFoundError(cls.model.__name__, id_)

    @classmethod
    def view_repr(cls, id_: T.Union[str, int], *, login_context) -> str:
        """Return a string representation"""
        check_level(login_context, cls.view_level, cls.__name__ + '.view_repr')
        try:
            return str(next(iter(cls.model.select_str_fields().where(
                getattr(cls.model, cls.model.pk_name) == id_))))
        except StopIteration:
            raise BuchSchlossNotFoundError(cls.model.__name__, id_)

    @classmethod
    def view_attr(cls, id_: T.Union[str, int], name: str, *, login_context):
        """Return the value of a specific attribute"""
        # this is said to be faster...
        check_level(login_context, cls.view_level, cls.__name__ + '.view_attr')
        try:
            return getattr(next(iter(cls.model.select(getattr(cls.model, name)).where(
                getattr(cls.model, cls.model.pk_name) == id_))), name)
        except StopIteration:
            raise BuchSchlossNotFoundError(cls.model.__name__, id_)

    @classmethod
    def search(cls,
               condition: tuple,
               complex_params: T.Iterable['ComplexSearch'] = (),
               complex_action: str = None,
               *,
               login_context
               ):
        """search for records. see search for details on arguments"""
        check_level(login_context, cls.view_level, cls.__name__ + '.search')
        return search(cls.model, condition, *complex_params,
                      complex_action=complex_action)


class Book(ActionNamespace):
    """Namespace for Book-related functions"""
    model = models.Book

    @staticmethod
    @level_required(2)
    def new(*, isbn: int, author: str, title: str, language: str, publisher: str,
            year: int, medium: str, shelf: str, series: T.Optional[str] = None,
            series_number: T.Optional[int] = None,
            concerned_people: T.Optional[str] = None,
            genres: T.Optional[str] = None, groups: T.Iterable[str] = (),
            library: str = 'main', login_context: LoginContext) -> int:
        """Attempt to create a new Book with the given arguments and return the ID

        automatically create groups as needed
        raise a BuchSchlossBaseError on failure

        See models.Book.__doc__ for details on arguments"""
        with models.db:
            try:
                b = models.Book.create(
                    isbn=isbn, author=author, title=title, language=language,
                    publisher=publisher, year=year, medium=medium,
                    shelf=shelf, series=series, series_number=series_number,
                    concerned_people=concerned_people, genres=genres,
                    library=models.Library.get_by_id(library),
                )
                for g in groups:
                    b.groups.add(models.Group.get_or_create(name=g)[0])
            except models.Library.DoesNotExist:
                raise BuchSchlossNotFoundError('Library', library)
            else:
                logging.info('{} created {}'.format(login_context, b))
        return b.id

    @staticmethod
    @from_db(models.Book)
    @level_required(2)
    def edit(book: T.Union[int, models.Book], *, login_context, **kwargs):
        """Edit a Book based on the arguments given.

        See Book.__doc__ for more information on the arguments
        raise a BuchSchlossBaseError if the Book isn't found
            or the new library does not exist
        return a set of error messages for errors during group changes
        """
        if ((not set(kwargs.keys()) <= {k for k in dir(models.Book)
                                        if isinstance(getattr(models.Book, k),
                                                      peewee.Field)})
                or 'id' in kwargs):
            raise TypeError('unexpected kwarg')
        groups = set(kwargs.pop('groups', ()))
        errors = _update_library_group(models.Group, book.groups, groups)
        lib = kwargs.pop('library', None)
        if lib is not None:
            try:
                book.library = models.Library.get_by_id(lib)
            except models.Library.DoesNotExist:
                raise BuchSchlossNotFoundError('Library', lib)
        for k, v in kwargs.items():
            if (isinstance(v, str)
                    and not isinstance(getattr(models.Book, k), peewee.CharField)):
                logging.warning('auto-type-conversion used')
                v = type(getattr(book, k))(v)
            setattr(book, k, v)
        book.save()
        logging.info('{} edited {}'.format(login_context, book))
        return errors

    @staticmethod
    @from_db(models.Book)
    def view_str(book: T.Union[int, models.Book], *, login_context):
        """Return data about a Book.

        Return a dictionary consisting of the following items as strings:
            - author, isbn, title, series, series_number, language, publisher,
                concerned_people, year, medium, genres, shelf, id
            - the name of the Library the Book is in
            - groups as a string consisting of group names separated by ';'
            - the book's status (available, borrowed or inactive)
            - return_date: either '-----' or the date the book will be returned
            - borrowed_by: '-----' or a representation of the borrowing Person
            - __str__: the string representation of the Book
        and 'borrowed_by_id', the ID of the Person that borrowed the Book (int)
            or None if not borrowed
        """
        r = {k: str(getattr(book, k) or '') for k in
             ('author', 'isbn', 'title', 'series', 'series_number', 'language',
              'publisher', 'concerned_people', 'year', 'medium', 'genres', 'shelf', 'id',
              )}
        r['library'] = book.library.name
        r['groups'] = ';'.join(g.name for g in book.groups)
        borrow = book.borrow or Dummy(id=None, _bool=False)
        r['status'] = utils.get_name('borrowed' if borrow else
                                     ('available' if book.is_active
                                      else 'inactive'))
        r['return_date'] = str(borrow.return_date.strftime(config.core.date_format))
        r['borrowed_by'] = str(borrow.person)
        r['borrowed_by_id'] = borrow.person.id
        r['__str__'] = str(book)
        logging.info('{} viewed {}'.format(login_context, book))
        return r


class Person(ActionNamespace):
    """Namespace for Person-related functions"""
    model = models.Person
    view_level = 1

    @staticmethod
    @level_required(3)
    def new(*, id_: int, first_name: str, last_name: str, class_: str,
            max_borrow: int = 3, libraries: T.Iterable[str] = ('main',),
            pay: bool = None, pay_date: date = None,
            login_context):
        """Attempt to create a new Person with the given arguments.

        raise a BuchSchlossBaseError on failure.
        Silently ignore nonexistent libraries

        See Person for details on arguments
        If ``pay`` is True and ``pay_date`` is None,
            set the pay_date to ``datetime.date.today()``
        """
        if pay_date is None and pay:
            pay_date = date.today()
        if max_borrow > 3 and not current_login.level >= 4:
            raise BuchSchlossPermError(4)
        p = models.Person(id=id_, first_name=first_name, last_name=last_name,
                          class_=class_, max_borrow=max_borrow, pay_date=pay_date)
        p.libraries = libraries
        try:
            p.save(force_insert=True)
        except peewee.IntegrityError as e:
            traceback.print_exc()
            if str(e).startswith('UNIQUE'):
                raise BuchSchlossError('Person_exists', 'Person_{}_exists', id_)
            else:
                raise
        else:
            logging.info('{} created {} with pay={}'.format(login_context, p, pay))

    @staticmethod
    @level_required(3)
    @from_db(models.Person)
    def edit(person: T.Union[int, models.Person], *, login_context, **kwargs):
        """Edit a Person based on the arguments given.

        See Person.__doc__ for more information on the arguments
        `pay` may be passed as argument with a truthy model to set
            `pay_date` to `datetime.date.today()`

        raise a BuchSchlossBaseError if the Person isn't found.
        Return a set of errors found during updating the person's libraries
        """
        if ((not set(kwargs.keys()) <= {k for k in dir(models.Person)
                                        if isinstance(getattr(models.Person, k),
                                                      peewee.Field)} | {'pay'})
                or 'id' in kwargs):
            raise TypeError('unexpected kwarg')
        if kwargs.pop('pay', False):
            kwargs['pay_date'] = date.today()
        errors = set()
        lib = set(kwargs.pop('libraries', ()))
        errors.update(_update_library_group(models.Library, person.libraries, lib))
        for k, v in kwargs.items():
            setattr(person, k, v)
        person.save()
        logging.info('{} edited {}'.format(login_context, person)
                     + (' setting pay_date to {}'.format(kwargs['pay_date'])
                        if 'pay_date' in kwargs else ''))
        return errors

    @staticmethod
    @level_required(1)
    @from_db(models.Person)
    def view_str(person: T.Union[models.Person, int], *, login_context):
        """Return data about a Person.

        Return a dict consisting of the following items as strings:
            - id, first_name, last_name, class_ max_borrow, pay_date attributes
            - libraries as a string, individual libraries separated by ;
            - borrows as a tuple of strings representing the borrows
            - __str__ , the string representation
        and 'borrow_book_ids', a sequence of the IDs of the borrowed books
            in the same order their representations appear in 'borrows'"""
        r = {k: str(getattr(person, k) or '') for k in
             'id first_name last_name class_ max_borrow pay_date'.split()}
        borrows = person.borrows
        r['borrows'] = tuple(map(str, borrows))
        r['borrow_book_ids'] = [b.book.id for b in borrows]
        r['libraries'] = ';'.join(L.name for L in person.libraries)
        r['__str__'] = str(person)
        logging.info('{} viewed {}'.format(login_context, person))
        return r


class Library(ActionNamespace):
    """Namespace for Library-related functions"""
    model = models.Library

    @staticmethod
    @level_required(3)
    def new(name: str, *,
            books: T.Sequence[int] = (),
            people: T.Sequence[int] = (),
            pay_required: bool = True,
            login_context):
        """Create a new Library with the specified name and add it to the specified
                people and books.

            ``people`` and ``books`` are sequences of the IDs of the people and books
                to gain access / be transferred to the new library

            ``pay_required`` indicates whether people need to have paid
                in order to borrow from the library

            raise a BuchSchlossBaseError if the Library exists
        """
        with models.db:
            try:
                lib = models.Library.create(name=name, pay_required=pay_required)
            except peewee.IntegrityError as e:
                if str(e).startswith('UNIQUE'):
                    raise BuchSchlossError('Library_exists', 'Library_{}_exists', name)
                else:
                    raise
            else:
                lib.people = people
                models.Book.update({models.Book.library: lib}
                                   ).where(models.Book.id << books).execute()

    @staticmethod
    @level_required(3)
    def edit(action: LibraryGroupAction, name: str, *,
             people: T.Sequence[int] = (),
             books: T.Sequence[int] = (),
             pay_required: bool = None,
             login_context):
        """Perform the given action on the Library with the given name

            DELETE will remove the reference to the library from all people
                and books (setting their library to 'main'),
                but not actually delete the Library itself
                ``people`` and ``books`` are ignored in this case
            ADD will add the Library to all given people and set the library
                of all the given books to the specified one
            REMOVE will remove the reference to the given Library in the given people
                and set the library of the given books to 'main'
            NONE will ignore ``people`` and ``books`` and
                take no action other than setting ``pay_required``

            ``name`` is the name of the Library to modify
            ``people`` is an iterable of the IDs of the people to modify
            ``books`` is an iterable of IDs of the books to modify
            ``pay_required`` will set the Library's payment requirement to itself if not None

            raise a BuchSchlossBaseError if the Library doesn't exist
        """
        try:
            lib: models.Library = models.Library.get_by_id(name)
        except models.Library.DoesNotExist:
            raise BuchSchlossNotFoundError('Library', name)
        with models.db:
            if action is LibraryGroupAction.DELETE:
                lib.people = ()
                models.Book.update({models.Book.library: models.Library.get_by_id('main')}
                                   ).where(models.Book.library == lib).execute()
            elif action is LibraryGroupAction.ADD:
                models.Book.update({models.Book.library: lib}
                                   ).where(models.Book.id << books).execute()
                for p in people:
                    lib.people.add(p)
            elif action is LibraryGroupAction.REMOVE:
                models.Book.update({models.Book.library: models.Library.get_by_id('main')}
                                   ).where((models.Book.library == lib)
                                           & (models.Book.id << books)).execute()
                for p in people:
                    lib.people.remove(p)
            if pay_required is not None:
                lib.pay_required = pay_required
                lib.save()

    @staticmethod
    @from_db(models.Library)
    def view_str(lib, *, login_context):
        """Return information on the Library

            Return a dict with the following items as strings:
            - __str__: a string representation of the Library
            - name: the name of the Library
            - people: the IDs of the people in the Library, separated by ';'
            - books: the IDs of the books in the Library, separated by ';'
        """
        return {
            '__str__': str(lib),
            'name': lib.name,
            'people': ';'.join(map(str, (p.id for p in lib.people))),
            'books': ';'.join(map(str, (b.id for b in lib.books))),
        }


class Group(ActionNamespace):
    """Namespace for Group-related functions"""
    model = models.Group

    @staticmethod
    @level_required(3)
    def new(name: str, books: T.Sequence[int] = (), *, login_context):
        """Create a new Group with the given name and books

            raise a BuchSchlossBaseError if the Group exists
            ignore nonexistent Books
        """
        with models.db:
            try:
                group = models.Group.create(name=name)
            except peewee.IntegrityError as e:
                if str(e).startswith('UNIQUE'):
                    raise BuchSchlossError('Group_exists', 'Group_{}_exists', name)
                else:
                    raise
            else:
                group.books = books

    @staticmethod
    @level_required(3)
    def edit(action: LibraryGroupAction, name: str, books: T.Iterable[int], *, login_context):
        """Perform the given action on the Group with the given name

            DELETE will remove all references to the Group,
                but not delete the Group itself. ``books`` is ignored in this case
            ADD will add the given Group to the given books
                ignore IDs of non-existing books
            REMOVE will remove the reference to the Group in all of the given books
                ignore books not in the Group and IDs of nonexistent books
            NONE does nothing
        """
        with models.db:
            try:
                group = models.Group.get_by_id(name)
            except models.Group.DoesNotExist:
                raise BuchSchlossNotFoundError('Group', name)
            else:
                if action is LibraryGroupAction.DELETE:
                    group.books = ()
                elif action is LibraryGroupAction.NONE:
                    pass
                else:
                    for book in books:
                        getattr(group.books, action.value)(book)

    @staticmethod
    @level_required(3)
    @from_db(models.Group)
    def activate(group, src: T.Sequence[str] = (), dest: str = 'main', *, login_context):
        """Activate a Group

            ``src`` is an iterable of the names of origin libraries
                if it is falsey (empty), books are taken from all libraries
            ``dest`` is the name of the target Library

            raise a BuchSchlossBaseError it the Group, the target Library
                or a source Library does not exist
        """
        if src and (models.Library.select(None)
                    .where(models.Library.name << src).count()
                    != len(src)):
            present_libraries = set(lib.name for lib in
                                    models.Library.select(models.Library.name)
                                    .where(models.Library.name << src))
            not_found = ', '.join(set(src) - present_libraries)
            raise BuchSchlossNotFoundError('Libraries', not_found)
        try:
            dest = models.Library.get_by_id(dest)
        except models.Library.DoesNotExist:
            raise BuchSchlossNotFoundError('Library', dest)
        books_to_update = (models.Book.select(models.Book.id)
                           .join(models.Book.groups.through_model)
                           .join(models.Group)
                           .where(models.Group.name == group.name)
                           .switch(models.Book))
        if src:
            books_to_update = books_to_update.where(models.Book.library << src)
        (models.Book.update(library=dest)
         .where(models.Book.id << [b.id for b in books_to_update])
         .execute())

    @staticmethod
    @from_db(models.Group)
    def view_str(group, *, login_context):
        """Return data on a Group

            Return a dict with the following items as strings:
            - __str__: a string representation of the Group
            - name: the name of the Group
            - books: the IDs of the books in the Group
                separated by ';'
        """
        return {
            '__str__': str(group),
            'name': group.name,
            'books': ';'.join(str(b.id) for b in group.books),
        }


class Borrow(ActionNamespace):
    """Namespace for Borrow-related functions"""
    model = models.Borrow
    view_level = 1

    @staticmethod
    @from_db(models.Book, models.Person)
    def new(book, person, weeks, *, login_context):
        """Borrow a book.

            ``book`` is the ID of the Book begin borrowed
            ``person`` is the ID of the Person borrowing the book
            ``weeks`` is the time to borrow in weeks.

            raise an error if
                a) the Person or Book does not exist
                b) the Person has reached their limit set in max_borrow
                c) the Person is not allowed to access the library the book is in
                d) the Book is not available
                e) the Person has not paid for over 52 weeks and the book's
                    Library requires payment
                f) ``weeks`` exceeds the one allowed to the executing member
                g) ``weeks`` is <= 0

            the maximum amount of time a book may be borrowed for is defined
            in the configuration settings
        """
        if weeks > config.core.borrow_time_limit[current_login.level]:
            raise BuchSchlossPermError(1)
        if weeks <= 0:
            raise BuchSchlossError('Borrow', 'borrow_length_not_positive')
        if not book.is_active or book.borrow:
            raise BuchSchlossError('Borrow', 'Book_{}_not_available', book.id)
        if book.library not in person.libraries:
            raise BuchSchlossError('Borrow', '{}_not_in_Library_{}',
                                   person, book.library.name)
        if (book.library.pay_required and (person.pay_date or date.min)
                + timedelta(weeks=52) < date.today()):
            raise BuchSchlossError('Borrow', 'Library_{}_needs_payment', book.library)
        if len(person.borrows) >= person.max_borrow:
            raise BuchSchlossError('Borrow', '{}_has_reached_max_borrow', person)
        rdate = date.today() + timedelta(weeks=weeks)
        models.Borrow.create(person=person, book=book, return_date=rdate)
        logging.info('{} borrowed {} to {} until {}'.format(
            login_context, book, person, rdate))
        latest = misc_data.latest_borrowers
        # since the values are written to the DB on explicit assignment only
        # and values aren't cached (yet, but I still don't want to rely on it)
        # but read on each lookup, the temporary variable is important
        if person.id in latest:
            latest.remove(person.id)
        else:
            latest = latest[:config.core.save_latest_borrowers - 1]
        latest.insert(0, person.id)
        misc_data.latest_borrowers = latest

    @staticmethod
    @level_required(1)
    @from_db(models.Book)
    def restitute(book, person, *, login_context):
        """return a book

            ``book`` is the ID of the Book to be returned
            ``person`` may be the ID of the returning Person or None

            if ``person`` is not None, verify that the specified Person
            actually has borrowed the Book before making modifications
            and raise a BuchSchlossBaseError if that is not the case
            Also raise a BuchSchlossBaseError if the book hasn't been borrowed,
            even if ``person`` is None

            return the returned Book's shelf
        """
        borrow = book.borrow
        if borrow is None:
            raise BuchSchlossError('not_borrowed', '{}_not_borrowed', book.id)
        if person is not None and borrow.person.id != person:
            raise BuchSchlossError('not_borrowed', '{}_not_borrowed_by_{}',
                                   book, person)
        borrow.is_back = True
        borrow.save()
        logging.info('{} confirmed {} was returned'.format(login_context, borrow))
        return book.shelf

    @staticmethod
    @level_required(1)
    @from_db(models.Borrow)
    def view_str(borrow, *, login_context):
        """Return information about a Borrow

            Return a dictionary containing the following items:
            - __str__: a string representation of the Borrow
            - person: a string representation of the borrowing Person
            - person_id: the ID of the borrowing Person
            - book: a string representation of the borrowed Book
            - book_id: the ID of the borrowed Book
            - return_date: a string representation of the date
                by which the book has to be returned
            - is_back: a string indicating whether the Book has been returned
        """
        return {
            '__str__': str(borrow),
            'person': str(borrow.person),
            'person_id': borrow.person.id,
            'book': str(borrow.book),
            'book_id': borrow.book.id,
            'return_date': str(borrow.return_date),
            'is_back': utils.get_name(str(borrow.is_back)),
        }


class Member(ActionNamespace):
    """namespace for Member-related functions"""
    model = models.Member
    view_level = 2

    @staticmethod
    @auth_required
    @level_required(4)
    def new(name: str, password: str, level: int, *, login_context):
        """Create a new Member

            ``name`` must be unique among members and is case-sensitive
            ``level`` must be between 0 and 4, inclusive
        """
        salt = urandom(config.core.salt_length)
        pass_hash = pbkdf(password.encode(), salt)
        with models.db:
            try:
                m = models.Member.create(name=name, password=pass_hash,
                                         salt=salt, level=level)
            except peewee.IntegrityError as e:
                if str(e).startswith('UNIQUE'):
                    raise BuchSchlossError('Member_exists', 'Member_{}_exists', name)
                else:
                    raise
        logging.info('{} created {}'.format(login_context, m))

    @staticmethod
    @auth_required
    @level_required(4)
    @from_db(models.Member)
    def edit(member, *, login_context, **kwargs):
        """Edit the given member.

            Set the given attributes on the given Member.
            As of now, only the level can be set.

            If the editee is currently logged in, a new level
            applies to all future actions immediately

            ATTENTION: DO NOT change password with this function
            use Member.change_password instead
        """
        old_str = str(member)
        if (not set(kwargs.keys()) <= {'level'}) or 'name' in kwargs:
            raise TypeError('unexpected kwarg')
        for k, v in kwargs.items():
            setattr(member, k, v)
        member.save()
        logging.info('{} edited {} to {}'.format(login_context, old_str, member))

    @staticmethod
    @auth_required
    @from_db(models.Member)
    def change_password(member, new_password, *, login_context):
        """Change a Member's password

            editing a password requires being level 4 or the editee
            If the editee is currently logged in, the new password
            needs to be used for authentication immediately
        """
        global current_login
        if current_login.level < 4 and current_login.name != member.name:
            raise BuchSchlossError('no_permission', 'must_be_level_4_or_editee')
        member.salt = urandom(config.core.salt_length)
        member.password = pbkdf(new_password.encode(), member.salt)
        member.save()
        if current_login.name == member.name:
            current_login = member
        logging.info("{} changed {}'s password".format(login_context, member))

    @staticmethod
    @from_db(models.Member)
    def view_str(member, *, login_context):
        """Return information about a Member

            Return a dictionary with the following string items:
            - __str__: a representation of the Member
            - name: the Member's name
            - level: the Member's level
        """
        return {
            '__str__': str(member),
            'name': member.name,
            'level': utils.get_level(member.level),
        }


def search(o: T.Type[models.Model], condition: T.Tuple = None,
           *complex_params: 'ComplexSearch', complex_action: str = 'or',
           ):
    """THIS IS AN INTERNAL FUNCTION -- for user searches, use *.search

        Search for objects.

        `condition` is a tuple of the form (<a>, <op>, <b>)
            with <op> being a logical operation ("and" or "or") and <a>
                and <b> in that case being condition tuples
            or a comparison operation ("contains", "eq", "ne", "gt", "ge",
                "lt" or "le")
                in which case <a> is a (possibly dotted) string corresponding
                to the attribute name and <b> is the model to compare to.
            It may be empty, in which case it has no effect, i.e. is True
                when used with an 'and' and False when used with an 'or'
            If the top-level condition is empty, all existing values are returned
        `complex_params` is a sequence of ComplexSearch instances to apply after
            executing the SQL SELECT
        `complex_action` is "and" or "or" and specifies how to handle multiple
            complex cases. If finer granularity is needed, it can be achieved with
            bitwise operators, providing bools are used.

        Note: for `condition`, there is no "not" available.
            Use the inverse comparision operator instead
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
        cur = mod = o
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
        return fv, q

    def handle_condition(cond, q):
        if not cond:
            return q
        a, op, b = cond
        if op in ('and', 'or'):
            if not a:
                return handle_condition(b, q)
            elif not b:
                return handle_condition(a, q)
            else:
                return getattr(operator, op + '_')(handle_condition(a, q),
                                                   handle_condition(b, q))
        else:
            a, q = follow_path(a, q)
            if op in ('eq', 'ne', 'gt', 'lt', 'ge', 'le'):
                return q.where(getattr(operator, op)(a, b))
            elif op == 'contains':
                return q.where(a.contains(b))
            else:
                raise ValueError('`op` must be "and", "or", "eq", "ne", "gt", "lt" '
                                 '"ge", "le" or "contains"')

    query = o.select(*o.str_fields)
    result = handle_condition(condition, query)
    if complex_params:
        return _do_complex_search(complex_action, result, complex_params)
    else:
        return result


def _do_complex_search(kind: str, objects: T.Iterable[models.Model], complex_params):
    """Perform the ComplexSearch operations.
        Once __search_old is removed, this can be merged into search"""
    results = set()
    for o in objects:
        for c in complex_params:
            if c.apply_lookups(o):
                if kind == 'or':
                    results.add(o)
                    break
            elif kind == 'and':
                break
        else:
            if kind == 'and':
                results.add(o)
    return results


def _cs_lookup(name):
    def wrapper(self, other):
        self.lookups.append((name, other))
        return self

    return wrapper


class ComplexSearch:  # TODO: use misc.Instance for this
    """Allow complex lookups and comparisons when using search().

    To later perform attr and/or item lookups on objects when searching,
    perform these lookups in an instance of ComplexSearch.
    e.g.: 'tim' in ComplexSearch().metadata['author'] TODO: update example
    Store attribute and item lookups internally, to actually perform them, call apply_lookups()
    Treat comparisons (== != < <= > >= in) as item lookups

    to use iterations, call iter and perform the operations you would perform
        on the individual items on the return model
    e.g.: [c['y'] for b in a for c in b.x] becomes iter(iter(ComplexSearch()).x)['y']
    where `a` is the base instance

    You can call a function on a lookup (or a sequence like above) by
    accessing the attribute ._call__<name>_
        where name is a key in .CALLABLE_FUNCTIONS that maps to the desired function.
        Currently included by default are `min`, `max`, `all`, `any`, `len` and `sum`
    e.g.: ``any(x in g.name for g in book.groups)`` becomes
        ``iter(ComplexSearch().groups).name._call__any_``;
          ``sum(x == b.c for b in a) >= 3`` becomes
        ``(iter(ComplexSearch()).c == x)._call__sum_ >= 3``;
          ``sum(any(a.b in x for a in c) for c in d) in y`` becomes
          ``(iter(c).b in x)._call__any_._call__sum_ in y``
          bad-looking ~ complexity * use_of_functions ** 3

    Comparisons also work if they are only supported by the known (not simulated)
    object **IF** the simulated one
        returns NotImplemented in the comparison function
    """
    CALLABLE_FUNCTIONS = {k: getattr(builtins, k) for k in
                          'min max all any len sum'.split()}

    def __init__(self, return_first_item=True):
        """Initialise self.

        see ComplexSearch.__doc__ for more inforamtion.
        see apply_lookups.__doc__ for information on return_first_item"""
        self.lookups = []
        self.return_first_item = return_first_item

    def __iter__(self):
        self.lookups.append(('__iter__', None))
        return self

    def __next__(self):
        # not really sure what to do here, could also raise TypeError or not include __next__
        raise StopIteration

    #  avoid "attr not found" and "does not support item lookups" warnings
    __getitem__ = _cs_lookup('__getitem__')

    def __getattr__(self, item):
        self.lookups.append(('__getattribute__', item))
        return self

    for op in 'eq ne ge gt le lt contains'.split():
        op = '__%s__' % op
        locals()[op] = _cs_lookup(op)

    def apply_lookups(self, to):
        """Apply the stored lookups to ``to``

        handle __iter__ and _call__<name>_ uses as stated in the class __doc__
        if return_first_item (set in __init__) is True, return only the first item.
            if only one item is expected, this is the way to go"""
        to = [to]
        for k, v in self.lookups:
            m = re.match('_call__(%s)_' % '|'.join(self.CALLABLE_FUNCTIONS.keys()), k)
            if m:
                to = self.CALLABLE_FUNCTIONS[m.group(1)](to if len(to) > 1 else to[0])
            elif k == '__iter__':
                new = []
                for obj in to:
                    for new_obj in iter(obj):
                        new.append(new_obj)
                to = new
            else:
                for i, obj in enumerate(to):
                    new = getattr(obj, k)(v)
                    if new is NotImplemented:
                        new = getattr(v, k)(obj)
                        if new is NotImplemented:
                            raise TypeError('unsupported operation %s between %s and %s'
                                            % (k, obj, v))
                    to[i] = new
        return to[0] if self.return_first_item else to


internal_lc = LoginContext(LoginType.INTERNAL, __name__, 5)
guest_lc = LoginContext(LoginType.GUEST, '', 0)
misc_data = MiscData()

logging.info('core operational')
