"""describe the migration"""

from playhouse import migrate
import sys

try:
    db_name = sys.argv[1]
except IndexError:
    db_name = input('database path -> ')
db = migrate.SqliteDatabase(db_name)
migrator = migrate.SqliteMigrator(db)

migrate.migrate(
    ...
)
