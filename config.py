"""
إعدادات التطبيق.

جميع القيم الحساسة (SECRET_KEY، بيانات البريد) تُقرأ من متغيرات البيئة
أو ملف .env ولا تُكتب داخل الكود أبداً.
"""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# تحميل ملف .env إن وجد (لا يُنشر مع الاستضافة)
try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except Exception:  # pragma: no cover - python-dotenv غير مثبت
    pass


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def load_config() -> dict:
    """يعيد قاموس إعدادات جاهزاً لحقنها في تطبيق Flask."""
    env = os.environ.get("ENV", "production").strip().lower()
    production = env == "production"

    secret = os.environ.get("SECRET_KEY", "").strip()
    if not secret:
        # مفتاح مؤقت عند الإقلاع بدون .env (تتبدّل الجلسات عند إعادة التشغيل)
        secret = secrets.token_hex(32)
        print(
            "[تحذير] لم يُضبط SECRET_KEY في البيئة — تم إنشاء مفتاح مؤقت. "
            "ضعه في ملف .env قبل النشر (انظر .env.example)."
        )

    data_file = Path(os.environ.get("DATA_FILE", "subscribers_1.xlsx"))
    if not data_file.is_absolute():
        data_file = BASE_DIR / data_file

    backup_dir = Path(os.environ.get("BACKUP_DIR", "backups"))
    if not backup_dir.is_absolute():
        backup_dir = BASE_DIR / backup_dir

    return {
        "SECRET_KEY": secret,
        "ENV_PRODUCTION": production,
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        # كوكي آمن فقط خلف HTTPS في الإنتاج
        "SESSION_COOKIE_SECURE": production,
        "PERMANENT_SESSION_LIFETIME_DAYS": _int("SESSION_DAYS", 7),
        "DATA_FILE": str(data_file),
        "BACKUP_DIR": str(backup_dir),
        # بيانات الموقع العامة (تُعرض في القوالب)
        "SITE_TITLE": os.environ.get("SITE_TITLE", "مشتركين منصة دبليوشارت تاسي"),
        "WHATSAPP_NUMBER": os.environ.get("WHATSAPP_NUMBER", "0558030717"),
        "SUPPORT_EMAIL": os.environ.get("SUPPORT_EMAIL", "wchart.ksa@gmail.com"),
        "CODE_URL": os.environ.get(
            "CODE_URL", "https://wchart.new.aryaf.sa/categories/tasi"
        ),
        "DISCLAIMER_TEXT": os.environ.get(
            "DISCLAIMER_TEXT",
            "هذه البوابة مخصّصة لإدارة ومتابعة اشتراكات مشتركي منصة دبليوشارت تاسي فقط، "
            "ولا تقدّم أي توصيات استثمارية أو تحليلات مالية. جميع البيانات المعروضة لأغراض "
            "إدارية وتنظيمية. الاشتراك شخصي وغير قابل للمشاركة. للاستفسار والدعم تواصل معنا "
            "عبر قنوات التواصل الرسمية المذكورة أعلاه.",
        ),
        # البريد عبر Gmail SMTP (STARTTLS على المنفذ 587)
        "SMTP_HOST": os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        "SMTP_PORT": _int("SMTP_PORT", 587),
        "SMTP_USER": os.environ.get("SMTP_USER", "wchart.ksa@gmail.com"),
        "SMTP_PASSWORD": os.environ.get("SMTP_PASSWORD", ""),
        "MAIL_FROM": os.environ.get("MAIL_FROM", "wchart.ksa@gmail.com"),
        "MAIL_REPLY_TO": os.environ.get("MAIL_REPLY_TO", os.environ.get("MAIL_FROM", "wchart.ksa@gmail.com")),
        # سياسات الأمان وحدود المحاولات
        "ACTIVATION_DAYS": _int("ACTIVATION_DAYS", 30),
        "LOGIN_MAX_ATTEMPTS": _int("LOGIN_MAX_ATTEMPTS", 5),
        "LOGIN_LOCK_MINUTES": _int("LOGIN_LOCK_MINUTES", 15),
        "ACTIVATE_MAX_ATTEMPTS": _int("ACTIVATE_MAX_ATTEMPTS", 5),
        "ACTIVATE_LOCK_MINUTES": _int("ACTIVATE_LOCK_MINUTES", 15),
        "RESET_MAX_REQUESTS": _int("RESET_MAX_REQUESTS", 3),
        "RESET_WINDOW_MINUTES": _int("RESET_WINDOW_MINUTES", 60),
        "RESET_MAX_ATTEMPTS": _int("RESET_MAX_ATTEMPTS", 5),
        "RESET_LOCK_MINUTES": _int("RESET_LOCK_MINUTES", 15),
        "RESET_CODE_TTL_MINUTES": _int("RESET_CODE_TTL_MINUTES", 15),
        # إعدادات خادم التطوير (يُشغَّل عبر python app.py)
        "FLASK_HOST": os.environ.get("FLASK_HOST", "127.0.0.1"),
        "FLASK_PORT": _int("FLASK_PORT", 5000),
        "FLASK_DEBUG": os.environ.get("FLASK_DEBUG", "true").strip().lower() in ("1", "true", "yes", "on"),
    }
