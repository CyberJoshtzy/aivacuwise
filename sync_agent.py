"""AiVacuwise sync agent: runs beside one barangay server and keeps it in sync with the cloud hub.

Every SYNC_INTERVAL seconds, when the hub is reachable:
  1. push: send records created or changed here (and deletions) to the hub
  2. pull: receive changes from every other server and apply them here
When the hub (or the internet) is down, nothing is lost: changes stay marked and are sent later.

Settings come from .env / the environment:
  HUB_URL (e.g. http://127.0.0.1:9000), SYNC_KEY, BILISLIKAS_SERVER_ID, POSTGRES_PORT,
  LOCAL_URL (this server, e.g. http://127.0.0.1:8000), SYNC_INTERVAL (seconds, default 30)
"""

import os
import sys
import time
from datetime import datetime

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(sys.argv[0])) or ".")
import database  # noqa: E402
import models  # noqa: E402
import sync_core  # noqa: E402

HUB = os.getenv("HUB_URL", "http://127.0.0.1:9000").rstrip("/")
KEY = os.getenv("SYNC_KEY", "")
LOCAL = os.getenv("LOCAL_URL", "http://127.0.0.1:8000").rstrip("/")
EVERY = int(os.getenv("SYNC_INTERVAL", "30"))
ME = models.SERVER_ID
HEADERS = {"X-Sync-Key": KEY}


def log(msg):
    print("%s [%s] %s" % (datetime.now().strftime("%H:%M:%S"), ME, msg), flush=True)


def state(db, key, default=None):
    r = db.get(models.SyncState, key)
    return r.value if r else default


def set_state(db, key, value):
    db.merge(models.SyncState(key=key, value=str(value)))


def push(db):
    sent = 0
    while True:
        rows = sync_core.dirty_rows(db)
        last_t = int(state(db, "push_tombstone_id", "0"))
        ts = (
            db.query(models.SyncTombstone)
            .filter(models.SyncTombstone.id > last_t)
            .order_by(models.SyncTombstone.id)
            .limit(300)
            .all()
        )
        if not rows and not ts:
            return sent
        body = {
            "server_id": ME,
            "rows": rows,
            "tombstones": [{"table": t.table_name, "uuid": t.record_uuid} for t in ts],
        }
        r = requests.post(HUB + "/sync/push", json=body, headers=HEADERS, timeout=30)
        r.raise_for_status()
        res = r.json()
        accepted = set(res.get("applied", [])) | set(res.get("aliased", []))
        # Skipped means the hub already has this version or a newer one, so these are done too.
        # Waiting rows stay marked and are sent again next round, after their parents.
        done = [
            x for x in rows if x["uuid"] in accepted or x["uuid"] in set(res.get("skipped", []))
        ]
        sync_core.mark_clean(db, done)
        if ts:
            set_state(db, "push_tombstone_id", ts[-1].id)
        set_state(db, "last_push_at", datetime.utcnow().isoformat())
        db.commit()
        sent += len(accepted) + len(ts)
        if res.get("waiting"):
            log("%d record(s) waiting for related records; will retry." % len(res["waiting"]))
        if not done and not ts:
            return sent


def pull(db):
    got = 0
    while True:
        since = int(state(db, "pull_seq", "0"))
        r = requests.get(
            HUB + "/sync/pull",
            params={"since": since, "exclude_origin": ME},
            headers=HEADERS,
            timeout=30,
        )
        r.raise_for_status()
        res = r.json()
        if res.get("rows"):
            applied, _skipped, _aliased, _waiting = sync_core.apply_rows(db, res["rows"])
            got += len(applied)
        if res.get("tombstones"):
            got += len(sync_core.apply_tombstones(db, res["tombstones"]))
        set_state(db, "pull_seq", res.get("next", since))
        set_state(db, "last_pull_at", datetime.utcnow().isoformat())
        db.commit()
        if not res.get("more"):
            return got


def main():
    if not KEY:
        sys.exit("SYNC_KEY is not set in .env. Add it, then start the agent again.")
    log("Sync agent started. Hub: %s, every %d s." % (HUB, EVERY))
    online = None
    while True:
        db = database.SessionLocal()
        try:
            sent = push(db)
            db.info.pop("sync_import", None)
            got = pull(db)
            if online is not True:
                log("Connected to the hub.")
            online = True
            if sent or got:
                log("Sent %d change(s), received %d change(s)." % (sent, got))
            if got:
                try:
                    requests.post(LOCAL + "/sync/notify", headers=HEADERS, timeout=5)
                except requests.RequestException:
                    pass
        except requests.RequestException as e:
            db.rollback()
            if online is not False:
                log(
                    "Hub not reachable (%s). Working offline; changes will be sent later."
                    % type(e).__name__
                )
            online = False
        except Exception as e:  # keep the agent alive, report the problem
            db.rollback()
            log("Problem during sync: %s" % e)
        finally:
            db.close()
        time.sleep(EVERY)


if __name__ == "__main__":
    main()
