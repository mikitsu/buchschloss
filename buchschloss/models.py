"""model definitions"""
import datetime
import json
import sys
import typing

import peewee
from peewee import (SqliteDatabase, CharField, IntegerField, DateField, BooleanField,
                    BlobField, ForeignKeyField, ManyToManyField, AutoField)
from playhouse.fields import PickleField

try:
    from . import config
except ImportError:
    try:
        from buchschloss import config
    except ImportError:
        config = None
if __name__ != '__main__':
    from . import utils
    from . import core

__all__ = [
    'db',
    'Model',
    'Person',
    'Book',
    'Library',
    'Group',
    'Borrow',
    'Member',
    'Misc',
]


T = typing

if config is not None:
    db = SqliteDatabase(config.core.database_name)
else:
    db = SqliteDatabase(input('Unable to locate config module. Please insert DB name -> '))


class JSONField(peewee.TextField):
    """Save JSON objects"""
    def python_value(self, value):
        return None if value is None else json.loads(value)

    def db_value(self, value):
        return None if value is None else json.dumps(value)


class Model(peewee.Model):
    """Base class for all models."""
    DoesNotExist: peewee.DoesNotExist
    str_fields: T.Iterable[peewee.Field]
    pk_name: str = 'id'

    class Meta:
        database = db

    @classmethod
    def select_str_fields(cls):
        """return cls.select(*cls.str_fields)"""
        return cls.select(*cls.str_fields)


class FormattedDateField(DateField):
    def python_value(self, value):
        return utils.FormattedDate.fromdate(super().python_value(value))

    def db_value(self, value):
        if isinstance(value, utils.FormattedDate):
            return value.todate()
        return value


class ScriptPermissionField(IntegerField):
    def python_value(self, value):
        # noinspection PyArgumentList
        return core.ScriptPermissions(value)

    def db_value(self, value):
        return value.value


class Person(Model):
    """Represent a registered Student

    Repräsentiert einen angemeldeten Schüler

    Attributes:
        - id
        - first_name
        - last_name
        - class_
        - max_borrow: max. number of borrowings allowed simultaneously
        - borrows: current borrows
        - borrow_permission: date until borrowing from restricted libraries is allowed
        - libraries: libraries allowed
    """
    id: T.Union[int, IntegerField] = IntegerField(primary_key=True)
    first_name: T.Union[str, CharField] = CharField()
    last_name: T.Union[str, CharField] = CharField()
    class_: T.Union[str, CharField] = CharField()
    max_borrow: T.Union[int, IntegerField] = IntegerField()
    borrow_permission: T.Union[datetime.date, DateField] = FormattedDateField(null=True)
    borrows: peewee.BackrefAccessor
    libraries: T.Union[peewee.ManyToManyQuery, peewee.ManyToManyField]  # libraries as backref

    str_fields = (id, last_name, first_name)

    def __str__(self):
        return utils.get_name('Person[{}]"{}, {}"').format(
            self.id, self.last_name, self.first_name
        )


class Library(Model):
    """Represent the libraries a Person has access to."""
    people: T.Union[peewee.ManyToManyQuery, peewee.ManyToManyField]\
        = ManyToManyField(Person, 'libraries')
    books: T.Union[peewee.ManyToManyQuery, peewee.ManyToManyField]
    name: T.Union[str, CharField] = CharField(primary_key=True)
    pay_required: T.Union[bool, BooleanField] = BooleanField(default=True)

    def __str__(self):
        return utils.get_name('Library[{}]').format(self.name)

    str_fields = (name,)
    pk_name = 'name'


class Book(Model):
    """Represent a Book.

    Attributes (selection):
        - author, isbn, title, series, language, publisher, concerned_people,
            year, medium, genres : general data about the book
        - id [automatically added]: the book ID
        - library: the book's library, determining ho can borrow it
        - groups: the book's groups, for easy library assignment
        - borrow: the book's borrow info
        - is_active [automatically added]: indicate if the book
            is still there (loss, damage, sold...)
    """
    isbn: T.Union[int, IntegerField] = IntegerField()
    author: T.Union[str, CharField] = CharField()
    title: T.Union[str, CharField] = CharField()
    series: T.Union[str, CharField] = CharField(null=True)
    series_number: T.Union[int, IntegerField] = IntegerField(null=True)
    language: T.Union[str, CharField] = CharField()
    publisher: T.Union[str, CharField] = CharField()
    concerned_people: T.Union[str, CharField] = CharField(null=True)
    year: T.Union[int, IntegerField] = IntegerField()
    medium: T.Union[str, CharField] = CharField()

    genres: peewee.BackrefAccessor
    borrow: peewee.BackrefAccessor
    groups: T.Union[peewee.ManyToManyQuery, peewee.ManyToManyField]  # groups as backref
    id: T.Union[int, IntegerField] = AutoField(primary_key=True)
    library: T.Union[Library, ForeignKeyField] = ForeignKeyField(Library, backref='books')
    shelf: T.Union[str, CharField] = CharField()
    is_active: T.Union[bool, BooleanField] = BooleanField(default=True)

    str_fields = (id, title)

    def __str__(self):
        return utils.get_name('Book[{}]"{}"').format(self.id, self.title)


class Genre(Model):
    """A single genre-book pair"""
    book = ForeignKeyField(Book, backref='genres')
    name: T.Union[str, CharField] = CharField()

    pk_name = 'name'  # for search

    class Meta:
        primary_key = peewee.CompositeKey('book', 'name')


class Group(Model):
    """Represent a Group."""
    books: T.Union[peewee.ManyToManyQuery, peewee.ManyToManyField]\
        = ManyToManyField(Book, 'groups')
    name: T.Union[str, CharField] = CharField(primary_key=True)

    def __str__(self):
        return utils.get_name('Group[{}]').format(self.name)

    str_fields = (name,)
    pk_name = 'name'


class Borrow(Model):
    """Represent a borrow action.

    Attributes:
        - person: the Person borrowing
        - book: the Book borrowed
        - is_back: if the Book was returned
        - return_date: date by which the Book must de returned
    """
    id: T.Union[int, IntegerField] = AutoField(primary_key=True)
    person: Person = ForeignKeyField(Person, backref='borrows')
    book: Book = ForeignKeyField(Book, backref='borrow')
    is_back: T.Union[bool, BooleanField] = BooleanField(default=False)
    return_date: T.Union[datetime.date, DateField] = FormattedDateField()

    # keep ID in, needed for further info
    str_fields = (id, person, book, return_date, is_back)

    def __str__(self):
        if self.is_back:
            is_back = utils.get_name('Borrow::is_back')
        else:
            is_back = utils.get_name('Borrow::until_{}').format(self.return_date)
        return '{}: {} {}'.format(self.person, self.book, is_back)


class Member(Model):
    """Represent a Member of the library organisation team"""
    name: T.Union[str, CharField] = CharField(primary_key=True)
    password: T.Union[bytes, BlobField] = BlobField()
    salt: T.Union[bytes, BlobField] = BlobField()
    level: T.Union[int, IntegerField] = IntegerField()

    str_fields = (name, level)
    pk_name = 'name'

    def __str__(self):
        return utils.get_name("Member[{}]({})").format(
            self.name, utils.level_names[self.level])


class Script(Model):
    """Represent a lua script"""
    name: T.Union[str, CharField] = CharField(primary_key=True)
    code: T.Union[str, peewee.TextField] = peewee.TextField()
    setlevel: T.Union[int, IntegerField] = IntegerField(null=True)
    storage: T.Union[dict, JSONField] = JSONField()
    permissions: 'T.Union[core.ScriptPermissions, ScriptPermissionField]' \
        = ScriptPermissionField()

    str_fields = (name, setlevel)
    pk_name = 'name'

    def __str__(self):
        if self.setlevel is None:
            return '{}[{}]'.format(utils.get_name('Script'), self.name)
        else:
            return '{}[{}]({})'.format(
                utils.get_name('Script'), self.name, utils.level_names[self.setlevel]
            )


class Misc(Model):
    """Store singular data (e.g. date for recurring action)

    Usable through the misc_data, instance of MiscData"""
    pk: T.Union[str, CharField] = CharField(primary_key=True)
    data: T.Any = PickleField()

    str_fields = (pk,)
    pk_name = 'pk'


models = Model.__subclasses__() + [Library.people.through_model, Group.books.through_model]
if __name__ == '__main__':
    print('Running this as a script will create tables in the DB '
          'and initialize them with basic data. Proceed? (y/n)')
    if not input().lower().startswith('y'):
        sys.exit()
    db.create_tables(models)
    print('created tables...')
    Misc.create(pk='last_script_invocations', data={})
    Member.create(name='SAdmin',
                  password=b'\xd2Kf\xef#o\xba\xe2\x84i\x896\x13\x99\x80\x94P\xd4'
                           b'\xab\x10n\xeaB\xda\x8c\xbf\xf9\x7f\xd4\xe7\x80\x87',
                  salt=b'{\x7f\xa5\xe7\x07\x1e>\xdf$\xc6\x8cX\xe6\x15J\x8ds\x88'
                       b'\x9d2}9\x98\x9b)x]\x8cc\x8a\xcb\xc8\x8aO\xb3y%g\x9d'
                       b'\x94\xd8\x03m\xec$V\xfa\xcdW3',
                  level=4)
    Library.create(name='main')
    print('Finished. Press return to exit')
    input()
