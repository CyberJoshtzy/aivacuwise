"""Adds full_name, designation, mobile_number to the existing users table (safe to run twice)."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

import database

engine = getattr(database, "engine", None) or next(
    (v for v in vars(database).values() if isinstance(v, Engine)), None
)
if engine is None:
    raise SystemExit("STOP: could not find the database engine in database.py")
cols = ["full_name", "designation", "mobile_number"]
with engine.begin() as conn:
    for col in cols:
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS " + col + " VARCHAR"))
have = {c["name"] for c in inspect(engine).get_columns("users")}
for col in cols:
    print(col + ": " + ("present" if col in have else "MISSING"))
