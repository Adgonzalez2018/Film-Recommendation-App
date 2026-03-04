import { useState, useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ping } from "../api/auth";

const DEV_BYPASS_AUTH = 
  import.meta?.env?.VITE_BYPASS_AUTH === "true" ||
  process.env?.REACT_APP_BYPASS_AUTH === "true";

export const useAuth = () => {
  const navigate = useNavigate();
  const location = useLocation();

  const PUBLIC_ROUTES = ["/signin", "/signup", "/connect"];
  const [isAuthenticating, setIsAuthenticating] = useState(true);
  const [authError, setAuthError] = useState(null);

  const accessToken = localStorage.getItem("access_token");

  useEffect(() => {
    let cancelled = false;

    const authenticateUser = async () => {
      setIsAuthenticating(true);
      setAuthError(null);

      if (DEV_BYPASS_AUTH) {
        if (!canceleld) setIsAuthenticating(false);
        return;
        }
      if (!accessToken) {
        if (!cancelled) setIsAuthenticating(false);
        if (!PUBLIC_ROUTES.includes(location.pathname)) {
          navigate("/signin"), {replace: true};
        }
        return;
      }

      try {
        const response = await ping(accessToken);

        if (response.status === 200) {
          const data = await response.json().catch(() => ({}));
          // User is authenticated, update username if needed

          if (data?.username) localStorage.setItem("username", data.username);
          if (data?.id) localStorage.setItem("userId", String(data.id));

          if (!cancelled) setIsAuthenticating(false);
          return;
        }  
        if (response.status === 401 || response.status === 403) {
          // Unauthorized or Forbidden - invalid token, logout and redirect
          localStorage.removeItem("access_token");
          localStorage.removeItem("refresh_token");
          localStorage.removeItem("username");
          localStorage.removeItem("userId");
          if (!cancelled) setIsAuthenticating(false);
          navigate("/signin", {replace:true});
          return;
        } 
        if (!cancelled) {
          setAuthError("Server unavailable. Please try again later.");
          setIsAuthenticating(false);
        }
      } catch (err) {
        console.error("Authentication failed:", err);
        // Network error - server unavailable
        setAuthError("Server unavailable. Please try again later.");
        setIsAuthenticating(false);
      }
    };

    authenticateUser();
    return () => {
      cancelled = true;
    };
  }, [accessToken, location.pathname, navigate]);

  return {
    isAuthenticating,
    authError,
    accessToken,
  };
};