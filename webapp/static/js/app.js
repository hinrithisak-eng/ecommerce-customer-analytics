// Shared behaviour for every page: theme toggle, keyboard shortcuts, toasts.
(function () {
  const root = document.documentElement;
  const save = t => { try { localStorage.setItem('eca-theme', t); } catch (e) { /* storage unavailable */ } };

  window.ECA = window.ECA || {};
  ECA.onTheme = [];
  ECA.toast = function (msg, ms) {
    const t = document.getElementById('toast');
    document.getElementById('toastText').textContent = msg;
    t.classList.add('show');
    clearTimeout(ECA._tt);
    ECA._tt = setTimeout(() => t.classList.remove('show'), ms || 3200);
  };

  document.getElementById('theme').addEventListener('click', () => {
    const t = root.dataset.theme === 'dark' ? 'light' : 'dark';
    root.dataset.theme = t;
    save(t);
    ECA.onTheme.forEach(fn => fn(t));
  });

  document.addEventListener('keydown', e => {
    const tag = (e.target.tagName || '').toLowerCase();
    if (['input', 'select', 'textarea'].includes(tag) || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key.toLowerCase() === 'd') document.getElementById('theme').click();
  });

  // auto-dismiss success flashes
  document.querySelectorAll('.flash.success').forEach(f => setTimeout(() => {
    f.style.transition = 'opacity .4s'; f.style.opacity = '0'; setTimeout(() => f.remove(), 450);
  }, 6000));

  // confirm before destructive form posts
  document.querySelectorAll('form[data-confirm]').forEach(f =>
    f.addEventListener('submit', e => { if (!confirm(f.dataset.confirm)) e.preventDefault(); }));
})();
