"""Test core"""

import datetime
from functools import partial

import pytest

from buchschloss import config, core, models, utils


def create_book(library='main', **options):
    """create a Book with falsey values. The Library can be specified"""
    kwargs = dict(isbn=0, author='', title='', language='', publisher='',
                  year=0, medium='', shelf='', library=library)
    return models.Book.create(**{**kwargs, **options})


def create_person(id_, **options):
    """create a Person with falsey values"""
    kwargs = dict(id=id_, first_name='', last_name='', class_='', max_borrow=0)
    return models.Person.create(**{**kwargs, **options})


def for_levels(func, perm_level, assert_func=lambda x: True):
    """test for correct level testing"""
    ctxt = core.internal_unpriv_lc
    for level in range(perm_level):
        ctxt.level = level
        with pytest.raises(core.BuchSchlossBaseError):
            func(login_context=ctxt)
    ctxt.level = perm_level
    assert assert_func(func(login_context=ctxt))
    return ctxt


def test_auth_required(db):
    """test the @auth_required decorator"""
    models.Member.create(
        name='name', salt=b'', level=0, password=core.pbkdf(b'Pa$$w0rd', b''))
    ctxt_member = core.LoginContext(core.LoginType.MEMBER, 0, name='name')
    ctxt_internal = core.internal_unpriv_lc

    @core.auth_required
    def test(login_context):
        """the initial docstring"""
        return True

    assert test.__doc__.startswith('the initial docstring')
    assert test.__doc__ != 'the initial docstring'
    assert test(login_context=ctxt_member, current_password='Pa$$w0rd')
    with pytest.raises(core.BuchSchlossBaseError):
        test(login_context=ctxt_member, current_password='something else')
    with pytest.raises(TypeError):
        test(login_context=ctxt_member)
    with pytest.raises(core.BuchSchlossBaseError):
        test(login_context=core.guest_lc, current_password='')
    with pytest.raises(core.BuchSchlossBaseError):
        test(login_context=core.guest_lc)
    with pytest.raises(core.BuchSchlossBaseError):
        test(login_context=ctxt_internal)
    ctxt_internal.level = 1
    assert test(login_context=ctxt_internal)


def test_login_logout(db):
    """test login and logout"""
    models.Member.create(name='name', level=0, salt=b'',
                         password=core.pbkdf(b'Pa$$w0rd', b''))
    with pytest.raises(core.BuchSchlossBaseError):
        core.login('name', 'wrong password')
    ctxt = core.login('name', 'Pa$$w0rd')
    assert ctxt.name == 'name'
    with pytest.raises(core.BuchSchlossBaseError):
        core.login('does not exist', '')
    config.core.hash_iterations.insert(0, 1)
    try:
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


def test_data_ns():
    FLAG = object()
    class DataA(core.Dummy): pk_name = 'a'
    class DataB(core.Dummy): pass

    def validate_datab(data_val, x_val):
        assert isinstance(data_val, core.DataNamespace)
        assert data_val._handlers == {'allow': 'ad'}
        assert data_val._login_context is FLAG
        assert data_val._data.x == x_val

    core.DataNamespace.data_handling[DataA] = {
        'allow': 'ab',
        'wrap_iter': {'i': DataB},
        'wrap_dns': {'d': DataB, 'n': DataB},
    }
    core.DataNamespace.data_handling[DataB] = {'allow': 'ad'}
    data = core.DataNamespace(
        DataA,
        DataA(a=1, b=[1, 2, 3], d=DataB(x=0), i=[DataB(x=1), DataB(x=2)], n=None),
        login_context=FLAG,
    )
    assert data.a == 1
    assert data.b == [1, 2, 3]
    validate_datab(data.d, 0)
    validate_datab(data.i[0], 1)
    assert data == 1
    assert {data: 'xyz'}[1] == 'xyz' == {1: 'xyz'}[data]


def test_person_new(db):
    """test Person.new"""
    ctxt = for_levels(
        partial(
            core.Person.new,
            id_=123,
            first_name='first',
            last_name='last',
            class_='cls'),
        3)
    person_new = partial(core.Person.new, login_context=ctxt)
    p = models.Person.get_by_id(123)
    assert p.id == 123
    assert p.first_name == 'first'
    assert p.last_name == 'last'
    assert p.max_borrow == 3
    assert len(p.libraries) == 0
    assert p.borrow_permission is None
    with pytest.raises(core.BuchSchlossBaseError):
        person_new(id_=123, first_name='first', last_name='last', class_='cls')
    with pytest.raises(core.BuchSchlossBaseError):
        person_new(id_=124, first_name='first', last_name='last', class_='cls',
                   max_borrow=5, pay=True)
    ctxt.level = 4
    person_new(id_=124, first_name='first', last_name='last', class_='cls',
               max_borrow=5, pay=True)
    p = models.Person.get_by_id(124)
    assert p.id == 124
    assert p.max_borrow == 5
    assert p.borrow_permission == datetime.date.today() + datetime.timedelta(weeks=52)
    person_new(id_=125, first_name='first', last_name='last', class_='cls',
               borrow_permission=datetime.date(1956, 1, 31))
    p = models.Person.get_by_id(125)
    assert p.id == 125
    assert p.borrow_permission == datetime.date(1956, 1, 31)
    models.Library.create(name='main')
    person_new(id_=126, first_name='first', last_name='last', class_='cls')
    p = models.Person.get_by_id(126)
    assert p.id == 126
    assert list(p.libraries) == [models.Library.get_by_id('main')]


def test_person_edit(db):
    """test Person.edit"""
    models.Person.create(id=123, first_name='first', last_name='last', class_='cls',
                         max_borrow=3, borrow_permission=datetime.date(1956, 1, 31))
    ctxt = for_levels(partial(core.Person.edit, 123), 3)
    person_edit = partial(core.Person.edit, login_context=ctxt)
    person_edit(123, first_name='other_value')
    assert models.Person.get_by_id(123).first_name == 'other_value'
    person_edit(123, last_name='value_for_last', borrow_permission=None)
    p = models.Person.get_by_id(123)
    assert p.last_name == 'value_for_last'
    assert p.borrow_permission is None
    person_edit(123, pay=True)
    assert (models.Person.get_by_id(123).borrow_permission
            == datetime.date.today() + datetime.timedelta(weeks=52))
    models.Library.create(name='lib_1')
    models.Library.create(name='lib_2')
    e = person_edit(123, libraries=('lib_1', 'lib_does_not_exist'))
    assert e
    assert (list(models.Person.get_by_id(123).libraries)
            == [models.Library.get_by_id('lib_1')])
    with pytest.raises(core.BuchSchlossBaseError):
        person_edit(124)
    with pytest.raises(TypeError):
        person_edit(123, no_option=123)
    with pytest.raises(TypeError):
        person_edit(123, id=124)


def test_person_view_str(db):
    """test Person.view_str"""
    p = models.Person.create(id=123, first_name='first', last_name='last', class_='cls',
                             max_borrow=3, borrow_permission=datetime.date(1956, 1, 31))
    ctxt = for_levels(partial(core.Person.view_str, 123), 1)
    person_view = partial(core.Person.view_str, login_context=ctxt)
    with pytest.raises(core.BuchSchlossBaseError):
        person_view(12345)
    assert person_view(123) == {
        'id': '123',
        'first_name': 'first',
        'last_name': 'last',
        'class_': 'cls',
        'max_borrow': '3',
        'borrow_permission': str(utils.FormattedDate.fromdate(datetime.date(1956, 1, 31))),
        'borrows': (),
        'borrow_book_ids': [],
        'libraries': '',
        '__str__': str(models.Person.get_by_id(123)),
    }
    p.libraries.add(models.Library.create(name='main'))
    assert person_view(123)['libraries'] == 'main'
    create_book()
    models.Borrow.create(person=123, book=1, return_date=datetime.date(1956, 1, 31))
    info = person_view(123)
    assert info['borrows'] == (str(models.Borrow.get_by_id(1)),)
    assert info['borrow_book_ids'] == [1]
    p.libraries.add(models.Library.create(name='testlib'))
    info = person_view(123)
    assert info['libraries'] in ('main;testlib', 'testlib;main')
    create_book()
    models.Borrow.create(person=123, book=2, return_date=datetime.date(1956, 1, 31))
    info = person_view(123)
    assert info['borrows'] in (
        (str(models.Borrow.get_by_id(1)), str(models.Borrow.get_by_id(2))),
        (str(models.Borrow.get_by_id(2)), str(models.Borrow.get_by_id(1))),
    )
    assert info['borrow_book_ids'] in ([1, 2], [2, 1])

# since view_repr is implemented in ActionNamespace,
# I hope we only need one test each. Person is chosen bc. you need level 1


def test_person_view_repr(db):
    """test Person.view_repr"""
    p = create_person(123)
    ctxt = for_levels(partial(core.Person.view_repr, 123), 1, lambda r: r == str(p))
    person_view = partial(core.Person.view_repr, login_context=ctxt)
    with pytest.raises(core.BuchSchlossBaseError):
        person_view(124)


def test_book_new(db):
    """test Book.new"""
    models.Library.create(name='main')
    ctxt = for_levels(partial(
        core.Book.new,
        isbn=123, year=456, author='author', title='title', language='lang',
        publisher='publisher', medium='medium', shelf='A1'),
        2,
        lambda r: r == 1
    )
    book_new = partial(core.Book.new, login_context=ctxt)
    b = models.Book.get_by_id(1)
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
        book_new(isbn=123, year=456, author='author', title='title', language='lang',
                 publisher='publisher', medium='medium', shelf='A1',
                 library='does_not_exist')
    models.Library.create(name='other_lib')
    b_id = book_new(isbn=123, year=456, author='author', title='title', language='lang',
                    publisher='publisher', medium='medium', shelf='A1',
                    library='other_lib')
    assert b_id == 2
    assert models.Book.get_by_id(b_id).library.name == 'other_lib'
    b_id = book_new(isbn=123, year=456, author='author', title='title', language='lang',
                    publisher='publisher', medium='medium', shelf='A1',
                    groups=['grp0'])
    assert b_id == 3
    assert list(models.Book.get_by_id(b_id).groups) == [models.Group.get_by_id('grp0')]
    b_id = book_new(isbn=123, year=456, author='author', title='title', language='lang',
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
    ctxt = for_levels(partial(core.Book.edit, 1, isbn=1), 2, lambda r: not r)
    book_edit = partial(core.Book.edit, login_context=ctxt)
    assert models.Book.get_by_id(1).isbn == 1
    assert models.Book.get_by_id(2).isbn == 0
    assert not book_edit(1, author='author', shelf='shl')
    assert models.Book.get_by_id(1).author == 'author'
    assert models.Book.get_by_id(1).shelf == 'shl'
    assert models.Book.get_by_id(2).author == ''
    assert models.Book.get_by_id(2).shelf == ''
    models.Library.create(name='lib')
    assert not book_edit(1, library='lib')
    assert models.Book.get_by_id(1).library.name == 'lib'
    assert models.Book.get_by_id(2).library.name == 'main'
    with pytest.raises(core.BuchSchlossBaseError):
        book_edit(1, library='does_not_exist')
    assert not book_edit(1, groups=['group-1'])
    assert set(g.name for g in models.Book.get_by_id(1).groups) == {'group-1'}
    e = book_edit(1, groups=('group-2', 'does not exist'))
    assert e == {utils.get_name('error::no_Group_with_id_{}').format('does not exist')}
    assert set(g.name for g in models.Book.get_by_id(1).groups) == {'group-2'}
    assert models.Book.get_by_id(1).library.name == 'lib'
    assert not book_edit(1, medium='med')
    assert not book_edit(1, year=123)
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
    book_view = partial(core.Book.view_str,
                        login_context=core.internal_unpriv_lc)
    assert book_view(1) == {
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
        'status': utils.get_name('Book::available'),
        'return_date': '-----',
        'borrowed_by': '-----',
        'borrowed_by_id': None,
        '__str__': str(b),
    }
    b.library = models.Library.get_by_id('lib1')
    b.save()
    assert book_view(1)['library'] == 'lib1'
    b.groups.add('grp0')
    assert book_view(1)['groups'] == 'grp0'
    b.groups.add('grp1')
    assert book_view(1)['groups'] in ('grp0;grp1', 'grp1;grp0')
    models.Person.create(id=123, first_name='first', last_name='last',
                         class_='cls', max_borrow=3)
    borrow = models.Borrow.create(book=1, person=123, return_date=datetime.date(1956, 1, 31))
    data = book_view(1)
    assert data['status'] == utils.get_name('Book::borrowed')
    assert data['return_date'] == datetime.date(1956, 1, 31).strftime(config.core.date_format)
    assert data['borrowed_by'] == str(models.Person.get_by_id(123))
    assert data['borrowed_by_id'] == 123
    borrow.is_back = True
    borrow.save()
    assert book_view(1)['status'] == utils.get_name('Book::available')
    b.is_active = False
    b.save()
    assert book_view(1)['status'] == utils.get_name('Book::inactive')


def test_library_new(db):
    """test Library.new"""
    models.Library.create(name='main')
    create_book()
    create_book()
    models.Person.create(id=123, first_name='', last_name='', class_='', max_borrow=0)
    models.Person.create(id=456, first_name='', last_name='', class_='', max_borrow=0)
    ctxt = for_levels(partial(core.Library.new, 'testlib'), 3)
    library_new = partial(core.Library.new, login_context=ctxt)
    assert models.Library.get_or_none(name='testlib')
    with pytest.raises(core.BuchSchlossBaseError):
        library_new('testlib')
    assert models.Library.get_by_id('testlib').pay_required
    library_new('test-1', books=[1], people=[123])
    assert models.Book.get_by_id(1).library.name == 'test-1'
    assert (tuple(models.Person.get_by_id(123).libraries)
            == (models.Library.get_by_id('test-1'),))
    library_new('test-2', books=(1, 2), people=[123, 456])
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
    ctxt = for_levels(partial(core.Library.edit, core.LibraryGroupAction.NONE, 'testlib'), 3)
    library_edit = partial(core.Library.edit, login_context=ctxt)
    with pytest.raises(core.BuchSchlossBaseError):
        library_edit(core.LibraryGroupAction.NONE, 'does not exist')
    library_edit(core.LibraryGroupAction.ADD, 'testlib', books=[1])
    assert models.Book.get_by_id(1).library.name == 'testlib'
    library_edit(core.LibraryGroupAction.ADD, 'testlib', books=[2, 3], people=[123])
    assert all(models.Book.get_by_id(n).library.name == 'testlib' for n in range(1, 4))
    assert [p.id for p in models.Library.get_by_id('testlib').people] == [123]
    library_edit(core.LibraryGroupAction.REMOVE, 'testlib', books=[3, 4], people=[123])
    assert models.Book.get_by_id(4).library.name == 'test-2'
    assert models.Book.get_by_id(3).library.name == 'main'
    assert not models.Person.get_by_id(123).libraries
    library_edit(core.LibraryGroupAction.DELETE, 'testlib')
    assert not models.Library.get_by_id('testlib').people
    assert not models.Library.get_by_id('testlib').books
    library_edit(core.LibraryGroupAction.NONE, 'testlib', pay_required=True)
    assert models.Library.get_by_id('testlib').pay_required
    library_edit(core.LibraryGroupAction.NONE, 'testlib', pay_required=None)
    assert models.Library.get_by_id('testlib').pay_required
    library_edit(core.LibraryGroupAction.NONE, 'testlib', pay_required=False)
    assert not models.Library.get_by_id('testlib').pay_required


def test_library_view_str(db):
    """test Library.view_str"""
    models.Library.create(name='main')
    lib = models.Library.create(name='lib')
    b_1 = create_book()
    b_2 = create_book()
    p_1 = create_person(123)
    p_2 = create_person(124)
    library_view = partial(core.Library.view_str,
                           login_context=core.internal_unpriv_lc)
    with pytest.raises(core.BuchSchlossBaseError):
        library_view('does not exist')
    assert library_view('lib') == {
        '__str__': str(lib),
        'name': 'lib',
        'people': '',
        'books': '',
    }
    lib.people.add(p_1)
    assert library_view('lib')['people'] == '123'
    lib.people.add(p_2)
    assert set(library_view('lib')['people'].split(';')) == {'123', '124'}
    b_1.library = lib
    b_1.save()
    assert library_view('lib')['books'] == '1'
    b_2.library = lib
    b_2.save()
    assert set(library_view('lib')['books'].split(';')) == {'1', '2'}


def test_group_new(db):
    """test Group.new"""
    models.Library.create(name='main')
    create_book()
    create_book()
    ctxt = for_levels(partial(core.Group.new, 'test-grp'), 3)
    group_new = partial(core.Group.new, login_context=ctxt)
    assert not models.Group.get_by_id('test-grp').books
    with pytest.raises(core.BuchSchlossBaseError):
        group_new('test-grp')
    group_new('test-2', [1, 2])
    assert list(g.name for g in models.Book.get_by_id(1).groups) == ['test-2']
    assert list(g.name for g in models.Book.get_by_id(2).groups) == ['test-2']
    group_new('test-3', [2])
    assert list(g.name for g in models.Book.get_by_id(1).groups) == ['test-2']
    assert set(g.name for g in models.Book.get_by_id(2).groups) == {'test-2', 'test-3'}
    group_new('test-4', [12345])


def test_group_edit(db):
    """test Group.edit"""
    models.Library.create(name='main')
    models.Group.create(name='group-1')
    models.Group.create(name='group-2')
    create_book()
    create_book()
    ctxt = for_levels(partial(core.Group.edit, core.LibraryGroupAction.NONE, 'group-1', ()), 3)
    group_edit = partial(core.Group.edit, login_context=ctxt)
    with pytest.raises(core.BuchSchlossBaseError):
        group_edit(core.LibraryGroupAction.NONE, 'does not exist', ())
    group_edit(core.LibraryGroupAction.ADD, 'group-1', [1])
    assert set(g.name for g in models.Book.get_by_id(1).groups) == {'group-1'}
    assert not models.Book.get_by_id(2).groups
    assert 'group-2' not in models.Book.get_by_id(1).groups + models.Book.get_by_id(2).groups
    group_edit(core.LibraryGroupAction.REMOVE, 'group-1', iter([1, 2, 3]))
    group_edit(core.LibraryGroupAction.ADD, 'group-1', [2])
    assert not models.Book.get_by_id(1).groups
    assert set(g.name for g in models.Book.get_by_id(2).groups) == {'group-1'}
    assert 'group-2' not in models.Book.get_by_id(1).groups + models.Book.get_by_id(2).groups
    group_edit(core.LibraryGroupAction.DELETE, 'group-1', ())
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
    ctxt = for_levels(partial(core.Group.activate, 'group-1'), 3, lambda r: not r)
    group_activate = partial(core.Group.activate, login_context=ctxt)
    with pytest.raises(core.BuchSchlossBaseError):
        group_activate('does not exist')
    books[0].groups.add('group-1')
    books[1].groups.add('group-2')
    assert not group_activate('group-1', dest='lib-1')
    assert models.Book.get_by_id(1).library.name == 'lib-1'
    assert models.Book.get_by_id(2).library.name == 'main'
    b = models.Book.get_by_id(3)
    assert b.library.name == 'main'
    b.groups.add('group-1')
    b.library = models.Library.get_by_id('lib-2')
    b.save()
    assert not group_activate('group-1', ['lib-1'])
    assert models.Book.get_by_id(1).library.name == 'main'
    assert models.Book.get_by_id(3).library.name == 'lib-2'
    with pytest.raises(core.BuchSchlossBaseError):
        group_activate('group-1', ['does not exist', 'lib-2'])
    with pytest.raises(core.BuchSchlossBaseError):
        group_activate('group-1', ['lib-1'], 'does not exist')


def test_group_view_str(db):
    """test Group.view_str"""
    models.Library.create(name='main')
    models.Group.create(name='group-1')
    create_book()
    create_book()
    group_view = partial(core.Group.view_str,
                         login_context=core.internal_unpriv_lc)
    assert group_view('group-1') == {
        '__str__': str(models.Group.get_by_id('group-1')),
        'name': 'group-1',
        'books': ''
    }
    with pytest.raises(core.BuchSchlossBaseError):
        group_view('does not exist')
    models.Group.get_by_id('group-1').books = [1]
    assert group_view('group-1')['books'] == '1'
    models.Group.get_by_id('group-1').books.add(2)
    assert group_view('group-1')['books'] in ('1;2', '2;1')
    models.Group.get_by_id('group-1').books.remove(1)
    assert group_view('group-1')['books'] == '2'


def test_member_new(db):
    """test member.new"""
    ctxt = for_levels(partial(core.Member.new, 'name', 'Pa$$w0rd', 3), 4)
    member_new = partial(core.Member.new, login_context=ctxt)
    m = models.Member.get_by_id('name')
    assert m.level == 3
    assert core.pbkdf(b'Pa$$w0rd', m.salt) == m.password
    with pytest.raises(core.BuchSchlossBaseError):
        member_new('name', 'other Pa$$w0rd', 1)


def test_member_edit(db):
    """test Member.edit"""
    models.Member.create(name='name', level=0, salt=b'', password=b'')
    ctxt = for_levels(partial(core.Member.edit, 'name', level=4), 4)
    member_edit = partial(core.Member.edit, login_context=ctxt)
    assert models.Member.get_by_id('name').level == 4
    for kw in ({'name': 'new'}, {'salt': b''}, {'password': b''}):
        with pytest.raises(TypeError):
            member_edit('name', **kw)
    with pytest.raises(core.BuchSchlossBaseError):
        member_edit('does not exist')


def test_member_change_password(db):
    """test Member.change_password"""
    models.Member.create(name='name', level=0, salt=b'', password=core.pbkdf(b'', b''))
    models.Member.create(name='other', level=0, salt=b'', password=core.pbkdf(b'', b''))
    for_levels(partial(core.Member.change_password, 'name', 'new'), 4)
    assert core.authenticate(models.Member.get_by_id('name'), 'new')
    ctxt_editee = core.LoginContext(core.LoginType.MEMBER, 0, name='name')
    ctxt_other = core.LoginContext(core.LoginType.MEMBER, 0, name='other')
    core.Member.change_password(
        'name', 'other', login_context=ctxt_editee, current_password='new')
    assert core.authenticate(models.Member.get_by_id('name'), 'other')
    with pytest.raises(core.BuchSchlossBaseError):
        core.Member.change_password(
            'name', 'third', login_context=ctxt_other, current_password='')


def test_member_view_str(db):
    """test Member.view_str"""
    models.Member.create(name='name', level=0, salt=b'', password=b'')
    assert core.Member.view_str('name', login_context=core.internal_unpriv_lc) == {
        '__str__': str(models.Member.get_by_id('name')),
        'name': 'name',
        'level': utils.level_names[0],
    }


def test_borrow_new(db):
    """test Borrow.new"""
    def restitute(borrow_id):
        b = models.Borrow.get_by_id(borrow_id)
        b.is_back = True
        b.save()

    models.Library.create(name='main')
    test_lib = models.Library.create(name='test-lib')
    models.Library.create(name='no-pay', pay_required=False)
    create_book()
    create_book()
    create_book('test-lib')
    create_book('no-pay')
    p = create_person(123, max_borrow=1,
                      borrow_permission=(datetime.date.today()
                                         + datetime.timedelta(days=1)),
                      libraries=['main', 'no-pay'])
    ctxt = core.internal_unpriv_lc
    borrow_new = partial(core.Borrow.new, login_context=ctxt)
    # follows config settings
    for i in range(5):
        ctxt.level = i
        with pytest.raises(core.BuchSchlossBaseError):
            borrow_new(1, 123, config.core.borrow_time_limit[i] + 1)
    weeks = config.core.borrow_time_limit[i]
    borrow_new(1, 123, weeks)
    # correct data
    assert len(models.Borrow.select()) == 1
    b = models.Borrow.get_by_id(1)
    assert b.person.id == 123
    assert b.book.id == 1
    assert b.return_date == datetime.date.today() + datetime.timedelta(weeks=weeks)
    # respects Person.max_borrow
    with pytest.raises(core.BuchSchlossBaseError):
        borrow_new(2, 123, weeks)
    # respects libraries
    restitute(1)
    with pytest.raises(core.BuchSchlossBaseError):
        borrow_new(3, 123, weeks)
    p.libraries.add(test_lib)
    borrow_new(3, 123, weeks)
    restitute(2)
    # respects pay_required and accepts keyword arguments
    p.borrow_permission = datetime.date.today() - datetime.timedelta(days=1)
    p.save()
    with pytest.raises(core.BuchSchlossBaseError):
        borrow_new(person=123, book=2, weeks=weeks)
    borrow_new(person=123, book=4, weeks=weeks)
    # allows overriding
    ctxt.level = 2
    with pytest.raises(core.BuchSchlossBaseError):
        borrow_new(2, 123, weeks, override=True)
    ctxt.level = 4
    borrow_new(2, 123, weeks, override=True)


def test_borrow_edit(db):
    """test Borrow.edit"""
    today = datetime.date.today()
    models.Library.create(name='main')
    create_person(123)
    create_book()
    models.Borrow.create(person=123, book=1, return_date=today)
    ctxt = for_levels(partial(core.Borrow.edit, 1, weeks=1), 1)
    assert (models.Borrow.get_by_id(1).return_date - today).days == 7
    with pytest.raises(TypeError):
        core.Borrow.edit(1, return_date=today, weeks=1, login_context=ctxt)
    core.Borrow.edit(1, return_date=today, is_back=True, login_context=ctxt)
    assert models.Borrow.get_by_id(1).return_date == today
    assert models.Borrow.get_by_id(1).is_back


def test_search(db):
    """test searches"""
    models.Library.create(name='main')
    book_1 = core.DataNamespace(core.Book, create_book(author='author name'), None)
    book_2 = core.DataNamespace(core.Book, create_book(author='author 2', year=2000), None)
    person = core.DataNamespace(core.Person, create_person(123, class_='cls', libraries=['main']), None)
    ctxt_person = for_levels(partial(core.Person.search, ()), 1)
    person_search = partial(core.Person.search, login_context=ctxt_person)
    book_search = partial(core.Book.search, login_context=core.internal_unpriv_lc)
    assert tuple(book_search(('author', 'eq', 'author name'))) == (book_1,)
    assert set(book_search(())) == {book_1, book_2}
    assert (tuple(book_search((('author', 'ne', 'author name'), 'or', ())))
            == (book_2,))
    assert (tuple(book_search((('author', 'contains', 'name'), 'and', ())))
            == (book_1,))
    assert (tuple(book_search((('library.people.class_', 'eq', 'cls'),
                               'and', ('id', 'lt', 2))))
            == (book_1,))
    assert (tuple(person_search(('libraries.books.author', 'contains', '2')))
            == (person,))
    assert (set(book_search(('library.people.libraries.books.year', 'gt', 1990)))
            == {book_1, book_2})
    assert tuple(person_search(('libraries', 'eq', 'main'))) == (person,)
    assert (set(book_search(('library.people.libraries', 'eq', 'main')))
            == {book_2, book_1})
    assert tuple(book_search(('year', 'ge', 2001))) == ()
    assert tuple(book_search(('year', 'ge', 2000))) == (book_2,)
    assert tuple(book_search(('id', 'in', (1, 200, 300)))) == (book_1,)
    assert tuple(book_search(('author', 'in', ('neither', 'matches')))) == ()


def test_script_new(db):
    """test Script.new"""
    ctxt = for_levels(partial(
        core.Script.new,
        name='test-script',
        code='this should be valid Lua code',
        setlevel=3,
        permissions=core.ScriptPermissions(3)),
        4,
    )
    script_new = partial(core.Script.new, login_context=ctxt)
    script = models.Script.get_by_id('test-script')
    assert script.name == 'test-script'
    assert script.code == 'this should be valid Lua code'
    assert script.setlevel == 3
    assert script.storage == {}
    assert script.permissions is core.ScriptPermissions(3)
    script_new(name='with-setlevel-none', code='mode Lua code',
               permissions=core.ScriptPermissions(0), setlevel=None)
    assert models.Script.get_by_id('with-setlevel-none').setlevel is None
    with pytest.raises(core.BuchSchlossBaseError):
        script_new(name='test-script', code='with the same name',
                   permissions=core.ScriptPermissions(0), setlevel=None)
    with pytest.raises(ValueError):
        script_new(name='contains:invalid"chars', code='',
                   permissions=core.ScriptPermissions(0), setlevel=None)


def test_script_edit(db):
    """test Script.edit"""
    # noinspection PyArgumentList
    models.Script.create(name='name', code='code', setlevel=3,
                         permissions=core.ScriptPermissions(0), storage={})
    ctxt = for_levels(partial(
        core.Script.edit,
        'name',
        code='new code'),
        4
    )
    script_edit = partial(core.Script.edit, login_context=ctxt)
    assert models.Script.get_by_id('name').code == 'new code'
    with pytest.raises(TypeError):
        script_edit('name', name='not allowed')
    with pytest.raises(TypeError):
        script_edit('name', unknown='attribute')
    with pytest.raises(core.BuchSchlossBaseError):
        script_edit('unknown', code='blah')


def test_script_execute(db, monkeypatch):
    """test Script.execute"""
    script = models.Script.create(name='name', code='code', setlevel=None, storage={},
                                  permissions=core.ScriptPermissions(0))
    ctxt = core.internal_unpriv_lc
    script_execute = partial(core.Script.execute, 'name', login_context=ctxt)
    calls = []

    def lua_prep_rt(*args, **kwargs):
        calls.append(kwargs)
        return type('', (), {
            'execute': lambda c: {
                'func': lambda: calls.append('func'),
            }
        })

    monkeypatch.setattr('buchschloss.lua.prepare_runtime', lua_prep_rt)
    monkeypatch.setattr(core.Script, 'callbacks', 'cls-cb-flag')
    monkeypatch.setitem(config.scripts.lua.mapping, 'name', {'key': 'value'})
    script_execute(callbacks='callback-flag')
    assert calls[-1].pop('add_ui') == ('callback-flag', 'script-data::name::')
    script.permissions |= core.ScriptPermissions.REQUESTS
    script.save()
    script_execute()
    assert calls[-1].pop('add_ui') == ('cls-cb-flag', 'script-data::name::')
    script.permissions |= core.ScriptPermissions.STORE
    script.save()
    monkeypatch.setattr(core.Script, 'callbacks', None)
    monkeypatch.delitem(config.scripts.lua.mapping, 'name')
    script_execute('func')
    assert calls.pop() == 'func'
    getter, setter = calls[-1].pop('add_storage')
    assert callable(getter) and callable(setter)
    if config.debug:
        # GitHub actions Python 3.6 seems to have this...
        exc = KeyError
    else:
        exc = core.BuchSchlossBaseError
    with pytest.raises(exc):
        script_execute('nonexistent')
    calls.pop()
    assert calls == [
        {'add_storage': None, 'add_requests': False, 'add_config': {'key': 'value'}},
        {'add_storage': None, 'add_requests': True, 'add_config': {'key': 'value'}},
        {'add_requests': True, 'add_ui': None, 'add_config': {}},
    ]


def test_script_view_str(db):
    """test Script.view_str"""
    script = models.Script.create(name='name', code='code', setlevel=None, storage={},
                                  permissions=core.ScriptPermissions(0))
    exp_repr = utils.get_name('Script') + '[name]'
    expected = {
        '__str__': exp_repr, 'name': 'name',
        'setlevel': '-----', 'permissions': ''}
    ctxt = for_levels(partial(core.Script.view_str, 'name'), 0, lambda x: x == expected)
    script_view_str = partial(core.Script.view_str, login_context=ctxt)
    script.setlevel = 0
    script.permissions = core.ScriptPermissions.STORE | core.ScriptPermissions.REQUESTS
    script.save()
    data = script_view_str('name')
    assert set(data.pop('permissions').split(';')) == {
        utils.get_name('Script::permissions::STORE'),
        utils.get_name('Script::permissions::REQUESTS')}
    l0 = utils.level_names[0]
    assert data == {'name': 'name', 'setlevel': l0, '__str__': exp_repr + l0.join('()')}
    script.setlevel = 3
    script.permissions = core.ScriptPermissions.STORE
    script.save()
    l3 = utils.level_names[3]
    assert (script_view_str('name')
            == {'name': 'name', 'setlevel': l3, '__str__': exp_repr + l3.join('()'),
                'permissions': utils.get_name('Script::permissions::STORE')})
    with pytest.raises(core.BuchSchlossBaseError):
        script_view_str('whatever')
