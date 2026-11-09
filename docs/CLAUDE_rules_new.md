# Ai-Vacuwise: Rules for Claude

Read this file before making any change in this repository.

## What this project is

Ai-Vacuwise is an undergraduate Computer Engineering thesis prototype: a quick, smart evacuation tracking and management system for multi-barangay disaster response.

- **Laptop server** (Ubuntu 24.04 LTS, i5-7200U, 8 GB RAM): runs PostgreSQL 16 and Redis 7 in Docker, and this FastAPI backend as a systemd service (`bilislikas.service`, port 8000).
- **Raspberry Pi edge device** (`pi_client/`, separate from this repo's backend): does facial recognition with `face_recognition` (dlib) and calls this API (`GET /evacuees/enrolled_faces`, `POST /checkin`). BLE tracker scanning will also run there.
- **Frontend**: plain HTML/CSS/JS in `static/app/`, plus `static/kiosk.html` and `static/dashboard.html`. No build tools, no CDN. Fonts are stored locally.
- The system **must keep working with no internet**. Cloud services (Railway, Aiven, ngrok) are optional and must never be required for a core flow.

## Commands

```bash
source venv/bin/activate          # always, before pip or pytest
pytest -q                         # all tests must pass before every commit
ruff check .                      # lint (includes security rules)
ruff format .                     # format
sudo systemctl restart bilislikas # after changing any .py file
journalctl -u bilislikas -f       # server logs
```

HTML, CSS, and JS edits do not need a server restart. After changing `app.js` or `app.css`, bump the `?v=` query string on their `<link>`/`<script>` tags so Firefox does not serve a cached copy.

## Code structure rules

1. **Do not add endpoints to `main.py`.** `main.py` only creates the app, mounts `static/`, and includes routers. New endpoints go in `routers/<feature>.py` using `APIRouter`. See `docs/REFACTOR_PLAN.md` for the target layout.
2. **Shared logic goes in `services/`**, not copied between routers. Example: occupancy is always computed with the "latest check-in event by id" rule in `services/occupancy.py`. Never write a second occupancy query.
3. **Never change an existing URL path or response shape** without being asked. The Raspberry Pi client, the kiosk, and the dashboard depend on them.
4. **Database schema changes use Alembic migrations** (`alembic revision --autogenerate -m "..."`), never manual `ALTER TABLE`. SQLAlchemy `create_all` does not alter existing tables.
5. Keep functions short (about 50 lines or less). If a function grows past that, split it.
6. Do not add a new dependency without explaining why it is needed and how much RAM it uses. This laptop has 8 GB.
7. Do not write one-off patch scripts that edit other source files. Edit the files directly.

## Testing rules

- Every new or changed endpoint needs a test in `tests/`.
- Tests use an in-memory SQLite database through the `get_db` override in `conftest.py`. They must never connect to the real PostgreSQL database.
- Do not use PostgreSQL-only column types in `models.py`; it would break the SQLite test setup.
- A change is not done until `pytest -q` passes.

## Security rules

- Secrets live only in `.env` (git-ignored). Never hardcode passwords, keys, tokens, or email credentials. Never print them in logs.
- Never read `.env` aloud in chat or copy its values into code, docs, or commit messages.
- Every endpoint that reads or changes evacuee data requires login (`auth.get_current_user`). City-wide actions require `auth.require_role("city_admin")`.
- A `barangay_official` may only read or change records of their own `barangay_id`. Enforce this on the server, never only in the UI.
- Passwords are hashed with `bcrypt` directly (not passlib). Reset codes are stored only as HMAC hashes.
- Use SQLAlchemy queries or bound parameters. Never build SQL with string formatting.
- Facial embeddings and evacuee personal data are sensitive (Data Privacy Act of 2012, RA 10173). Do not log them, and do not return them from endpoints that do not need them.

## Style

- Python: formatted with `ruff format`, imports sorted by ruff.
- Use `datetime.now(timezone.utc)` instead of the deprecated `datetime.utcnow()` in new code.
- User-facing text: simple, formal English. Avoid em dashes.

## Git

- One feature or fix per commit, with a clear message.
- Run `git status` before committing and make sure `.env`, `venv/`, and `*.bak_*` files are not staged.
