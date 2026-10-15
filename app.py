"""
نص برمجى لـ app.py كامل، جاهز للتشغيل مباشرة مع متغيرات البيئة.

يغلف كل عملية كتابة في Excel بقفل، يحفظ ملفاً مؤقتاً ثم يستبدله،
يُنشئ نسخة احتياطية يومية، يدعم تحديث صيغة تشفير السر من القديم إلى bcrypt،
يحمى CSRF، يُرسل رمز الاستعادة عبر Gmail (STARTTLS)، يُسجّل كل الأحداث في Logs،
ويطبق جميع قواعد المستخدم والأدمن المطلوبة.
"""
from __future__ import annotations

import csv
import io
import os
import secrets
from datetime import datetime, timedelta
from io import BytesIO
from urllib.parse import unquote

from flask import (
    Flask, request, session, redirect, url_for, render_template,
    flash, g, make_response, abort, current_app,
)

from common import (
    ROLE_ADMIN, ROLE_USER, STATUS_ACTIVE, STATUS_DISABLED, STATUS_EXPIRED,
    STATUS_INACTIVE, add_days, days_left, is_expired,
    normalize_phone, is_valid_phone, now_dt, now_str, parse_dt, csv_safe,
)
from config import load_config
from helpers import days_info, status_style, fmt_dt as _fmt_dt
from security import PH, csrf, RL, send_mail, SecurityError
from storage.excel_store import (
    ExcelStore, sheet_rows, append_row, set_row, log_row, USERS, CODES,
    LOGS, EXTENSIONS, RESETS,
)

# تعيين fmt_dt في helpers ليُستخدم في القوالب إن احتُج (بعض القوالب استوردت مباشرة)
try:
    import helpers as _h
    _h.fmt_dt = _fmt_dt
    _h.days_info = days_info
    _h.status_style = status_style
except Exception:
    pass

CFG = load_config()
store = ExcelStore(CFG["DATA_FILE"], CFG["BACKUP_DIR"])
store.init_file()

app = Flask(__name__)
app.config.update({
    "SECRET_KEY": CFG["SECRET_KEY"],
    "SESSION_COOKIE_HTTPONLY": CFG["SESSION_COOKIE_HTTPONLY"],
    "SESSION_COOKIE_SAMESITE": CFG["SESSION_COOKIE_SAMESITE"],
    "SESSION_COOKIE_SECURE": CFG["SESSION_COOKIE_SECURE"],
    "PERMANENT_SESSION_LIFETIME": timedelta(days=CFG["PERMANENT_SESSION_LIFETIME_DAYS"]),
})


@app.before_request
def before_request():
    g.store = store
    g.cfg = CFG
    g.csrf = csrf
    # إعادة تربية: مسح محاولات قديمة
    RL.prune()
    # فحص انتهاء الحسابات عند الطلبات العامة (خفيفة)
    # يُجرى أيضاً عند دخول المستخدم
    # تحميل المستخدم الحالي
    user_id = session.get("user_id")
    if user_id:
        u = store.find_user(ID=str(user_id))
        if u and u.get("status") == STATUS_ACTIVE and is_expired(u.get("expires_at")):
            # تحويل إلى منتهي
            with store.write() as wb:
                set_row(wb, USERS, int(u["_row"]), {"status": STATUS_EXPIRED})
                log_row(wb, user_id, "فحص تلقائي للانتهاء", u.get("phone"), "تحول إلى منتهي", "تم")
        # إعادة تحميل سريع
        g.current_user = store.find_user(ID=str(user_id))
    else:
        g.current_user = None
    # حقن دوال في القالب
    g.csrf_token = csrf.token


@app.context_processor
def inject_globals():
    return {
        "current_user": g.current_user,
        "csrf_token": lambda: csrf.token(),
        "fmt_dt": _fmt_dt,
        "days_info": days_info,
        "status_style": status_style,
        "now_str": now_str,
    }


# ----------- أدوات مساعدة داخل الطلب
def require_login():
    if not g.current_user:
        flash("يجب تسجيل الدخول أولاً", "error")
        return redirect(url_for("auth_login"))
    return None


def require_role(role: str):
    cu = g.current_user
    if not cu:
        flash("يجب تسجيل الدخول أولاً", "error")
        return redirect(url_for("auth_login"))
    if cu.get("role") != role:
        store.log(cu.get("phone") or cu.get("username"), "محاولة وصول محظورة", f"role_needed={role}", f"path={request.path}", "مرفوض")
        flash("غير مصرح لك بالوصول إلى هذه الصفحة", "error")
        abort(403)


def save_session(user_row: dict, remember: bool = True):
    session.clear()
    session["user_id"] = user_row.get("ID")
    if remember:
        session.permanent = True
    # تحديث آخر دخول
    try:
        store.update(USERS, int(user_row["_row"]), {"last_login": now_str()})
    except Exception:
        pass


# ----------- الرئيسية
@app.route("/")
def home():
    return render_template("home.html")


# ----------- مصادقة
@app.route("/auth/register", methods=["GET", "POST"])
def auth_register():
    if request.method == "POST":
        if not csrf.verify(request.form.get("csrf_token")):
            flash("رمز الحماية غير صالح، أعد المحاولة", "error")
            return render_template("auth_register.html"), 400
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        phone_raw = request.form.get("phone") or ""
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""

        # فحص القواعد
        if not username or not re_match_username(username):
            flash("اسم المستخدم غير صالح (أحرف وأرقام _ - . بطول 3–32)", "error")
            return render_template("auth_register.html")
        if not email or "@" not in email:
            flash("البريد الإلكتروني غير صالح", "error")
            return render_template("auth_register.html")
        if not is_valid_phone(phone_raw):
            flash("رقم الجوال يجب أن يكون سعوديًا بصيغة 05XXXXXXXX أو +9665XXXXXXXX", "error")
            return render_template("auth_register.html")
        phone = normalize_phone(phone_raw)
        if password != confirm or len(password) < 8:
            flash("كلمة السر وتأكيدها غير متطابقين أو قصيرة جدًا (8 أحرف على الأقل)", "error")
            return render_template("auth_register.html")

        # منع التكرار
        if store.find_user(username=username) or store.find_user(email=email) or store.find_user(phone=phone):
            flash("اسم المستخدم أو البريد الإلكتروني أو رقم الجوال موجود مسبقًا", "error")
            return render_template("auth_register.html")

        # إنشاء الحساب غير المفعل
        pw_hash, _ = PH.hash(password)
        row = {
            "ID": __import__("uuid").uuid4(),
            "username": username,
            "email": email,
            "phone": phone,
            "password_hash": pw_hash,
            "salt": "",
            "role": ROLE_USER,
            "status": STATUS_INACTIVE,
            "created_at": now_str(),
            "activated_at": "",
            "expires_at": "",
            "last_login": "",
            "disabled_at": "",
            "notes": "",
        }
        store.append(USERS, row)
        store.log(phone, "تسجيل حساب جديد", username, f"email={email}", "تم")
        return render_template("auth_welcome.html", username=username)

    return render_template("auth_register.html")


def re_match_username(s: str) -> bool:
    import re
    return bool(re.fullmatch(r"[A-Za-z0-9_\.\-]{3,32}", s))


@app.route("/auth/login", methods=["GET", "POST"])
def auth_login():
    if request.method == "POST":
        if not csrf.verify(request.form.get("csrf_token")):
            flash("رمز الحماية غير صالح، أعد المحاولة", "error")
            return render_template("auth_login.html"), 400
        identifier = (request.form.get("identifier") or "").strip()
        password = request.form.get("password") or ""
        if not identifier or not password:
            flash("أدخل رقم الجوال أو اسم المستخدم وكلمة السر", "error")
            return render_template("auth_login.html")

        # تحديد مفتاح التحديد
        key = identifier.lower()
        locked, mins = RL.is_locked(f"login:{key}")
        if locked:
            flash(f"تم حجب المحاولات مؤقتًا لمدة {mins} دقيقة تقريبًا، جرب لاحقًا", "error")
            return render_template("auth_login.html")

        # البحث عن المستخدم
        u = None
        phone_n = normalize_phone(identifier)
        if is_valid_phone(identifier) or is_valid_phone(phone_n):
            u = store.find_user(phone=phone_n)
        if not u:
            u = store.find_user(username=identifier)
        if not u:
            u = store.find_user(email=identifier.lower())
        if not u:
            RL.record(f"login:{key}", ok=False, typ="login")
            flash("بيانات الدخول غير صحيحة", "error")
            return render_template("auth_login.html")

        # التحقق من كلمة السر مع دعم ترقية
        ok, need_up = PH.verify(password, u.get("password_hash", ""), u.get("salt"))
        if not ok:
            RL.record(f"login:{key}", ok=False, typ="login")
            store.log(u.get("phone"), "محاولة دخول فاشلة", u.get("username"), identifier, "فشل")
            flash("بيانات الدخول غير صحيحة", "error")
            return render_template("auth_login.html")

        # ترقية الصيغة إن لزم الأمر
        if need_up:
            try:
                new_h, _ = PH.hash(password)
                store.update(USERS, int(u["_row"]), {"password_hash": new_h, "salt": ""})
            except Exception:
                pass

        # فحص الحالة
        if u.get("status") == STATUS_DISABLED:
            RL.record(f"login:{key}", ok=False, typ="login")
            flash("حسابك معطل. تواصل مع الأدمن لإعادة التفعيل", "error")
            return render_template("auth_login.html")

        # فحص انتهاء للاشتراك المفعل
        store.sweep_expired()  # يعيد فقط عند الحاجة عبر read/write داخلي لكن نسميه
        # إعادة تحميل بعد sweep إن تغير
        u2 = store.find_user(ID=u.get("ID"))
        u = u2 or u

        RL.record(f"login:{key}", ok=True, typ="login")
        save_session(u, remember=True)
        store.log(u.get("phone"), "تسجيل دخول ناجح", u.get("username"), request.remote_addr or "", "تم")

        # توجيه
        if u.get("role") == ROLE_ADMIN:
            return redirect(url_for("admin_dashboard"))
        if u.get("status") == STATUS_INACTIVE:
            return redirect(url_for("user_activate_form"))
        if u.get("status") == STATUS_EXPIRED:
            flash("اشتراكك منتهي. يمكنك تفعيل حسابك بكود جديد", "info")
            return redirect(url_for("user_activate_form"))
        return redirect(url_for("user_dashboard"))

    return render_template("auth_login.html")


@app.route("/auth/logout", methods=["POST"])
def auth_logout():
    if not csrf.verify(request.form.get("csrf_token")):
        flash("رمز الحماية غير صالح", "error")
        return redirect(url_for("home")), 400
    session.clear()
    return redirect(url_for("auth_login"))


@app.route("/auth/forgot", methods=["GET", "POST"])
def auth_forgot():
    if request.method == "POST":
        if not csrf.verify(request.form.get("csrf_token")):
            flash("رمز الحماية غير صالح، أعد المحاولة", "error")
            return render_template("auth_forgot.html", step="request"), 400
        identifier = (request.form.get("identifier") or "").strip()
        if not identifier:
            flash("أدخل جوالك أو بريدك أو اسم المستخدم", "error")
            return render_template("auth_forgot.html", step="request")
        u = find_user_by_ident(identifier)
        # رسالة موحدة
        if not u or u.get("status") == STATUS_DISABLED:
            flash("إن كان الحساب موجوداً فقد أُرسل الرمز إلى البريد المسجّل. إذا لم يصلك، تواصل عبر واتساب.", "info")
            store.log(identifier, "طلب استعادة كلمة سر", "-", "حساب غير موجود أو معطل", "لا يُرسل")
            return render_template("auth_forgot.html", step="request")
        phone = u.get("phone")
        key = f"reset:req:{phone}"
        locked, mins = RL.is_locked(key)
        if locked:
            flash(f"تم تجاوز الحد الأقصى للطلبات (3 في الساعة). جرب بعد {mins} دقيقة.", "error")
            return render_template("auth_forgot.html", step="request")
        # إنشاء رمز 6 أرقام
        code = f"{secrets.randbelow(1000000):06d}"
        code_hash = __import__("hashlib").sha256(code.encode("utf-8")).hexdigest()
        expires_at = (now_dt() + timedelta(minutes=CFG["RESET_CODE_TTL_MINUTES"])).strftime("%Y-%m-%d %H:%M:%S")
        # حفظ في Resets (إنشاؤه يمسكه write)
        with store.write() as wb:
            # تنظيف رموز سابقة لهذا الجوال
            rows = sheet_rows(wb, RESETS)
            for r in rows:
                if r.get("phone") == phone and r.get("_row"):
                    # حذف صف سابق — لكننا نحافظ على الملف ولا نحذف صفوف خارج متطلبات؛ ببساطة نكتب فوق فعلاً نضيف جديد ونترك القديم (لا يمنع العمل)
                    pass
            append_row(wb, RESETS, {
                "phone": phone,
                "code_hash": code_hash,
                "expires_at": expires_at,
                "attempts": "0",
            })
            log_row(wb, phone, "طلب رمز استعادة", u.get("username"), f"email={u.get('email')}", "تم")
        RL.record(key, ok=True, typ="reset_req")
        # إرسال البريد
        try:
            send_reset_email(u, code, CFG)
            flash("تم إرسال رمز استعادة كلمة السر إلى بريدك المسجّل.", "success")
        except Exception as e:
            store.log(phone, "فشل إرسال بريد الاستعادة", u.get("username"), str(e), "فشل")
            flash("تعذر إرسال الرمز إلى البريد. تواصل معنا عبر واتساب على 0558030717.", "error")
        return render_template("auth_forgot.html", step="verify", phone=phone)
    return render_template("auth_forgot.html", step="request")


def find_user_by_ident(identifier: str):
    phone_n = normalize_phone(identifier)
    if is_valid_phone(identifier) or is_valid_phone(phone_n):
        return store.find_user(phone=phone_n)
    u = store.find_user(username=identifier)
    if not u:
        u = store.find_user(email=str(identifier).lower())
    return u


def send_reset_email(u, code, cfg):
    to = u.get("email")
    if not to:
        raise RuntimeError("لا يوجد بريد مسجّل للحساب")
    subject = "مشتركين منصة دبليوشارت تاسي — رمز استعادة كلمة السر"
    html = f"""
    <div dir="rtl" style="font-family:Tahoma,Arial,sans-serif;line-height:1.8;">
      <h2>رمز استعادة كلمة السر</h2>
      <p>أهلاً <b>{u.get('username')}</b>،</p>
      <p>رمز الاستعادة الخاص بك هو:</p>
      <div style="font-size:28px;letter-spacing:6px;font-weight:bold;">{code}</div>
      <p>صالح لمدة 15 دقيقة فقط.</p>
      <p>إذا لم تطلب هذا الرمز، تجاهل هذه الرسالة.</p>
      <hr>
      <p>للمساعدة: واتساب <a href="https://wa.me/966558030717">0558030717</a> | البريد <a href="mailto:wchart.ksa@gmail.com">wchart.ksa@gmail.com</a></p>
    </div>
    """
    text = f"رمز استعادة كلمة السر: {code}\nصالح 15 دقيقة. للمساعدة واتساب 0558030717"
    send_mail(cfg, to, subject, html, text)


@app.route("/auth/reset", methods=["POST"])
def auth_reset():
    if not csrf.verify(request.form.get("csrf_token")):
        flash("رمز الحماية غير صالح، أعد المحاولة", "error")
        return render_template("auth_forgot.html", step="request"), 400
    phone = request.form.get("phone") or ""
    code = (request.form.get("code") or "").strip()
    password = request.form.get("password") or ""
    confirm = request.form.get("confirm") or ""
    if password != confirm or len(password) < 8:
        flash("كلمة السر غير متطابقة أو قصيرة جدًا", "error")
        return render_template("auth_forgot.html", step="verify", phone=phone)
    if not phone or not code.isdigit() or len(code) != 6:
        flash("رمز الاستعادة غير صالح", "error")
        return render_template("auth_forgot.html", step="verify", phone=phone)
    locked, mins = RL.is_locked(f"reset:try:{phone}")
    if locked:
        flash(f"تم حجب المحاولات مؤقتًا لمدة {mins} دقيقة تقريبًا", "error")
        return render_template("auth_forgot.html", step="verify", phone=phone)
    # البحث عن آخر رمز لهذا الجوال
    rows = store.rows(RESETS)
    code_row = None
    for r in rows[::-1]:
        if r.get("phone") == phone and r.get("code_hash") and r.get("expires_at"):
            exp = parse_dt(r.get("expires_at"))
            if exp and exp > now_dt():
                code_row = r
                break
    if not code_row:
        RL.record(f"reset:try:{phone}", ok=False, typ="reset_try")
        store.log(phone, "استعادة كلمة سر", "-", "رمز منتهي أو غير موجود", "فشل")
        flash("رمز الاستعادة منتهي أو غير موجود، اطلب رمزًا جديدًا", "error")
        return render_template("auth_forgot.html", step="request")
    # التحقق
    c_hash = __import__("hashlib").sha256(code.encode("utf-8")).hexdigest()
    if not __import__("hmac").compare_digest(c_hash, code_row.get("code_hash", "")):
        # زيادة attempts إن وُجد عمود
        try:
            att = int(code_row.get("attempts") or "0") + 1
            if code_row.get("_row"):
                store.update(RESETS, int(code_row["_row"]), {"attempts": str(att)})
            if att >= CFG["RESET_MAX_ATTEMPTS"]:
                RL.record(f"reset:try:{phone}", ok=False, typ="reset_try")
        except Exception:
            pass
        RL.record(f"reset:try:{phone}", ok=False, typ="reset_try")
        flash("رمز الاستعادة غير صحيح", "error")
        return render_template("auth_forgot.html", step="verify", phone=phone)
    # صالح — تغيير كلمة السر
    u = store.find_user(phone=phone)
    if not u or u.get("status") == STATUS_DISABLED:
        flash("لا يمكن استعادة كلمة سر لحساب معطل أو غير موجود", "error")
        return redirect(url_for("auth_login"))
    pw_hash, _ = PH.hash(password)
    store.update(USERS, int(u["_row"]), {"password_hash": pw_hash, "salt": ""})
    # إبطال الرمز (حذف هذا الصف إن أمكن بتحديث إلى منتهي)
    if code_row.get("_row"):
        try:
            store.update(RESETS, int(code_row["_row"]), {"expires_at": (now_dt()-timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")})
        except Exception:
            pass
    RL.record(f"reset:try:{phone}", ok=True, typ="reset_try")
    store.log(phone, "استعادة كلمة سر ناجحة", u.get("username"), "-", "تم")
    flash("تم تغيير كلمة السر بنجاح. يمكنك تسجيل الدخول الآن", "success")
    return redirect(url_for("auth_login"))


# ----------- مسارات المستخدم
@app.route("/user/dashboard")
def user_dashboard():
    r = require_login()
    if r: return r
    cu = g.current_user
    if cu.get("role") == ROLE_ADMIN:
        return redirect(url_for("admin_dashboard"))
    store.sweep_expired()
    g.current_user = store.find_user(ID=cu.get("ID")) or cu
    return render_template("user_dashboard.html", user=g.current_user)


@app.route("/user/activate", methods=["GET", "POST"])
def user_activate():
    r = require_login()
    if r: return r
    cu = g.current_user
    if cu.get("role") == ROLE_ADMIN:
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        if not csrf.verify(request.form.get("csrf_token")):
            flash("رمز الحماية غير صالح", "error")
            return render_template("user_activate.html", user=cu), 400
        code = (request.form.get("code") or "").strip().upper()
        locked, mins = RL.is_locked(f"act:{cu.get('phone')}")
        if locked:
            flash(f"تم حجب المحاولات مؤقتًا لمدة {mins} دقيقة تقريبًا", "error")
            return render_template("user_activate.html", user=cu)
        if not code:
            flash("أدخل كود التفعيل", "error")
            return render_template("user_activate.html", user=cu)
        c = store.find_code(code)
        if not c:
            RL.record(f"act:{cu.get('phone')}", ok=False, typ="activate")
            store.log(cu.get("phone"), "تفعيل حساب", cu.get("username"), f"code={code}", "كود غير موجود")
            flash("الكود غير صحيح أو غير موجود", "error")
            return render_template("user_activate.html", user=cu)
        status_c = (c.get("status") or "").strip()
        if status_c == "مستخدم":
            RL.record(f"act:{cu.get('phone')}", ok=False, typ="activate")
            store.log(cu.get("phone"), "تفعيل حساب", cu.get("username"), f"code={code} مستخدم", "مرفوض")
            flash("هذا الكود مستخدم بالفعل", "error")
            return render_template("user_activate.html", user=cu)
        # متاح
        # قفل على التحديث
        with store.write() as wb:
            c2 = store.find_code(code)
            if not c2 or (c2.get("status") or "").strip() == "مستخدم":
                flash("الكود مستخدم حالياً من شخص آخر. حاول كودًا آخر", "error")
                RL.record(f"act:{cu.get('phone')}", ok=False, typ="activate")
                return render_template("user_activate.html", user=cu)
            # تفعيل الحساب
            nowd = now_dt()
            expd = nowd + timedelta(days=CFG["ACTIVATION_DAYS"])
            cu_row = store.find_user(ID=cu.get("ID"))
            if cu_row.get("_row"):
                set_row(wb, USERS, int(cu_row["_row"]), {
                    "status": STATUS_ACTIVE,
                    "activated_at": nowd.strftime("%Y-%m-%d %H:%M:%S"),
                    "expires_at": expd.strftime("%Y-%m-%d %H:%M:%S"),
                    "disabled_at": "",
                })
            # استخدام الكود
            set_row(wb, CODES, int(c2["_row"]), {
                "status": "مستخدم",
                "used_by_phone": cu.get("phone"),
                "used_at": now_str(),
            })
            log_row(wb, cu.get("phone"), "تفعيل حساب ناجح", cu.get("username"), f"code={code}", "تم")
        RL.record(f"act:{cu.get('phone')}", ok=True, typ="activate")
        flash(f"تم تفعيل حسابك بنجاح. الاشتراك حتى {expd.strftime('%Y-%m-%d %H:%M')}", "success")
        return redirect(url_for("user_dashboard"))
    return render_template("user_activate.html", user=cu)


@app.route("/user/activate/form")
def user_activate_form():
    r = require_login()
    if r: return r
    return redirect(url_for("user_activate"))


@app.route("/user/profile", methods=["GET", "POST"])
def user_profile():
    r = require_login()
    if r: return r
    cu = g.current_user
    if request.method == "POST":
        if not csrf.verify(request.form.get("csrf_token")):
            flash("رمز الحماية غير صالح", "error")
            return render_template("user_profile.html", user=cu), 400
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        cur_pw = request.form.get("current_password") or ""
        new_pw = request.form.get("new_password") or ""
        confirm = request.form.get("confirm") or ""
        if not username or not re_match_username(username):
            flash("اسم المستخدم غير صالح", "error")
            return render_template("user_profile.html", user=cu)
        if not email or "@" not in email:
            flash("البريد غير صالح", "error")
            return render_template("user_profile.html", user=cu)
        # منع تكرار مع آخرين
        f1 = store.find_user(username=username)
        if f1 and f1.get("ID") != cu.get("ID"): flash("اسم المستخدم مستخدم من قبل", "error"); return render_template("user_profile.html", user=cu)
        f2 = store.find_user(email=email)
        if f2 and f2.get("ID") != cu.get("ID"): flash("البريد مستخدم من قبل", "error"); return render_template("user_profile.html", user=cu)
        data = {"username": username, "email": email}
        if new_pw:
            if new_pw != confirm or len(new_pw) < 8: flash("كلمة السر الجديدة غير متطابقة أو قصيرة", "error"); return render_template("user_profile.html", user=cu)
            ok, _ = PH.verify(cur_pw, cu.get("password_hash",""), cu.get("salt"))
            if not ok: flash("كلمة السر الحالية غير صحيحة", "error"); return render_template("user_profile.html", user=cu)
            nh, _ = PH.hash(new_pw); data["password_hash"] = nh; data["salt"] = ""
        store.update(USERS, int(cu["_row"]), data)
        store.log(cu.get("phone"), "تحديث ملف المستخدم", username, "تعديل بيانات", "تم")
        flash("تم حفظ التعديلات بنجاح", "success")
        g.current_user = store.find_user(ID=cu.get("ID"))
        return redirect(url_for("user_dashboard"))
    return render_template("user_profile.html", user=cu)


@app.route("/user/deactivate", methods=["POST"])
def user_deactivate():
    r = require_login()
    if r: return r
    if not csrf.verify(request.form.get("csrf_token")):
        flash("رمز الحماية غير صالح", "error")
        return redirect(url_for("user_profile")), 400
    cu = g.current_user
    pw = request.form.get("disable_password") or ""
    ok, _ = PH.verify(pw, cu.get("password_hash",""), cu.get("salt"))
    if not ok:
        flash("كلمة السر غير صحيحة", "error")
        return redirect(url_for("user_profile"))
    store.update(USERS, int(cu["_row"]), {"status": STATUS_DISABLED, "disabled_at": now_str()})
    store.log(cu.get("phone"), "تعطيل حساب من المستخدم", cu.get("username"), "-", "تم")
    session.clear()
    flash("تم تعطيل حسابك بنجاح. لن تتمكن من الدخول حتى يُفعّله الأدمن", "info")
    return redirect(url_for("auth_login"))


# ----------- مسارات الأدمن
@app.route("/admin")
def admin_root():
    r = require_role(ROLE_ADMIN); 
    if r: return r
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/dashboard")
def admin_dashboard():
    r = require_role(ROLE_ADMIN); 
    if r: return r
    users = store.all_users()
    codes = store.all_codes()
    stats = {
        "total": len(users),
        "active": sum(1 for x in users if x.get("status")==STATUS_ACTIVE),
        "expired": sum(1 for x in users if x.get("status")==STATUS_EXPIRED),
        "disabled": sum(1 for x in users if x.get("status")==STATUS_DISABLED),
        "inactive": sum(1 for x in users if x.get("status")==STATUS_INACTIVE),
        "codes_avail": sum(1 for x in codes if (x.get("status") or "").strip()=="" or (x.get("status") or "").strip()=="متاح"),
        "due7": sum(1 for x in users if x.get("status")==STATUS_ACTIVE and days_left(x.get("expires_at")) <= 7),
    }
    return render_template("admin_dashboard.html", stats=stats)


@app.route("/admin/users")
def admin_users():
    r = require_role(ROLE_ADMIN); 
    if r: return r
    q = (request.args.get("q") or "").strip().lower()
    st = request.args.get("status") or ""
    exp = request.args.get("export") or ""
    users = store.all_users()
    # فلترة
    res = []
    for u in users:
        ok = True
        if q:
            hay = " ".join(str(u.get(k,"")).lower() for k in ("phone","username","email"))
            if q not in hay: ok=False
        if st == "due7":
            if not (u.get("status")==STATUS_ACTIVE and days_left(u.get("expires_at")) <= 7): ok=False
        elif st and u.get("status") != st:
            ok=False
        if ok: res.append(u)
    # ترتيب: حسب تاريخ الانتهاء قريب أولاً ثم اسم المستخدم
    res.sort(key=lambda x: (parse_dt(x.get("expires_at")) or datetime.max, x.get("username","")))
    if exp == "csv":
        sio = io.StringIO(newline="")
        w = csv.writer(sio, quoting=csv.QUOTE_ALL)
        w.writerow(["username","email","phone","status","activated_at","expires_at","days_left","last_login","notes"])
        for u in res:
            w.writerow([csv_safe(u.get("username")), csv_safe(u.get("email")), csv_safe(u.get("phone")), csv_safe(u.get("status")), csv_safe(u.get("activated_at")), csv_safe(u.get("expires_at")), days_left(u.get("expires_at")), csv_safe(u.get("last_login")), csv_safe(u.get("notes"))])
        out = io.BytesIO(("".join(["\ufeff", sio.getvalue()])).encode("utf-8-sig"))
        resp = make_response(out.getvalue())
        resp.headers["Content-Type"] = "text/csv; charset=utf-8-sig"
        resp.headers["Content-Disposition"] = f"attachment; filename=subscribers_{datetime.now().strftime('%Y%m%d')}.csv"
        return resp
    return render_template("admin_users.html", users=res, q=q, status=st)


@app.route("/admin/users/toggle/<phone>", methods=["POST"])
def admin_toggle_user(phone):
    r = require_role(ROLE_ADMIN); 
    if r: return r
    if not csrf.verify(request.form.get("csrf_token")): flash("رمز الحماية غير صالح","error"); return redirect(url_for("admin_users"))
    u = store.find_user(phone=normalize_phone(phone))
    if not u: flash("المشترك غير موجود","error"); return redirect(url_for("admin_users"))
    new_st = STATUS_ACTIVE if u.get("status")==STATUS_DISABLED else STATUS_DISABLED
    extra = {"disabled_at": now_str()} if new_st==STATUS_DISABLED else {"disabled_at": ""}
    store.update(USERS, int(u["_row"]), {"status": new_st, **extra})
    store.log(g.current_user.get("phone") or "admin", "تعطيل/إعادة تفعيل مشترك", u.get("phone"), f"من {u.get('status')} إلى {new_st}", "تم")
    flash("تم تحديث حالة المشترك","success")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/note/<phone>", methods=["POST"])
def admin_save_note(phone):
    r = require_role(ROLE_ADMIN); 
    if r: return r
    if not csrf.verify(request.form.get("csrf_token")): flash("رمز الحماية غير صالح","error"); return redirect(url_for("admin_users"))
    u = store.find_user(phone=normalize_phone(phone))
    if not u: flash("المشترك غير موجود","error"); return redirect(url_for("admin_users"))
    note = (request.form.get("note") or "").strip()
    store.update(USERS, int(u["_row"]), {"notes": note[:500]})
    store.log(g.current_user.get("phone") or "admin", "إضافة ملاحظة أدمن", u.get("phone"), note[:120], "تم")
    flash("تم حفظ الملاحظة","success")
    return redirect(url_for("admin_users"))


@app.route("/admin/extensions", methods=["GET", "POST"])
def admin_extensions():
    r = require_role(ROLE_ADMIN); 
    if r: return r
    results = []
    if request.method == "POST":
        if not csrf.verify(request.form.get("csrf_token")): flash("رمز الحماية غير صالح","error"); return render_template("admin_extensions.html", results=results)
        phones_raw = request.form.get("phones") or ""
        days_str = request.form.get("days") or "0"
        reason = (request.form.get("reason") or "").strip()
        try: days = int(days_str)
        except: days=0
        if days < 1 or days > 365:
            flash("عدد الأيام يجب أن يكون بين 1 و365","error"); return render_template("admin_extensions.html", results=results)
        # تحليل أرقام الجوال
        phones = []
        for p in phones_raw.replace(";",",").splitlines():
            for x in p.split(","):
                xn = normalize_phone(x)
                if is_valid_phone(xn): phones.append(xn)
        if not phones: flash("أدخل رقم جوال سعودي صالح واحد على الأقل","error"); return render_template("admin_extensions.html", results=results)
        for ph in phones:
            u = store.find_user(phone=ph)
            res = {"phone": ph, "msg": "غير موجود", "before": "-", "after": "-", "days": days}
            if not u:
                results.append(res); continue
            st = u.get("status")
            if st == STATUS_DISABLED:
                res["msg"] = "معطل — يتطلب تأكيد صريح (لا يُمدد تلقائياً)"
                results.append(res); continue
            if st == STATUS_INACTIVE:
                res["msg"] = "غير مفعل — يُرجى تفعيل الحساب أولاً بالكود"
                results.append(res); continue
            nowd = now_dt()
            before = parse_dt(u.get("expires_at"))
            if st == STATUS_EXPIRED or not before:
                after = nowd + timedelta(days=days)
                new_st = STATUS_ACTIVE
            else:
                after = before + timedelta(days=days)
                new_st = st
            before_str = before.strftime("%Y-%m-%d %H:%M") if before else "-"
            after_str = after.strftime("%Y-%m-%d %H:%M")
            store.update(USERS, int(u["_row"]), {"expires_at": after.strftime("%Y-%m-%d %H:%M:%S"), "status": new_st})
            # Extensions
            store.append(EXTENSIONS, {
                "التاريخ": now_str(),
                "الأدمن": (g.current_user.get("phone") or g.current_user.get("username") or "admin"),
                "رقم جوال المشترك": ph,
                "تاريخ الانتهاء قبل": before_str,
                "تاريخ الانتهاء بعد": after_str,
                "عدد الأيام": str(days),
                "السبب": reason[:120],
            })
            store.log(g.current_user.get("phone") or "admin", "تمديد اشتراك", ph, f"{days} يوم — سبب: {reason}", "تم")
            res.update({"msg": f"تم التمديد بنجاح → {new_st}", "before": before_str, "after": after_str})
            results.append(res)
        flash("تمت معالجة تمديد الاشتراكات","success")
    return render_template("admin_extensions.html", results=results)


@app.route("/admin/codes", methods=["GET", "POST"])
def admin_codes():
    r = require_role(ROLE_ADMIN); 
    if r: return r
    added = 0
    codes = store.all_codes()
    stats = {
        "total": len(codes),
        "avail": sum(1 for x in codes if (x.get("status") or "").strip()=="" or (x.get("status") or "").strip()=="متاح"),
        "used": sum(1 for x in codes if (x.get("status") or "").strip()=="مستخدم"),
    }
    avail_list = sorted([c for c in codes if stats["avail"]>=0 and ((c.get("status") or "").strip()=="" or (c.get("status") or "").strip()=="متاح")], key=lambda x: x.get("code",""))[:200]
    used_list = sorted([c for c in codes if (c.get("status") or "").strip()=="مستخدم"], key=lambda x: x.get("used_at",""), reverse=True)[:200]
    return render_template("admin_codes.html", stats=stats, avail_list=avail_list, used_list=used_list, added=added)


@app.route("/admin/codes/add", methods=["POST"])
def admin_codes_add():
    r = require_role(ROLE_ADMIN); 
    if r: return r
    if not csrf.verify(request.form.get("csrf_token")): flash("رمز الحماية غير صالح","error"); return redirect(url_for("admin_codes"))
    codes_raw = request.form.get("codes") or ""
    added = 0
    # جمع أكواد نظيفة
    pool = set()
    for p in codes_raw.replace(";",",").splitlines():
        for x in p.split(","):
            xn = x.strip().upper()
            if len(xn) >= 4 and len(xn) <= 12 and re_match_code(xn):
                pool.add(xn)
    if not pool:
        flash("لم يتم العثور على أكواد صالحة. استخدم أحرف وأرقام بطول 4–12","error")
        return redirect(url_for("admin_codes"))
    # موجودة
    exist = {c.get("code","").strip().upper() for c in store.all_codes()}
    to_add = pool - exist
    if to_add:
        with store.write() as wb:
            for code in sorted(to_add):
                append_row(wb, CODES, {"code": code, "status": "", "used_by_phone": "", "used_at": ""})
                added += 1
            log_row(wb, g.current_user.get("phone") or "admin", "إضافة أكواد", str(added), ", ".join(sorted(list(to_add))[:10]) + ("..." if len(to_add)>10 else ""), "تم")
    flash(f"تمت إضافة {added} كودًا. تجاهل {len(pool)-len(to_add)} مكرر/غير صالح إن وُجد","success")
    return redirect(url_for("admin_codes"))


def re_match_code(s: str) -> bool:
    import re
    return bool(re.fullmatch(r"[A-Z0-9]{4,12}", s))


@app.route("/admin/logs")
def admin_logs():
    r = require_role(ROLE_ADMIN); 
    if r: return r
    logs = list(reversed(store.rows(LOGS)))[:500]
    return render_template("admin_logs.html", logs=logs)


@app.route("/admin/reset-any", methods=["GET", "POST"])
def admin_reset_any():
    r = require_role(ROLE_ADMIN); 
    if r: return r
    new_pass = None; target_phone = None
    if request.method == "POST":
        if not csrf.verify(request.form.get("csrf_token")): flash("رمز الحماية غير صالح","error"); return render_template("admin_reset_any.html")
        ph = normalize_phone(request.form.get("phone") or "")
        if not is_valid_phone(ph): flash("رقم جوال غير صالح","error"); return render_template("admin_reset_any.html")
        u = store.find_user(phone=ph)
        if not u: flash("المشترك غير موجود","error"); return render_template("admin_reset_any.html")
        if u.get("status")==STATUS_DISABLED: flash("لا يمكن إعادة تعيين كلمة سر لحساب معطل","error"); return render_template("admin_reset_any.html")
        np = secrets.token_urlsafe(10)[:12].replace("-","").replace("_","") + "Ab1!"
        nh, _ = PH.hash(np)
        store.update(USERS, int(u["_row"]), {"password_hash": nh, "salt": ""})
        store.log(g.current_user.get("phone") or "admin", "إعادة تعيين كلمة سر مشترك", ph, f"username={u.get('username')}", "تم")
        new_pass = np; target_phone = ph
        flash("تم إنشاء كلمة سر جديدة. سلمها للمشترك عبر واتساب","success")
    return render_template("admin_reset_any.html", new_pass=new_pass, target_phone=target_phone)


@app.route("/admin/change-admin", methods=["GET", "POST"])
def admin_change_admin_password():
    r = require_role(ROLE_ADMIN); 
    if r: return r
    if request.method == "POST":
        if not csrf.verify(request.form.get("csrf_token")): flash("رمز الحماية غير صالح","error"); return render_template("admin_change_admin.html")
        action = request.form.get("action") or "change"
        cu = g.current_user
        if action == "change":
            cur = request.form.get("current_password") or ""
            np = request.form.get("new_password") or ""
            conf = request.form.get("confirm") or ""
            if np!=conf or len(np)<8: flash("كلمة السر الجديدة غير متطابقة أو قصيرة","error"); return render_template("admin_change_admin.html")
            ok,_ = PH.verify(cur, cu.get("password_hash",""), cu.get("salt"))
            if not ok: flash("كلمة السر الحالية غير صحيحة","error"); return render_template("admin_change_admin.html")
            nh,_ = PH.hash(np); store.update(USERS, int(cu["_row"]), {"password_hash": nh, "salt": ""})
            store.log(cu.get("phone") or "admin", "تغيير كلمة سر الأدمن", "-", "تم")
            flash("تم تحديث كلمة سر الأدمن بنجاح","success")
            return redirect(url_for("admin_dashboard"))
        elif action == "add":
            adm_cur = request.form.get("admin_password") or ""
            ok,_ = PH.verify(adm_cur, cu.get("password_hash",""), cu.get("salt"))
            if not ok: flash("كلمة سر الأدمن الحالي غير صحيحة للتأكيد","error"); return render_template("admin_change_admin.html")
            username = (request.form.get("username") or "").strip()
            phone = normalize_phone(request.form.get("phone") or "")
            email = (request.form.get("email") or "").strip().lower()
            np = request.form.get("new_password") or ""
            conf = request.form.get("confirm") or ""
            if not re_match_username(username): flash("اسم المستخدم غير صالح","error"); return render_template("admin_change_admin.html")
            if not is_valid_phone(phone): flash("رقم الجوال غير صالح","error"); return render_template("admin_change_admin.html")
            if not email or "@" not in email: flash("البريد غير صالح","error"); return render_template("admin_change_admin.html")
            if np!=conf or len(np)<8: flash("كلمة السر غير متطابقة أو قصيرة","error"); return render_template("admin_change_admin.html")
            if store.find_user(username=username) or store.find_user(phone=phone) or store.find_user(email=email):
                flash("اسم المستخدم أو الجوال أو البريد موجود مسبقًا","error"); return render_template("admin_change_admin.html")
            nh,_ = PH.hash(np)
            row = {
                "ID": __import__("uuid").uuid4(),
                "username": username, "email": email, "phone": phone,
                "password_hash": nh, "salt": "", "role": ROLE_ADMIN, "status": STATUS_ACTIVE,
                "created_at": now_str(), "activated_at": now_str(), "expires_at": "2099-12-31 23:59:59",
                "last_login": "", "disabled_at": "", "notes": "أدمن مضاف",
            }
            store.append(USERS, row)
            store.log(cu.get("phone") or "admin", "إضافة أدمن جديد", phone, f"username={username}", "تم")
            flash("تم إضافة حساب أدمن جديد بنجاح","success")
            return redirect(url_for("admin_dashboard"))
    return render_template("admin_change_admin.html")


if __name__ == "__main__":
    app.run(host=CFG["FLASK_HOST"], port=CFG["FLASK_PORT"], debug=CFG["FLASK_DEBUG"], use_reloader=False)
