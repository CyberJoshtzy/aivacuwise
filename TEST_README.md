# AiVacuwise backend test suite

Covers check-in, walk-in registration, transfers (including the occupancy
accuracy fix), authentication, and the two facial recognition endpoints the
Raspberry Pi client depends on.

## How it works

Tests run against a fresh in-memory SQLite database, not your real Postgres
container. Nothing here touches `bilislikas_db` or the test data already in
it (`cityadmin`, `brgytest`, the households you registered, etc). Each test
gets its own empty database that is created and thrown away automatically.

## Setup (run once)

1. Copy `conftest.py`, `pytest.ini`, `requirements-test.txt`, and the
   `tests/` folder into `~/aivacuwise`, alongside `main.py`.
2. In a terminal:

```
cd ~/aivacuwise
source venv/bin/activate
pip install -r requirements-test.txt
```

## Running the tests

```
cd ~/aivacuwise
source venv/bin/activate
pytest -v
```

The backend server (`uvicorn`) does NOT need to be running for this - the
tests call the FastAPI app directly in-process, they don't make real HTTP
requests to port 8000.

## If something fails on the first run

This suite was written from the documented API behavior in the setup log,
not by reading main.py/schemas.py directly, so a few field names or status
codes might not match exactly on the first run (for example, if `sex` is
stored as an Enum with different casing than "male"/"female", or a create
endpoint returns 201 instead of 200 in a way the test didn't expect). That's
expected and normal for a first pass. Paste me the `pytest -v` output and
I'll adjust the fixtures/tests to match your actual code.

## Adding more tests later

Follow the same pattern as the existing test files: use the `client` fixture
for an authenticated-or-not TestClient, and `staff_headers`/`admin_headers`
for protected routes. Good next candidates once this first batch passes:
household registration (`POST /households`), the dashboard summary endpoint
role-filtering (once a second barangay exists), and the GPS ping endpoints.
