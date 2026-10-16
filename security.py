"""
خدمات الأمان والتوقيع والبريد والحدود.

- تشفير كلمة السر: bcrypt (أقل تعقيداً ونشيط على ويندوز). للتوافق مع البيانات
  الموجودة في الملف، تُفحص أيضاً صيغة SHA-256 + salt إن اكتُشفت.
- جلسات: تُدار من قبل Flask عبر SECRET_KEY ووضع الكوكي.
- حماية CSRF: توليد/التحقق عبر فئة بسيطة باستخدام flask.session.
- تسجيل المحاولات الخاطئة (دخول، تفعيل، استعادة) لمنع الهجوم.
- إرسال البريد عبر SMTP (Gmail: STARTTLS على المنفذ 587) باستخدام كلمة مرور التطبيق.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import smtplib
import time
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

try:
    import bcrypt
except Exception:
    bcrypt = None  # سيُرفض إنشاء سيسلت جديد إن غير متوفّر، لكن الملف فيه قيم موجودة


@dataclass(frozen=True)
class _Bucket:
    key: str
    max: int
    window: int  # ثواني
    lock: int  # ثواني للإيقاف


def _bucket(key: str, typ: str) -> _Bucket:
    cfg = {
        "login": (5, 60 * 15, 60 * 15),
        "activate": (5, 60 * 15, 60 * 15),
        "reset_req": (3, 60 * 60, 60 * 15),
        "reset_try": (5, 60 * 15, 60 * 15),
    }
    m, w, l = cfg.get(typ, (5, 60 * 5, 60 * 10))
    return _Bucket(f"limit:{typ}:{key}", m, w, l)


class RateLimiter:
    """حد بسيط ذاكرة (يُجرى داخل عملية واحدة؛ الإنتاج أحادي العملية عادةً)."""

    def __init__(self):
        # حافظات: _attempts[key] = [(ts, ok?), ...] | locked_until
        self._attempts: dict[str, list[tuple[float, bool]]] = {}
        self._locked: dict[str, float] = {}

    def is_locked(self, key: str) -> tuple[bool, int]:
        until = self._locked.get(key, 0.0)
        if until > time.time():
            return True, max(1, int(until - time.time()) // 60)
        # تفكيك تلقائي إن انقضى
        if until > 0.0:
            self._locked.pop(key, None)
        return False, 0

    def record(self, key: str, ok: bool, typ: str) -> None:
        b = _bucket(key, typ)
        now = time.time()
        lst = self._attempts.setdefault(b.key, [])
        # إزالة خارج النافذة
        lst[:] = [(ts, res) for ts, res in lst if ts > now - b.window]
        if not ok:
            lst.append((now, False))
            if len(lst) >= b.max:
                self._locked[key] = now + b.lock
        else:
            # نجاح — يمسح أي قفل سابق وسجل الفشل
            self._locked.pop(key, None)
            lst.clear()

    def prune(self) -> None:
        now = time.time()
        for k, lst in list(self._attempts.items()):
            lst[:] = [(ts, res) for ts, res in lst if ts > now - 7200]
            if not lst:
                self._attempts.pop(k, None)
        for k, until in list(self._locked.items()):
            if until <= now:
                self._locked.pop(k, None)


RL = RateLimiter()


class PasswordHasher:
    """تشفير كلمة السر مع دعم التوافق مع الصيغة القديمة SHA-256+salt."""

    def __init__(self):
        self.use_bcrypt = bcrypt is not None

    def hash(self, password: str) -> tuple[str, str | None]:
        if not self.use_bcrypt:
            raise RuntimeError("bcrypt غير متوفر؛ غير قادر على توليد تشفير حديث آمن")
        pwd = password.encode("utf-8")
        salt_bytes = bcrypt.gensalt()
        hashed = bcrypt.hashpw(pwd, salt_bytes)
        return hashed.decode("ascii"), None

    def needs_upgrade(self, stored: str) -> bool:
        if not stored:
            return False
        if stored.startswith("scrypt:") or stored.startswith("bcrypt:"):
            return False
        return True

    def verify(self, password: str, stored: str, salt: str | None = None) -> tuple[bool, bool]:
        """
        يتحقق من كلمة السر.
        يعيد (مطابق، يحتاج ترقية) — يحتاج ترقية إذا كانت الصيغة قديمة فازداد توافقاً.
        """
        if not password or not stored:
            return False, False
        pwd = password.encode("utf-8")
        stored_bytes = stored.encode("ascii", errors="ignore")
        if stored.startswith("$2"):
            try:
                return bcrypt.checkpw(pwd, stored_bytes), False
            except Exception:
                return False, False
        # صيغة قديمة متوقعة: SHA-256(password+salt) أو تخزين مركب (تم حفظها في الملف)
        # الملف يحتوي على password_hash في صيغة scrypt:* في بعض الحالات؟ راجعنا الملف: بعض الصفوف scrypt:32768...
        if stored.startswith("scrypt:"):
            try:
                # معالجة بسيطة لنموذج scrypt الأصلي الموجود (فقط للتوافق مع نموذج الاختبار)
                parts = stored.split("$")
                if len(parts) == 3:
                    _, salt_hex, hash_hex = parts
                    salt_b = bytes.fromhex(salt_hex)
                    calc = hashlib.scrypt(pwd, salt=salt_b, n=32768, r=8, p=1, dklen=64)
                    return hmac.compare_digest(calc.hex(), hash_hex), False
            except Exception:
                pass
        # محاولة أخرى: قد يكون الـhash + salt مفصولين بشكل مختلف
        if salt:
            try:
                calc = hashlib.sha256((password + str(salt)).encode("utf-8")).hexdigest()
                return hmac.compare_digest(calc, stored.lower()), True
            except Exception:
                pass
        # آخر محاولة: مطابقة مباشرة إذا كان تخزين SHA-256 فقط
        try:
            calc2 = hashlib.sha256(pwd).hexdigest()
            return hmac.compare_digest(calc2, stored.lower()), True
        except Exception:
            pass
        return False, False


PH = PasswordHasher()


class CSRFProtect:
    """حماية بسيطة ضد CSRF للفورمات POST عبر الجلسة."""

    def token(self) -> str:
        # يعيد نفس الرمز خلال صلاحيته (ساعة) حتى لو استُدعي عدة مرات في الصفحة
        from flask import session

        token = session.get("_csrf_token")
        ts = session.get("_csrf_time", 0.0)
        if not token or (time.time() - ts) > 3600:
            token = secrets.token_urlsafe(32)
            session["_csrf_token"] = token
            session["_csrf_time"] = time.time()
        return token

    def verify(self, token: str | None) -> bool:
        from flask import session

        if not token:
            return False
        saved = session.get("_csrf_token")
        if not saved:
            return False
        # عمر قصير (ساعة)
        ts = session.get("_csrf_time", 0.0)
        if time.time() - ts > 3600:
            session.pop("_csrf_token", None)
            session.pop("_csrf_time", None)
            return False
        return hmac.compare_digest(str(saved), str(token))


csrf = CSRFProtect()


def send_mail(smtp_cfg: dict, to_email: str, subject: str, html: str, text: str = "") -> bool:
    """
    إرسال بريد Gmail عبر SMTP (STARTTLS 587).
    لتفادي إساءة الاستخدام في وضع الاختبار يُسمح بإرجاع True إذا لم تُضبط SMTP_PASSWORD
    لكن يوصى بضبطها فعلياً في الإنتاج. في هذا المشروع نُبلغ المستخدم بالتواصل عبر واتساب عند الفشل.
    """
    user = smtp_cfg.get("SMTP_USER") or ""
    pwd = smtp_cfg.get("SMTP_PASSWORD") or ""
    host = smtp_cfg.get("SMTP_HOST", "smtp.gmail.com")
    port = smtp_cfg.get("SMTP_PORT", 587)
    if not pwd or not user:
        # لا توجد بيانات بريد — لا نُعطّل مسار المستخدم لكن نترك استثناء/تحذير لطبقة أعلى
        raise RuntimeError("لم تُضبط بيانات SMTP_PASSWORD/SMTP_USER في متغيرات البيئة")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_cfg.get("MAIL_FROM") or user
    msg["To"] = to_email
    msg["Reply-To"] = smtp_cfg.get("MAIL_REPLY_TO") or msg["From"]

    if text:
        msg.attach(MIMEText(text, "plain", "utf-8"))
    if html:
        msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.ehlo()
            s.starttls()
            s.ehlo()
            s.login(user, pwd)
            s.sendmail(msg["From"], [to_email], msg.as_string())
        return True
    except Exception:
        raise


# إعادة استثناءات مفهومة قليلاً عند الفشل
class SecurityError(Exception):
    pass
