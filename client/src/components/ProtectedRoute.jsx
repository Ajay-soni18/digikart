/* Route guards. ProtectedRoute requires login; AdminRoute also requires staff. */
import { Navigate, useLocation } from "react-router";
import { useAuth } from "../auth/AuthContext";
import { FullScreenLoader } from "./ui/Spinner";

export function ProtectedRoute({ children, adminOnly = false }) {
  const { isAuthenticated, isAdmin, loading } = useAuth();
  const location = useLocation();

  if (loading) return <FullScreenLoader label="Checking your session…" />;

  if (!isAuthenticated) {
    // Remember where they were headed so we can return after login.
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  if (adminOnly && !isAdmin) {
    return <Navigate to="/dashboard" replace />;
  }
  return children;
}
