# النشر على استضافة cPanel — دليل تفصيلي

هذا الدليل يشرح نشر «مشتركين منصة دبليوشارت تاسي» على استضافة تعمل بـ **cPanel**
وتدعم **Setup Python App** (Passenger).

> بدائل لا يحتاجها هذا الدليل: على Linux عام استخدم `gunicorn` + `nginx`، وعلى ويندوز استخدم `waitress`.

افتراضات الأمثلة:
- اسم مستخدم cPanel: `wchartk` — **بدّله باسمك الحقيقي**.
- مجلد التطبيق: `wchart_app`.

---

## ٠) المتطلبات المسبقة

- استضافة cPanel فيها خيار **Setup Python App**.
- صلاحية **Terminal** أو **SSH** (تسهّل الخطوات كثيراً).
- دومين موجّه للاستضافة.
- بيانات Gmail + **App Password** (انظر القسم 4 في `README.md`).

---

## ١) إنشاء تطبيق Python في cPanel

1. cPanel ← **Setup Python App** ← **Create Application**.
2. املأ الحقول:
   - **Python version**: أحدث نسخة متاحة (3.11/3.12/3.13).
   - **Application root**: `wchart_app` ← **اكتبها بدون `public_html/`**، فيصبح المسار `/home/wchartk/wchart_app`.
   - **Application URL**: دومينك.
   - **Application startup file**: `passenger_wsgi.py`
   - **Application Entry point**: `application`
3. اضغط **Create**.

سيُعرض أمر مشابه (احتفظ به):

```bash
source /home/wchartk/virtualenv/wchart_app/3.12/bin/activate
cd /home/wchartk/wchart_app
```

> **لماذا خارج `public_html`؟** لأن المشروع يحتوي `.env` وملف `subscribers_1.xlsx`.
> لو وُضعا داخل مجلد الويب لأمكن تحميلهما مباشرة من المتصفح — خطر أمني كبير.

---

## ٢) رفع ملفات المشروع

### الخيار الأول: عبر Git (الأسرع)

```bash
cd /home/wchartk/wchart_app
git clone https://github.com/wchart-ksa/wchart-tasi-subscribers.git .
```

> النقطة `.` في النهاية ترفع محتوى المستودع داخل المجلد نفسه.

### الخيار الثاني: عبر File Manager

1. نزّل المشروع: GitHub ← **Code → Download ZIP**.
2. **File Manager** ← ادخل `/home/wchartk/wchart_app` (أنشئه إن لم يوجد).
3. ارفع الـZIP ← **Extract**.
4. تأكد أن `app.py` و`passenger_wsgi.py` في جذر المجلد مباشرة (لا داخل مجلد فرعي).

### ضبط الصلاحيات

```bash
cd /home/wchartk/wchart_app
find . -type d -exec chmod 755 {} \;
find . -type f -exec chmod 644 {} \;
```

---

## ٣) تثبيت المتطلبات

```bash
source /home/wchartk/virtualenv/wchart_app/3.12/bin/activate
cd /home/wchartk/wchart_app
pip install --upgrade pip
pip install -r requirements.txt
```

> على الاستضافة يمكن حذف سطر `waitress` من `requirements.txt` (Passenger هو الخادم)،
> لكن إبقاؤه لا يضر.

تحقق:

```bash
pip list | grep -Ei "flask|openpyxl|dotenv|bcrypt"
```

---

## ٤) إنشاء ملف `.env`

من **File Manager** أنشئ ملف `.env` داخل `/home/wchartk/wchart_app`:

```ini
SECRET_KEY=ضع-هنا-مفتاحاً-عشوائياً-طويلاً
ENV=production
DATA_FILE=subscribers_1.xlsx
BACKUP_DIR=backups
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=wchart.ksa@gmail.com
SMTP_PASSWORD=كلمة-مرور-التطبيق-App-Password
MAIL_FROM=wchart.ksa@gmail.com
MAIL_REPLY_TO=wchart.ksa@gmail.com
SESSION_DAYS=7
ACTIVATION_DAYS=30
```

توليد `SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

> **مهم**: `ENV=production` يجعل كوكي الجلسة `Secure` — لا تفعّله قبل تشغيل HTTPS (الخطوة ٨).

> بديل: بعض إصدارات cPanel توفّر قسم **Environment variables** في صفحة التطبيق؛
> يمكنك إدخال القيم هناك بدلاً من `.env`. الأفضل استخدام `.env` لأن التطبيق يقرأه مباشرة.

---

## ٥) رفع ملف قاعدة البيانات

عبر **File Manager**:

1. ادخل `/home/wchartk/wchart_app`.
2. أنشئ مجلد `backups` (صلاحية 755).
3. ارفع `subscribers_1.xlsx` إلى `/home/wchartk/wchart_app` مباشرة.

تحقق:

```bash
ls -la /home/wchartk/wchart_app/subscribers_1.xlsx
ls -ld /home/wchartk/wchart_app/backups
```

> **لا ترفع هذا الملف إلى GitHub إطلاقاً** — فقط عبر File Manager/FTP إلى السيرفر.

---

## ٦) إنشاء حساب الأدمن

```bash
source /home/wchartk/virtualenv/wchart_app/3.12/bin/activate
cd /home/wchartk/wchart_app
python scripts/create_admin.py --username admin --phone 0504169042 --email wchart.ksa@gmail.com --password AdminPass123
```

بعد أول دخول غيّر كلمة السر من لوحة الأدمن.

---

## ٧) إعادة تشغيل التطبيق

من **Setup Python App** ← زر **Restart**.

أو من Terminal:

```bash
cd /home/wchartk/wchart_app
mkdir -p tmp
touch tmp/restart.txt
```

افتح دومينك: يجب أن تظهر الصفحة الرئيسية.

---

## ٨) تفعيل HTTPS (إلزامي مع `ENV=production`)

1. cPanel ← **SSL/TLS Status** ← حدّد دومينك ← **Run AutoSSL**.
2. أو **Let's Encrypt SSL** ← **Install**.
3. انتظر دقيقة ثم افتح `https://دومينك`.

لإجبار التحويل من HTTP إلى HTTPS، أنشئ `.htaccess` داخل `public_html`:

```apache
RewriteEngine On
RewriteCond %{HTTPS} off
RewriteRule ^(.*)$ https://%{HTTP_HOST}%{REQUEST_URI} [L,R=301]
```

ثم أعد تشغيل التطبيق (الخطوة ٧).

---

## ٩) المهمة اليومية (Cron)

التطبيق يفحص الانتهاء عند كل دخول، لكن يُستحسن جدولة مهمة يومية للنسخ الاحتياطي وفحص الانتهاء:

من **Cron Jobs** أضف مهمة يومية (مثلاً الساعة ٣ فجراً):

```bash
cd /home/wchartk/wchart_app && /home/wchartk/virtualenv/wchart_app/3.12/bin/python scripts/daily_maintenance.py >> /home/wchartk/wchart_app/daily.log 2>&1
```

> `scripts/daily_maintenance.py` ينشئ نسخة احتياطية واحدة يومياً ويحوّل الحسابات المنتهية إلى «منتهي».
> يمكن تشغيله يدوياً في أي وقت — آمن للتكرار.

---

## ١٠) التحقق النهائي

- [ ] فتح الموقع بـ HTTPS يعمل.
- [ ] تسجيل حساب جديد → رسالة الترحيب.
- [ ] دخول الأدمن → لوحة الأدمن.
- [ ] تفعيل حساب بكود من الشيت → الحالة «مفعل».
- [ ] «نسيت كلمة السر» → استلام رمز على البريد.
- [ ] امتلاء مجلد `backups/` بعد أول كتابة.

---

## ١١) حل المشاكل الشائعة

| المشكلة | السبب المحتمل | الحل |
|---|---|---|
| خطأ 500 | خطأ في الكود أو مكتبة ناقصة | `tail -50 ~/wchart_app/stderr.log` أو صفحة **Errors** |
| `ModuleNotFoundError: flask` | لم تُفعّل البيئة | فعّلها ثم `pip install -r requirements.txt` |
| `ModuleNotFoundError: bcrypt` | مكتبة ناقصة | `pip install bcrypt` ثم أعد التشغيل |
| `No such file: subscribers_1.xlsx` | الملف بمكان خطأ | ضعه في `/home/wchartk/wchart_app` |
| `PermissionError` على xlsx | صلاحيات/ملكية | `chmod 664 subscribers_1.xlsx` وتأكد أن المالك مستخدم cPanel |
| لا يحفظ الجلسة | `ENV=production` بدون HTTPS | فعّل SSL أو اجعل `ENV=development` مؤقتاً للاختبار |
| التعديلات لا تظهر | لم يُعد التشغيل | `touch tmp/restart.txt` |

---

## ١٢) نقاط أمنية مهمة

| النقطة | الإجراء |
|---|---|
| `.env` و`subscribers_1.xlsx` | يبقيان **خارج** `public_html` |
| صلاحيات الملفات | `644` للملفات و`755` للمجلدات |
| HTTPS | إلزامي مع `ENV=production` |
| GitHub | لا تُرفع البيانات الحقيقية أو `.env` |
| النسخ الاحتياطية | تُحفظ في `backups/` (آخر ٣٠ نسخة) |
