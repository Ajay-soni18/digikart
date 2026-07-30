import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router";
import { AuthShell } from "./AuthShell";
import { GoogleAuthPanel } from "./GoogleAuthPanel";
import { useAuth } from "../../auth/AuthContext";

export default function Login() {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const redirectTo = location.state?.from?.pathname || "/dashboard";

  useEffect(() => {
    document.title = "Sign in · Digikart";
  }, []);

  useEffect(() => {
    if (isAuthenticated) navigate(redirectTo, { replace: true });
  }, [isAuthenticated, navigate, redirectTo]);

  return (
    <AuthShell
      title="Welcome to Digikart"
      subtitle="Sign in or create your account with Google."
    >
      <GoogleAuthPanel />
    </AuthShell>
  );
}
