/*
 * Auth state for the whole app.
 *
 * Holds the logged-in user, bootstraps it from a stored token on load, and
 * exposes Google sign-in / logout. Accounts are created and authenticated
 * SOLELY through Google: `loginWithGoogle` posts a Google ID token to the
 * backend, which verifies it and returns our own JWTs (the same single-device
 * tokens the rest of the app already uses). Tokens live in localStorage (see
 * api.js); the API client handles attaching and refreshing them.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, setAuthFailureHandler, tokenStore } from "../lib/api";
import { clearFileCache } from "../lib/fileCache";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true); // bootstrapping the session

  const clearSession = useCallback(() => {
    tokenStore.clear();
    setUser(null);
    // Wipe locally cached files whenever the session ends, so a different
    // account on this device can't open the previous user's paid files from
    // the local cache. Best-effort and scoped to OUR file store only — it never
    // touches tokens, theme, reading positions, or any other site's data.
    clearFileCache().catch(() => {});
  }, []);

  // If a token refresh ultimately fails, drop the session (this is a logout too,
  // so the cached files are cleared for the same reason).
  useEffect(() => {
    setAuthFailureHandler(() => {
      setUser(null);
      clearFileCache().catch(() => {});
    });
  }, []);

  // On first load, if we have a token, fetch the current user.
  useEffect(() => {
    let active = true;
    async function bootstrap() {
      if (!tokenStore.access && !tokenStore.refresh) {
        setLoading(false);
        return;
      }
      try {
        const { data } = await api.get("/auth/me/");
        if (active) setUser(data);
      } catch {
        if (active) clearSession();
      } finally {
        if (active) setLoading(false);
      }
    }
    bootstrap();
    return () => {
      active = false;
    };
  }, [clearSession]);

  // Exchange a Google ID token (from the "Continue with Google" button) for our
  // own JWTs. The backend verifies the token, then creates the account on first
  // sign-in or logs the returning user in — both return {user, access, refresh}.
  const loginWithGoogle = useCallback(async (credential) => {
    const { data } = await api.post("/auth/google/", { credential });
    tokenStore.set({ access: data.access, refresh: data.refresh });
    setUser(data.user);
    return data.user;
  }, []);

  const logout = useCallback(async () => {
    try {
      if (tokenStore.refresh) {
        await api.post("/auth/logout/", { refresh: tokenStore.refresh });
      }
    } catch {
      /* ignore — we clear locally regardless */
    } finally {
      clearSession();
    }
  }, [clearSession]);

  const value = useMemo(
    () => ({
      user,
      loading,
      isAuthenticated: !!user,
      isAdmin: !!user?.is_admin,
      loginWithGoogle,
      logout,
      setUser,
    }),
    [user, loading, loginWithGoogle, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
