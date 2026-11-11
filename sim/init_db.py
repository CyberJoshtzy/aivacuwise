"""Creates all AiVacuwise tables in the database chosen by POSTGRES_PORT (used for Server B and the hub)."""

import os
import sys

sys.path.insert(0, os.getcwd())
from sqlalchemy import inspect  # noqa: E402

import database  # noqa: E402
import models  # noqa: E402

models.Base.metadata.create_all(bind=database.engine)
names = inspect(database.engine).get_table_names()
print(
    "  %s: database on port %s has %d tables"
    % (models.SERVER_ID, os.getenv("POSTGRES_PORT", "5432"), len(names))
)
