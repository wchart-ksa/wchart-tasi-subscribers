"""
مهمة صيانة يومية: نسخة احتياطية + فحص انتهاء الاشتراكات.

تُستخدم مع Cron على الاستضافة (cPanel) أو يدوياً:

    python scripts/daily_maintenance.py

وهي آمنة للتشغيل المتكرر:
- تنشئ نسخة احتياطية واحدة فقط في اليوم (backups/<اسم الملف>_YYYY-MM-DD.xlsx).
- تحوّل الحسابات «مفعل» التي انتهى تاريخها إلى «منتهي» فقط.
"""
import sys
from pathlib import Path

# إتاحة استيراد وحدات المشروع عند التشغيل من أي مكان
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import load_config
from storage.excel_store import ExcelStore


def main() -> int:
    cfg = load_config()
    store = ExcelStore(cfg["DATA_FILE"], cfg["BACKUP_DIR"])
    store.init_file()

    backup = store.ensure_backup()
    swept = store.sweep_expired()

    print(f"[صيانة] ملف البيانات: {cfg['DATA_FILE']}")
    print(f"[صيانة] النسخة الاحتياطية: {backup if backup else 'لم تُنشأ (الملف غير موجود)'}")
    print(f"[صيانة] حسابات حُوّلت إلى «منتهي»: {swept}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
