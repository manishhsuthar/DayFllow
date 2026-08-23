import { apiGet, apiPost, clearTokens, getTokens, setTokens } from "@/api/client";

export type Role = "ADMIN" | "HR" | "EMP" | "INT";

export interface OrganizationSummary {
  name: string;
  slug: string;
  timezone: string;
  logo_url: string;
}

export interface CurrentUser {
  id: number;
  login_id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: Role;
  department: string;
  employment_type: string;
  date_of_joining: string;
  must_change_password: boolean;
  organization: OrganizationSummary | null;
}

interface SessionResponse {
  access: string;
  refresh: string;
  must_change_password: boolean;
  user: CurrentUser;
}

export const login = async (loginId: string, password: string): Promise<CurrentUser> => {
  const data: SessionResponse = await apiPost("/auth/login/", {
    login_id: loginId,
    password,
  });
  setTokens({ access: data.access, refresh: data.refresh });
  return data.user;
};

/** Signup creates a company. It cannot join an existing one (audit V-01). */
export const signup = async (payload: {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
  company_name: string;
  timezone?: string;
}) => apiPost("/accounts/register/", payload);

/**
 * The server is the authority on who you are and what role you hold. The app used
 * to read its role out of localStorage, so editing one key revealed the whole
 * admin interface (audit V-24).
 */
export const fetchCurrentUser = () => apiGet("/auth/me/") as Promise<CurrentUser>;

/** Blacklists the refresh token server-side, then clears local state. */
export const logout = async () => {
  const tokens = getTokens();
  try {
    if (tokens?.refresh) {
      await apiPost("/auth/logout/", { refresh: tokens.refresh });
    }
  } catch {
    // A already-expired token is fine: the session is gone either way.
  } finally {
    clearTokens();
  }
};

export const changePassword = async (oldPassword: string, newPassword: string) => {
  const data: SessionResponse & { detail: string } = await apiPost("/auth/change-password/", {
    old_password: oldPassword,
    new_password: newPassword,
  });
  // A fresh session, so the caller is not left holding a token minted under the
  // old password.
  if (data.access) {
    setTokens({ access: data.access, refresh: data.refresh });
  }
  return data.user;
};

export const requestPasswordReset = (email: string) =>
  apiPost("/auth/password-reset/", { email }) as Promise<{ detail: string }>;

export const confirmPasswordReset = (payload: {
  uid: string;
  token: string;
  new_password: string;
}) => apiPost("/auth/password-reset/confirm/", payload) as Promise<{ detail: string }>;
