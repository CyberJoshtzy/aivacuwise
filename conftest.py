"""Shared pytest fixtures for the Ai-Vacuwise backend test suite.

Design decisions:

- Tests run against a fresh in-memory SQLite database, never the real
  PostgreSQL container. Each test gets a new, empty database.
- Every module-level `engine` and `SessionLocal` in the project (for example
  the activity-log middleware in iso_quality.py) is pointed at the test
  database while a test runs, so no test can write into bilislikas_db.
  This redirect happens after app startup, because startup code uses
  PostgreSQL-only ALTER TABLE statements.
- Tables defined outside models.py (login_logs, activity log, and so on) are
  created too, by collecting every SQLAlchemy MetaData object in the project.
- The app now requires login for almost every request (iso_quality.py
  middleware), and only the IT Administrator may call POST /users. So the
  test admin is created directly in the database, and the `client` fixture
  is signed in as that admin by default. To test an endpoint WITHOUT login,
  pass headers={"Authorization": ""} on that request.

This only works because models.py does not use PostgreSQL-only column types.
"""

import os
import sys

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import MetaData, create_engine  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import approvals  # noqa: E402
import auth  # noqa: E402
import database  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402

ADMIN_USERNAME = "test_admin"
ADMIN_EMAIL = "test_admin@bilislikas.local"
ADMIN_PASSWORD = "TestAdmin123!"  # test-only account in the in-memory database
STAFF_USERNAME = "test_staff"
STAFF_PASSWORD = "TestStaff123!"  # test-only account in the in-memory database

VENV_DIR = os.path.join(PROJECT_DIR, "venv")
TESTS_DIR = os.path.join(PROJECT_DIR, "tests")


# ---- Helpers ---------------------------------------------------------------


def _project_modules():
    """Imported modules that belong to this project (not venv, not tests)."""
    for mod in list(sys.modules.values()):
        path = getattr(mod, "__file__", None) or ""
        if (
            path.startswith(PROJECT_DIR + os.sep)
            and not path.startswith(VENV_DIR)
            and not path.startswith(TESTS_DIR)
        ):
            yield mod


def _all_metadata():
    """models.Base.metadata plus any other MetaData objects defined in the project."""
    found = [models.Base.metadata]
    for mod in _project_modules():
        for value in list(vars(mod).values()):
            if isinstance(value, MetaData) and all(value is not m for m in found):
                found.append(value)
    return found


def _redirect_database(test_engine, test_sessionmaker):
    """Point every module-level engine and SessionLocal at the test database.

    Returns what was replaced, so it can be restored after the test.
    """
    replaced = []
    for mod in _project_modules():
        for name, value in list(vars(mod).items()):
            if isinstance(value, Engine) and value is not test_engine:
                replaced.append((mod, name, value))
                setattr(mod, name, test_engine)
            elif name == "SessionLocal" and isinstance(value, sessionmaker):
                replaced.append((mod, name, value))
                setattr(mod, name, test_sessionmaker)
    return replaced


def _restore(replaced):
    for mod, name, value in replaced:
        setattr(mod, name, value)


def _login(test_client, username, password):
    resp = test_client.post("/login", data={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


# ---- Database and client ---------------------------------------------------


@pytest.fixture()
def test_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata_list = _all_metadata()
    for metadata in metadata_list:
        metadata.create_all(bind=engine)
    yield engine
    for metadata in reversed(metadata_list):
        metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def test_sessionmaker(test_engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture()
def db_session(test_sessionmaker):
    session = test_sessionmaker()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def admin_user(db_session):
    """The test city_admin, created directly in the test database."""
    user = models.User(
        username=ADMIN_USERNAME,
        email=approvals.IT_ADMIN_EMAIL,
        password_hash=auth.get_password_hash(ADMIN_PASSWORD),
        role="city_admin",
    )
    if hasattr(models.User, "account_status"):
        user.account_status = "active"
    if hasattr(models.User, "is_superuser"):
        user.is_superuser = True
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def client(db_session, test_engine, test_sessionmaker, admin_user):
    """A TestClient on the in-memory database, signed in as the test admin."""

    def override_get_db():
        yield db_session

    main.app.dependency_overrides[database.get_db] = override_get_db
    with TestClient(main.app) as test_client:
        # Startup has finished, so it is now safe to redirect every engine.
        replaced = _redirect_database(test_engine, test_sessionmaker)
        try:
            token = _login(test_client, ADMIN_USERNAME, ADMIN_PASSWORD)
            test_client.headers["Authorization"] = f"Bearer {token}"
            yield test_client
        finally:
            _restore(replaced)
    main.app.dependency_overrides.clear()


# ---- Auth fixtures ---------------------------------------------------------


@pytest.fixture()
def admin_headers(client):
    """Authorization headers for the test city_admin (the client already sends them)."""
    return {"Authorization": client.headers["Authorization"]}


@pytest.fixture()
def staff_headers(client, admin_headers, barangay):
    """A barangay_official account for `barangay`."""
    resp = client.post(
        "/admin/users",
        json={
            "username": STAFF_USERNAME,
            "password": STAFF_PASSWORD,
            "role": "barangay_official",
            "barangay_id": barangay["id"],
        },
        headers=admin_headers,
    )
    assert resp.status_code in (200, 201), resp.text
    token = _login(client, STAFF_USERNAME, STAFF_PASSWORD)
    return {"Authorization": f"Bearer {token}"}


# ---- Reference data fixtures -----------------------------------------------


@pytest.fixture()
def barangay(client):
    resp = client.post("/barangays", json={"name": "Test Barangay"})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


@pytest.fixture()
def center(client, barangay):
    resp = client.post(
        "/evacuation_centers",
        json={
            "name": "Test Elementary School",
            "address": "123 Test St",
            "capacity": 50,
            "barangay_id": barangay["id"],
        },
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


@pytest.fixture()
def second_center(client, barangay):
    resp = client.post(
        "/evacuation_centers",
        json={
            "name": "Second Test Center",
            "address": "456 Test Ave",
            "capacity": 50,
            "barangay_id": barangay["id"],
        },
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


# ---- Evacuee fixtures ------------------------------------------------------


@pytest.fixture()
def evacuee(client, barangay):
    resp = client.post(
        "/evacuees",
        json={
            "full_name": "Juan Dela Cruz",
            "birthdate": "1990-01-01",
            "sex": "male",
            "address": "789 Sample Rd",
            "contact_number": "09171234567",
            "registered_barangay_id": barangay["id"],
        },
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


# ---- Speed: fast bcrypt during tests only --------------------------------
# Real passwords use bcrypt's default cost (12 rounds, about 0.3 s per hash).
# Tests create and sign in accounts for every test, so they use 4 rounds.
# This changes nothing outside the test run.
import bcrypt  # noqa: E402

_real_gensalt = bcrypt.gensalt


def _fast_gensalt(rounds=4, prefix=b"2b"):
    return _real_gensalt(4, prefix)


bcrypt.gensalt = _fast_gensalt


# ---- Account approval --------------------------------------------------------


@pytest.fixture()
def approve(client, db_session):
    """Approve a pending account the way the City Hall IT Administrator would.

    The test client is signed in as the IT Administrator, so this calls the real
    POST /admin/users/{id}/approve endpoint.
    """

    def _approve(email):
        email = email.strip().lower()
        user = db_session.query(models.User).filter(models.User.email == email).first()
        assert user is not None, "no account for " + email
        resp = client.post(f"/admin/users/{user.id}/approve")
        assert resp.status_code == 200, resp.text
        return resp

    return _approve
