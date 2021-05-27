"""describe the migration"""

import peewee
from playhouse import migrate
import sys

try:
    db_name = sys.argv[1]
except IndexError:
    db_name = input('database path -> ')
db = migrate.SqliteDatabase(db_name)
migrator = migrate.SqliteMigrator(db)


class Book(peewee.Model):
    class Meta:
        database = db


class GroupTemp(peewee.Model):
    class Meta:
        database = db
        primary_key = peewee.CompositeKey('book', 'name')
    book = peewee.ForeignKeyField(Book)
    name = peewee.CharField()


db.create_tables([GroupTemp])
db.execute_sql("""
INSERT INTO grouptemp (book_id, name) 
    SELECT book_id, group_id FROM group_book_through;
""")
db.execute_sql('DROP TABLE group_book_through;')
db.execute_sql('DROP TABLE "group";')  # I don't have the models here
migrate.migrate(
    migrator.rename_table('grouptemp', 'group')
)
