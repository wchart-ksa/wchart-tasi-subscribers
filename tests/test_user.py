"""رحلات المستخدم: التفعيل، اللوحة، الملف الشخصي، تعطيل الحساب."""
import support
from common import STATUS_ACTIVE, STATUS_DISABLED, STATUS_INACTIVE
from security import PH
from storage.excel_store import CODES


def test_dashboard_requires_login(client):
    resp = client.get("/user/dashboard")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


def test_activate_success(client, store):
    support.seed_user(store, "uact", "0501010101", "Secret123", status=STATUS_INACTIVE)
    store.append(CODES, {"code": "ACT1234", "status": "", "used_by_phone": "", "used_at": ""})
    support.login(client, "uact", "Secret123")
    resp = support.post(client, "/user/activate", {"code": "ACT1234"}, follow=True)
    assert resp.status_code == 200
    u = store.find_user(phone="0501010101")
    assert u["status"] == STATUS_ACTIVE
    assert u["expires_at"]
    c = store.find_code("ACT1234")
    assert c["status"] == "مستخدم"
    assert c["used_by_phone"] == "0501010101"
    assert c["used_at"]


def test_activate_rejects_used_code(client, store):
    support.seed_user(store, "uact2", "0502010101", "Secret123", status=STATUS_INACTIVE)
    store.append(CODES, {"code": "USED12", "status": "مستخدم",
                         "used_by_phone": "0500000000", "used_at": "2026-01-01 00:00:00"})
    support.login(client, "uact2", "Secret123")
    resp = support.post(client, "/user/activate", {"code": "USED12"})
    assert resp.status_code == 200
    assert "مستخدم بالفعل" in resp.get_data(as_text=True)
    assert store.find_user(phone="0502010101")["status"] == STATUS_INACTIVE


def test_activate_rejects_unknown_code(client, store):
    support.seed_user(store, "uact3", "0503010101", "Secret123", status=STATUS_INACTIVE)
    support.login(client, "uact3", "Secret123")
    resp = support.post(client, "/user/activate", {"code": "NOPE9999"})
    assert resp.status_code == 200
    assert "غير صحيح" in resp.get_data(as_text=True)


def test_dashboard_shows_active_user(client, store):
    support.seed_user(store, "active1", "0504010101", "Secret123")
    support.login(client, "active1", "Secret123")
    resp = client.get("/user/dashboard")
    assert resp.status_code == 200
    assert "active1" in resp.get_data(as_text=True)


def test_profile_update_and_password_change(client, store):
    support.seed_user(store, "profile1", "0505010101", "Secret123")
    support.login(client, "profile1", "Secret123")
    resp = support.post(client, "/user/profile", {
        "username": "profile1new", "email": "newmail@example.com",
        "current_password": "Secret123", "new_password": "BetterPass9", "confirm": "BetterPass9",
    }, follow=True)
    assert resp.status_code == 200
    u = store.find_user(phone="0505010101")
    assert u["username"] == "profile1new"
    assert u["email"] == "newmail@example.com"
    ok, _ = PH.verify("BetterPass9", u["password_hash"], u["salt"])
    assert ok


def test_deactivate_own_account(client, store):
    support.seed_user(store, "deact1", "0506010101", "Secret123")
    support.login(client, "deact1", "Secret123")
    resp = support.post(client, "/user/deactivate", {"disable_password": "Secret123"})
    assert resp.status_code == 302
    assert store.find_user(phone="0506010101")["status"] == STATUS_DISABLED
