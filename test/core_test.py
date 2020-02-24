"""Test core"""

import datetime
import pytest

from buchschloss import config

config.core.mapping['database name'] = ':memory:'

from buchschloss import core, models, utils  # noqa


@pytest.fixture
def db():
    """bind the models to the test database"""
    # since in-memory databases clear data when closing,
    # we don't need an explicit drop_tables
    models.db.create_tables(models.models)
    with models.db:
        yield


@pytest.fixture
def with_current_login():
    """work with functions needing the currently logged in members password"""
    def inner(func):
        core.current_login.password = core.pbkdf(b'current', b'')
        def wrapper(*args, **kwargs):  # noqa
            return func(*args, current_password='current', **kwargs)
        return wrapper
    return inner


def create_book(library='main', **options):
    """create a Book with falsey values. The Library can be specified"""
    kwargs = dict(isbn=0, author='', title='', language='', publisher='',
                  year=0, medium='', shelf='', library=library)
    return models.Book.create(**{**kwargs, **options})


def create_person(id_, **options):
    """create a Person with falsey values"""
    kwargs = dict(id=id_, first_name='', last_name='', class_='', max_borrow=0)
    return models.Person.create(**{**kwargs, **options})


def for_levels(func, perm_level):
    """test for correct level testing"""
    for level in range(perm_level):
        core.current_login.level = level
        with pytest.raises(core.BuchSchlossBaseError):
            func()
    core.current_login.level = perm_level
    return func()


def test_auth_required(db):
    """test the @auth_required decorator"""
    core.current_login = models.Member.create(
        name='name', salt=b'', level=0, password=core.pbkdf(b'Pa$$w0rd', b''))

    @core.auth_required
    def test():
        """the initial docstring"""
        return True

    test.__doc__: str
    assert test.__doc__.startswith('the initial docstring')
    assert test.__doc__ != 'the initial docstring'
    assert test(current_password='Pa$$w0rd')
    with pytest.raises(core.BuchSchlossBaseError):
        test(current_password='something else')
    with pytest.raises(TypeError):
        test()


def test_login_logout(db):
    """test login and logout"""
    m = models.Member.create(name='name', level=0, salt=b'',
                             password=core.pbkdf(b'Pa$$w0rd', b''))
    core.current_login = core.dummy_member
    with pytest.raises(core.BuchSchlossBaseError):
        core.login('name', 'wrong password')
    assert core.current_login is core.dummy_member
    core.login('name', 'Pa$$w0rd')
    assert core.current_login == m
    with pytest.raises(core.BuchSchlossBaseError):
        core.login('does not exist', '')
    assert core.current_login == m
    config.core.hash_iterations.insert(0, 1)
    try:
        core.logout()
        assert core.current_login is core.dummy_member
        core.login('name', 'Pa$$w0rd')
        assert models.Member.get_by_id('name').password == core.pbkdf(b'Pa$$w0rd', b'')
    finally:
        config.core.hash_iterations.pop(0)


def test_misc_data(db):
    """test the misc_data accessor for the misc table"""
    models.Misc.create(pk='test_pk_1', data=[1, 2, 3])
    models.Misc.create(pk='test_pk_2', data=0)
    assert core.misc_data.test_pk_1 == [1, 2, 3]
    core.misc_data.test_pk_2 = 'test_string'
    assert models.Misc.get_by_id('test_pk_2').data == 'test_string'
    assert core.misc_data.test_pk_1 == [1, 2, 3]
    core.misc_data.test_pk_1 += [4]
    assert core.misc_data.test_pk_1 == [1, 2, 3, 4]
    with pytest.raises(AttributeError):
        core.misc_data.does_not_exist
    with pytest.raises(AttributeError):
        core.misc_data.also_doesnt_exist = None


def test_person_new(db):
    """test Person.new"""
    for level in range(3):
        core.current_login.level = level
        with pytest.raises(core.BuchSchlossBaseError):
            core.Person.new(123, 'first', 'last', 'cls')
    core.current_login.level = 3
    core.Person.new(123, 'first', 'last', 'cls')
    p = models.Person.get_by_id(123)
    assert p.id == 123
    assert p.first_name == 'first'
    assert p.last_name == 'last'
    assert p.max_borrow == 3
    assert len(p.libraries) == 0
    assert p.pay_date is None
    with pytest.raises(core.BuchSchlossBaseError):
        core.Person.new(123, 'first', 'last', 'cls')
    with pytest.raises(core.BuchSchlossBaseError):
        core.Person.new(124, 'first', 'last', 'cls', 5, pay=True)
    core.current_login.level = 4
    old_today = datetime.date.today()  # in case this is run around midnight...
    core.Person.new(124, 'first', 'last', 'cls', 5, pay=True)
    p = models.Person.get_by_id(124)
    assert p.id == 124
    assert p.max_borrow == 5
    assert p.pay_date in (datetime.date.today(), old_today)
    core.Person.new(125, 'first', 'last', 'cls', pay_date=datetime.date(1956, 1, 31))
    p = models.Person.get_by_id(125)
    assert p.id == 125
    assert p.pay_date == datetime.date(1956, 1, 31)
    models.Library.create(name='main')
    core.Person.new(126, 'first', 'last', 'cls')
    p = models.Person.get_by_id(126)
    assert p.id == 126
    assert list(p.libraries) == [models.Library.get_by_id('main')]


def test_person_edit(db):
    """test Person.edit"""
    models.Person.create(id=123, first_name='first', last_name='last', class_='cls',
                         max_borrow=3, pay_date=datetime.date(1956, 1, 31))
    for level in range(3):
        core.current_login.level = level
        with pytest.raises(core.BuchSchlossBaseError):
            core.Person.edit(123)
    core.current_login.level = 4
    core.Person.edit(123, first_name='other_value')
    assert models.Person.get_by_id(123).first_name == 'other_value'
    core.Person.edit(123, last_name='value_for_last', pay_date=None)
    p = models.Person.get_by_id(123)
    assert p.last_name == 'value_for_last'
    assert p.pay_date is None
    old_today = datetime.date.today()
    core.Person.edit(123, pay=True)
    assert models.Person.get_by_id(123).pay_date in (datetime.date.today(), old_today)
    models.Library.create(name='lib_1')
    models.Library.create(name='lib_2')
    e = core.Person.edit(123, libraries=('lib_1', 'lib_does_not_exist'))
    assert e
    assert list(models.Person.get_by_id(123).libraries) == [models.Library.get_by_id('lib_1')]
    with pytest.raises(core.BuchSchlossBaseError):
        core.Person.edit(124)
    with pytest.raises(TypeError):
        core.Person.edit(123, no_option=123)
    with pytest.raises(TypeError):
        core.Person.edit(123, id=124)


def test_person_view_str(db):
    """test Person.view_str"""
    p = models.Person.create(id=123, first_name='first', last_name='last', class_='cls',
                             max_borrow=3, pay_date=datetime.date(1956, 1, 31))
    core.current_login.level = 0
    with pytest.raises(core.BuchSchlossBaseError):
        core.Person.view_str(123)
    core.current_login.level = 1
    with pytest.raises(core.BuchSchlossBaseError):
        core.Person.view_str(12345)
    assert core.Person.view_str(123) == {
        'id': '123',
        'first_name': 'first',
        'last_name': 'last',
        'class_': 'cls',
        'max_borrow': '3',
        'pay_date': str(utils.FormattedDate.fromdate(datetime.date(1956, 1, 31))),
        'borrows': (),
        'borrow_book_ids': [],
        'libraries': '',
        '__str__': str(models.Person.get_by_id(123)),
    }
    p.libraries.add(models.Library.create(name='main'))
    assert core.Person.view_str(123)['libraries'] == 'main'
    create_book()
    models.Borrow.create(person=123, book=1, return_date=datetime.date(1956, 1, 31))
    info = core.Person.view_str(123)
    assert info['borrows'] == (str(models.Borrow.get_by_id(1)),)
    assert info['borrow_book_ids'] == [1]
    p.libraries.add(models.Library.create(name='testlib'))
    info = core.Person.view_str(123)
    assert info['libraries'] in ('main;testlib', 'testlib;main')
    create_book()
    models.Borrow.create(person=123, book=2, return_date=datetime.date(1956, 1, 31))
    info = core.Person.view_str(123)
    assert info['borrows'] in (
        (str(models.Borrow.get_by_id(1)), str(models.Borrow.get_by_id(2))),
        (str(models.Borrow.get_by_id(2)), str(models.Borrow.get_by_id(1))),
    )
    assert info['borrow_book_ids'] in ([1, 2], [2, 1])

# since view_repr and view_attr are implemented in ActionNamespace,
# I hope we only need one test each. Person is chosen bc. you need level 1


def test_person_view_repr(db):
    """test Person.view_repr"""
    p = create_person(123)
    assert str(p) == for_levels(lambda: core.Person.view_repr(123), 1)
    with pytest.raises(core.BuchSchlossBaseError):
        core.Person.view_repr(124)


def test_person_view_attr(db):
    """test Person.view_attr"""
    create_person(123)
    assert for_levels(lambda: core.Person.view_attr(123, 'id'), 1) == 123


def test_book_new(db):
    """test Book.new"""
    models.Library.create(name='main')
    b_id = for_levels(lambda: core.Book.new(
        isbn=123, year=456, author='author', title='title', language='lang',
        publisher='publisher', medium='medium', shelf='A1'), 2)
    assert b_id == 1
    b = models.Book.get_by_id(b_id)
    assert b.isbn == 123
    assert b.year == 456
    assert b.author == 'author'
    assert b.title == 'title'
    assert b.language == 'lang'
    assert b.publisher == 'publisher'
    assert b.medium == 'medium'
    assert b.shelf == 'A1'
    assert b.library.name == 'main'
    assert tuple(b.groups) == ()
    with pytest.raises(core.BuchSchlossBaseError):
        core.Book.new(isbn=123, year=456, author='author', title='title', language='lang',
                      publisher='publisher', medium='medium', shelf='A1',
                      library='does_not_exist')
    models.Library.create(name='other_lib')
    b_id = core.Book.new(isbn=123, year=456, author='author', title='title', language='lang',
                         publisher='publisher', medium='medium', shelf='A1',
                         library='other_lib')
    assert b_id == 2
    assert models.Book.get_by_id(b_id).library.name == 'other_lib'
    b_id = core.Book.new(isbn=123, year=456, author='author', title='title', language='lang',
                         publisher='publisher', medium='medium', shelf='A1',
                         groups=['grp0'])
    assert b_id == 3
    assert list(models.Book.get_by_id(b_id).groups) == [models.Group.get_by_id('grp0')]
    b_id = core.Book.new(isbn=123, year=456, author='author', title='title', language='lang',
                         publisher='publisher', medium='medium', shelf='A1',
                         groups=['grp0', 'grp1'])
    assert b_id == 4
    assert set(models.Book.get_by_id(b_id).groups) == {
        models.Group.get_by_id('grp0'), models.Group.get_by_id('grp1')}


def test_book_edit(db):
    """test Book.edit"""
    models.Library.create(name='main')
    models.Group.create(name='group-1')
    models.Group.create(name='group-2')
    create_book()
    create_book()
    for level in range(2):
        core.current_login.level = level
        with pytest.raises(core.BuchSchlossBaseError):
            core.Book.edit(1, isbn=1)
    core.current_login.level = 2
    assert not core.Book.edit(1, isbn=1)
    assert models.Book.get_by_id(1).isbn == 1
    assert models.Book.get_by_id(2).isbn == 0
    assert not core.Book.edit(1, author='author', shelf='shl')
    assert models.Book.get_by_id(1).author == 'author'
    assert models.Book.get_by_id(1).shelf == 'shl'
    assert models.Book.get_by_id(2).author == ''
    assert models.Book.get_by_id(2).shelf == ''
    models.Library.create(name='lib')
    assert not core.Book.edit(1, library='lib')
    assert models.Book.get_by_id(1).library.name == 'lib'
    assert models.Book.get_by_id(2).library.name == 'main'
    with pytest.raises(core.BuchSchlossBaseError):
        core.Book.edit(1, library='does_not_exist')
    assert not core.Book.edit(1, groups=['group-1'])
    assert set(g.name for g in models.Book.get_by_id(1).groups) == {'group-1'}
    e = core.Book.edit(1, groups=('group-2', 'does not exist'))
    assert e == {utils.get_name('no_Group_with_id_{}').format('does not exist')}
    assert set(g.name for g in models.Book.get_by_id(1).groups) == {'group-2'}
    assert models.Book.get_by_id(1).library.name == 'lib'
    assert not core.Book.edit(1, medium='med')
    assert not core.Book.edit(1, year=123)
    assert models.Book.get_by_id(1).medium == 'med'
    assert models.Book.get_by_id(1).year == 123
    assert models.Book.get_by_id(2).medium == ''
    assert models.Book.get_by_id(2).year == 0


def test_book_view_str(db):
    """test Book.view_str"""
    for n in range(2):
        models.Library.create(name='lib{}'.format(n))
        models.Group.create(name='grp{}'.format(n))
    models.Book.create(isbn=123, author='author', title='title', language='lang',
                       publisher='publ', year=456, medium='rare', library='lib0',
                       shelf='A5')
    b = models.Book.get_by_id(1)
    core.current_login.level = 0
    assert core.Book.view_str(1) == {
        'id': '1',
        'isbn': '123',
        'author': 'author',
        'title': 'title',
        'language': 'lang',
        'publisher': 'publ',
        'year': '456',
        'medium': 'rare',
        'series': '',
        'series_number': '',
        'concerned_people': '',
        'genres': '',
        'shelf': 'A5',
        'library': 'lib0',
        'groups': '',
        'status': utils.get_name('available'),
        'return_date': '-----',
        'borrowed_by': '-----',
        'borrowed_by_id': None,
        '__str__': str(b),
    }
    b.library = models.Library.get_by_id('lib1')
    b.save()
    assert core.Book.view_str(1)['library'] == 'lib1'
    b.groups.add('grp0')
    assert core.Book.view_str(1)['groups'] == 'grp0'
    b.groups.add('grp1')
    assert core.Book.view_str(1)['groups'] in ('grp0;grp1', 'grp1;grp0')
    models.Person.create(id=123, first_name='first', last_name='last',
                         class_='cls', max_borrow=3)
    borrow = models.Borrow.create(book=1, person=123, return_date=datetime.date(1956, 1, 31))
    data = core.Book.view_str(1)
    assert data['status'] == utils.get_name('borrowed')
    assert data['return_date'] == datetime.date(1956, 1, 31).strftime(config.core.date_format)
    assert data['borrowed_by'] == str(models.Person.get_by_id(123))
    assert data['borrowed_by_id'] == 123
    borrow.is_back = True
    borrow.save()
    assert core.Book.view_str(1)['status'] == utils.get_name('available')
    b.is_active = False
    b.save()
    assert core.Book.view_str(1)['status'] == utils.get_name('inactive')


def test_library_new(db):
    """test Library.new"""
    models.Library.create(name='main')
    create_book()
    create_book()
    models.Person.create(id=123, first_name='', last_name='', class_='', max_borrow=0)
    models.Person.create(id=456, first_name='', last_name='', class_='', max_borrow=0)
    for level in range(3):
        core.current_login.level = level
        with pytest.raises(core.BuchSchlossBaseError):
            core.Library.new('testlib')
    core.current_login.level = 3
    core.Library.new('testlib')
    assert models.Library.get_or_none(name='testlib')
    with pytest.raises(core.BuchSchlossBaseError):
        core.Library.new('testlib')
    assert models.Library.get_by_id('testlib').pay_required
    core.Library.new('test-1', books=[1], people=[123])
    assert models.Book.get_by_id(1).library.name == 'test-1'
    assert (tuple(models.Person.get_by_id(123).libraries)
            == (models.Library.get_by_id('test-1'),))
    core.Library.new('test-2', books=(1, 2), people=[123, 456])
    assert models.Book.get_by_id(1).library.name == 'test-2'
    assert models.Book.get_by_id(1).library.name == 'test-2'
    assert (set(models.Person.get_by_id(123).libraries)
            == {models.Library.get_by_id('test-1'), models.Library.get_by_id('test-2')})
    assert (tuple(models.Person.get_by_id(456).libraries)
            == (models.Library.get_by_id('test-2'),))


def test_library_edit(db):
    """test Library.edit"""
    models.Library.create(name='main')
    models.Library.create(name='testlib')
    models.Library.create(name='test-2')
    create_book()
    create_book()
    create_book()
    create_book('test-2')
    create_person(123)
    create_person(124)
    for level in range(3):
        core.current_login.level = level
        with pytest.raises(core.BuchSchlossBaseError):
            core.Library.edit(core.LibraryGroupAction.NONE, 'testlib')
    core.current_login.level = 3
    core.Library.edit(core.LibraryGroupAction.NONE, 'testlib')
    with pytest.raises(core.BuchSchlossBaseError):
        core.Library.edit(core.LibraryGroupAction.NONE, 'does not exist')
    core.Library.edit(core.LibraryGroupAction.ADD, 'testlib', books=[1])
    assert models.Book.get_by_id(1).library.name == 'testlib'
    core.Library.edit(core.LibraryGroupAction.ADD, 'testlib', books=[2, 3], people=[123])
    assert all(models.Book.get_by_id(n).library.name == 'testlib' for n in range(1, 4))
    assert [p.id for p in models.Library.get_by_id('testlib').people] == [123]
    core.Library.edit(core.LibraryGroupAction.REMOVE, 'testlib', books=[3, 4], people=[123])
    assert models.Book.get_by_id(4).library.name == 'test-2'
    assert models.Book.get_by_id(3).library.name == 'main'
    assert not models.Person.get_by_id(123).libraries
    core.Library.edit(core.LibraryGroupAction.DELETE, 'testlib')
    assert not models.Library.get_by_id('testlib').people
    assert not models.Library.get_by_id('testlib').books
    core.Library.edit(core.LibraryGroupAction.NONE, 'testlib', pay_required=True)
    assert models.Library.get_by_id('testlib').pay_required
    core.Library.edit(core.LibraryGroupAction.NONE, 'testlib', pay_required=None)
    assert models.Library.get_by_id('testlib').pay_required
    core.Library.edit(core.LibraryGroupAction.NONE, 'testlib', pay_required=False)
    assert not models.Library.get_by_id('testlib').pay_required


def test_library_view_str(db):
    """test Library.view_str"""
    models.Library.create(name='main')
    lib = models.Library.create(name='lib')
    b_1 = create_book()
    b_2 = create_book()
    p_1 = create_person(123)
    p_2 = create_person(124)
    core.current_login.level = 0
    with pytest.raises(core.BuchSchlossBaseError):
        core.Library.view_str('does not exist')
    assert core.Library.view_str('lib') == {
        '__str__': str(lib),
        'name': 'lib',
        'people': '',
        'books': '',
    }
    lib.people.add(p_1)
    assert core.Library.view_str('lib')['people'] == '123'
    lib.people.add(p_2)
    assert set(core.Library.view_str('lib')['people'].split(';')) == {'123', '124'}
    b_1.library = lib
    b_1.save()
    assert core.Library.view_str('lib')['books'] == '1'
    b_2.library = lib
    b_2.save()
    assert set(core.Library.view_str('lib')['books'].split(';')) == {'1', '2'}


def test_group_new(db):
    """test Group.new"""
    models.Library.create(name='main')
    create_book()
    create_book()
    for level in range(3):
        core.current_login.level = level
        with pytest.raises(core.BuchSchlossBaseError):
            core.Group.new('test-grp')
    core.current_login.level = 3
    core.Group.new('test-grp')
    assert not models.Group.get_by_id('test-grp').books
    with pytest.raises(core.BuchSchlossBaseError):
        core.Group.new('test-grp')
    core.Group.new('test-2', [1, 2])
    assert list(g.name for g in models.Book.get_by_id(1).groups) == ['test-2']
    assert list(g.name for g in models.Book.get_by_id(2).groups) == ['test-2']
    core.Group.new('test-3', [2])
    assert list(g.name for g in models.Book.get_by_id(1).groups) == ['test-2']
    assert set(g.name for g in models.Book.get_by_id(2).groups) == {'test-2', 'test-3'}
    core.Group.new('test-4', [12345])


def test_group_edit(db):
    """test Group.edit"""
    models.Library.create(name='main')
    models.Group.create(name='group-1')
    models.Group.create(name='group-2')
    create_book()
    create_book()
    for level in range(3):
        core.current_login.level = level
        with pytest.raises(core.BuchSchlossBaseError):
            core.Group.edit(core.LibraryGroupAction.NONE, 'group-1', ())
    core.current_login.level = 3
    core.Group.edit(core.LibraryGroupAction.NONE, 'group-1', ())
    with pytest.raises(core.BuchSchlossBaseError):
        core.Group.edit(core.LibraryGroupAction.NONE, 'does not exist', ())
    core.Group.edit(core.LibraryGroupAction.ADD, 'group-1', [1])
    assert set(g.name for g in models.Book.get_by_id(1).groups) == {'group-1'}
    assert not models.Book.get_by_id(2).groups
    assert 'group-2' not in models.Book.get_by_id(1).groups + models.Book.get_by_id(2).groups
    core.Group.edit(core.LibraryGroupAction.REMOVE, 'group-1', iter([1, 2, 3]))
    core.Group.edit(core.LibraryGroupAction.ADD, 'group-1', [2])
    assert not models.Book.get_by_id(1).groups
    assert set(g.name for g in models.Book.get_by_id(2).groups) == {'group-1'}
    assert 'group-2' not in models.Book.get_by_id(1).groups + models.Book.get_by_id(2).groups
    core.Group.edit(core.LibraryGroupAction.DELETE, 'group-1', ())
    assert not models.Book.get_by_id(1).groups
    assert not models.Book.get_by_id(2).groups
    assert set() == {'group-1', 'group-2'} & set(models.Book.get_by_id(1).groups
                                                 + models.Book.get_by_id(2).groups)


def test_group_activate(db):
    """test Group.activate"""
    models.Library.create(name='main')
    models.Library.create(name='lib-1')
    models.Library.create(name='lib-2')
    models.Group.create(name='group-1')
    models.Group.create(name='group-2')
    books = [create_book(),
             create_book(),
             create_book(),
             ]
    for level in range(3):
        core.current_login.level = level
        with pytest.raises(core.BuchSchlossBaseError):
            core.Group.activate('group-1')
    core.current_login.level = 3
    assert not core.Group.activate('group-1')
    with pytest.raises(core.BuchSchlossBaseError):
        core.Group.activate('does not exist')
    books[0].groups.add('group-1')
    books[1].groups.add('group-2')
    assert not core.Group.activate('group-1', dest='lib-1')
    assert models.Book.get_by_id(1).library.name == 'lib-1'
    assert models.Book.get_by_id(2).library.name == 'main'
    b = models.Book.get_by_id(3)
    assert b.library.name == 'main'
    b.groups.add('group-1')
    b.library = models.Library.get_by_id('lib-2')
    b.save()
    assert not core.Group.activate('group-1', ['lib-1'])
    assert models.Book.get_by_id(1).library.name == 'main'
    assert models.Book.get_by_id(3).library.name == 'lib-2'
    with pytest.raises(core.BuchSchlossBaseError):
        core.Group.activate('group-1', ['does not exist', 'lib-2'])
    with pytest.raises(core.BuchSchlossBaseError):
        core.Group.activate('group-1', ['lib-1'], 'does not exist')


def test_group_view_str(db):
    """test Group.view_str"""
    models.Library.create(name='main')
    models.Group.create(name='group-1')
    create_book()
    create_book()
    assert core.Group.view_str('group-1') == {
        '__str__': str(models.Group.get_by_id('group-1')),
        'name': 'group-1',
        'books': ''
    }
    with pytest.raises(core.BuchSchlossBaseError):
        core.Group.view_str('does not exist')
    models.Group.get_by_id('group-1').books = [1]
    assert core.Group.view_str('group-1')['books'] == '1'
    models.Group.get_by_id('group-1').books.add(2)
    assert core.Group.view_str('group-1')['books'] in ('1;2', '2;1')
    models.Group.get_by_id('group-1').books.remove(1)
    assert core.Group.view_str('group-1')['books'] == '2'


def test_member_new(db, with_current_login):
    """test member.new"""
    member_new = with_current_login(core.Member.new)
    for_levels(lambda: member_new('name', 'Pa$$w0rd', 3), 4)
    m = models.Member.get_by_id('name')
    assert m.level == 3
    assert core.pbkdf(b'Pa$$w0rd', m.salt) == m.password
    with pytest.raises(core.BuchSchlossBaseError):
        member_new('name', 'other Pa$$w0rd', 1)


def test_member_edit(db, with_current_login):
    """test Member.edit"""
    member_edit = with_current_login(core.Member.edit)
    models.Member.create(name='name', level=0, salt=b'', password=b'')
    assert models.Member.get_by_id('name').level == 0
    for_levels(lambda: member_edit('name', level=4), 4)
    assert models.Member.get_by_id('name').level == 4
    for kw in ({'name': 'new'}, {'salt': b''}, {'password': b''}):
        with pytest.raises(TypeError):
            member_edit('name', **kw)
    with pytest.raises(core.BuchSchlossBaseError):
        member_edit('does not exist')


def test_member_change_password(db, with_current_login):
    """test Member.change_password"""
    change_password = with_current_login(core.Member.change_password)
    models.Member.create(name='name', level=0, salt=b'', password=b'')
    core.current_login.name = ''
    for_levels(lambda: change_password('name', 'new'), 4)
    assert core.authenticate(models.Member.get_by_id('name'), 'new')
    core.current_login.name = 'name'
    core.current_login.level = 0
    change_password('name', 'other')
    assert core.authenticate(models.Member.get_by_id('name'), 'other')


def test_member_view_str(db):
    """test Member.view_str"""
    models.Member.create(name='name', level=0, salt=b'', password=b'')
    core.current_login.level = 0
    assert core.Member.view_str('name') == {
        '__str__': str(models.Member.get_by_id('name')),
        'name': 'name',
        'level': utils.get_level(0),
    }


def test_borrow_new(db):
    """test Borrow.new"""
    def restitute(borrow_id):
        b = models.Borrow.get_by_id(borrow_id)
        b.is_back = True
        b.save()

    models.Misc.create(pk='latest_borrowers', data=[])
    models.Library.create(name='main')
    test_lib = models.Library.create(name='test-lib')
    models.Library.create(name='no-pay', pay_required=False)
    create_book()
    create_book()
    create_book('test-lib')
    create_book('no-pay')
    p = create_person(123, max_borrow=1,
                      pay_date=(datetime.date.today()
                                - datetime.timedelta(weeks=52, days=-1)),
                      libraries=['main', 'no-pay'])
    # follows config settings
    for i in range(5):
        core.current_login.level = i
        with pytest.raises(core.BuchSchlossBaseError):
            core.Borrow.new(1, 123, config.core.borrow_time_limit[i] + 1)
    weeks = config.core.borrow_time_limit[i]
    core.Borrow.new(1, 123, weeks)
    # correct data
    assert len(models.Borrow.select()) == 1
    assert models.Misc.get_by_id('latest_borrowers').data == [123]
    b = models.Borrow.get_by_id(1)
    assert b.person.id == 123
    assert b.book.id == 1
    assert b.return_date == datetime.date.today() + datetime.timedelta(weeks=weeks)
    # respects Person.max_borrow
    with pytest.raises(core.BuchSchlossBaseError):
        core.Borrow.new(2, 123, weeks)
    # respects libraries
    restitute(1)
    with pytest.raises(core.BuchSchlossBaseError):
        core.Borrow.new(3, 123, weeks)
    p.libraries.add(test_lib)
    core.Borrow.new(3, 123, weeks)
    restitute(2)
    # respects pay_required and accepts keyword arguments
    p.pay_date = datetime.date.today() - datetime.timedelta(weeks=52, days=1)
    p.save()
    with pytest.raises(core.BuchSchlossBaseError):
        core.Borrow.new(person=123, book=2, weeks=weeks)
    core.Borrow.new(person=123, book=4, weeks=weeks)


def test_search(db):
    """test searches"""
    models.Library.create(name='main')
    book_1 = create_book(author='author name')
    book_2 = create_book(author='author 2', year=2000)
    person = create_person(123, class_='cls', libraries=['main'])
    assert tuple(core.Book.search(('author', 'eq', 'author name'))) == (book_1,)
    assert set(core.Book.search(())) == {book_1, book_2}
    assert (tuple(core.Book.search((('author', 'ne', 'author name'), 'or', ())))
            == (book_2,))
    assert (tuple(core.Book.search((('author', 'contains', 'name'), 'and', ())))
            == (book_1,))
    assert (tuple(core.Book.search((('library.people.class_', 'eq', 'cls'),
                                    'and', ('id', 'lt', 2))))
            == (book_1,))
    assert (tuple(core.Person.search(('libraries.books.author', 'contains', '2')))
            == (person,))
    assert (set(core.Book.search(('library.people.libraries.books.year', 'gt', 1990)))
            == {book_1, book_2})
    assert tuple(core.Person.search(('libraries', 'eq', 'main'))) == (person,)
    assert (set(core.Book.search(('library.people.libraries', 'eq', 'main')))
            == {book_2, book_1})
    assert tuple(core.Book.search(('year', 'ge', 2001))) == ()
    assert tuple(core.Book.search(('year', 'ge', 2000))) == (book_2,)
