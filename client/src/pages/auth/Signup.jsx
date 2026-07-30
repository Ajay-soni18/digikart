import { useEffect } from "react";
import { useNavigate } from "react-router";
import { AuthShell } from "./AuthShell";
import { GoogleAuthPanel } from "./GoogleAuthPanel";
import { useAuth } from "../../auth/AuthContext";

export default function Signup() {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    document.title = "Create account · Digikart";
  }, []);

  useEffect(() => {
    if (isAuthenticated) navigate("/dashboard", { replace: true });
  }, [isAuthenticated, navigate]);

  return (
    <AuthShell
      title="Create your account"
      subtitle="Sign up with Google — it's the only way to join Digikart."
    >
      <GoogleAuthPanel />
    </AuthShell>
  );
}
