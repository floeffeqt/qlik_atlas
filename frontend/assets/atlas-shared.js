(function () {
  var TOKEN_STORAGE_KEY = 'auth_access_token';
  var USER_STORAGE_KEY = 'atlas_auth_user_v1';
  var FOCUS_PROJECT_STORAGE_KEY = 'atlas_focus_project_id_v1';
  var FOCUS_CUSTOMER_STORAGE_KEY = 'atlas_focus_customer_id_v1';
  var refreshInFlight = null;

  function redirectToLogin() {
    window.location.href = '/login.html';
  }

  function clearLegacyToken() {
    try {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
    } catch (_err) {}
  }

  function clearCachedUser() {
    try {
      localStorage.removeItem(USER_STORAGE_KEY);
    } catch (_err) {}
  }

  function clearAuthState() {
    clearLegacyToken();
    clearCachedUser();
  }

  function normalizeUser(user) {
    if (!user || typeof user !== 'object') return null;
    if (user.id === undefined || user.id === null) return null;
    return {
      id: Number(user.id) || 0,
      email: String(user.email || ''),
      role: String(user.role || 'user'),
      is_active: user.is_active !== false,
      created_at: String(user.created_at || ''),
    };
  }

  function getCachedUser() {
    try {
      var raw = localStorage.getItem(USER_STORAGE_KEY);
      if (!raw) return null;
      return normalizeUser(JSON.parse(raw));
    } catch (_err) {
      return null;
    }
  }

  function setCachedUser(user) {
    var normalized = normalizeUser(user);
    if (!normalized) {
      clearCachedUser();
      return null;
    }
    try {
      localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(normalized));
    } catch (_err) {}
    return normalized;
  }

  function applyUserUi(user, options) {
    var opts = options || {};
    var currentUser = normalizeUser(user);
    if (opts.emailElementId) {
      var emailEl = document.getElementById(opts.emailElementId);
      if (emailEl) {
        emailEl.textContent = currentUser ? (currentUser.email || ('User #' + (currentUser.id || '-'))) : '-';
      }
    }
    if (opts.adminFabId) {
      var adminFab = document.getElementById(opts.adminFabId);
      if (adminFab) {
        adminFab.style.display = currentUser && currentUser.role === 'admin' ? 'inline-block' : 'none';
      }
    }
  }

  function enforceRole(user, options) {
    var opts = options || {};
    if (!opts.requiredRole) return false;
    var currentUser = normalizeUser(user);
    if (!currentUser) return false;
    if (String(currentUser.role || 'user') !== String(opts.requiredRole)) {
      window.location.href = String(opts.onRoleMismatchRedirect || '/');
      return true;
    }
    return false;
  }

  function getToken() {
    return null;
  }

  function decodeJwtPayload() {
    return {};
  }

  function authHeaders(extra) {
    return Object.assign({}, extra || {});
  }

  function isRefreshRelatedPath(path) {
    var raw = String(path || '');
    return raw.indexOf('/api/auth/login') === 0
      || raw.indexOf('/api/auth/logout') === 0
      || raw.indexOf('/api/auth/refresh') === 0;
  }

  function buildFetchOptions(opts) {
    var options = Object.assign({ credentials: 'include' }, opts || {});
    options.headers = authHeaders(options.headers || {});
    return options;
  }

  async function refreshAccessToken() {
    if (refreshInFlight) return refreshInFlight;
    refreshInFlight = fetch('/api/auth/refresh', {
      method: 'POST',
      credentials: 'include',
    }).then(async function (response) {
      if (!response.ok) {
        clearAuthState();
        return null;
      }
      var payload = await response.json().catch(function () { return null; });
      var normalized = setCachedUser(payload && payload.user ? payload.user : null);
      return normalized;
    }).finally(function () {
      refreshInFlight = null;
    });
    return refreshInFlight;
  }

  async function logout() {
    clearAuthState();
    try {
      await fetch('/api/auth/logout', {
        method: 'POST',
        credentials: 'include',
      });
    } catch (_err) {}
    redirectToLogin();
  }

  async function apiFetch(path, opts) {
    var options = buildFetchOptions(opts);
    var response = await fetch(path, options);
    if (response.status !== 401 || isRefreshRelatedPath(path) || options._skipRefresh) {
      if (response.status === 401 && isRefreshRelatedPath(path)) {
        clearAuthState();
        redirectToLogin();
      }
      return response;
    }

    var refreshedUser = await refreshAccessToken();
    if (!refreshedUser) {
      clearAuthState();
      redirectToLogin();
      return response;
    }

    var retryOptions = buildFetchOptions(opts);
    retryOptions._skipRefresh = true;
    var retryResponse = await fetch(path, retryOptions);
    if (retryResponse.status === 401) {
      clearAuthState();
      redirectToLogin();
    }
    return retryResponse;
  }

  async function apiFetchJson(path, fallbackMessage, opts) {
    var response = await apiFetch(path, opts);
    if (response.ok) {
      return await response.json();
    }
    var message = fallbackMessage || 'Backend request failed';
    try {
      var payload = await response.json();
      if (payload && payload.detail) {
        if (typeof payload.detail === 'string') message = payload.detail;
        else if (payload.detail.message) message = payload.detail.message;
      }
    } catch (_err) {}
    var error = new Error(message);
    error.status = response.status;
    throw error;
  }

  async function fetchCurrentUser(options) {
    var response = await fetch('/api/auth/me', { credentials: 'include' });
    if (response.status === 401) {
      var refreshed = await refreshAccessToken();
      if (!refreshed) {
        clearAuthState();
        redirectToLogin();
        return null;
      }
      response = await fetch('/api/auth/me', { credentials: 'include' });
    }
    if (response.status === 401 || response.status === 403) {
      clearAuthState();
      redirectToLogin();
      return null;
    }
    if (!response.ok) return null;
    var user = await response.json().catch(function () { return null; });
    var normalized = setCachedUser(user);
    applyUserUi(normalized, options);
    enforceRole(normalized, options);
    return normalized;
  }

  function refreshSession(options) {
    return fetchCurrentUser(options).catch(function () {
      return null;
    });
  }

  function requireAuth(options) {
    var opts = options || {};
    var cachedUser = getCachedUser();
    applyUserUi(cachedUser, opts);
    if (!enforceRole(cachedUser, opts)) {
      window.setTimeout(function () {
        refreshSession(opts);
      }, 0);
    }
    return { user: cachedUser || null, token: '' };
  }

  function bindLogout(buttonId) {
    var button = document.getElementById(buttonId);
    if (!button) return;
    button.addEventListener('click', function (event) {
      if (event && typeof event.preventDefault === 'function') event.preventDefault();
      logout();
    });
  }

  function showToast(message, duration, elementId) {
    var toast = document.getElementById(elementId || 'toast');
    if (!toast) return;
    toast.textContent = String(message || '');
    toast.classList.add('show');
    window.setTimeout(function () {
      toast.classList.remove('show');
    }, duration || 3000);
  }

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function readFocusState(search) {
    var params = new URLSearchParams(search || window.location.search);
    var projectFromUrl = String(params.get('project') || '').trim();
    var customerFromUrl = String(params.get('customer') || '').trim();
    var projectFromStorage = String(localStorage.getItem(FOCUS_PROJECT_STORAGE_KEY) || '').trim();
    var customerFromStorage = String(localStorage.getItem(FOCUS_CUSTOMER_STORAGE_KEY) || '').trim();
    return {
      project: projectFromUrl || projectFromStorage,
      customer: customerFromUrl || customerFromStorage,
    };
  }

  function persistFocusState(state) {
    var nextState = state || {};
    if (nextState.project) localStorage.setItem(FOCUS_PROJECT_STORAGE_KEY, String(nextState.project));
    else localStorage.removeItem(FOCUS_PROJECT_STORAGE_KEY);
    if (nextState.customer) localStorage.setItem(FOCUS_CUSTOMER_STORAGE_KEY, String(nextState.customer));
    else localStorage.removeItem(FOCUS_CUSTOMER_STORAGE_KEY);
  }

  function projectCustomerId(project) {
    if (!project || typeof project !== 'object') return '';
    if (project.customer_id !== undefined && project.customer_id !== null) return String(project.customer_id);
    if (project.customer && project.customer.id !== undefined && project.customer.id !== null) {
      return String(project.customer.id);
    }
    return '';
  }

  function syncCustomerFromProject(state, projectsById) {
    var currentState = state || {};
    if (!currentState.project) return currentState;
    var project = (projectsById || {})[String(currentState.project)];
    var customerId = projectCustomerId(project);
    if (customerId) currentState.customer = customerId;
    return currentState;
  }

  function updateNavProjectContext(projectId, customerId, selector) {
    var pid = String(projectId || '').trim();
    var cid = String(customerId || '').trim();
    document.querySelectorAll(selector || 'a.nav-link').forEach(function (link) {
      var baseHref = link.getAttribute('data-base-href');
      if (!baseHref) {
        baseHref = String(link.getAttribute('href') || '').split('?')[0];
        link.setAttribute('data-base-href', baseHref);
      }
      var nextHref = baseHref;
      if (baseHref === '/' || baseHref === '/analytics.html' || baseHref === '/lineage.html' || baseHref === '/script-sync.html') {
        var params = new URLSearchParams();
        if (pid) params.set('project', pid);
        if (cid) params.set('customer', cid);
        var query = params.toString();
        nextHref = baseHref + (query ? ('?' + query) : '');
      }
      link.setAttribute('href', nextHref);
    });
  }

  window.AtlasShared = {
    TOKEN_STORAGE_KEY: TOKEN_STORAGE_KEY,
    USER_STORAGE_KEY: USER_STORAGE_KEY,
    FOCUS_PROJECT_STORAGE_KEY: FOCUS_PROJECT_STORAGE_KEY,
    FOCUS_CUSTOMER_STORAGE_KEY: FOCUS_CUSTOMER_STORAGE_KEY,
    requireAuth: requireAuth,
    bindLogout: bindLogout,
    logout: logout,
    getToken: getToken,
    getCachedUser: getCachedUser,
    setCachedUser: setCachedUser,
    refreshSession: refreshSession,
    refreshAccessToken: refreshAccessToken,
    decodeJwtPayload: decodeJwtPayload,
    authHeaders: authHeaders,
    apiFetch: apiFetch,
    apiFetchJson: apiFetchJson,
    showToast: showToast,
    escapeHtml: escapeHtml,
    readFocusState: readFocusState,
    persistFocusState: persistFocusState,
    projectCustomerId: projectCustomerId,
    syncCustomerFromProject: syncCustomerFromProject,
    updateNavProjectContext: updateNavProjectContext,
  };
})();
