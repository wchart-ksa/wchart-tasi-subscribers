"""تجهيز بيئة الاختبار: ملف Excel مؤقت + تطبيق Flask معزول.

يجب ضبط متغيرات البيئة قبل استيراد app لأن الإعدادات تُقرأ عند الاستيراد.
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="tasi_tests_"))

os.environ["ENV"] = "development"
os.environ["SECRET_KEY"] = "test-secret-key-0123456789abcdef"
os.environ["DATA_FILE"] = str(_TMP / "subscribers_test.xlsx")
os.environ["BACKUP_DIR"] = str(_TMP / "backups")
os.environ["SMTP_PASSWORD"] = ""  # يمنع أي إرسال بريد حقيقي أثناء الاختبار

import pytest  # noqa: E402

import app as app_module  # noqa: E402
from security import RL  # noqa: E402


@pytest.fixture()
def store():
    """يعيد ملف بيانات نظيفاً ويسقط حدود المحاولات قبل كل اختبار."""
    s = app_module.store
    data_file = Path(s.data_file)
    if data_file.exists():
        data_file.unlink()
    backup_dir = Path(s.backup_dir)
    if backup_dir.exists():
        for leftover in backup_dir.glob("*"):
            try:
                leftover.unlink()
            except OSError:
                pass
    s.init_file()
    RL._attempts.clear()
    RL._locked.clear()
    return s


@pytest.fixture()
def client(store):
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c
