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
    avatarIcon: document.getElementById('authAvatarIcon'),
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
      els.profileBtn.title = 'Subscribe';
      els.profileBtn.setAttribute('aria-label', 'Subscribe');
      els.profileBtn.setAttribute('aria-haspopup', 'dialog');
      if (els.avatarIcon) els.avatarIcon.hidden = true;
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
      els.name.textContent = user.name || 'Subscribe';
      els.email.textContent = user.email || '';
    } else {
      els.profileLabel.textContent = 'Subscribe';
      els.profileBtn.title = 'Subscribe';
      els.profileBtn.setAttribute('aria-label', 'Subscribe');
      els.profileBtn.removeAttribute('aria-haspopup');
      els.avatarImg.removeAttribute('src');
      els.avatarImg.hidden = true;
      els.avatarFallback.hidden = true;
      els.avatarFallback.textContent = '';
      if (els.avatarIcon) els.avatarIcon.hidden = false;
      els.name.textContent = 'Subscribe';
      els.email.textContent = '';
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
        : (resolverOk ? 'Sign in with Google to subscribe' : 'Subscription server offline');
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
      els.status.textContent = 'Continue with Google to choose daily or weekly email.';
    } else if (frequency) {
      els.status.textContent = 'Current plan: ' + frequency + ' — one headline image per email.';
    } else {
      els.status.textContent = 'Not subscribed yet — pick daily or weekly below.';
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

  let gisPromise = null;
  let tokenClient = null;

  function loadGis() {
    if (gisPromise) return gisPromise;
    gisPromise = new Promise((resolve, reject) => {
      if (window.google && window.google.accounts && window.google.accounts.oauth2) {
        resolve();
        return;
      }
      const existing = document.querySelector('script[data-ai-art-gis]');
      if (existing) {
        existing.addEventListener('load', () => resolve());
        existing.addEventListener('error', () => reject(new Error('GIS load failed')));
        return;
      }
      const s = document.createElement('script');
      s.src = 'https://accounts.google.com/gsi/client';
      s.async = true;
      s.setAttribute('data-ai-art-gis', '1');
      s.onload = () => resolve();
      s.onerror = () => reject(new Error('GIS load failed'));
      document.head.appendChild(s);
    });
    return gisPromise;
  }

  function ensureTokenClient() {
    if (tokenClient) return tokenClient;
    if (!CLIENT_ID) throw new Error('Google client id not configured');
    if (!(window.google && window.google.accounts && window.google.accounts.oauth2)) {
      return null;
    }
    tokenClient = window.google.accounts.oauth2.initTokenClient({
      client_id: CLIENT_ID,
      scope: 'openid email profile',
      callback: (resp) => {
        if (resp && resp.error) {
          const msg = resp.error_description || resp.error || 'Sign-in failed';
          if (!/popup_closed|access_denied|closed/i.test(msg)) {
            alert(msg);
          }
          return;
        }
        if (!resp || !resp.access_token) {
          alert('Sign-in failed — no access token');
          return;
        }
        accessToken = resp.access_token;
        fetchProfile(accessToken)
          .then((u) => {
            user = u;
            saveStored();
            renderAuth();
            return refreshSubscription();
          })
          .then(() => openProfile())
          .catch((err) => alert(err.message || String(err)));
      },
      error_callback: (err) => {
        const msg = (err && (err.message || err.type)) || 'Google sign-in failed';
        if (/popup|window/i.test(msg)) {
          alert(
            'Sign-in popup was blocked. Allow popups for this site, then try Sign in again.'
          );
          return;
        }
        if (!/popup_closed|closed_by_user|access_denied/i.test(msg)) {
          alert(msg);
        }
      },
    });
    return tokenClient;
  }

  /** Must run synchronously from a click — awaiting first breaks the popup gesture. */
  function signInFromClick() {
    if (!CLIENT_ID) {
      alert('Google client id not configured');
      return;
    }
    const client = ensureTokenClient();
    if (!client) {
      loadGis()
        .then(() => {
          ensureTokenClient();
          alert('Google sign-in is ready — click Sign in again.');
        })
        .catch((e) => alert(e.message || String(e)));
      return;
    }
    // Interactive account chooser; empty prompt often fails the popup after an await.
    client.requestAccessToken({ prompt: 'select_account' });
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
    signInFromClick();
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
  // Preload GIS so Sign in can open the popup in the same click gesture.
  if (CLIENT_ID) {
    loadGis()
      .then(() => {
        try { ensureTokenClient(); } catch (e) { /* ignore until click */ }
      })
      .catch(() => { /* retry on click */ });
  }
  probeResolver().then(() => {
    if (accessToken) refreshSubscription();
  });
})();
