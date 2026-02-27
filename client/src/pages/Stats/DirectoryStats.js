// directoryStats.js — landing page: choose Weekly or All Time
import { useEffect, useState } from "react";
import "./Stats.css";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import { StatsLoading } from "./components/Statshelpers";

export default function DirectoryStats() {
  const navigate = useNavigate();
  const { isAuthenticating, authError } = useAuth();

  // Stagger the three elements fading in
  const [showTitle,   setShowTitle]   = useState(false);
  const [showWeekly,  setShowWeekly]  = useState(false);
  const [showAllTime, setShowAllTime] = useState(false);

  useEffect(() => {
    const t1 = setTimeout(() => setShowTitle(true),   300);
    const t2 = setTimeout(() => setShowWeekly(true),  900);
    const t3 = setTimeout(() => setShowAllTime(true), 1400);
    return () => { clearTimeout(t1); clearTimeout(t2); clearTimeout(t3); };
  }, []);

  if (isAuthenticating) return <StatsLoading message="Authenticating…" />;

  if (authError) {
    return (
      <div className="root" style={{ display:"flex", flexDirection:"column",
        alignItems:"center", justifyContent:"center", gap:"1.5rem" }}>
        <p style={{ fontFamily:"'EB Garamond',serif", fontStyle:"italic",
          color:"rgba(226,221,212,0.5)", fontSize:"1rem" }}>{authError}</p>
        <button className="ctrl-btn" onClick={() => navigate("/signin")}>Sign In</button>
      </div>
    );
  }

  return (
    <div className="root">
      {/* grain + vignette come from .root::after in Stats.css */}

      <div className="dir-stage">

        {/* ── FIN title ── */}
        <div className={`dir-title${showTitle ? " dir-vis" : ""}`}>
          — Fin —
        </div>

        {/* ── Two choice boxes ── */}
        <div className="dir-choices">

          <button
            className={`dir-box${showWeekly ? " dir-vis" : ""}`}
            onClick={() => navigate("/stats/weekly")}
          >
            <span className="dir-box-label">This Week's <br></br>Report</span>
          </button>

          <button
            className={`dir-box${showAllTime ? " dir-vis" : ""}`}
            onClick={() => navigate("/stats/alltime")}
          >
            <span className="dir-box-label">Lifetime <br></br> Report</span>
          </button>

        </div>
      </div>

      {/* bottom-right nav */}
      <div className="controls">
        <button className="ctrl-btn" onClick={() => navigate("/chat")}>Chat</button>
        <button className="ctrl-btn" onClick={() => navigate("/profile")}>Profile</button>
      </div>
    </div>
  );
}