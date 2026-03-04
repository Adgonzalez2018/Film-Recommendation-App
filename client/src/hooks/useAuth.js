import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ping } from "../api/auth";
import { apiFetch } from "../api/client";

const DEV_BYPASS_AUTH =
  import.meta?.env?.VITE_BYPASS_AUTH === "true" ||
  process.env?.REACT_APP_BYPASS_AUTH === "true";

const PUBLIC_ROUTES = ["/signin", "/signup", "/reset-password"];

const ONBOARDING_ROUTE = "/connect";
const APP_HOME_ROUTE = "/chat";

export const useAuth = () => {
  const navigate = useNavigate();
  const location = useLocation();

  const [isAuthenticating, setIsAuthenticating] = useState(true);
  const [authError, setAuthError] = useState(null);

  const [isOnboarded, setIsOnboarded] = useState(null); // null = unknown, true/false known
  const accessToken = localStorage.getItem("access_token");

  useEffect(() => {
    let cancelled = false;

    const hardRedirect = (to) => {
      if (location.pathname !== to) {
        navigate(to, { replace: true });
      }
    };

    const clearTokens = () => {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      localStorage.removeItem("username");
      localStorage.removeItem("userId");
    };

    const run = async () => {
      setIsAuthenticating(true);
      setAuthError(null);

      if (DEV_BYPASS_AUTH) {
        if (!cancelled) {
          setIsOnboarded(true);
          setIsAuthenticating(false);
        }
        return;
      }

      // 1) No token -> allow public routes, otherwise force signin
      if (!accessToken) {
        if (!cancelled) {
          setIsOnboarded(false);
          setIsAuthenticating(false);
        }

        if (!PUBLIC_ROUTES.includes(location.pathname)) {
          hardRedirect("/signin");
        }
        return;
      }

      // 2) Token exists -> verify token
      try {
        const pingRes = await ping(accessToken);

        if (pingRes.status === 200) {
          const data = await pingRes.json().catch(() => ({}));
          if (data?.username) localStorage.setItem("username", data.username);
          if (data?.id) localStorage.setItem("userId", String(data.id));
        } else if (pingRes.status === 401 || pingRes.status === 403) {
          clearTokens();
          if (!cancelled) {
            setIsOnboarded(false);
            setIsAuthenticating(false);
          }
          hardRedirect("/signin");
          return;
        } else {
          if (!cancelled) {
            setAuthError("Server unavailable. Please try again later.");
            setIsAuthenticating(false);
          }
          return;
        }
      } catch (err) {
        console.error("ping failed:", err);
        if (!cancelled) {
          setAuthError("Server unavailable. Please try again later.");
          setIsAuthenticating(false);
        }
        return;
      }

      // 3) Token valid -> check onboarding
      try {
        const onboardRes = await apiFetch("/api/onboarding-status/", {
          token: accessToken,
          method: "GET",
        });

        if (!onboardRes.ok) {
          // If onboarding endpoint fails, keep user in app but don’t loop them
          if (!cancelled) {
            setIsOnboarded(null);
            setIsAuthenticating(false);
          }
          return;
        }

        const onboard = await onboardRes.json().catch(() => ({}));
        const onboarded = Boolean(onboard?.is_onboarded);

        if (!cancelled) {
          setIsOnboarded(onboarded);
          setIsAuthenticating(false);
        }

        // 4) Centralized routing rules
        const path = location.pathname;

        // If not onboarded, keep them on connect (unless they're on signin/signup/reset)
        if (!onboarded) {
          if (!PUBLIC_ROUTES.includes(path) && path !== ONBOARDING_ROUTE) {
            hardRedirect(ONBOARDING_ROUTE);
          }
          return;
        }

        // If onboarded, keep them out of connect/signin/signup
        if (onboarded) {
          if (path === ONBOARDING_ROUTE || PUBLIC_ROUTES.includes(path)) {
            hardRedirect(APP_HOME_ROUTE);
          }
        }
      } catch (err) {
        console.error("onboarding-status failed:", err);
        if (!cancelled) {
          setIsOnboarded(null);
          setIsAuthenticating(false);
        }
      }
    };

    run();

    return () => {
      cancelled = true;
    };
  }, [accessToken, location.pathname, navigate]);

  return {
    isAuthenticating,
    authError,
    accessToken,
    isOnboarded, // useful for UI conditionals if you want
  };
};