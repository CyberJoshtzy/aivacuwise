"""Covers user authentication: login, and that protected routes actually
reject requests without a valid token (not just trusted to work)."""


def test_login_and_users_me(client, admin_headers):
    # admin_headers already proves POST /users + POST /login work; this
    # confirms the token it returns is actually usable on a protected route.
    resp = client.get("/users/me", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "test_admin"
    assert body["role"] == "city_admin"


def test_login_rejects_wrong_password(client, admin_headers):
    resp = client.post(
        "/login",
        data={"username": "test_admin", "password": "WrongPassword!"},
    )
    assert resp.status_code == 401


def test_protected_route_rejects_missing_token(client):
    client.headers.pop("Authorization", None)  # this test checks the not-signed-in case
    resp = client.get("/users/me")
    assert resp.status_code == 401


def test_protected_route_rejects_garbage_token(client):
    resp = client.get("/users/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


def test_barangay_official_cannot_create_admin_users(client, staff_headers):
    # POST /admin/users requires city_admin specifically; a barangay_official
    # token should be rejected, not silently allowed.
    resp = client.post(
        "/admin/users",
        json={
            "username": "should_not_be_created",
            "password": "Whatever123!",
            "role": "barangay_official",
        },
        headers=staff_headers,
    )
    assert resp.status_code in (401, 403)
