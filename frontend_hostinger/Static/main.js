// Static/main.js
(() => {
  // Read runtime config set by config.js
  const APP_CONFIG = window.APP_CONFIG || {};
  const API_BASE = APP_CONFIG.API_BASE || "";
  const FRONTEND_BASE = APP_CONFIG.FRONTEND_BASE || "";

  // currentUser will be loaded from backend on page load
  let currentUser = null;

  // small helper: toast notifications
  function showNotification(message, type='info', timeout=3500) {
    const colors = {
      success: 'linear-gradient(90deg,#10b981,#06b6d4)',
      error: 'linear-gradient(90deg,#ef4444,#f97316)',
      warning: 'linear-gradient(90deg,#f59e0b,#f97316)',
      info: 'linear-gradient(90deg,#3b82f6,#8b5cf6)'
    };
    const n = document.createElement('div');
    n.style.cssText = `
      position: fixed; top: 16px; right: 16px; padding: 14px 18px; border-radius: 12px;
      color: white; z-index: 9999; transform: translateX(120%); transition: transform .25s;
      background: ${colors[type] || colors.info}; box-shadow: 0 8px 30px rgba(2,6,23,.4);
    `;
    n.textContent = message;
    document.body.appendChild(n);
    requestAnimationFrame(()=> n.style.transform = 'translateX(0)');
    setTimeout(() => { n.style.transform = 'translateX(120%)'; setTimeout(()=> n.remove(), 300); }, timeout);
  }

  
  async function fetchCurrentUser() {
    if (!API_BASE) return null;
    try {
      const res = await fetch(`${API_BASE}/current_user`, { credentials: 'include' });
  
      if (res.status === 204) return null;
    
      const ct = res.headers.get('content-type') || '';
      if (!ct.includes('application/json')) return null;
      const j = await res.json();
      return j.user || null;
    } catch (e) {
      console.warn('fetchCurrentUser failed', e);
      return null;
    }
  }


  document.querySelectorAll('[data-auth-login]').forEach(el => {
    el.addEventListener('click', (e) => {
      e.preventDefault();
      if (!API_BASE) {
        showNotification('Backend not configured (API_BASE missing).', 'error');
        return;
      }
      // redirect to absolute backend login URL
      window.location.href = `${API_BASE}/auth/login`;
    });
  });

  // wire logout buttons
  document.querySelectorAll('[data-auth-logout]').forEach(el => {
    el.addEventListener('click', async (e) => {
      e.preventDefault();
      if (!API_BASE) { showNotification('Backend not configured', 'error'); return; }
      try {
        // call logout endpoint; backend should clear session cookie and redirect or return success
        await fetch(`${API_BASE}/auth/logout`, { method: 'POST', credentials: 'include' });
      } catch (err) {
        console.warn('logout error', err);
      } finally {
        // refresh UI: clear user and reload page
        currentUser = null;
        window.location.href = FRONTEND_BASE || "/";
      }
    });
  });

  // front-end check before upload/match
  function requireLogin() {
    if (!currentUser) {
      showNotification('Please sign in with Google first.', 'warning');
      return false;
    }
    return true;
  }

  // Upload form handling
  const cvUploadForm = document.getElementById('cv-upload-form');
  if (cvUploadForm) {
    cvUploadForm.addEventListener('submit', async function (e) {
      e.preventDefault();
      if (!requireLogin()) return;
      const filesInput = document.getElementById('cv-files');
      if (!filesInput || filesInput.files.length === 0) {
        showNotification('Select at least one CV file.', 'error');
        return;
      }
      const formData = new FormData();
      Array.from(filesInput.files).forEach(f => formData.append('files[]', f));
      const uploadButton = document.getElementById('upload-button');
      if (uploadButton) uploadButton.disabled = true;
      try {
        const resp = await fetch(`${API_BASE}/upload-cvs`, { method: 'POST', body: formData, credentials: 'include' });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || 'Upload failed');
        showNotification(data.message || 'Uploaded', 'success');
      } catch (err) {
        showNotification(err.message || 'Upload error', 'error');
      } finally {
        if (uploadButton) uploadButton.disabled = false;
      }
    });
  }

  // Job description match handling
  const jdForm = document.getElementById('jd-form');
  if (jdForm) {
    jdForm.addEventListener('submit', async function (e) {
      e.preventDefault();
      if (!requireLogin()) return;
      const textarea = document.getElementById('job-description');
      const jd = textarea ? textarea.value.trim() : '';
      if (!jd) { showNotification('Please enter job description', 'error'); return; }

      const matchButton = document.getElementById('match-button');
      if (matchButton) matchButton.disabled = true;
      try {
        const resp = await fetch(`${API_BASE}/match-cvs`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ job_description: jd })
        });
        const results = await resp.json();
        if (!resp.ok) throw new Error(results.error || 'Matching failed');
        document.dispatchEvent(new CustomEvent('matches-ready', { detail: results }));
        showNotification('Matching done', 'success');
      } catch (err) {
        showNotification(err.message || 'Matching error', 'error');
      } finally {
        if (matchButton) matchButton.disabled = false;
      }
    });
  }

  // handle matches-ready (optional)
  document.addEventListener('matches-ready', (e) => {
    console.log('Matches ready: ', e.detail);
  });

  // Drag & drop for upload zone (unchanged)
  const uploadZone = document.getElementById('upload-zone');
  if (uploadZone) {
    ['dragenter','dragover'].forEach(ev => uploadZone.addEventListener(ev, ev2 => { ev2.preventDefault(); uploadZone.classList.add('dragover'); }));
    ['dragleave','drop'].forEach(ev => uploadZone.addEventListener(ev, ev2 => { ev2.preventDefault(); uploadZone.classList.remove('dragover'); }));
    uploadZone.addEventListener('drop', ev => {
      if (ev.dataTransfer.files.length) {
        const input = document.getElementById('cv-files');
        input.files = ev.dataTransfer.files;
        input.dispatchEvent(new Event('change'));
      }
    });
  }

  // expose helpers and attempt to load current user on init
  window._cvMatcher = { showNotification, requireLogin, getCurrentUser: () => currentUser };

  (async function init() {
    currentUser = await fetchCurrentUser();
    // update UI if you have placeholders
    if (currentUser) {
      // show/hide blocks if present
      const userBlock = document.getElementById('user-block');
      const loginBlock = document.getElementById('login-block');
      if (userBlock) {
        userBlock.style.display = 'flex';
        const pic = document.getElementById('user-pic');
        const name = document.getElementById('user-name');
        if (pic && currentUser.picture) pic.src = currentUser.picture;
        if (name && currentUser.name) name.textContent = currentUser.name;
      }
      if (loginBlock) loginBlock.style.display = 'none';
    } else {
      const userBlock = document.getElementById('user-block');
      const loginBlock = document.getElementById('login-block');
      if (userBlock) userBlock.style.display = 'none';
      if (loginBlock) loginBlock.style.display = 'block';
    }
  })();

})();
