import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import {
  changePassword as apiChangePassword,
  fetchCurrentUser,
  login as apiLogin,
  logout as apiLogout,
  signup as apiSignup,
  type CurrentUser,
  type Role,
} from "@/api/auth";
import { clearTokens, getTokens, setSessionExpiredHandler } from "@/api/client";

interface AuthContextType {
  user: CurrentUser | null;
  /** True until the stored session has been checked against the server. */
  isLoading: boolean;
  isAuthenticated: boolean;
  mustChangePassword: boolean;
  hasRole: (...roles: Role[]) => boolean;
  isOwner: boolean;
  isManagement: boolean;
  login: (loginId: string, password: string) => Promise<CurrentUser>;
  signup: (payload: Parameters<typeof apiSignup>[0]) => Promise<unknown>;
  changePassword: (oldPassword: string, newPassword: string) => Promise<CurrentUser>;
  refreshUser: () => Promise<CurrentUser | null>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  /**
   * Identity comes from the server, every session, and is never persisted.
   *
   * The app used to hydrate `user` -- including `role` -- straight out of
   * localStorage, a value the user controls, so setting `{"role":"ADMIN"}` there
   * revealed the entire admin interface (audit V-24).
   */
  const refreshUser = useCallback(async () => {
    if (!getTokens()) {
      setUser(null);
      return null;
    }
    try {
      const current = await fetchCurrentUser();
      setUser(current);
      return current;
    } catch {
      clearTokens();
      setUser(null);
      return null;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      await refreshUser();
      if (!cancelled) setIsLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshUser]);

  // When a refresh token finally expires, drop the user so the guards redirect.
  useEffect(() => {
    setSessionExpiredHandler(() => setUser(null));
    return () => setSessionExpiredHandler(null);
  }, []);

  const login = useCallback(async (loginId: string, password: string) => {
    const current = await apiLogin(loginId, password);
    setUser(current);
    return current;
  }, []);

  const signup = useCallback(
    (payload: Parameters<typeof apiSignup>[0]) => apiSignup(payload),
    [],
  );

  const changePassword = useCallback(async (oldPassword: string, newPassword: string) => {
    const current = await apiChangePassword(oldPassword, newPassword);
    setUser(current);
    return current;
  }, []);

  const logout = useCallback(async () => {
    await apiLogout();
    setUser(null);
  }, []);

  const value = useMemo<AuthContextType>(() => {
    const hasRole = (...roles: Role[]) => Boolean(user && roles.includes(user.role));
    return {
      user,
      isLoading,
      isAuthenticated: Boolean(user),
      mustChangePassword: Boolean(user?.must_change_password),
      hasRole,
      isOwner: hasRole("ADMIN"),
      isManagement: hasRole("ADMIN", "HR"),
      login,
      signup,
      changePassword,
      refreshUser,
      logout,
    };
  }, [user, isLoading, login, signup, changePassword, refreshUser, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
};

export default AuthContext;
