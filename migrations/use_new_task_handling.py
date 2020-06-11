"""change misc.check_time (time) to misc.last_script_invocations (dict)"""

import peewee
from playhouse.fields import PickleField
import sys

try:
    db_name = sys.argv[1]
except IndexError:
    db_name = input('database path -> ')
db = peewee.SqliteDatabase(db_name)


class Misc(peewee.Model):
    """Store singular data (e.g. date for recurring action)

    Usable through the misc_data, instance of MiscData"""
    pk = peewee.CharField(primary_key=True)
    data = PickleField()

    class Meta:
        database = db


with db:
    Misc.delete_by_id('check_time')
    Misc.create(pk='last_script_invocations', data={})
