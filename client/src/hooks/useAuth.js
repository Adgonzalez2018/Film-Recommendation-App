// src/hooks/useAuth.js
import { useEffect, useState } from "react";
import { apiFetch } from "../api/client";

function clearAuth() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
  localStorage.removeItem("username");
  localStorage.removeItem("userId");
}

export function useAuth() {
  const [accessToken, setAccessToken] = useState(
    localStorage.getItem("access_token")
  );

  const [isAuthenticating, setIsAuthenticating] = useState(true);
  const [authError, setAuthError] = useState(null);
  const [isOnboarded, setIsOnboarded] = useState(null); // null unknown, true/false known

  useEffect(() => {
    let cancelled = false;

    const run = async () => {
      setIsAuthenticating(true);
      setAuthError(null);

      if (!accessToken) {
        if (!cancelled) {
          setIsOnboarded(false);
          setIsAuthenticating(false);
        }
        return;
      }

      try {
        const res = await apiFetch("/api/onboarding-status/", {
          token: accessToken,
          method: "GET",
        });

        const data = await res.json().catch(() => ({}));

        if (res.status === 401 || res.status === 403) {
          clearAuth();
          if (!cancelled) {
            setIsOnboarded(false);
            setIsAuthenticating(false);
          }
          return;
        }

        if (!res.ok) {
          throw new Error(data?.detail || data?.error || "Auth check failed.");
        }

        if (!cancelled) {
          setIsOnboarded(Boolean(data?.is_onboarded));
          setIsAuthenticating(false);
        }
      } catch (e) {
        if (!cancelled) {
          setAuthError(e?.message || "Server unavailable.");
          setIsAuthenticating(false);
        }
      }
    };

    run();
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  // If other code sets localStorage directly, you can optionally add a helper:
  const setToken = (token) => {
    if (token) localStorage.setItem("access_token", token);
    else clearAuth();
    setAccessToken(token);
  };

  return {
    accessToken,
    setAccessToken: setToken,
    isAuthenticating,
    authError,
    isOnboarded,
  };
}