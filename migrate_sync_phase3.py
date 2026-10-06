"""Cloud sync, Phase 3 migration: adds sync_dirty to every synced table and creates sync_log.
Records this server created are marked as "still to send", so the first sync uploads them.

Uses the database chosen by POSTGRES_PORT (default 5432 = Server A). Stop that server's backend first.
Safe to run twice.
"""
import os

import database
import models
from sqlalchemy import inspect, text

engine = database.engine
server = models.SERVER_ID
with engine.begin() as conn:
    conn.execute(text("SET lock_timeout = '10s'"))
    for cls in models.SYNCED_MODELS:
        t = cls.__table__.name
        conn.execute(text('ALTER TABLE %s ADD COLUMN IF NOT EXISTS sync_dirty BOOLEAN DEFAULT FALSE' % t))
        conn.execute(text('UPDATE %s SET sync_dirty = TRUE WHERE origin = :o AND sync_dirty IS NOT TRUE' % t), {'o': server})
        conn.execute(text('UPDATE %s SET sync_dirty = FALSE WHERE sync_dirty IS NULL' % t))
        conn.execute(text('CREATE INDEX IF NOT EXISTS ix_%s_sync_dirty ON %s (sync_dirty)' % (t, t)))
models.Base.metadata.create_all(bind=engine, tables=[models.SyncLog.__table__])
insp = inspect(engine)
ok = 'sync_log' in insp.get_table_names()
with engine.connect() as conn:
    waiting = 0
    for cls in models.SYNCED_MODELS:
        t = cls.__table__.name
        ok = ok and 'sync_dirty' in {c['name'] for c in insp.get_columns(t)}
        waiting += conn.execute(text('SELECT count(*) FROM %s WHERE sync_dirty' % t)).scalar()
print('%s (database port %s): %s, %d records waiting to be sent'
      % (server, os.getenv('POSTGRES_PORT', '5432'), 'READY' if ok else 'PROBLEM', waiting))
