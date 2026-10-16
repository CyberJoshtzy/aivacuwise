# Refactor Plan: Splitting main.py into Routers

**Goal:** turn `main.py` from one large file (with patch-script blocks appended at the end) into small feature files, **without changing any URL, request, or response**. The Raspberry Pi client, kiosk, and dashboard must keep working with zero changes.

**Safety net:** the existing pytest suite (21 tests plus the password reset tests). Run `pytest -q` after every step. If a step breaks a test, undo that step with `git checkout -- .` and try again.

## Target layout

```
bilislikas2.0/
  main.py                  # create app, mount /static, include routers (about 30 lines)
  config.py                # reads .env settings in one place
  database.py              # engine, SessionLocal, get_db (unchanged)
  models.py                # SQLAlchemy models (unchanged for now)
  schemas.py               # Pydantic schemas (unchanged for now)
  auth.py                  # hashing, JWT, get_current_user, require_role (unchanged)
  connection_manager.py    # ConnectionManager class AND the shared `manager` instance
  routers/
    __init__.py
    users.py               # POST /users, POST /admin/users, POST /login, GET /users/me
    barangays.py           # /barangays
    centers.py             # /evacuation_centers (+ PUT/DELETE, evacuee list)
    evacuees.py            # /evacuees (+ facial_embedding, enrolled_faces, history, PUT/DELETE)
    checkin.py             # POST /checkin, POST /checkin/walkin
    transfers.py           # /transfers, /evacuees/{id}/transfers
    households.py          # /households, /barangays/{id}/households, status
    trackers.py            # /trackers, /gps_pings
    dashboard.py           # GET /dashboard/summary, WS /ws/dashboard, page routes /dashboard, /kiosk
    password_reset.py      # moved from the project root
  services/
    __init__.py
    occupancy.py           # get_current_evacuees_at_center (the "latest event" rule)
  scripts/archive/         # old patch_*.py, fix_*.py, set_emails.py (kept for history, not run)
  alembic/                 # database migrations
  tests/
```

## Step 0: Prepare (one commit)

1. Make sure everything is committed and `pytest -q` passes.
2. Create a branch: `git checkout -b refactor/routers`
3. Move old one-off scripts: `mkdir -p scripts/archive && git mv patch_*.py fix_*.py set_emails.py scripts/archive/`
   (skip any file that does not exist).
4. Commit: `git commit -m "Move one-off patch scripts to scripts/archive"`

## Step 1: Move shared pieces out first (one commit)

These must move first, because routers will import them. If they stayed in `main.py`, every router would import `main.py` and `main.py` would import every router, which is a circular import error.

1. **The broadcast manager.** If `manager = ConnectionManager()` is created inside `main.py`, move that line to the bottom of `connection_manager.py`. Then in `main.py` use `from connection_manager import manager`.
2. **The occupancy helper.** Move `_get_current_evacuees_at_center` into `services/occupancy.py`, rename it `get_current_evacuees_at_center`, and import it in `main.py`.
3. Run `pytest -q`. Commit: `"Move broadcast manager and occupancy helper to shared modules"`

## Step 2: Move one feature at a time (one commit each)

Recommended order, smallest and least risky first:

1. `barangays.py`
2. `trackers.py`
3. `households.py`
4. `transfers.py`
5. `checkin.py`
6. `evacuees.py`
7. `centers.py`
8. `users.py`
9. `dashboard.py` (includes the WebSocket; do it last)
10. `password_reset.py` (just `git mv` it into `routers/` and fix its import in `main.py`)

For each feature:

1. Create `routers/<feature>.py` with the template below.
2. **Cut** (do not copy) the endpoint functions from `main.py` and paste them in.
3. Change `@app.get(...)` to `@router.get(...)` (same for post, put, delete, websocket).
4. In `main.py`, add `app.include_router(<feature>.router)`.
5. Run `pytest -q`, then restart the service and open the dashboard once to check.
6. Commit: `"Move <feature> endpoints to routers/<feature>.py"`

### Router template

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import auth
import models
import schemas
from connection_manager import manager
from database import get_db

router = APIRouter(tags=["transfers"])


@router.get("/transfers", response_model=list[schemas.TransferOut])
def list_transfers(db: Session = Depends(get_db)): ...
```

Do **not** add a `prefix=` to `APIRouter` during this refactor. Keeping the full path in each decorator guarantees the URLs stay exactly the same.

### Two things to watch for

- **Route order.** FastAPI matches routes in the order they are registered. A fixed path like `/evacuees/enrolled_faces` must be registered before a path with a variable in the same position, like `/evacuees/{evacuee_id}`. Keep them in the same order they had in `main.py`.
- **The edit and delete block.** The appended block at the end of `main.py` finds models with a helper `_bl_model(table)` that builds the table name at runtime. That workaround existed only because of copy-paste corruption of double underscores. When moving these endpoints, replace `_bl_model("evacuees")` with `models.Evacuee` and `_bl_model("evacuation_centers")` with `models.EvacuationCenter` (check the exact class names in `models.py`).

## Step 3: Final main.py

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from routers import (
    barangays,
    centers,
    checkin,
    dashboard,
    evacuees,
    households,
    password_reset,
    trackers,
    transfers,
    users,
)

app = FastAPI(title="BilisLikas 2.0 API")
app.mount("/static", StaticFiles(directory="static"), name="static")

for module in (
    users,
    barangays,
    centers,
    evacuees,
    checkin,
    transfers,
    households,
    trackers,
    dashboard,
    password_reset,
):
    app.include_router(module.router)
```

Keep any startup code that exists today (for example `models.Base.metadata.create_all(bind=engine)`) until Alembic is set up in Step 4.

## Step 4: Set up Alembic for schema changes (one commit)

This replaces manual `ALTER TABLE` commands for every future schema change (center coordinates, relief records, incidents, and so on).

1. `pip install alembic` (already in `requirements-dev.txt`), then `alembic init alembic`
2. In `alembic/env.py`, set `target_metadata = models.Base.metadata` (add `import models` near the top), and set the database URL from the same place `database.py` reads it.
3. Create an empty baseline that represents the current tables: `alembic revision -m "baseline"`
4. Mark the real database as already at that baseline, without changing it: `alembic stamp head`
5. From now on, after editing `models.py`: `alembic revision --autogenerate -m "add center coordinates"`, **read the generated file**, then `alembic upgrade head`.
6. Back up first, every time: `docker exec bilislikas_postgres pg_dump -U bilislikas_admin bilislikas_db > backup_$(date +%F).sql`

## Step 5: Finish

1. `ruff format .` then `ruff check . --fix`, run `pytest -q`, and commit the formatting alone as `"Format codebase with ruff"` (a separate commit keeps real changes easy to read).
2. Merge: `git checkout main && git merge refactor/routers && git push`
3. On the Pi, run `recognize.py` once to confirm check-ins still reach the server.

## Later (not needed before the defense)

- Split `models.py` and `schemas.py` per feature only if they become hard to read.
- Add tests for households, dashboard role filtering, and GPS pings.
- Replace `datetime.utcnow()` with `datetime.now(timezone.utc)`.
