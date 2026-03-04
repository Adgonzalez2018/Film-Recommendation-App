import { Routes, Route, Navigate } from "react-router-dom";
import { useAuth } from "./hooks/useAuth";

import LandingPage from "./pages/Landing/LandingPage";

import Register from "./pages/Auth/Register";
import SignIn from "./pages/Auth/SignIn";
import Imports from "./pages/Connect/Imports";

import Profile from "./pages/Profile/Profile";

import Chat from "./pages/Chat/Chat";

import WeeklyStats from "./pages/Stats/WeeklyStats"
import DirectoryStats from "./pages/Stats/DirectoryStats"
import AllStats from "./pages/Stats/AllStats"

function RequireAuth({ children }){
  const { accessToken, isAuthenticating } = useAuth();
  if (isAuthenticating) return null;
  if (!accessToken) return <Navigate to="/signin" replace />;
  return children;
}

function RequireOnboarding({ children }){
  const { isOnboarded, isAuthenticating } = useAuth();
  if (isAuthenticating) return null;
  // if auth is true but onboarding unknown, keep waiting
  if (isOnboarded == null) return null;
  if (!isOnboarded) return <Navigte to="/import" replace/>;
  return children;
}


export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      
      <Route path="/signup" element={<Register />} />
      <Route path="/signin" element={<SignIn />} />
      <Route path="/profile" element={<Profile/>}/>

      <Route path="/import" 
      element={
        <RequireAuth>
          <Imports />          
        </RequireAuth>
    } 
      />


      <Route path="/chat" element={
        <RequireOnboarding>
          <Chat /> 
        </RequireOnboarding>
      } 
        />

      <Route path="/stats" element={
        <RequireOnboarding>
          <DirectoryStats />
        </RequireOnboarding>
        } 
        />
      <Route path="/stats/weekly" element={<WeeklyStats />} />
      <Route path="/stats/alltime" element={<AllStats />} />

      
    </Routes>
  );
}
