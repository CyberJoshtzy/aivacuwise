"""Creates any tables defined in models.py that do not exist yet in PostgreSQL (safe, never drops or alters)."""

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

import database
import models

engine = getattr(database, "engine", None)
if engine is None:
    engine = next((v for v in vars(database).values() if isinstance(v, Engine)), None)
if engine is None:
    raise SystemExit("STOP: could not find the database engine in database.py")

before = set(inspect(engine).get_table_names())
models.Base.metadata.create_all(bind=engine)
after = set(inspect(engine).get_table_names())
added = sorted(after - before)
print("Created tables: " + (", ".join(added) if added else "none (all tables already existed)"))
print("incidents table present: " + ("yes" if "incidents" in after else "NO"))
