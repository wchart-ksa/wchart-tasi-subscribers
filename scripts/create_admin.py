"""
سكربت لإنشاء حساب أدمن افتراضي أو أدمن مخصص.

يُنفذ مرة واحدة (أول تشغيل مثالي) ولا يدخل في مسارات التطبيق.
لا يُنشئ حساب أدمن عبر التسجيل العام أبداً.
"""
import argparse
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

BASE_DIR = Path(__file__).resolve().parent.parent
if load_dotenv:
    load_dotenv(BASE_DIR / ".env")

sys.path.insert(0, str(BASE_DIR))

from config import load_config
from common import ROLE_ADMIN, STATUS_ACTIVE, normalize_phone, is_valid_phone, now_str
from security import PH
from storage.excel_store import ExcelStore, append_row, log_row, sheet_rows, USERS


def main():
    parser = argparse.ArgumentParser(
        description="إنشاء حساب أدمن لأول مرة أو إضافي من سطر الأوامر"
    )
    parser.add_argument("--username", default="admin")
    parser.add_argument("--phone", default="0504169042")
    parser.add_argument("--email", default="wchart.ksa@gmail.com")
    parser.add_argument("--password", default="AdminPass123")
    args = parser.parse_args()

    cfg = load_config()
    store = ExcelStore(cfg["DATA_FILE"], cfg["BACKUP_DIR"])
    store.init_file()

    phone = normalize_phone(args.phone)
    if not is_valid_phone(phone):
        print("خطأ: رقم الجوال يجب أن يكون بصيغة سعودية 05XXXXXXXX")
        sys.exit(1)

    # التحقق من وجود أدمن بنفس الجوال/اسم المستخدم
    with store.read() as wb:
        rows = sheet_rows(wb, USERS)

    def exists(**cond):
        for r in rows:
            if r.get("ID") and all(str(r.get(k, "")).strip().lower() == str(v).strip().lower() for k, v in cond.items()):
                return True
        return False

    if exists(phone=phone) or exists(username=args.username):
        print("يوجد حساب بنفس اسم المستخدم أو رقم الجوال بالفعل. لم يتم إنشاء حساب جديد.")
        return

    pw_hash, _ = PH.hash(args.password)
    admin_row = {
        "ID": __import__("uuid").uuid4(),
        "username": args.username.strip(),
        "email": args.email.strip().lower(),
        "phone": phone,
        "password_hash": pw_hash,
        "salt": "",
        "role": ROLE_ADMIN,
        "status": STATUS_ACTIVE,
        "created_at": now_str(),
        "activated_at": now_str(),
        "expires_at": "2099-12-31 23:59:59",
        "last_login": "",
        "disabled_at": "",
        "notes": "أدمن النظام",
    }

    with store.write() as wb:
        append_row(wb, USERS, admin_row)
        log_row(
            wb,
            "النظام",
            "إنشاء أدمن من سكربت",
            f"phone={phone}",
            f"username={admin_row['username']}",
            "تم",
        )

    print("تم إنشاء حساب الأدمن بنجاح:")
    print("اسم المستخدم:", admin_row["username"])
    print("رقم الجوال:", phone)
    print("البريد:", admin_row["email"])
    print("كلمة السر:", args.password)
    print("ملاحظة: لا تشارك ملف .env ولا تحفظ كلمة السر داخل الشيفرة.")


if __name__ == "__main__":
    import uuid

    main()
