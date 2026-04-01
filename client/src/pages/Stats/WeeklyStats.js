// weeklyStats.js — weekly report (day-by-day chart + ranked lists)
import { useEffect, useRef, useState } from "react";
import "./Stats.css";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import { fetchWeeklyStats } from "../../api/stats";
import { CreditedList, DecadeSection, BarChart, StatsLoading, StatsError } from "./components/Statshelpers";

export default function WeeklyStats() {
  const navigate = useNavigate();
  const { isAuthenticating, authError, accessToken } = useAuth();

  const [report,       setReport]       = useState(null);
  const [loadingStats, setLoadingStats] = useState(true);
  const [statsError,   setStatsError]   = useState(null);

  const portRef = useRef(null);
  const rafRef  = useRef(null);
  const [playing, setPlaying] = useState(false);
  const speed = 0.55;

  useEffect(() => () => cancelAnimationFrame(rafRef.current), []);

  useEffect(() => {
    if (isAuthenticating || authError || !accessToken) return;
    let cancelled = false;

    async function load() {
      try {
        setLoadingStats(true);
        setStatsError(null);
        const data = await fetchWeeklyStats(accessToken);
        if (!cancelled) setReport(data);
      } catch (err) {
        if (!cancelled) setStatsError(err?.message || "Could not load weekly stats.");
      } finally {
        if (!cancelled) setLoadingStats(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, [isAuthenticating, authError, accessToken]);

  const tick = () => {
    const el = portRef.current;
    if (!el) return;

    const maxScroll = el.scrollHeight - el.clientHeight;
    const next = Math.min(el.scrollTop + speed, maxScroll);
    el.scrollTop = next;

    if (next >= maxScroll - 1){
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
      setPlaying(false);
      return;
    }
    rafRef.current = requestAnimationFrame(tick);
  };

  const toggle = () => {
    if (playing) { cancelAnimationFrame(rafRef.current); setPlaying(false); }
    else         { rafRef.current = requestAnimationFrame(tick); setPlaying(true); }
  };

  if (isAuthenticating)            return <StatsLoading message="Authenticating…" />;
  if (authError)                   return <StatsError message={authError} onRetry={() => window.location.reload()} />;
  if (loadingStats)                return <StatsLoading message="Generating your weekly report…" />;
  if (statsError)                  return <StatsError message={statsError} onRetry={() => window.location.reload()} />;
  if (!report)                     return null;

  return (
    <div className="root">
      <div className="fade-top" />
      <div className="fade-bottom" />

      <div className="scrollport" ref={portRef}>
        <div className="stage">

          <div className="s-watches">
            <div className="s-watches-label">Films Watched</div>
            <div className="s-watches-num">{report.totalWatches}</div>
            <div className="s-watches-unit">watches this week</div>
            <div className="s-watches-change">
              {report.percentChange == null ? "- new week" : `↑ ${Math.round(report.percentChange)}% vs last week`}
              </div>
          </div>

          <div className="rule" />
          <BarChart report={report} />
          <div className="rule" />

          <CreditedList header="Top Director"  items={report.directors}   />
          <div className="rule" />
          <CreditedList header="Top Actor"     items={report.actors}      />
          <div className="rule" />
          <CreditedList header="Top Genre"     items={report.genres}      />
          <div className="rule" />
          <CreditedList header="Most Recent"   items={report.recentFilms} />
          <div className="rule" />
          <DecadeSection report={report} />

          <div className="fin">— fin —</div>
        </div>
      </div>

      <div className="controls">
        <button className="ctrl-btn" onClick={() => navigate("/stats")}>Back</button>
        <button className="ctrl-btn" onClick={() => navigate("/chat")}>Chat</button>
        <button className="play-corner-btn" onClick={toggle}>{playing ? "⏸ Pause" : "▶ Roll Credits"}</button>
        <button className="profile-corner-btn" onClick={() => navigate("/profile")}>Profile</button>
      </div>
    </div>
  );
}