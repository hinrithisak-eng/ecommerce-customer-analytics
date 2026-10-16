// Shared behaviour: theme switch, confirm dialogs, database status polling.
(function () {
  const root = document.documentElement;

  document.getElementById('theme').addEventListener('click', () => {
    const t = root.dataset.theme === 'dark' ? 'light' : 'dark';
    root.dataset.theme = t;
    try { localStorage.setItem('ca-theme', t); } catch (e) { /* storage unavailable */ }
    document.dispatchEvent(new CustomEvent('ca:theme', { detail: t }));
  });

  document.querySelectorAll('form[data-confirm]').forEach(f =>
    f.addEventListener('submit', e => { if (!confirm(f.dataset.confirm)) e.preventDefault(); }));

  // Poll the database change counter. Pages that show live data listen for `ca:data-changed`.
  const status = document.getElementById('dbStatus');
  const updated = document.getElementById('dbUpdated');
  const navOrders = document.getElementById('navOrders');
  const time = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  let version = window.CA.version;
  async function poll() {
    if (document.hidden) return;
    try {
      const r = await fetch(window.CA.versionUrl, { cache: 'no-store' });
      const v = await r.json();
      status.classList.remove('offline');
      navOrders.textContent = v.orders.toLocaleString();
      if (v.version !== version) {
        version = v.version;
        updated.textContent = 'Updated ' + time();
        document.dispatchEvent(new CustomEvent('ca:data-changed', { detail: v }));
      }
    } catch (e) {
      status.classList.add('offline');
      updated.textContent = 'Server not reachable';
    }
  }
  setInterval(poll, 4000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });
})();
