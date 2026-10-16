"""Adds the three new evacuee columns to the existing PostgreSQL table (safe to run twice)."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

import database

engine = getattr(database, "engine", None) or next(
    (v for v in vars(database).values() if isinstance(v, Engine)), None
)
if engine is None:
    raise SystemExit("STOP: could not find the database engine in database.py")
with engine.begin() as conn:
    for col in ["civil_status", "special_needs", "emergency_contact"]:
        conn.execute(text("ALTER TABLE evacuees ADD COLUMN IF NOT EXISTS " + col + " VARCHAR"))
cols = {c["name"] for c in inspect(engine).get_columns("evacuees")}
for col in ["civil_status", "special_needs", "emergency_contact"]:
    print(col + ": " + ("present" if col in cols else "MISSING"))
