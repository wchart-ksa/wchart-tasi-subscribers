"""
وظائف المساعدة لطبقة العرض (حقن القوالب).
"""
from datetime import datetime

from common import (
    DT_FMT, ROLE_ADMIN, ROLE_USER, STATUS_ACTIVE, STATUS_DISABLED,
    STATUS_EXPIRED, STATUS_INACTIVE, days_left, is_expired, now_dt, normalize_phone,
    parse_dt,
)


def fmt_dt(v):
    dt = parse_dt(v)
    return dt.strftime("%Y-%m-%d %H:%M") if dt else ""


def days_info(expires_at):
    dt = parse_dt(expires_at)
    if not dt:
        return {"days": 0, "status_cls": "badge-neutral", "text": "غير محدد"}
    left = days_left(expires_at)
    if left <= 0:
        return {"days": 0, "status_cls": "badge-warn", "text": "منتهي"}
    if left <= 7:
        return {"days": left, "status_cls": "badge-warn", "text": f"متبقي {left} أيام"}
    if left <= 14:
        return {"days": left, "status_cls": "badge-ok", "text": f"متبقي {left} أيام"}
    return {"days": left, "status_cls": "badge-ok", "text": f"متبقي {left} أيام"}


def status_style(status):
    s = str(status or "")
    if s == STATUS_ACTIVE:
        return "badge-ok"
    if s == STATUS_EXPIRED:
        return "badge-warn"
    if s == STATUS_DISABLED:
        return "badge-danger"
    if s == STATUS_INACTIVE:
        return "badge-neutral"
    return "badge-neutral"


def is_phone_display_only():
    return True
