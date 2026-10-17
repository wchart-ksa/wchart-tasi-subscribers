"""سلوك القفل: ملف Excel مفتوح في برنامج آخر يجب ألا يُسقط الطلب بصفحة مطوّر."""
import app as app_module
import support


def test_permission_error_handler_registered():
    assert PermissionError in app_module.app.error_handler_spec[None][None]


def test_locked_data_file_returns_503_not_500(client, store):
    support.seed_user(store, "locku", "0501119999", "LockPass1")
    handle = open(store.data_file, "rb")  # قفل شبيه بـ Excel (يمنع الاستبدال الذري)
    try:
        resp = support.login(client, "locku", "LockPass1")
        assert resp.status_code == 503
        assert "503" in resp.get_data(as_text=True)
    finally:
        handle.close()
