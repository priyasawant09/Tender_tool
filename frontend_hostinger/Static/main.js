// Static/main.js
(() => {
  // Runtime config (ensure config.js loads before this)
  const APP_CONFIG = window.APP_CONFIG || {};
  const API_BASE = (APP_CONFIG.API_BASE || window.API_BASE) || "https://ai-cv-backend-gojz.onrender.com";
  const FRONTEND_BASE = (APP_CONFIG.FRONTEND_BASE || window.FRONTEND_BASE) || "https://ghostwhite-fox-926923.hostingersite.com";

  // currentUser will be loaded from backend on page load (via JWT or session)
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

  // -------------------------
  // JWT handling helpers
  // -------------------------
  function getQueryParam(name) {
    const params = new URLSearchParams(window.location.search);
    return params.get(name);
  }

  // If token exists in URL, store and remove from URL to avoid leaking in history
  function storeTokenFromUrl() {
    const token = getQueryParam('token');
    if (!token) return null;
    try {
      localStorage.setItem('cvmatcher_token', token);
      // remove token from URL without reload
      const url = new URL(window.location.href);
      url.searchParams.delete('token');
      window.history.replaceState({}, document.title, url.pathname + url.search);
      return token;
    } catch (e) {
      console.error('storeTokenFromUrl error', e);
      return null;
    }
  }

  function getAuthToken() {
    const urlToken = storeTokenFromUrl();
    if (urlToken) return urlToken;
    return localStorage.getItem('cvmatcher_token');
  }

  function clearAuthToken() {
    localStorage.removeItem('cvmatcher_token');
  }

  
  async function fetchWithAuth(url, opts = {}) {
    opts.headers = opts.headers || {};
    const token = getAuthToken();
    if (token) {
      opts.headers['Authorization'] = 'Bearer ' + token;
    }
    const resp = await fetch(url, opts);
    if (resp.status === 401) {
      clearAuthToken();
    }
    return resp;
  }

  // -------------------------
  // API: current user
  // -------------------------
  async function fetchCurrentUser() {
    try {
      const resp = await fetchWithAuth(`${API_BASE}/current_user`, {
        headers: { "Accept": "application/json" }
      });

      if (!resp.ok) {
        if (resp.status === 401) return null;
        // other non-OK statuses - log and return null
        console.error("current_user failed", resp.status);
        return null;
      }

      const json = await resp.json();
      // backend returns { user: ... } — normalize to user object or null
      return (json && json.user) ? json.user : null;

    } catch (err) {
      console.error("fetchCurrentUser error", err);
      return null;
    }
  }

  // -------------------------
  // Login button wiring
  // -------------------------
  // Any element with [data-auth-login] will redirect to backend login
  document.querySelectorAll('[data-auth-login]').forEach(el => {
    el.addEventListener('click', (e) => {
      e.preventDefault();
      // Redirect the browser to backend which initiates Google OAuth
      window.location.href = `${API_BASE}/auth/login?next=/`;
    });
  });

  // -------------------------
  // Logout wiring
  // -------------------------
  document.querySelectorAll('[data-auth-logout]').forEach(el => {
    el.addEventListener('click', async (e) => {
      e.preventDefault();
      // Clear local token immediately
      clearAuthToken();
      // Optionally call backend logout to clear server session (if any)
      try {
        await fetch(`${API_BASE}/auth/logout`, { method: 'GET' });
      } catch (err) {
        // ignore but log
        console.warn('logout request failed', err);
      } finally {
        // redirect to frontend root (or reload)
        window.location.href = FRONTEND_BASE || "/";
      }
    });
  });

  // -------------------------
  // requireLogin helper
  // -------------------------
  function requireLogin() {
    if (!currentUser) {
      showNotification('Please sign in with Google first.', 'warning');
      return false;
    }
    return true;
  }

  // -------------------------
  // Upload form handling
  // -------------------------
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
        const resp = await fetchWithAuth(`${API_BASE}/upload-cvs`, {
          method: 'POST',
          body: formData
          // if backend requires cookies for upload, add credentials: 'include' here
        });
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

  // -------------------------
  // Job description match handling
  // -------------------------
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
        const resp = await fetchWithAuth(`${API_BASE}/match-cvs`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
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

  // -------------------------
  // Drag & drop for upload zone (unchanged)
  // -------------------------
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

  // expose helpers
  window._cvMatcher = { showNotification, requireLogin, getCurrentUser: () => currentUser };

  // -------------------------
  // Initialization on load
  // -------------------------
  (async function init() {
    // First, capture token from URL (if present) and store it
    storeTokenFromUrl();

    // Then try to fetch current user (via JWT or session)
    currentUser = await fetchCurrentUser();

    // update UI: show profile if logged in else show login button
    const userBlock = document.getElementById('user-block');
    const loginBlock = document.getElementById('login-block');

    if (currentUser) {
      if (userBlock) {
        userBlock.style.display = 'flex';
        const pic = document.getElementById('user-pic');
        const name = document.getElementById('user-name');
        if (pic && currentUser.picture) pic.src = currentUser.picture;
        if (name && currentUser.name) name.textContent = currentUser.name;
      }
      if (loginBlock) loginBlock.style.display = 'none';
    } else {
      if (userBlock) userBlock.style.display = 'none';
      if (loginBlock) loginBlock.style.display = 'block';
      // optional: automatically redirect to backend login
      //window.location.href = `${API_BASE}/auth/login?next=/`;
    }
  })();

window._cvMatcher = window._cvMatcher || {};
window._cvMatcher.fetchWithAuth = fetchWithAuth;
window._cvMatcher.getAuthToken = getAuthToken;
window._cvMatcher.storeTokenFromUrl = storeTokenFromUrl;

})();
