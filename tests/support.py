"""أدوات مساعدة لاختبارات الرحلات (بدون استيراد app)."""
import time

from common import ROLE_USER, STATUS_ACTIVE, now_str
from security import PH
from storage.excel_store import USERS

CSRF = "test-csrf-token"


def post(client, url, data=None, follow=False):
    """POST مع رمز CSRF صالح داخل الجلسة."""
    with client.session_transaction() as sess:
        sess["_csrf_token"] = CSRF
        sess["_csrf_time"] = time.time()
    payload = {"csrf_token": CSRF}
    if data:
        payload.update(data)
    return client.post(url, data=payload, follow_redirects=follow)


def seed_user(
    store,
    username,
    phone,
    password,
    status=STATUS_ACTIVE,
    role=ROLE_USER,
    email=None,
    expires_at="2099-01-01 00:00:00",
):
    """يضيف مستخدماً بتشفير bcrypt ويعيد صفه."""
    password_hash, _ = PH.hash(password)
    store.append(
        USERS,
        {
            "ID": f"id-{username}",
            "username": username,
            "email": email or f"{username}@example.com",
            "phone": phone,
            "password_hash": password_hash,
            "salt": "",
            "role": role,
            "status": status,
            "created_at": now_str(),
            "activated_at": now_str(),
            "expires_at": expires_at,
            "last_login": "",
            "disabled_at": "",
            "notes": "",
        },
    )
    return store.find_user(username=username)


def login(client, identifier, password, follow=False):
    return post(client, "/auth/login", {"identifier": identifier, "password": password}, follow=follow)
