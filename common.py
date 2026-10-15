"""
دوال مشتركة صغيرة تستخدمها بقية طبقات المشروع (وقت، تواريخ، توحيد الجوال،
تحييد الخلايا ضد حقن الصيغ في Excel).
"""
import re
from datetime import datetime, timedelta

# صيغة التخزين الموحدة للتواريخ داخل الملف
DT_FMT = "%Y-%m-%d %H:%M:%S"

# قيم افتراضية
STATUS_INACTIVE = "غير مفعل"
STATUS_ACTIVE = "مفعل"
STATUS_EXPIRED = "منتهي"
STATUS_DISABLED = "معطل"

ROLE_USER = "user"
ROLE_ADMIN = "admin"


def now_str() -> str:
    """التاريخ والوقت الحاليين بالصيغة الموحدة."""
    return datetime.now().strftime(DT_FMT)


def now_dt() -> datetime:
    return datetime.now()


def parse_dt(value) -> datetime | None:
    """يحوّل قيمة مقروءة من Excel إلى كائن تاريخ (أو None إن كانت فارغة/غير صالحة)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in (DT_FMT, "%Y-%m-%d %H:%M", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def add_days(base: datetime, days: int) -> datetime:
    return base + timedelta(days=days)


def days_left(expires_at) -> int:
    """الأيام المتبقية حتى الانتهاء (0 إذا منتهٍ)."""
    exp = parse_dt(expires_at)
    if not exp:
        return 0
    remaining = exp - datetime.now()
    if remaining.total_seconds() <= 0:
        return 0
    # تقريب لأعلى: اشتراك ينتهي اليوم يُعدّ يوماً واحداً متبقياً
    return max(1, -(-int(remaining.total_seconds()) // 86400))


def is_expired(expires_at) -> bool:
    exp = parse_dt(expires_at)
    return exp is not None and datetime.now() >= exp


_PHONE_RE = re.compile(r"^(05\d{8})$")


def normalize_phone(raw) -> str:
    """
    يوحّد رقم الجوال السعودي إلى صيغة 05XXXXXXXX.
    يقبل: 05XXXXXXXX أو +9665XXXXXXXX أو 9665XXXXXXXX أو 5XXXXXXXX (10 خانات) أو أرقام بفواصل/مسافات.
    يعيد النص كما هو (المُنقّى) إن لم يكن صالحاً — التحقق النهائي يتم بـ is_valid_phone.
    """
    text = str(raw or "").strip()
    text = text.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if text.startswith("+"):
        text = text[1:]
    if text.startswith("00966"):
        text = "966" + text[5:]
    if text.startswith("966"):
        text = "0" + text[3:]
    if text.startswith("00"):
        text = text[2:]
    # إن بدأ بالصفر متبوعاً برقم غير 5 حوّله كما هو للتحقق
    return text


def is_valid_phone(raw) -> bool:
    return bool(_PHONE_RE.match(normalize_phone(raw)))


# الخلايا التي تبدأ بـ = + - @ قد تنفَّذ كصيغ عند فتح الملف في Excel
def excel_safe(value):
    """تحييد النصوص الخطرة قبل كتابتها في Excel أو CSV."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def csv_safe(value):
    """تحييد خلايا CSV بنفس منطق Excel."""
    return excel_safe(value)
