import React from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import type { Role } from "@/api/auth";

const Loading: React.FC = () => (
  <div className="flex min-h-screen items-center justify-center bg-background">
    <div className="flex flex-col items-center gap-3">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      <p className="text-sm text-muted-foreground">Loading your workspace…</p>
    </div>
  </div>
);

/**
 * Route guard.
 *
 * The previous guard checked only `isAuthenticated`, derived from a localStorage
 * value the user controls, and no route checked `role` at all -- so every admin
 * screen rendered for any logged-in user (audit V-24).
 *
 * This is defence in depth, not the security boundary: the API enforces the same
 * rules server-side. It exists so people are not shown screens whose every
 * request would 403.
 */
export const RequireAuth: React.FC<{ roles?: Role[]; children?: React.ReactNode }> = ({
  roles,
  children,
}) => {
  const { isLoading, isAuthenticated, user, mustChangePassword } = useAuth();
  const location = useLocation();

  if (isLoading) return <Loading />;

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }

  // A pending rotation blocks the whole API server-side, so there is nothing
  // useful to render until it is done.
  if (mustChangePassword && location.pathname !== "/change-password") {
    return <Navigate to="/change-password" replace />;
  }

  if (roles && user && !roles.includes(user.role)) {
    const home = user.role === "ADMIN" || user.role === "HR"
      ? "/dashboard/admin"
      : "/dashboard/employee";
    return <Navigate to={home} replace />;
  }

  return <>{children ?? <Outlet />}</>;
};

/** Renders children only for the given roles. For hiding actions, not data. */
export const RoleGate: React.FC<{ roles: Role[]; children: React.ReactNode; fallback?: React.ReactNode }> = ({
  roles,
  children,
  fallback = null,
}) => {
  const { user } = useAuth();
  if (!user || !roles.includes(user.role)) return <>{fallback}</>;
  return <>{children}</>;
};

export default RequireAuth;
