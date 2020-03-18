"""add a table for Lua scripts"""

from buchschloss import core, models

models.db.create_tables([models.Script])
