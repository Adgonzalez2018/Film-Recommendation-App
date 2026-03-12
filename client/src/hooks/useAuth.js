// src/hooks/useAuth.js
import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { apiFetch } from "../api/client";

function clearAuth() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh");
  localStorage.removeItem("username");
  localStorage.removeItem("userId");
}

export function useAuth() {
  const location = useLocation();

  const [accessToken, setAccessTokenState] = useState(
    localStorage.getItem("access_token")
  );
  const [isAuthenticating, setIsAuthenticating] = useState(true);
  const [authError, setAuthError] = useState(null);
  const [isOnboarded, setIsOnboarded] = useState(null);

  // sync token from localStorage on route change
  useEffect(() => {
    const latestToken = localStorage.getItem("access_token");
    if (latestToken !== accessToken) {
      setAccessTokenState(latestToken);
    }
  }, [location.pathname, accessToken]);

  useEffect(() => {
    let cancelled = false;

    const run = async () => {
      setIsAuthenticating(true);
      setAuthError(null);

      if (!accessToken) {
        if (!cancelled) {
          setIsOnboarded(null);
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
            setAccessTokenState(null);
            setIsOnboarded(null);
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

  const setToken = (token) => {
    if (token) {
      localStorage.setItem("access_token", token);
      setAccessTokenState(token);
    } else {
      clearAuth();
      setAccessTokenState(null);
      setIsOnboarded(null);
    }
  };

  return {
    accessToken,
    setAccessToken: setToken,
    isAuthenticating,
    authError,
    isOnboarded,
  };
}