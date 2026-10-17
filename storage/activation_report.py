"""
تقرير مشتق: المشتركون الذين فعّلوا كوداً — عمودان فقط (رقم الجوال، حالة التفعيل).

- يُبنى من ورقة Users في ملف البيانات الأساسي ولا يُقرأ منه شيء.
- يُعاد توليده بالكامل عند أي تغيّر في حالة الاشتراك ليبقى مطابقاً للبيانات.
- يُحفظ حفظاً ذرياً (ملف مؤقت ثم استبدال) حتى يبقى الملف قابلاً للقراءة دائماً.
"""
from __future__ import annotations

import os
import secrets
import time
from pathlib import Path

import openpyxl

from common import STATUS_ACTIVE, STATUS_INACTIVE
from storage.excel_store import USERS

HEADERS = ["رقم الجوال", "حالة التفعيل"]
SHEET = "المفعّلون"
DEFAULT_FILENAME = "activated_subscribers.xlsx"

ACTIVE_TEXT = "مفعل"
INACTIVE_TEXT = "غير مفعل"


def rows_for(store) -> list[tuple[str, str]]:
    """
    يعيد (رقم الجوال، حالة التفعيل) لكل من فعّل كوداً يوماً ما.

    يُستثنى فقط من لم يُفعّل أبداً (الحالة «غير مفعل» بلا تاريخ تفعيل)؛
    من أصبح «معطل» أو «منتهي» يبقى في التقرير بحالة «غير مفعل».
    """
    out: list[tuple[str, str]] = []
    for u in store.all_users():
        activated = bool((u.get("activated_at") or "").strip())
        if not activated and u.get("status") == STATUS_INACTIVE:
            continue
        phone = (u.get("phone") or "").strip()
        if not phone:
            continue
        state = ACTIVE_TEXT if u.get("status") == STATUS_ACTIVE else INACTIVE_TEXT
        out.append((phone, state))
    return out


def sync(store, path) -> Path:
    """يعيد بناء ملف التقرير بالكامل ليطابق الحالة الحالية، ويعيد مساره."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = SHEET
    ws.append(HEADERS)
    for phone, state in rows_for(store):
        ws.append([phone, state])

    tmp = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
    try:
        wb.save(tmp)
    finally:
        wb.close()

    last_error = None
    for _ in range(5):  # الملف قد يكون مفتوحاً في Excel مؤقتاً
        try:
            os.replace(tmp, path)
            last_error = None
            break
        except OSError as exc:
            last_error = exc
            time.sleep(0.15)
    if last_error is not None:
        tmp.unlink(missing_ok=True)
        raise last_error
    return path
