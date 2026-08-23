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

export const login = async (loginId, password) => {
  const response = await fetch(`${BASE_URL}/auth/login/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ login_id: loginId, password }),
  });

  if (!response.ok) {
    const errorData = await response.json();
    const errorMessage = Object.values(errorData).flat().join(' ');
    throw new Error(errorMessage || "Login failed");
  }

  return response.json();
};

export const signup = async (userData) => {
  const response = await fetch(`${BASE_URL}/accounts/register/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(userData),
  });

  if (!response.ok) {
    const errorData = await response.json();
    const errorMessage = Object.values(errorData).flat().join(' ');
    throw new Error(errorMessage || "Signup failed");
  }

  return response.json();
};

