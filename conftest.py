"""Shared pytest fixtures for the BilisLikas 2.0 backend test suite.

Design decision: tests run against a fresh in-memory SQLite database instead
of the real Postgres container. This is deliberate for this thesis prototype:

  - No risk of ever touching the real bilislikas_db data (the one with
    cityadmin/brgytest and any real test evacuees already in it).
  - Each test gets a brand new, empty database (tables created fresh in the
    db_session fixture, dropped again afterward), so tests never interfere
    with each other and don't depend on run order.
  - SQLite in-memory is instant to set up/tear down, which matters on this
    laptop's 8 GB RAM / i5-7200U - spinning up a second Postgres container
    or database per test run would be slower and heavier for no real benefit
    at this scale.

This only works because models.py doesn't use any Postgres-only column
types (no ARRAY, no native JSON type, etc.) - if that ever changes, this
fixture would need to switch to a real (throwaway) Postgres test database
instead.
"""

import os
import sys

# Make sure the project root (where main.py, models.py, etc. live) is
# importable regardless of what directory pytest is invoked from.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

import database
import models
import main


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        models.Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    """A TestClient wired to the in-memory test database instead of Postgres."""

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    main.app.dependency_overrides[database.get_db] = override_get_db
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()


# ---- Reference data fixtures --------------------------------------------

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


# ---- Auth fixtures --------------------------------------------------------

@pytest.fixture()
def admin_headers(client):
    """Bootstraps the very first city_admin account (only works once, while
    the users table is empty - same as POST /users in real use) and returns
    ready-to-use Authorization headers for it."""
    client.post(
        "/users",
        json={
            "username": "test_admin",
            "password": "TestAdmin123!",
            "role": "city_admin",
        },
    )
    resp = client.post(
        "/login",
        data={"username": "test_admin", "password": "TestAdmin123!"},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def staff_headers(client, admin_headers, barangay):
    """A barangay_official account for `barangay`, created the same way the
    kiosk/Pi client would authenticate."""
    resp = client.post(
        "/admin/users",
        json={
            "username": "test_staff",
            "password": "TestStaff123!",
            "role": "barangay_official",
            "barangay_id": barangay["id"],
        },
        headers=admin_headers,
    )
    assert resp.status_code in (200, 201), resp.text

    login_resp = client.post(
        "/login",
        data={"username": "test_staff", "password": "TestStaff123!"},
    )
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


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
