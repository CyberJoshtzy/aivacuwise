"""Cloud sync, Phase 1 migration: adds uuid / updated_at / origin to the existing tables,
fills them in for records that already exist, and creates sync_tombstones and sync_state.

STOP THE SERVICE FIRST:  sudo systemctl stop aivacuwise
Then:                    python3 migrate_sync_phase1.py
Then:                    sudo systemctl start aivacuwise
Safe to run twice.
"""

import os

from sqlalchemy import inspect, text

import database
import models

engine = database.engine
TABLES = [c.__table__.name for c in models.SYNCED_MODELS]
server = os.getenv("BILISLIKAS_SERVER_ID", "local")

with engine.begin() as conn:
    conn.execute(text("SET lock_timeout = '10s'"))
    for t in TABLES:
        conn.execute(text("ALTER TABLE %s ADD COLUMN IF NOT EXISTS uuid VARCHAR(36)" % t))
        conn.execute(text("ALTER TABLE %s ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP" % t))
        conn.execute(text("ALTER TABLE %s ADD COLUMN IF NOT EXISTS origin VARCHAR" % t))
        conn.execute(text("UPDATE %s SET uuid = gen_random_uuid()::text WHERE uuid IS NULL" % t))  # noqa: S608
        conn.execute(
            text(
                "UPDATE %s SET updated_at = (now() AT TIME ZONE 'utc') WHERE updated_at IS NULL" % t  # noqa: S608
            )
        )
        conn.execute(text("UPDATE %s SET origin = :o WHERE origin IS NULL" % t), {"o": server})  # noqa: S608
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_%s_uuid ON %s (uuid)" % (t, t)))
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_%s_updated_at ON %s (updated_at)" % (t, t))
        )
    conn.execute(text("ALTER TABLE barangays ADD COLUMN IF NOT EXISTS district VARCHAR"))

models.Base.metadata.create_all(
    bind=engine, tables=[models.SyncTombstone.__table__, models.SyncState.__table__]
)

insp = inspect(engine)
ok = True
with engine.connect() as conn:
    for t in TABLES:
        cols = {c["name"] for c in insp.get_columns(t)}
        missing = conn.execute(text("SELECT count(*) FROM %s WHERE uuid IS NULL" % t)).scalar()  # noqa: S608
        total = conn.execute(text("SELECT count(*) FROM %s" % t)).scalar()  # noqa: S608
        good = {"uuid", "updated_at", "origin"} <= cols and missing == 0
        ok = ok and good
        print("%-20s %4d records  %s" % (t, total, "ready" if good else "PROBLEM"))
print(
    "sync_tombstones and sync_state: "
    + ("present" if {"sync_tombstones", "sync_state"} <= set(insp.get_table_names()) else "MISSING")
)
print("Server name for this database: " + server)
print("ALL TABLES READY" if ok else "Some tables have a problem: paste this output to Claude.")
