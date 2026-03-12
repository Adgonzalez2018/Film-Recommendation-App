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

function LoadingScreen({ text = "Loading..." }) {
  return <div>{text}</div>;
}

function ProtectedRoute({ children }) {
  const { accessToken, isAuthenticating } = useAuth();

  if (isAuthenticating) return <LoadingScreen text="Checking auth..." />;
  if (!accessToken) return <Navigate to="/signin" replace />;
  return children;
}

function OnboardedRoute({ children }) {
  const { accessToken, isAuthenticating, isOnboarded } = useAuth();

  if (isAuthenticating) return <LoadingScreen text="Checking account..." />;
  if (!accessToken) return <Navigate to="/signin" replace />;
  if (isOnboarded == null) return <LoadingScreen text="Checking onboarding..." />;
  if (!isOnboarded) return <Navigate to="/connect" replace />;
  return children;
}

function AppEntry() {
  const { accessToken, isAuthenticating, isOnboarded } = useAuth();

  if (isAuthenticating) return <LoadingScreen text="Loading app..." />;
  if (!accessToken) return <Navigate to="/signin" replace />;
  if (isOnboarded == null) return <LoadingScreen text="Checking onboarding..." />;

  return <Navigate to={isOnboarded ? "/chat" : "/connect"} replace />;
}

export default function AppRoutes() {
  const { authError } = useAuth();

  if (authError) {
    return <div>Auth error: {authError}</div>;
  }

  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/signup" element={<Register />} />
      <Route path="/signin" element={<SignIn />} />
      <Route path="/app" element={<AppEntry />} />

      <Route
        path="/profile"
        element={
          <ProtectedRoute>
            <Profile />
          </ProtectedRoute>
        }
      />

      <Route
        path="/connect"
        element={
          <ProtectedRoute>
            <Imports />
          </ProtectedRoute>
        }
      />

      <Route
        path="/chat"
        element={
          <OnboardedRoute>
            <Chat />
          </OnboardedRoute>
        }
      />

      <Route
        path="/stats"
        element={
          <OnboardedRoute>
            <DirectoryStats />
          </OnboardedRoute>
        }
      />

      <Route
        path="/stats/weekly"
        element={
          <OnboardedRoute>
            <WeeklyStats />
          </OnboardedRoute>
        }
      />

      <Route
        path="/stats/alltime"
        element={
          <OnboardedRoute>
            <AllStats />
          </OnboardedRoute>
        }
      />
    </Routes>
  );
}