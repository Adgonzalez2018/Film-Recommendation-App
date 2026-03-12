import { Routes, Route, Navigate } from "react-router-dom";
import { useAuth } from "./hooks/useAuth";

import LandingPage from "./pages/Landing/LandingPage";

import Register from "./pages/Auth/Register";
import SignIn from "./pages/Auth/SignIn";
import Imports from "./pages/Connect/Imports";

import Profile from "./pages/Profile/Profile";

import Chat from "./pages/Chat/Chat";

import WeeklyStats from "./pages/Stats/WeeklyStats";
import DirectoryStats from "./pages/Stats/DirectoryStats";
import AllStats from "./pages/Stats/AllStats";

function RequireAuth({ children }) {
  const { accessToken, isAuthenticating } = useAuth();

  if (isAuthenticating) return null;
  if (!accessToken) return <Navigate to="/signin" replace />;
  return children;
}

function AppGate() {
  const { accessToken, isOnboarded, isAuthenticating } = useAuth();

  if (isAuthenticating) return null;
  if (!accessToken) return <Navigate to="/signin" replace />;
  if (isOnboarded == null) return null;

  return <Navigate to={isOnboarded ? "/chat" : "/connect"} replace />;
}

function RequireOnboarding({ children }) {
  const { accessToken, isOnboarded, isAuthenticating } = useAuth();

  if (isAuthenticating) return null;
  if (!accessToken) return <Navigate to="/signin" replace />;
  if (isOnboarded == null) return null;
  if (!isOnboarded) return <Navigate to="/connect" replace />;

  return children;
}

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />

      <Route path="/signup" element={<Register />} />
      <Route path="/signin" element={<SignIn />} />

      <Route path="/app" element={<AppGate />} />

      <Route
        path="/profile"
        element={
          <RequireAuth>
            <Profile />
          </RequireAuth>
        }
      />

      <Route
        path="/connect"
        element={
          <RequireAuth>
            <Imports />
          </RequireAuth>
        }
      />

      <Route
        path="/chat"
        element={
          <RequireOnboarding>
            <Chat />
          </RequireOnboarding>
        }
      />

      <Route
        path="/stats"
        element={
          <RequireOnboarding>
            <DirectoryStats />
          </RequireOnboarding>
        }
      />

      <Route
        path="/stats/weekly"
        element={
          <RequireOnboarding>
            <WeeklyStats />
          </RequireOnboarding>
        }
      />

      <Route
        path="/stats/alltime"
        element={
          <RequireOnboarding>
            <AllStats />
          </RequireOnboarding>
        }
      />
    </Routes>
  );
}