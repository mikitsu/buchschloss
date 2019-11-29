"""Test core"""

import datetime
import pytest
import peewee

from buchschloss import core, models

testing_db = peewee.SqliteDatabase(':memory:')


@pytest.fixture  # adapted from http://docs.peewee-orm.com/en/3.1.0/peewee/api.html#Database.bind_ctx
def db():
    """bind the models to the test database"""
    with testing_db.bind_ctx(models.models):
        testing_db.create_tables(models.models)
        try:
            yield
        finally:
            testing_db.drop_tables(models.models)


def test_misc_data(db):
    """test the misc_data accessor for the misc table"""
    models.Misc.create(pk='test_pk_1', data=[1, 2, 3])
    models.Misc.create(pk='test_pk_2', data=0)
    assert core.misc_data.test_pk_1 == [1, 2, 3]
    core.misc_data.test_pk_2 = 'test_string'
    assert models.Misc.get_by_id('test_pk_2').data == 'test_string'
    models.db.connect()
    assert core.misc_data.test_pk_1 == [1, 2, 3]
    assert models.db.close()
    models.db.connect()
    core.misc_data.test_pk_1 += [4]
    assert core.misc_data.test_pk_1 == [1, 2, 3, 4]
    assert models.db.close()
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
    core.current_login.level = 4
    old_today = datetime.date.today()  # in case this is run around midnight...
    core.Person.new(124, 'first', 'last', 'cls', pay=True)
    p = models.Person.get_by_id(124)
    assert p.id == 124
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
