/**
 * HTTP client.
 *
 * Three things changed here, all of them audit findings:
 *
 * - Access tokens are 15 minutes now, not a day (V-23), so the client has to
 *   refresh. A single in-flight refresh is shared by every concurrent 401 so a
 *   burst of requests cannot each burn a refresh token.
 * - Logout blacklists the refresh token server-side instead of only clearing
 *   localStorage, which left the session valid for up to a week (V-23).
 * - List endpoints are paginated now (V-29), so `unwrapList` accepts either shape.
 */

const getBaseUrl = () => {
  const envUrl = import.meta.env.VITE_API_BASE_URL as string | undefined;
  if (envUrl && !envUrl.startsWith("/")) {
    return envUrl;
  }
  if (window.location.protocol === "file:") {
    // Electron loads from file://, so a relative path has nothing to resolve against.
    return (import.meta.env.VITE_DESKTOP_API_BASE_URL as string) || "http://localhost:8000/api";
  }
  return envUrl || "/api";
};

const BASE_URL = getBaseUrl();

const TOKEN_KEY = "dayflow_auth_tokens";

export interface AuthTokens {
  access: string;
  refresh: string;
}

/** Raised for any non-2xx response, carrying enough detail to act on. */
export class ApiError extends Error {
  status: number;
  code?: string;
  fieldErrors: Record<string, string[]>;

  constructor(message: string, status: number, code?: string, fieldErrors: Record<string, string[]> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.fieldErrors = fieldErrors;
  }

  /** The subscription lapsed or a seat limit was hit. */
  get isBillingBlocked() {
    return this.status === 402 || this.code === "subscription_inactive";
  }

  /** The account still holds its issued temporary password. */
  get needsPasswordRotation() {
    return this.code === "password_rotation_required";
  }
}

// ---------------------------------------------------------------------------
// Token storage
// ---------------------------------------------------------------------------

export const getTokens = (): AuthTokens | null => {
  try {
    const raw = localStorage.getItem(TOKEN_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed?.access ? (parsed as AuthTokens) : null;
  } catch {
    return null;
  }
};

export const setTokens = (tokens: AuthTokens) => {
  localStorage.setItem(TOKEN_KEY, JSON.stringify(tokens));
};

export const clearTokens = () => {
  localStorage.removeItem(TOKEN_KEY);
};

export const getAuthToken = () => getTokens()?.access ?? "";

/** Called when the session cannot be recovered, so the app can route to /login. */
let onSessionExpired: (() => void) | null = null;
export const setSessionExpiredHandler = (handler: (() => void) | null) => {
  onSessionExpired = handler;
};

// ---------------------------------------------------------------------------
// Refresh
// ---------------------------------------------------------------------------

// Shared so N concurrent 401s trigger one refresh, not N. With refresh-token
// rotation enabled server-side, racing refreshes would invalidate each other.
let refreshInFlight: Promise<string | null> | null = null;

const refreshAccessToken = async (): Promise<string | null> => {
  const tokens = getTokens();
  if (!tokens?.refresh) return null;

  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const response = await fetch(`${BASE_URL}/auth/refresh/`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh: tokens.refresh }),
        });
        if (!response.ok) {
          clearTokens();
          onSessionExpired?.();
          return null;
        }
        const data = await response.json();
        // Rotation is on server-side, so a new refresh token comes back with it.
        setTokens({ access: data.access, refresh: data.refresh ?? tokens.refresh });
        return data.access as string;
      } catch {
        return null;
      } finally {
        refreshInFlight = null;
      }
    })();
  }

  return refreshInFlight;
};

// ---------------------------------------------------------------------------
// Requests
// ---------------------------------------------------------------------------

const parseError = async (response: Response): Promise<ApiError> => {
  let message = response.statusText || "Request failed";
  let code: string | undefined;
  const fieldErrors: Record<string, string[]> = {};

  try {
    const data = await response.json();
    if (typeof data?.detail === "string") {
      message = data.detail;
    }
    if (typeof data?.code === "string") {
      code = data.code;
    }
    for (const [key, value] of Object.entries(data ?? {})) {
      if (key === "detail" || key === "code" || key === "error_id") continue;
      const messages = Array.isArray(value) ? value.map(String) : [String(value)];
      fieldErrors[key] = messages;
    }
    if (message === (response.statusText || "Request failed")) {
      const flat = Object.values(fieldErrors).flat();
      if (flat.length) message = flat.join(" ");
    }
    if (data?.error_id) {
      message = `${message} (reference ${data.error_id})`;
    }
  } catch {
    /* not JSON; keep the status text */
  }

  return new ApiError(message, response.status, code, fieldErrors);
};

interface RequestOptions {
  method?: string;
  body?: unknown;
  /** Set false for the auth endpoints, which must not trigger a refresh loop. */
  retryOnUnauthorized?: boolean;
  raw?: boolean;
}

const request = async (path: string, options: RequestOptions = {}): Promise<any> => {
  const { method = "GET", body, retryOnUnauthorized = true, raw = false } = options;

  const send = (token: string) => {
    const headers: Record<string, string> = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (token) headers.Authorization = `Bearer ${token}`;

    return fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  };

  let response = await send(getAuthToken());

  if (response.status === 401 && retryOnUnauthorized) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      response = await send(refreshed);
    } else {
      clearTokens();
      onSessionExpired?.();
    }
  }

  if (!response.ok) {
    throw await parseError(response);
  }

  if (raw) return response;
  if (response.status === 204) return null;
  return response.json();
};

export const apiGet = (path: string) => request(path);
export const apiPost = (path: string, body: unknown = {}) => request(path, { method: "POST", body });
export const apiPut = (path: string, body: unknown) => request(path, { method: "PUT", body });
export const apiPatch = (path: string, body: unknown) => request(path, { method: "PATCH", body });
export const apiDelete = (path: string) => request(path, { method: "DELETE" });

/**
 * Accept either a paginated envelope or a bare array.
 *
 * List endpoints gained pagination (audit V-29); a couple still return a bare
 * array because they are inherently small. Callers should not have to care.
 */
export const unwrapList = <T,>(payload: any): T[] => {
  if (Array.isArray(payload)) return payload as T[];
  if (payload && Array.isArray(payload.results)) return payload.results as T[];
  return [];
};

export const getPageCount = (payload: any): number => {
  if (Array.isArray(payload)) return payload.length;
  return typeof payload?.count === "number" ? payload.count : 0;
};

export const apiDownload = async (path: string) => {
  const response = (await request(path, { raw: true })) as Response;
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="([^"]+)"/i);
  return { blob, filename: match?.[1] || "download" };
};

// ---------------------------------------------------------------------------
// Realtime
// ---------------------------------------------------------------------------

export const getRealtimeWebSocketUrl = () => {
  const token = getAuthToken();
  if (!token) return "";

  let urlStr = import.meta.env.VITE_WS_URL as string | undefined;
  if (!urlStr) {
    urlStr = window.location.protocol === "file:" ? "ws://localhost:8000/ws/updates/" : "/ws/updates/";
  }

  if (urlStr.startsWith("/")) {
    const resolved = new URL(urlStr, window.location.href);
    resolved.protocol = resolved.protocol === "https:" ? "wss:" : "ws:";
    urlStr = resolved.toString();
  }

  return urlStr;
};

/**
 * The credential travels as a subprotocol rather than a query parameter, which
 * kept it out of access logs, proxy logs and browser history (audit V-12).
 */
export const getRealtimeSubprotocol = () => {
  const token = getAuthToken();
  return token ? `dayflow.jwt.${token}` : "";
};
