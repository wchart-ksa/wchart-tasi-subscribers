"""رحلات الزائر والمصادقة: الصفحات العامة، التسجيل، الدخول، الخروج، الاستعادة."""
import hashlib
from datetime import datetime, timedelta

import support
from common import STATUS_ACTIVE, STATUS_DISABLED, STATUS_INACTIVE
from security import PH


def test_public_pages_render(client):
    for url in ("/", "/auth/login", "/auth/register", "/auth/forgot"):
        resp = client.get(url)
        assert resp.status_code == 200, url
    assert client.get("/static/logo.svg").status_code == 200


def test_unknown_url_returns_404(client):
    assert client.get("/no-such-page").status_code == 404


def test_register_creates_inactive_hashed_user(store, client):
    r = support.post(client, "/auth/register", {
        "username": "ali_1", "email": "Ali@Example.com", "phone": "+966558030717",
        "password": "Secret123", "confirm": "Secret123",
    })
    assert r.status_code == 200
    u = store.find_user(username="ali_1")
    assert u is not None
    assert u["status"] == STATUS_INACTIVE
    assert u["phone"] == "0558030717"
    assert u["email"] == "ali@example.com"
    assert u["password_hash"].startswith("$2")


def test_register_rejects_invalid_and_duplicates(store, client):
    bad = support.post(client, "/auth/register", {
        "username": "x", "email": "no-at", "phone": "1", "password": "a", "confirm": "b"})
    assert bad.status_code == 200
    assert store.find_user(username="x") is None

    support.seed_user(store, "dupuser", "0501111111", "Secret123")
    dup = support.post(client, "/auth/register", {
        "username": "dupuser", "email": "fresh@example.com",
        "phone": "0502222222", "password": "Secret123", "confirm": "Secret123"})
    assert dup.status_code == 200
    assert store.find_user(phone="0502222222") is None


def test_register_requires_csrf(store, client):
    resp = client.post("/auth/register", data={
        "username": "nocsrf", "email": "n@example.com", "phone": "0503333333",
        "password": "Secret123", "confirm": "Secret123"})
    assert resp.status_code == 400
    assert store.find_user(username="nocsrf") is None


def test_login_wrong_then_locked(client, store):
    support.seed_user(store, "lockme", "0504444444", "Secret123")
    for _ in range(5):
        support.login(client, "lockme", "wrong-password")
    blocked = support.login(client, "lockme", "wrong-password")
    assert blocked.status_code == 200
    assert "حجب" in blocked.get_data(as_text=True)


def test_login_inactive_redirects_to_activate(client, store):
    support.seed_user(store, "inactive1", "0505555555", "Secret123", status=STATUS_INACTIVE)
    resp = support.login(client, "inactive1", "Secret123")
    assert resp.status_code == 302
    assert "/user/activate" in resp.headers["Location"]


def test_login_disabled_is_rejected(client, store):
    support.seed_user(store, "disabled1", "0506666666", "Secret123", status=STATUS_DISABLED)
    resp = support.login(client, "disabled1", "Secret123")
    assert resp.status_code == 200
    assert "معطل" in resp.get_data(as_text=True)


def test_logout_clears_session(client, store):
    support.seed_user(store, "byeuser", "0507777777", "Secret123")
    support.login(client, "byeuser", "Secret123")
    resp = support.post(client, "/auth/logout")
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_forgot_request_limit(client, store):
    support.seed_user(store, "reqme", "0508888888", "Secret123")
    for _ in range(3):
        support.post(client, "/auth/forgot", {"identifier": "0508888888"})
    resp = support.post(client, "/auth/forgot", {"identifier": "0508888888"})
    assert "تجاوز الحد" in resp.get_data(as_text=True)


def test_reset_with_valid_code(client, store):
    support.seed_user(store, "forgotme", "0509999999", "OldPass123")
    code = "123456"
    store.append("Resets", {
        "phone": "0509999999",
        "code_hash": hashlib.sha256(code.encode("utf-8")).hexdigest(),
        "expires_at": (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S"),
        "attempts": "0",
    })
    resp = support.post(client, "/auth/reset", {
        "phone": "0509999999", "code": code,
        "password": "NewPass456", "confirm": "NewPass456"})
    assert resp.status_code == 302
    user = store.find_user(phone="0509999999")
    changed, _ = PH.verify("NewPass456", user["password_hash"], user["salt"])
    assert changed
    still_old, _ = PH.verify("OldPass123", user["password_hash"], user["salt"])
    assert not still_old


def test_reset_with_wrong_code(client, store):
    support.seed_user(store, "forgotme2", "0501010101", "OldPass123")
    store.append("Resets", {
        "phone": "0501010101",
        "code_hash": hashlib.sha256(b"999999").hexdigest(),
        "expires_at": (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S"),
        "attempts": "0",
    })
    resp = support.post(client, "/auth/reset", {
        "phone": "0501010101", "code": "000000",
        "password": "NewPass123", "confirm": "NewPass123"})
    assert resp.status_code == 200
    assert "غير صحيح" in resp.get_data(as_text=True)
    old = store.find_user(phone="0501010101")
    ok, _ = PH.verify("OldPass123", old["password_hash"], old["salt"])
    assert ok
