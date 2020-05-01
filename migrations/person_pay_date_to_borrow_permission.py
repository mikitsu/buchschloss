"""Rename Person.pay_date to Person.borrow_permission and set forward 52 weeks"""

from playhouse import migrate
import sys

try:
    db_name = sys.argv[1]
except IndexError:
    db_name = input('database path -> ')
db = migrate.SqliteDatabase(db_name)
migrator = migrate.SqliteMigrator(db)

migrate.migrate(
    migrator.rename_column('person', 'pay_date', 'borrow_permission')
)

db.execute_sql("""
UPDATE person
    SET borrow_permission = date(borrow_permission, "364 days")
    WHERE borrow_permission IS NOT NULL
""")
