/**
 * main.js - التفاعلات الخفيفة لموقع «مشتركين منصة دبليوشارت تاسي»
 * تبديل المظهر (فاتح / داكن)، القائمة المتنقلة، وإدارة النوافذ المنبثقة
 */

document.addEventListener('DOMContentLoaded', function () {
  // -------------------------------------------------------------
  // 1) إدارة الوضع الفاتح والداكن (Theme Toggle)
  // -------------------------------------------------------------
  const themeToggleBtn = document.getElementById('themeToggleBtn');
  const themeIcon = document.getElementById('themeIcon');

  function getPreferredTheme() {
    const saved = localStorage.getItem('wchart_theme');
    if (saved) return saved;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('wchart_theme', theme);
    if (themeIcon) {
      themeIcon.textContent = theme === 'dark' ? '☀️' : '🌙';
    }
  }

  applyTheme(getPreferredTheme());

  if (themeToggleBtn) {
    themeToggleBtn.addEventListener('click', function () {
      const current = document.documentElement.getAttribute('data-theme') || 'light';
      applyTheme(current === 'dark' ? 'light' : 'dark');
    });
  }

  // -------------------------------------------------------------
  // 2) قائمة الجوال (Mobile Menu)
  // -------------------------------------------------------------
  const mobileToggle = document.getElementById('mobileMenuToggle');
  const mainNav = document.getElementById('mainNav');

  if (mobileToggle && mainNav) {
    mobileToggle.addEventListener('click', function () {
      mainNav.classList.toggle('active');
    });
  }

  // -------------------------------------------------------------
  // 3) التنبيهات Alerts
  // -------------------------------------------------------------
  document.querySelectorAll('.alert-close').forEach(function (btn) {
    btn.addEventListener('click', function () {
      const alert = this.closest('.alert');
      if (alert) alert.remove();
    });
  });

  setTimeout(function () {
    document.querySelectorAll('.alert-success').forEach(function (el) {
      el.style.transition = 'opacity 0.5s ease';
      el.style.opacity = '0';
      setTimeout(function () { el.remove(); }, 500);
    });
  }, 6000);

  // -------------------------------------------------------------
  // 4) النوافذ المنبثقة Modals
  // -------------------------------------------------------------
  window.openModal = function (modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
      modal.classList.add('open');
      document.body.style.overflow = 'hidden';
    }
  };

  window.closeModal = function (modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
      modal.classList.remove('open');
      document.body.style.overflow = '';
    }
  };

  document.querySelectorAll('.modal-overlay').forEach(function (overlay) {
    overlay.addEventListener('click', function (e) {
      if (e.target === this) {
        this.classList.remove('open');
        document.body.style.overflow = '';
      }
    });
  });

  document.querySelectorAll('.modal-close, .btn-modal-cancel').forEach(function (btn) {
    btn.addEventListener('click', function () {
      const modal = this.closest('.modal-overlay');
      if (modal) {
        modal.classList.remove('open');
        document.body.style.overflow = '';
      }
    });
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      document.querySelectorAll('.modal-overlay.open').forEach(function (modal) {
        modal.classList.remove('open');
        document.body.style.overflow = '';
      });
    }
  });
});
