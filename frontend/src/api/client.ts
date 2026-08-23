const getBaseUrl = () => {
  const envUrl = import.meta.env.VITE_API_BASE_URL;
  if (envUrl && !envUrl.startsWith("/")) {
    return envUrl;
  }
  if (window.location.protocol === "file:" || !envUrl) {
    return "https://dayfllow.onrender.com/api";
  }
  return envUrl || "/api";
};

const BASE_URL = getBaseUrl();

export const getAuthToken = () => {
  const raw = localStorage.getItem("dayflow_auth_tokens");
  if (!raw) {
    return "";
  }

  try {
    const tokens = JSON.parse(raw);
    if (tokens?.access) {
      return tokens.access as string;
    }
  } catch {
    return "";
  }

  return "";
};

export const getRealtimeWebSocketUrl = () => {
  const token = getAuthToken();
  if (!token) {
    return "";
  }

  const configuredUrl = import.meta.env.VITE_WS_URL as string | undefined;
  let urlStr = configuredUrl;

  if (!urlStr) {
    if (window.location.protocol === "file:") {
      urlStr = "wss://dayfllow.onrender.com/ws/updates/";
    } else {
      urlStr = "/ws/updates/";
    }
  }

  if (urlStr.startsWith("/")) {
    const resolvedUrl = new URL(urlStr, window.location.href);
    if (resolvedUrl.protocol === "http:") {
      resolvedUrl.protocol = "ws:";
    } else if (resolvedUrl.protocol === "https:") {
      resolvedUrl.protocol = "wss:";
    }
    urlStr = resolvedUrl.toString();
  }

  const url = new URL(urlStr);
  url.searchParams.set("token", token);
  return url.toString();
};

const getAuthHeaders = () => {
  const accessToken = getAuthToken();
  if (accessToken) {
    return { Authorization: `Bearer ${accessToken}` };
  }

  return {};
};

const parseError = async (response: Response) => {
  try {
    const data = await response.json();
    const message =
      (data?.detail as string) ||
      Object.values(data || {}).flat().join(" ") ||
      response.statusText;
    return message || "Request failed";
  } catch {
    return response.statusText || "Request failed";
  }
};

export const apiGet = async (path: string) => {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
    },
  });

  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  return response.json();
};

export const apiPost = async (path: string, body: unknown) => {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  return response.json();
};

export const apiPut = async (path: string, body: unknown) => {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  return response.json();
};

export const apiDelete = async (path: string) => {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: "DELETE",
    headers: {
      ...getAuthHeaders(),
    },
  });

  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
};

export const apiDownload = async (path: string) => {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: {
      ...getAuthHeaders(),
    },
  });

  if (!response.ok) {
    throw new Error(await parseError(response));
  }

  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="([^"]+)"/i);
  const filename = match?.[1] || "download";
  return { blob, filename };
};
