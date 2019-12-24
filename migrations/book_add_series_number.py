"""add a column "series_number" to Book"""

import peewee
from playhouse import migrate
import sys

try:
    db_name = sys.argv[1]
except IndexError:
    db_name = input('database path -> ')
db = peewee.SqliteDatabase(db_name)
migrator = migrate.SqliteMigrator(db)

migrate.migrate(
    migrator.add_column('book', 'series_number', peewee.IntegerField(null=True))
)
