"""Instead of a single text field, store genres in a separate table"""
# NOTE: the splitting assumes genres are separated by semicolons

# To do these updates via peewee,
# I'd probably have to copy Book and Genre models (for the FK).
# (in hindsight, that would probably have been less work)
# splitting from https://stackoverflow.com/a/32051164

from playhouse import migrate
import sys

try:
    db_name = sys.argv[1]
except IndexError:
    db_name = input('database path -> ')
db = migrate.SqliteDatabase(db_name)
migrator = migrate.SqliteMigrator(db)
db.execute_sql("""
CREATE TABLE genre (
    book_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    PRIMARY KEY (book_id, name),
    FOREIGN KEY (book_id) REFERENCES book (id)
);""")
db.execute_sql("""
INSERT INTO genre (book_id, name)
WITH split(b_id, word, str) AS (
    SELECT book.id, '', book.genres||';' FROM book
    UNION ALL SELECT
    b_id,
    substr(str, 0, instr(str, ';')),
    substr(str, instr(str, ';')+1)
    FROM split WHERE str!=''
) SELECT b_id, word FROM split WHERE word !='';
""")
migrate.migrate(
    migrator.drop_column('book', 'genres')
)
