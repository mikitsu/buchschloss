"""common fixtures"""
import pytest

from buchschloss import config

config.core.mapping['database name'] = ':memory:'
config.core.log.mapping['file'] = ''

from buchschloss import core, models  # noqa


@pytest.fixture
def db():
    """bind the models to the test database"""
    # since in-memory databases clear data when closing,
    # we don't need an explicit drop_tables
    models.db.create_tables(models.models)
    models.Misc.create(pk='last_script_invocations', data={})
    with models.db:
        yield
