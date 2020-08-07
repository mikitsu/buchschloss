"""add a table for Lua scripts"""

from buchschloss import core, models  # noqa -- needed bc. of circular imports

models.db.create_tables([models.Script])
