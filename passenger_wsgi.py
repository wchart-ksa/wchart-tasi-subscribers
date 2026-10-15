"""
نقطة تشغيل التطبيق على استضافة cPanel (Passenger).

cPanel يبحث عن متغير باسم `application` في هذا الملف.
لا حاجة لتعديله — فقط ضعه في مجلد المشروع (Application root).
"""
import os
import sys

# إضافة مجلد المشروع إلى مسار الاستيراد (مطلوب على Passenger)
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from app import app as application  # noqa: E402
