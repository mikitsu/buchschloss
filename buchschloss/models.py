import datetime
import sys
import typing

import peewee
from peewee import SqliteDatabase, CharField, IntegerField, DateField, BooleanField, BlobField, \
    ForeignKeyField, ManyToManyField, AutoField
from playhouse.fields import PickleField

try:
    from . import config
except ImportError:
    try:
        import buchschloss.config
    except ImportError:
        try:
            from buchschloss import config
        except ImportError:
            config = None
try:
    from . import utils
except ImportError:
    if __name__ != '__main__':
        raise

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
    db = SqliteDatabase('.'.join(config.DATABASE_NAME))
else:
    db = SqliteDatabase(input('Unable to locate config module. Please insert DB name -> '))


class Model(peewee.Model):
    """Base class for all models."""
    DoesNotExist: peewee.DoesNotExist
    repr_data: T.Mapping[str, str]
    str_fields: T.Iterable[peewee.Field]
    pk_type: T.Type
    pk_name: str = 'id'

    class Meta:
        database = db

    def __init_subclass__(cls):
        if hasattr(cls, 'pk_type'):
            return
        for k, v in vars(cls).items():
            if isinstance(v, peewee.Field) and v.primary_key:
                cls.pk_type = typing.get_type_hints(cls)[k]
                break


class FormatedDateField(DateField):
    def python_value(self, value):
        return utils.FormatedDate.fromdate(super().python_value(value))

    def db_value(self, value):
        if isinstance(value, utils.FormatedDate):
            return value.todate()
        return value


class Person(Model):
    """Represent a registered Student

    Repräsentiert einen angemeldeten Schüler

    Attributes:
        - id: ID Schülerausweisnummer
        - first_name: Vorname
        - last_name: Nachname
        - class_: Klasse
        - max_borrow: max. no. of borrowings allowed simultaneously; maximale Ausleihanzahl
        - borrows: current borrows; derzeitige Ausleihen
        - libraries: libraries allowed; erlaubte Bibliotheken
    """
    id: int = IntegerField(primary_key=True)
    first_name: str = CharField()
    last_name: str = CharField()
    class_: str = CharField()
    max_borrow: int = IntegerField()
    pay_date: datetime.date = FormatedDateField(null=True)
    # libraries as backref
    # borrows as backref

    repr_data = {
        'ein': 'eine',
        'name': 'Person',
        'id': 'Schülerausweisnummer',
    }
    str_fields = (id, last_name, first_name)
    pk_type = int

    def __str__(self):
        return '%s[%i]"%s, %s"' % (utils.get_name(type(self).__name__.lower()),
                                   self.id, self.last_name, self.first_name)


class Library(Model):
    """Represent the libraries a Person has access to.

    Speichert die Bibliotheken, zu denen eine Person Zugang hat."""
    person: T.Iterable[Person] = ManyToManyField(Person, 'libraries')
    name: str = CharField(primary_key=True)
    pay_required: bool = BooleanField(default=True)

    def __str__(self):
        return self.name

    repr_data = {
        'ein': 'eine',
        'name': 'Bibliothek',
        'id': 'Name'
    }
    str_fields = (name,)
    pk_name = 'name'


class Book(Model):
    """Represent a Book.

    Repräsentiert ein Buch.
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
    isbn: int = IntegerField()
    author: str = CharField()
    title: str = CharField()
    series: str = CharField(null=True)
    language: str = CharField()
    publisher: str = CharField()
    concerned_people: str = CharField(null=True)
    year: int = IntegerField()
    medium: str = CharField()
    genres: str = CharField(null=True)

    # groups as backref
    id: int = AutoField(primary_key=True)
    library: Library = ForeignKeyField(Library)
    shelf: str = CharField()
    is_active: bool = BooleanField(default=True)

    @property
    def borrow(self):
        return Borrow.get_or_none(Borrow.book == self, is_back=False)

    repr_data = {
        'ein': 'ein',
        'name': 'Buch',
        'id': 'ID',
    }
    str_fields = (id, title)

    def __str__(self):
        return '%s[%i]"%s"' % (utils.get_name(type(self).__name__.lower()),
                               self.id, self.title)


class Group(Model):
    """Represent a Group.

    Repräsentiert eine Gruppe"""
    book: T.Iterable[Book] = ManyToManyField(Book, 'groups')
    name: str = CharField(primary_key=True)

    def __str__(self):
        return self.name

    repr_data = {
        'ein': 'eine',
        'name': 'Gruppe',
        'id': 'Name'
    }
    str_fields = (name,)
    pk_name = 'name'


class Borrow(Model):
    """Represent a borrow action.

    Repräsentiert einen Entleihvorgang.

    Attributes:
        - person: the Person borrowing; die ausleihende Person
        - book: the Book borrowed; das ausgeliehene Buch
        - is_back: if the Book was returned; ob das Buch bereits zurckgegeben wurde
        - return_date: date by which the Book must de returned; Datum bis zu dem das Buch zurckgegeben sein muss
    """
    id: int = AutoField(primary_key=True)
    person: Person = ForeignKeyField(Person, backref='borrows')
    book: Book = ForeignKeyField(Book)
    is_back: bool = BooleanField(default=False)
    return_date: datetime.date = FormatedDateField()

    repr_data = {
        'ein': 'ein',
        'name': 'Ausleihvorgang',
        'id': 'ID',
    }
    str_fields = (id, person, book, return_date, is_back)  # keep ID in, needed for further info

    def __str__(self):
        return '{}: {} {}'.format(self.person, self.book, utils.get_name('is_back')
                                  if self.is_back else
                                  utils.get_name('until_{}'.format(self.return_date)))


class Member(Model):
    """Represent a Member of the Rund-ums-Lesen-AG

    Repräsentiert ein Mitglied der Rund-ums-Lesen-AG,
    d.h. eine Person, die Ausleihen, Rückgaben und ggf. Verwaltungsaufgeben durchführen kann."""
    name: str = CharField(primary_key=True)
    password: bytes = BlobField()
    salt: bytes = BlobField()
    level: int = IntegerField()

    repr_data = {
        'ein': 'ein',
        'name': 'Mitglied',
        'id': 'Name'
    }
    str_fields = (name, level)
    pk_name = 'name'

    def __str__(self):
        return "Mitglied[{}]({})".format(self.name, config.MEMBER_LEVELS[self.level])


class Misc(Model):
    """Store singular data (e.g. date for recurring action)

    Usable through the misc_data, instance of MiscData"""
    pk: int = CharField(primary_key=True)
    data: object = PickleField()

    repr_data = {
        'ein': 'ein',
        'name': 'Interna',
        'id': 'Name'
    }
    str_fields = (pk,)
    pk_name = 'pk'


if __name__ == '__main__':
    print('Running this as a script will create tables in the DB '
          'and initialize them with basic data. Proceed? (y/n)')
    if not input().lower().startswith('y'):
        sys.exit()
    db.create_tables(Model.__subclasses__())
    # noinspection PyUnresolvedReferences
    db.create_tables([Library.person.through_model, Group.book.through_model])
    print('created tables...')
    Misc.create(pk='check_date', data=datetime.datetime.now())
    Misc.create(pk='latest_borrowers', data=[])
    Member.create(name='SAdmin', password=b'\xd2Kf\xef#o\xba\xe2\x84i\x896\x13\x99\x80\x94P\xd4\xab\x10n\xeaB\xda'
                                          b'\x8c\xbf\xf9\x7f\xd4\xe7\x80\x87',
                  salt=b'{\x7f\xa5\xe7\x07\x1e>\xdf$\xc6\x8cX\xe6\x15J\x8ds\x88\x9d2}9\x98\x9b)x]\x8cc\x8a\xcb'
                       b'\xc8\x8aO\xb3y%g\x9d\x94\xd8\x03m\xec$V\xfa\xcdW3',
                  level=4)
    Library.create(name='main')
    print('Finished. Press return to exit')
    input()
