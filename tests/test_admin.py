"""رحلات الأدمن: الحماية بالأدوار، الأكواد، التمديد، التعطيل، التصدير، الأسرار."""
from datetime import datetime, timedelta

import support
from common import ROLE_ADMIN, ROLE_USER, STATUS_ACTIVE, STATUS_DISABLED, parse_dt
from storage.excel_store import EXTENSIONS

ADMIN_PHONE = "0509990000"
ADMIN_PASS = "AdminPass1"


def _login_admin(client, store):
    support.seed_user(store, "admin1", ADMIN_PHONE, ADMIN_PASS, role=ROLE_ADMIN,
                      expires_at="2099-12-31 23:59:59")
    return support.login(client, "admin1", ADMIN_PASS)


def test_non_admin_gets_403(client, store):
    support.seed_user(store, "plain", "0501110000", "Secret123", role=ROLE_USER)
    support.login(client, "plain", "Secret123")
    assert client.get("/admin/dashboard").status_code == 403


def test_admin_pages_render(client, store):
    _login_admin(client, store)
    for url in ["/admin/dashboard", "/admin/users", "/admin/codes", "/admin/logs",
                "/admin/extensions", "/admin/reset-any", "/admin/change-admin"]:
        assert client.get(url).status_code == 200, url


def test_admin_codes_add_and_dedupe(client, store):
    _login_admin(client, store)
    support.post(client, "/admin/codes/add", {"codes": "AB12, ab12, X9, GOODCODE"})
    codes = {c["code"] for c in store.all_codes()}
    assert codes == {"AB12", "GOODCODE"}


def test_admin_extension_adds_days(client, store):
    _login_admin(client, store)
    before_str = (datetime.now() + timedelta(days=5)).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    phone = "0502220000"
    support.seed_user(store, "ext1", phone, "Secret123", status=STATUS_ACTIVE, expires_at=before_str)
    support.post(client, "/admin/extensions", {"phones": phone, "days": "10", "reason": "اختبار"})
    u = store.find_user(phone=phone)
    assert parse_dt(u["expires_at"]) - parse_dt(before_str) == timedelta(days=10)
    assert store.rows(EXTENSIONS)


def test_admin_toggle_user(client, store):
    _login_admin(client, store)
    phone = "0503330000"
    support.seed_user(store, "tog1", phone, "Secret123", status=STATUS_ACTIVE)
    support.post(client, f"/admin/users/toggle/{phone}")
    assert store.find_user(phone=phone)["status"] == STATUS_DISABLED
    support.post(client, f"/admin/users/toggle/{phone}")
    assert store.find_user(phone=phone)["status"] == STATUS_ACTIVE


def test_admin_export_csv(client, store):
    _login_admin(client, store)
    support.seed_user(store, "csv1", "0504440000", "Secret123")
    resp = client.get("/admin/users?export=csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["Content-Type"]
    assert b"csv1" in resp.data


def test_admin_save_note(client, store):
    _login_admin(client, store)
    phone = "0505550000"
    support.seed_user(store, "note1", phone, "Secret123")
    support.post(client, f"/admin/users/note/{phone}", {"note": "ملاحظة مهمة"})
    assert store.find_user(phone=phone)["notes"] == "ملاحظة مهمة"


def test_admin_reset_any_changes_password(client, store):
    _login_admin(client, store)
    phone = "0506660000"
    support.seed_user(store, "reset1", phone, "Secret123")
    old_hash = store.find_user(phone=phone)["password_hash"]
    resp = support.post(client, "/admin/reset-any", {"phone": phone})
    assert resp.status_code == 200
    assert store.find_user(phone=phone)["password_hash"] != old_hash


def test_admin_can_add_admin(client, store):
    _login_admin(client, store)
    resp = support.post(client, "/admin/change-admin", {
        "action": "add", "admin_password": ADMIN_PASS,
        "username": "admin2", "phone": "0507770000",
        "email": "admin2@example.com", "new_password": "SecondPass1", "confirm": "SecondPass1",
    })
    assert resp.status_code in (200, 302)
    new_admin = store.find_user(username="admin2")
    assert new_admin and new_admin["role"] == ROLE_ADMIN
