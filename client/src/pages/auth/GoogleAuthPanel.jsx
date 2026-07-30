/*
 * The single "Continue with Google" action shared by the login & signup pages.
 *
 * Google is the ONLY way to sign in or create an account. The official Google
 * button returns a signed ID token (`credential`); we hand it to the backend
 * (via AuthContext.loginWithGoogle), which verifies it and logs the user in —
 * creating the account automatically on the first sign-in. We never collect a
 * password, email, name or phone number here.
 */
import { useState } from "react";
import { useLocation, useNavigate } from "react-router";
import { GoogleLogin } from "@react-oauth/google";
import { Alert } from "../../components/ui/Alert";
import { Spinner } from "../../components/ui/Spinner";
import { useAuth } from "../../auth/AuthContext";
import { apiError } from "../../lib/api";

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || "";

export function GoogleAuthPanel() {
  const { loginWithGoogle } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const redirectTo = location.state?.from?.pathname || "/dashboard";

  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const handleCredential = async (credential) => {
    if (!credential) {
      setError("Google didn't return a sign-in token. Please try again.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await loginWithGoogle(credential);
      navigate(redirectTo, { replace: true });
    } catch (err) {
      setError(apiError(err, "Could not sign you in with Google. Please try again."));
      setBusy(false); // leave the button visible to retry; success unmounts us
    }
  };

  return (
    <div className="space-y-5">
      <Alert tone="error">{error}</Alert>

      {!GOOGLE_CLIENT_ID ? (
        <Alert tone="warning">
          Google sign-in isn't configured. Set <code>VITE_GOOGLE_CLIENT_ID</code> in the
          frontend environment to enable it.
        </Alert>
      ) : busy ? (
        <div className="flex items-center justify-center gap-2 py-3 text-sm font-medium text-ink-soft">
          <Spinner className="h-4 w-4" /> Signing you in…
        </div>
      ) : (
        /* Always render Google's light ("outline") button — in both site themes,
           per design choice — so the official branding stays consistent. */
        <div className="flex justify-center">
          <GoogleLogin
            onSuccess={(resp) => handleCredential(resp.credential)}
            onError={() => setError("Google sign-in was cancelled or failed. Please try again.")}
            theme="outline"
            text="continue_with"
            shape="pill"
            size="large"
            width="300"
            logo_alignment="center"
          />
        </div>
      )}

      <div className="flex items-center gap-3 text-xs font-medium text-ink-soft">
        <span className="h-px flex-1 bg-line" />
        Google only
        <span className="h-px flex-1 bg-line" />
      </div>

      <p className="text-center text-xs leading-relaxed text-ink-soft">
        Digikart accounts are created with Google. Use <span className="font-semibold text-ink">Continue with Google</span> to
        sign in — the first time, it creates your account automatically. Your Google email is your
        login; we never see your Google password.
      </p>
    </div>
  );
}
