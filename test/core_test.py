"""Test core"""

import datetime
from functools import partial

import pytest

from buchschloss import config, core, models, utils


def create_book(library='main', **options):
    """create a Book with falsey values. The Library can be specified"""
    genres = options.pop('genres', ())
    kwargs = dict(isbn=0, author='', title='', language='', publisher='',
                  year=0, medium='', shelf='', library=library)
    b = models.Book.create(**{**kwargs, **options})
    for g in genres:
        models.Genre.get_or_create(name=g, book=b)
    return b


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
    class DataA(core.Dummy):
        pk_name = 'a'
        @staticmethod
        def check_view_permissions(lc, dns):
            pass
    class DataB(core.Dummy): pass

    def validate_datab(data_val, x_val):
        assert isinstance(data_val, core.DataNamespace)
        assert data_val.handlers == {'allow': 'ad'}
        assert data_val.login_context is FLAG
        assert data_val.data.x == x_val

    core.DataNamespace.data_handling[DataA] = {
        'allow': 'ab',
        'wrap_iter': {'i': DataB},
        'wrap_dns': {'d': DataB, 'n': DataB},
        'transform': {'g': lambda gs: [g.x for g in gs]},
    }
    core.DataNamespace.data_handling[DataB] = {'allow': 'ad'}
    data = core.DataNamespace(
        DataA,
        DataA(a=1, b=[1, 2, 3], d=DataB(x=0), i=[DataB(x=1), DataB(x=2)], n=None,
              g=[DataB(x=5), DataB(x=7)]),
        login_context=FLAG,
    )
    assert data['a'] == 1
    assert data['b'] == [1, 2, 3]
    validate_datab(data['d'], 0)
    validate_datab(data['i'][0], 1)
    assert data['g'] == [5, 7]
    assert data == 1
    assert {data: 'xyz'}[1] == 'xyz' == {1: 'xyz'}[data]


def test_data_ns_handlers(db):
    models.Library.create(name='name')
    create_book('name')
    create_person(123)
    models.Borrow.create(person=123, book=1, return_date=datetime.date.today())
    models.Member.create(name='name', level=3, password=b'', salt=b'')
    models.Script.create(name='name', code='', storage={}, permissions=core.ScriptPermissions(0))
    ids = {'Book': 1, 'Person': 123, 'Borrow': 1}
    for ns in core.ActionNamespace.namespaces:
        dns = getattr(core, ns).view_ns(ids.get(ns, 'name'), login_context=core.internal_unpriv_lc)
        for k in dns:
            dns[k]


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
    models.Library.create(name='lib')
    person_new(id_=127, first_name='first', last_name='last', class_='cls', libraries=('lib',))
    assert list(models.Person.get_by_id(127).libraries) == [models.Library.get_by_id('lib')]


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
    person_edit(123, libraries=['lib_2'])
    with pytest.raises(core.BuchSchlossBaseError):
        person_edit(123, first_name='another', libraries=('lib_1', 'lib_does_not_exist'))
    assert (list(models.Person.get_by_id(123).libraries)
            == [models.Library.get_by_id('lib_2')])
    assert models.Person.get_by_id(123).first_name == 'other_value'
    person_edit(123, libraries=['lib_1'])
    assert (list(models.Person.get_by_id(123).libraries)
            == [models.Library.get_by_id('lib_1')])
    with pytest.raises(core.BuchSchlossBaseError):
        person_edit(124)
    with pytest.raises(TypeError):
        person_edit(123, no_option=123)
    with pytest.raises(TypeError):
        person_edit(123, id=124)


def test_book_new(db):
    """test Book.new"""
    models.Library.create(name='main')
    ctxt = for_levels(partial(
        core.Book.new,
        isbn=123, year=456, author='author', title='title', language='lang',
        publisher='publisher', medium='medium', shelf='A1', genres=('one', 'two')),
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
    assert set(b.genres) == {models.Genre.get_by_id((b, k)) for k in ('one', 'two')}
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
    b = models.Book.get_by_id(b_id)
    assert list(b.groups) == [models.Group.get_by_id((b, 'grp0'))]
    b_id = book_new(isbn=123, year=456, author='author', title='title', language='lang',
                    publisher='publisher', medium='medium', shelf='A1',
                    groups=['grp0', 'grp1'])
    assert b_id == 4
    b = models.Book.get_by_id(b_id)
    assert set(b.groups) == {
        models.Group.get_by_id((b, 'grp0')), models.Group.get_by_id((b, 'grp1'))}


def test_book_edit(db):
    """test Book.edit"""
    models.Library.create(name='main')
    create_book()
    create_book()
    ctxt = for_levels(partial(core.Book.edit, 1, isbn=1), 2, lambda r: not r)
    book_edit = partial(core.Book.edit, login_context=ctxt)
    assert models.Book.get_by_id(1).isbn == 1
    assert models.Book.get_by_id(2).isbn == 0
    book_edit(1, author='author', shelf='shl')
    assert models.Book.get_by_id(1).author == 'author'
    assert models.Book.get_by_id(1).shelf == 'shl'
    assert models.Book.get_by_id(2).author == ''
    assert models.Book.get_by_id(2).shelf == ''
    models.Library.create(name='lib')
    book_edit(1, library='lib')
    assert models.Book.get_by_id(1).library.name == 'lib'
    assert models.Book.get_by_id(2).library.name == 'main'
    with pytest.raises(core.BuchSchlossBaseError):
        book_edit(1, library='does_not_exist')
    assert not book_edit(1, groups=['group-1'])
    assert set(g.name for g in models.Book.get_by_id(1).groups) == {'group-1'}
    assert models.Book.get_by_id(1).library.name == 'lib'
    book_edit(1, medium='med')
    book_edit(1, year=123)
    assert models.Book.get_by_id(1).medium == 'med'
    assert models.Book.get_by_id(1).year == 123
    assert models.Book.get_by_id(2).medium == ''
    assert models.Book.get_by_id(2).year == 0

    book_edit(2, genres=('two',))
    for new in (('one', 'two'), ('one',), ('three',)):
        book_edit(1, genres=new)
        b = models.Book.get_by_id(1)
        assert set(b.genres) == {models.Genre.get_by_id((b, k)) for k in new}
    assert models.Book.get_by_id(2).genres[0].name == 'two'


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
    ctxt = for_levels(partial(core.Library.edit, 'main'), 3)
    library_edit = partial(core.Library.edit, login_context=ctxt)
    library_edit('main', pay_required=True)
    assert models.Library.get_by_id('main').pay_required
    library_edit('main')
    assert models.Library.get_by_id('main').pay_required
    library_edit('main', pay_required=False)
    assert not models.Library.get_by_id('main').pay_required


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
    weeks = 10
    ctxt = for_levels(partial(core.Borrow.new, 1, 123, weeks), 1)
    borrow_new = partial(core.Borrow.new, login_context=ctxt)
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
    book_1 = core.DataNamespace(
        core.Book,
        create_book(author='author name', genres=('one', 'two')),
        core.internal_unpriv_lc,
    )
    book_2 = core.DataNamespace(
        core.Book,
        create_book(author='author 2', year=2000),
        core.internal_unpriv_lc,
    )
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
    assert tuple(book_search(('genres', 'eq', 'one'))) == (book_1,)


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
