/*
 * Central API client for the Django backend.
 *
 * - Base URL comes from VITE_API_BASE_URL; we append the versioned /api/v1 path.
 * - The access token is attached to every request.
 * - On a 401 we transparently try ONE refresh using the refresh token, then
 *   replay the original request. Concurrent 401s share a single refresh call
 *   (single-flight) so we never fire multiple refreshes at once.
 */
import axios from "axios";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

// Absolute /api/v1 base — used where we can't go through axios (e.g. pdf.js,
// which does its own ranged fetches for progressive PDF streaming).
const API_V1 = `${BASE_URL}/api/v1`;

const ACCESS_KEY = "digikart_access";
const REFRESH_KEY = "digikart_refresh";

export const tokenStore = {
  get access() {
    return localStorage.getItem(ACCESS_KEY);
  },
  get refresh() {
    return localStorage.getItem(REFRESH_KEY);
  },
  set({ access, refresh }) {
    if (access) localStorage.setItem(ACCESS_KEY, access);
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

// A timeout so a stalled network never leaves the UI spinning forever — a
// timed-out request rejects and surfaces a friendly message (see apiError).
// Large file uploads in the admin override this with `timeout: 0` (adminApi.js).
const REQUEST_TIMEOUT = 30000;

export const api = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  headers: { "Content-Type": "application/json" },
  timeout: REQUEST_TIMEOUT,
});

// A bare client for the refresh call so it doesn't go through the interceptor
// (which would loop on failure).
const refreshClient = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  timeout: REQUEST_TIMEOUT,
});

api.interceptors.request.use((config) => {
  const token = tokenStore.access;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

let refreshPromise = null;

// Called when refresh ultimately fails — the AuthProvider registers a handler
// here so it can clear user state and bounce to /login.
let onAuthFailure = () => {};
export function setAuthFailureHandler(fn) {
  onAuthFailure = fn;
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    const status = error.response?.status;

    // Only attempt refresh for a genuine 401 we haven't already retried, and
    // never for the auth endpoints themselves (Google sign-in + token refresh).
    const isAuthCall = original?.url?.includes("/auth/google") ||
      original?.url?.includes("/auth/token/refresh");

    if (status === 401 && !original._retry && !isAuthCall && tokenStore.refresh) {
      original._retry = true;
      try {
        refreshPromise =
          refreshPromise ||
          refreshClient
            .post("/auth/token/refresh/", { refresh: tokenStore.refresh })
            .then((r) => r.data);
        const data = await refreshPromise;
        refreshPromise = null;
        tokenStore.set({ access: data.access, refresh: data.refresh });
        original.headers.Authorization = `Bearer ${data.access}`;
        return api(original);
      } catch (refreshError) {
        refreshPromise = null;
        tokenStore.clear();
        onAuthFailure();
        return Promise.reject(refreshError);
      }
    }
    return Promise.reject(error);
  }
);

/** True when a request never got a response (offline, DNS, CORS, timeout). */
export function isNetworkError(error) {
  return !!error && !error.response;
}

/**
 * Turn any axios/API error into a clean, user-safe message. Never exposes raw
 * HTML, stack traces, or status codes.
 *
 * - No response → distinguishes a timeout from a connection failure.
 * - DRF body → uses `detail` or the first field error.
 * - The backend only sends a `debug` block to staff (or in dev), so when it's
 *   present we append it — that's how admins see extra detail safely.
 */
export function apiError(error, fallback = "Something went wrong. Please try again.") {
  // No response at all: network down, CORS, DNS, or a timeout.
  if (isNetworkError(error)) {
    if (error?.code === "ECONNABORTED" || /timeout/i.test(error?.message || "")) {
      return "The server is taking too long to respond. Please try again.";
    }
    return "Can't reach the server. Please check your internet connection and try again.";
  }

  const data = error.response?.data;
  let message = fallback;
  if (typeof data === "string") {
    // A non-JSON (e.g. HTML) body should never be shown verbatim.
    message = data.trim().startsWith("<") ? fallback : data;
  } else if (data && typeof data === "object") {
    if (data.detail) {
      message = data.detail;
    } else {
      // DRF field errors: { field: ["msg", ...] }
      const first = Object.values(data)[0];
      if (Array.isArray(first)) message = first[0];
      else if (typeof first === "string") message = first;
    }
  }

  // Staff-only extra detail (backend gates this; normal users never receive it).
  const debug = data?.debug;
  if (debug?.message) {
    message = `${message} (${debug.type || "Error"}: ${debug.message})`;
  }
  return message;
}
