import { Routes, Route } from "react-router-dom";
import LandingPage from "./pages/Landing/LandingPage";

import SignUp from "./pages/Auth/SignUp";
import SignIn from "./pages/Auth/SignIn";

import Chat from "./pages/Chat/Chat";
import Stats from "./pages/Stats/Stats";

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/signup" element={<SignUp />} />
      <Route path="/signin" element={<SignIn />} />
      <Route path="/chat" element={<Chat />} />
      <Route path="/stats" element={<Stats />} />
    </Routes>
  );
}
