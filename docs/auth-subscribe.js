/* AI Art: Google login + peppertrees subscribe (daily / weekly / cancel). */
(function () {
  const cfg = window.AI_ART_CONFIG || {};
  const CLIENT_ID = cfg.googleClientId || '';
  const RESOLVER = (cfg.resolverBase || 'https://peppertrees.syntithenai.com').replace(/\/$/, '');
  const AUTH_KEY = 'ai_art_google_auth_v1';
  const TUNEBOOK_KEY = 'tunebook_google_auth_v1';

  const els = {
    profileBtn: document.getElementById('authProfileBtn'),
    avatarImg: document.getElementById('authAvatarImg'),
    avatarFallback: document.getElementById('authAvatarFallback'),
    profileLabel: document.getElementById('authProfileLabel'),
    dialog: document.getElementById('profileDialog'),
    close: document.getElementById('profileDialogClose'),
    name: document.getElementById('profileName'),
    email: document.getElementById('profileEmail'),
    status: document.getElementById('profileSubStatus'),
    offlineWarn: document.getElementById('profileOfflineWarn'),
    subActions: document.getElementById('subActions'),
    daily: document.getElementById('subDaily'),
    weekly: document.getElementById('subWeekly'),
    cancel: document.getElementById('subCancel'),
    logout: document.getElementById('authLogout'),
  };

  let accessToken = '';
  let user = null;
  let resolverOk = false;
  let frequency = null;

  function loadStored() {
    try {
      const raw = localStorage.getItem(AUTH_KEY) || localStorage.getItem(TUNEBOOK_KEY);
      if (!raw) return;
      const data = JSON.parse(raw);
      if (!data || !data.accessToken || !data.expiresAt || data.expiresAt < Date.now()) return;
      accessToken = data.accessToken;
      user = data.user || null;
    } catch (e) { /* ignore */ }
  }

  function saveStored() {
    if (!accessToken || !user) return;
    const payload = {
      accessToken,
      expiresAt: Date.now() + 50 * 60 * 1000,
      user,
      updatedAt: Date.now(),
    };
    try { localStorage.setItem(AUTH_KEY, JSON.stringify(payload)); } catch (e) { /* ignore */ }
  }

  function clearStored() {
    accessToken = '';
    user = null;
    frequency = null;
    try { localStorage.removeItem(AUTH_KEY); } catch (e) { /* ignore */ }
  }

  function initials(name, email) {
    const s = (name || email || '?').trim();
    return (s[0] || '?').toUpperCase();
  }

  function firstName(name, email) {
    const s = (name || '').trim();
    if (s) return s.split(/\s+/)[0];
    const e = (email || '').trim();
    if (e.includes('@')) return e.split('@')[0];
    return 'Account';
  }

  function renderAuth() {
    if (!els.profileBtn) return;
    if (user) {
      els.profileLabel.textContent = firstName(user.name, user.email);
      els.profileBtn.title = 'Account';
      els.profileBtn.setAttribute('aria-label', 'Account');
      els.profileBtn.setAttribute('aria-haspopup', 'dialog');
      if (user.picture) {
        els.avatarImg.src = user.picture;
        els.avatarImg.hidden = false;
        els.avatarFallback.hidden = true;
      } else {
        els.avatarImg.removeAttribute('src');
        els.avatarImg.hidden = true;
        els.avatarFallback.hidden = false;
        els.avatarFallback.textContent = initials(user.name, user.email);
      }
      els.name.textContent = user.name || 'Signed in';
      els.email.textContent = user.email || '';
    } else {
      els.profileLabel.textContent = 'Sign in';
      els.profileBtn.title = 'Sign in with Google';
      els.profileBtn.setAttribute('aria-label', 'Sign in with Google');
      els.profileBtn.removeAttribute('aria-haspopup');
      els.avatarImg.removeAttribute('src');
      els.avatarImg.hidden = true;
      els.avatarFallback.hidden = false;
      els.avatarFallback.textContent = '?';
      els.dialog.classList.remove('open');
      els.dialog.hidden = true;
    }
    updateSubButtons();
  }

  function updateSubButtons() {
    const enable = resolverOk && !!accessToken;
    [els.daily, els.weekly, els.cancel].forEach((btn) => {
      if (!btn) return;
      btn.disabled = !enable;
      btn.title = enable
        ? ''
        : (resolverOk ? 'Sign in to manage email' : 'Subscription server offline');
    });
    if (els.subActions) {
      els.subActions.setAttribute('aria-disabled', enable ? 'false' : 'true');
    }
    if (els.offlineWarn) {
      els.offlineWarn.hidden = resolverOk;
    }
    if (!resolverOk) {
      els.status.textContent = 'Subscription settings are disabled until the home server is back online.';
    } else if (!accessToken) {
      els.status.textContent = 'Sign in with Google to choose daily or weekly email.';
    } else if (frequency) {
      els.status.textContent = 'Current plan: ' + frequency + ' email digest.';
    } else {
      els.status.textContent = 'Not subscribed.';
    }
  }

  async function probeResolver() {
    try {
      const res = await fetch(RESOLVER + '/ai-art/health', { method: 'GET', mode: 'cors' });
      const data = await res.json().catch(() => ({}));
      resolverOk = res.ok && data && data.ok === true;
    } catch (e) {
      resolverOk = false;
    }
    updateSubButtons();
  }

  async function fetchProfile(token) {
    const res = await fetch('https://www.googleapis.com/oauth2/v3/userinfo', {
      headers: { Authorization: 'Bearer ' + token },
    });
    if (!res.ok) throw new Error('userinfo failed');
    const u = await res.json();
    return {
      email: (u.email || '').toLowerCase(),
      name: u.name || '',
      picture: u.picture || '',
    };
  }

  function loadGis() {
    return new Promise((resolve, reject) => {
      if (window.google && window.google.accounts && window.google.accounts.oauth2) {
        resolve();
        return;
      }
      const s = document.createElement('script');
      s.src = 'https://accounts.google.com/gsi/client';
      s.async = true;
      s.onload = () => resolve();
      s.onerror = () => reject(new Error('GIS load failed'));
      document.head.appendChild(s);
    });
  }

  async function signIn() {
    if (!CLIENT_ID) {
      alert('Google client id not configured');
      return;
    }
    await loadGis();
    await new Promise((resolve, reject) => {
      const client = window.google.accounts.oauth2.initTokenClient({
        client_id: CLIENT_ID,
        scope: 'openid email profile',
        callback: async (resp) => {
          try {
            if (!resp || !resp.access_token) throw new Error('No access token');
            accessToken = resp.access_token;
            user = await fetchProfile(accessToken);
            saveStored();
            renderAuth();
            await refreshSubscription();
            openProfile();
            resolve();
          } catch (err) {
            reject(err);
          }
        },
        error_callback: (err) => reject(err || new Error('Google sign-in failed')),
      });
      client.requestAccessToken({ prompt: '' });
    });
  }

  async function api(path, opts) {
    const res = await fetch(RESOLVER + path, {
      ...opts,
      headers: {
        Authorization: 'Bearer ' + accessToken,
        'Content-Type': 'application/json',
        ...(opts && opts.headers ? opts.headers : {}),
      },
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || data.error || ('HTTP ' + res.status));
    return data;
  }

  async function refreshSubscription() {
    if (!accessToken || !resolverOk) {
      updateSubButtons();
      return;
    }
    try {
      const data = await api('/ai-art/subscribe', { method: 'GET' });
      frequency = data.subscribed ? data.frequency : null;
      updateSubButtons();
    } catch (e) {
      els.status.textContent = 'Could not load subscription: ' + e.message;
    }
  }

  async function setFrequency(freq) {
    if (!resolverOk || !accessToken) return;
    els.status.textContent = 'Saving…';
    try {
      const data = await api('/ai-art/subscribe', {
        method: 'POST',
        body: JSON.stringify({ frequency: freq }),
      });
      frequency = data.frequency || freq;
      updateSubButtons();
    } catch (e) {
      els.status.textContent = 'Subscribe failed: ' + e.message;
    }
  }

  async function cancelSub() {
    if (!resolverOk || !accessToken) return;
    els.status.textContent = 'Cancelling…';
    try {
      await api('/ai-art/subscribe', { method: 'DELETE' });
      frequency = null;
      updateSubButtons();
    } catch (e) {
      els.status.textContent = 'Cancel failed: ' + e.message;
    }
  }

  function openProfile() {
    els.dialog.hidden = false;
    els.dialog.classList.add('open');
    updateSubButtons();
    refreshSubscription();
  }
  function closeProfile() {
    els.dialog.classList.remove('open');
    els.dialog.hidden = true;
  }

  function onProfileClick() {
    if (user) {
      openProfile();
      return;
    }
    signIn().catch((e) => alert(e.message || String(e)));
  }

  function bootGoatcounter() {
    const endpoint = cfg.goatcounterUrl || '';
    if (!endpoint) return;
    const s = document.createElement('script');
    s.async = true;
    s.src = 'https://gc.zgo.at/count.js';
    s.setAttribute('data-goatcounter', endpoint);
    s.setAttribute(
      'data-goatcounter-settings',
      JSON.stringify({ allow_local: location.hostname === 'localhost' || location.hostname === '127.0.0.1' })
    );
    document.head.appendChild(s);
  }

  els.profileBtn.addEventListener('click', onProfileClick);
  els.close.addEventListener('click', closeProfile);
  els.dialog.addEventListener('click', (e) => {
    if (e.target === els.dialog) closeProfile();
  });
  els.daily.addEventListener('click', () => setFrequency('daily'));
  els.weekly.addEventListener('click', () => setFrequency('weekly'));
  els.cancel.addEventListener('click', cancelSub);
  els.logout.addEventListener('click', () => {
    clearStored();
    renderAuth();
    closeProfile();
  });

  loadStored();
  renderAuth();
  bootGoatcounter();
  probeResolver().then(() => {
    if (accessToken) refreshSubscription();
  });
})();
