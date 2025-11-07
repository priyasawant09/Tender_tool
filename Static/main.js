// static/style/main.js
(() => {
  // read the current user set by template
  const currentUser = window.currentUser || null;

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

  // wire login button(s) if any non-Jinja link exists
  document.querySelectorAll('[data-auth-login]').forEach(el => {
    el.addEventListener('click', (e) => {
      e.preventDefault();
      // redirect to Flask auth
      window.location.href = '/auth/login';
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
      uploadButton.disabled = true;
      try {
        const resp = await fetch('/upload-cvs', { method: 'POST', body: formData, credentials: 'same-origin' });
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
      matchButton.disabled = true;
      try {
        const resp = await fetch('/match-cvs', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({ job_description: jd })
        });
        const results = await resp.json();
        if (!resp.ok) throw new Error(results.error || 'Matching failed');
        // simple event dispatch so template's inline JS can handle rendering if still present
        document.dispatchEvent(new CustomEvent('matches-ready', { detail: results }));
        showNotification('Matching done', 'success');
      } catch (err) {
        showNotification(err.message || 'Matching error', 'error');
      } finally {
        matchButton.disabled = false;
      }
    });
  }

  // Example: when results are ready, inline template code can listen and render
  // (Your current index.html already does rendering; this is optional)
  document.addEventListener('matches-ready', (e) => {
    // if you want to do something from external JS when results are ready
    console.log('Matches ready: ', e.detail);
  });

  // small UX: highlight upload zone on drag
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

  // expose helpers for console if needed
  window._cvMatcher = { showNotification, requireLogin, currentUser };
})();
