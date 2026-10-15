// ثيم فاتح/داكن + قائمة متنقلة
(function(){
  const root = document.documentElement;
  const themeToggle = document.getElementById('themeToggle');
  const navToggle = document.getElementById('navToggle');
  const navMenu = document.getElementById('navMenu');

  // حفظ/استعادة الثيم
  const saved = localStorage.getItem('theme') || 'light';
  root.setAttribute('data-theme', saved);

  if (themeToggle) {
    themeToggle.addEventListener('click', function(){
      const cur = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', cur);
      localStorage.setItem('theme', cur);
    });
  }

  if (navToggle && navMenu) {
    navToggle.addEventListener('click', function(){
      const open = navMenu.classList.toggle('open');
      navToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    // إغلاق عند النقر على رابط
    navMenu.querySelectorAll('a').forEach(function(a){
      a.addEventListener('click', function(){
        navMenu.classList.remove('open');
        navToggle.setAttribute('aria-expanded', 'false');
      });
    });
  }
})();
