"""اختبارات الوحدات الأساسية: الجوال، التواريخ، تحييد Excel، طبقة التخزين، حدود المحاولات."""
from datetime import datetime, timedelta

import pytest

import support
from common import STATUS_ACTIVE, STATUS_EXPIRED, days_left, excel_safe, is_valid_phone, normalize_phone
from helpers import days_info, status_style
from security import RL


def test_phone_normalization():
    assert normalize_phone("+966558030717") == "0558030717"
    assert normalize_phone("966558030717") == "0558030717"
    assert normalize_phone("055 803 0717") == "0558030717"
    assert is_valid_phone("0558030717")
    assert not is_valid_phone("123456")


def test_days_left():
    assert days_left((datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")) == 3
    assert days_left("2000-01-01 00:00:00") == 0


def test_excel_safe_blocks_formulas():
    assert excel_safe("=cmd|'x'").startswith("'")
    assert excel_safe("عادي") == "عادي"


def test_helper_badges():
    assert status_style(STATUS_ACTIVE) == "badge-ok"
    assert status_style(STATUS_EXPIRED) == "badge-warn"
    assert days_info("2000-01-01 00:00:00")["status_cls"] == "badge-warn"


def test_store_write_creates_backup(store):
    support.seed_user(store, "core1", "0500000000", "Secret123")
    assert store.find_user(username="core1")
    from pathlib import Path

    assert list(Path(store.backup_dir).glob("*.xlsx"))


def test_store_rejects_unknown_sheet(store):
    with pytest.raises(KeyError):
        store.rows("Users2")


def test_sweep_expired_transitions_status(store):
    support.seed_user(store, "olduser", "0500000000", "Secret123", expires_at="2000-01-01 00:00:00")
    assert store.sweep_expired() == 1
    assert store.find_user(username="olduser")["status"] == STATUS_EXPIRED
    assert store.sweep_expired() == 0


def test_rate_limiter_locks_after_max_failures():
    RL._attempts.clear()
    RL._locked.clear()
    key = "login:someone"
    for _ in range(5):
        RL.record(key, ok=False, typ="login")
    locked, _mins = RL.is_locked(key)
    assert locked is True


def test_rate_limiter_success_clears_state():
    RL._attempts.clear()
    RL._locked.clear()
    key = "login:ok"
    for _ in range(3):
        RL.record(key, ok=False, typ="login")
    RL.record(key, ok=True, typ="login")
    locked, _mins = RL.is_locked(key)
    assert locked is False
