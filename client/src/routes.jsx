import { Routes, Route } from "react-router-dom";
import LandingPage from "./pages/Landing/LandingPage";

import Register from "./pages/Auth/Register";
import SignIn from "./pages/Auth/SignIn";
import Imports from "./pages/Connect/Imports";

import Profile from "./pages/Profile/Profile";

import Chat from "./pages/Chat/Chat";

import WeeklyStats from "./pages/Stats/WeeklyStats"
import DirectoryStats from "./pages/Stats/DirectoryStats"
import AllStats from "./pages/Stats/AllStats"



export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      
      <Route path="/signup" element={<Register />} />
      <Route path="/signin" element={<SignIn />} />
      <Route path="/profile" element={<Profile/>}/>

      <Route path="/import" element={<Imports />} />


      <Route path="/chat" element={<Chat />} />

      <Route path="/stats" element={<DirectoryStats />} />
      <Route path="/stats/weekly" element={<WeeklyStats />} />
      <Route path="/stats/alltime" element={<AllStats />} />

      
    </Routes>
  );
}
