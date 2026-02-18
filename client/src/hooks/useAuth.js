import { useState, useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";

export const useAuth = () => {
  const navigate = useNavigate();
  const location = useLocation();

  const PUBLIC_ROUTES = ["/signin", "/signup", "/connect"];
  const [isAuthenticating, setIsAuthenticating] = useState(true);
  const [authError, setAuthError] = useState(null);

  const accessToken = localStorage.getItem("access_token");

  useEffect(() => {
    const authenticateUser = async () => {
      setIsAuthenticating(true);
      setAuthError(null);

      if (!accessToken) {
        setIsAuthenticating(false);
        if (!PUBLIC_ROUTES.includes(location.pathname)) {
          navigate("/signin");
        }
        return;
      }

      try {
        const response = await ping(accessToken);
        if (response.status === 200) {
          const data = await response.json();
          // User is authenticated, update username if needed
          localStorage.setItem("username", data.username);
          localStorage.setItem("userId", data.id);
          setIsAuthenticating(false);
        } else if (response.status === 401 || response.status === 403) {
          // Unauthorized or Forbidden - invalid token, logout and redirect
          localStorage.removeItem("access_token");
          localStorage.removeItem("username");
          localStorage.removeItem("userId");
          setIsAuthenticating(false);
          navigate("/signin");
        } else {
          // Other error (4xx, 5xx) - server unavailable
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
  }, [accessToken, navigate]);

  return {
    isAuthenticating,
    authError,
    accessToken,
  };
};