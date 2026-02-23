const AUTH_TOKEN_KEY = 'auth_access_token';

export function setToken(token) {
  localStorage.setItem(AUTH_TOKEN_KEY, token);
}

export function getToken() {
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

export function removeToken() {
  localStorage.removeItem(AUTH_TOKEN_KEY);
}

export async function apiFetch(path, opts = {}) {
  const url = path.startsWith('/') ? path : `/${path}`;
  const headers = opts.headers || {};
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;
  headers['Content-Type'] = headers['Content-Type'] || 'application/json';
  const res = await fetch(url, { ...opts, headers });
  if (res.status === 401) {
    removeToken();
    window.location.href = '/login.html';
    return res;
  }
  return res;
}

export async function login(email, password) {
  const res = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Login failed');
  }
  const payload = await res.json();
  setToken(payload.access_token);
  return payload;
}

export async function register(email, password) {
  const res = await fetch('/api/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Registration failed');
  }
  const payload = await res.json();
  setToken(payload.access_token);
  return payload;
}
