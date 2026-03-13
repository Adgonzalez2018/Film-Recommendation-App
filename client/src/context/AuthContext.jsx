import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { apiFetch } from "../api/client";

const AuthContext = createContext(null);

function clearAuthStorage() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh");
  localStorage.removeItem("username");
  localStorage.removeItem("userId");
}

export function AuthProvider({ children }) {
  const [accessToken, setAccessTokenState] = useState(
    localStorage.getItem("access_token")
  );
  const [isAuthenticating, setIsAuthenticating] = useState(true);
  const [authError, setAuthError] = useState(null);
  const [isOnboarded, setIsOnboarded] = useState(null);
  const [onboardingStatus, setOnboardingStatus] = useState(null);

  const refreshOnboarding = useCallback(async (tokenOverride = null) => {
    const token = tokenOverride ?? accessToken;

    setAuthError(null);
    
    if (!token) {
        setOnboardedAndStatus(null, null);
        setIsAuthenticating(false);
        return null;
    }

    try {
        const res = await apiFetch("/api/onboarding-status/", {
            token,
            method: "GET",
        });

        const data = await res.json().catch(() => ({}));

        if (res.status === 401 || res.status === 403){
            clearAuthStorage();
            setAccessTokenState(null);
            setOnboardedAndStatus(null, null);
            setIsAuthenticating(false);
            return null;
        }

        if (!res.ok){
            throw new Error(data?.detail || data?.error || "Auth check failed.");
        }

        setOnboardedAndStatus(Boolean(data?.is_onboarded), data);
        setIsAuthenticating(false);
        return data;
    } catch (e) {
        setAuthError(e?.message || "Server unavailable.");
        setIsAuthenticating(false);
        return null;
    }
  }, [accessToken]);

  function setOnboardedAndStatus(onboarded, statusData){
    setIsOnboarded(onboarded);
    setOnboardingStatus(statusData);
  }

    useEffect(() => {
    let cancelled = false;

    const run = async () => {
        setIsAuthenticating(true);

        if (!accessToken) {
            if (!cancelled) {
                setOnboardedAndStatus(null, null);
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

            if (res.status === 401 || res.status === 403){
                clearAuthStorage();
                if (!cancelled) {
                    setAccessTokenState(null);
                    setOnboardedAndStatus(null, null);
                    setIsAuthenticating(false);
                }
                return;
            }
            
            if (!res.ok) {
                throw new Error(data?.detail || data?.error || "Auth check failed.");
            }

            if (!cancelled) {
                setOnboardedAndStatus(Boolean(data?.is_onboarded), data);
                setIsAuthenticating(false);
            }
        } catch(e) {
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

  const setAccessToken = (token) => {
    if (token) {
      localStorage.setItem("access_token", token);
      setAccessTokenState(token);
    } else {
      clearAuthStorage();
      setAccessTokenState(null);
      setOnboardedAndStatus(null, null);
      setIsOnboarded(null);
    }
  };

  const setRefreshToken = (token) => {
    if (token) localStorage.setItem("refresh", token);
    else localStorage.removeItem("refresh");
  };

  const logout = () => {
    clearAuthStorage();
    setAccessTokenState(null);
    setOnboardedAndStatus(null, null);
    setAuthError(null);
  };

  return (
    <AuthContext.Provider
      value={{
        accessToken,
        setAccessToken,
        setRefreshToken,
        logout,
        isAuthenticating,
        authError,
        isOnboarded,
        onboardingStatus,
        refreshOnboarding,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used inside an AuthProvider");
  }
  return ctx;
}