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

function ProtectedRoute({ accessToken, isAuthenticating, children }) {
  if (isAuthenticating) return <LoadingScreen text="Checking auth..." />;
  if (!accessToken) return <Navigate to="/signin" replace />;
  return children;
}

function OnboardedRoute({
  accessToken,
  isAuthenticating,
  isOnboarded,
  children,
}) {
  if (isAuthenticating) return <LoadingScreen text="Checking account..." />;
  if (!accessToken) return <Navigate to="/signin" replace />;
  if (isOnboarded == null) return <LoadingScreen text="Checking onboarding..." />;
  if (!isOnboarded) return <Navigate to="/connect" replace />;
  return children;
}

function AppEntry({ accessToken, isAuthenticating, isOnboarded }) {
  if (isAuthenticating) return <LoadingScreen text="Loading app..." />;
  if (!accessToken) return <Navigate to="/signin" replace />;
  if (isOnboarded == null) return <LoadingScreen text="Checking onboarding..." />;
  return <Navigate to={isOnboarded ? "/chat" : "/connect"} replace />;
}

export default function AppRoutes() {
  const { accessToken, isAuthenticating, isOnboarded, authError } = useAuth();

  if (authError) {
    return <div>Auth error: {authError}</div>;
  }

  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/signup" element={<Register />} />
      <Route path="/signin" element={<SignIn />} />
      <Route
        path="/app"
        element={
          <AppEntry
            accessToken={accessToken}
            isAuthenticating={isAuthenticating}
            isOnboarded={isOnboarded}
          />
        }
      />
      <Route
        path="/profile"
        element={
          <ProtectedRoute
            accessToken={accessToken}
            isAuthenticating={isAuthenticating}
          >
            <Profile />
          </ProtectedRoute>
        }
      />
      <Route
        path="/connect"
        element={
          <ProtectedRoute
            accessToken={accessToken}
            isAuthenticating={isAuthenticating}
          >
            <Imports />
          </ProtectedRoute>
        }
      />
      <Route
        path="/chat"
        element={
          <OnboardedRoute
            accessToken={accessToken}
            isAuthenticating={isAuthenticating}
            isOnboarded={isOnboarded}
          >
            <Chat />
          </OnboardedRoute>
        }
      />
      <Route
        path="/stats"
        element={
          <OnboardedRoute
            accessToken={accessToken}
            isAuthenticating={isAuthenticating}
            isOnboarded={isOnboarded}
          >
            <DirectoryStats />
          </OnboardedRoute>
        }
      />
      <Route
        path="/stats/weekly"
        element={
          <OnboardedRoute
            accessToken={accessToken}
            isAuthenticating={isAuthenticating}
            isOnboarded={isOnboarded}
          >
            <WeeklyStats />
          </OnboardedRoute>
        }
      />
      <Route
        path="/stats/alltime"
        element={
          <OnboardedRoute
            accessToken={accessToken}
            isAuthenticating={isAuthenticating}
            isOnboarded={isOnboarded}
          >
            <AllStats />
          </OnboardedRoute>
        }
      />
    </Routes>
  );
}