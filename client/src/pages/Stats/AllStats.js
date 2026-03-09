import { useEffect, useMemo, useRef, useState } from "react";
import "./Stats.css";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import { fetchAllTimeStats } from "../../api/stats";
import { CreditedList, DecadeSection, StatsLoading, StatsError } from "./components/Statshelpers";

export default function AllStats() {
  const navigate = useNavigate();
  const { isAuthenticating, authError, accessToken } = useAuth();

  const [report, setReport] = useState(null);
  const [loadingStats, setLoadingStats] = useState(true);
  const [statsError, setStatsError] = useState(null);

  const portRef = useRef(null);
  const rafRef = useRef(null);
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
        const data = await fetchAllTimeStats(accessToken);
        if (!cancelled) setReport(data);
      } catch (err) {
        if (!cancelled) {
          setStatsError(err?.message || "Could not load all-time stats.");
        }
      } finally {
        if (!cancelled) setLoadingStats(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [isAuthenticating, authError, accessToken]);

  const recentFilmItems = useMemo(() => {
    if (!report?.recentFilms?.length) return [];

    return report.recentFilms.map((film) => ({
      name: film?.year ? `${film.title} (${film.year})` : film?.title || "Unknown film",
    }));
  }, [report]);

  const totalDays = report?.totalTimeWatched?.days ?? 0;
  const remainingHours = report?.totalTimeWatched?.hours ?? 0;
  const totalHours = report?.totalHoursWatched ?? 0;

  const tick = () => {
    if (portRef.current) portRef.current.scrollTop += speed;
    rafRef.current = requestAnimationFrame(tick);
  };

  const toggle = () => {
    if (playing) {
      cancelAnimationFrame(rafRef.current);
      setPlaying(false);
    } else {
      rafRef.current = requestAnimationFrame(tick);
      setPlaying(true);
    }
  };

  if (isAuthenticating) return <StatsLoading message="Authenticating…" />;
  if (authError) return <StatsError message={authError} onRetry={() => window.location.reload()} />;
  if (loadingStats) return <StatsLoading message="Generating your all-time report…" />;
  if (statsError) return <StatsError message={statsError} onRetry={() => window.location.reload()} />;
  if (!report) return null;

  return (
    <div className="root">
      <div className="fade-top" />
      <div className="fade-bottom" />

      <div className="scrollport" ref={portRef}>
        <div className="stage">
          <div className="s-watches">
            <div className="s-watches-label">Films Watched</div>
            <div className="s-watches-num">{report.totalWatches}</div>
            <div className="s-watches-unit">films all time</div>

            <div className="s-runtime">
              <div className="s-runtime-label">Time Watched</div>
              <div className="s-runtime-main">
                {totalDays}d {remainingHours}h
              </div>
              <div className="s-runtime-sub">{totalHours} total hours</div>
            </div>
          </div>

          <div className="rule" />

          <CreditedList header="Top Director" items={report.directors || []} />
          <div className="rule" />

          <CreditedList header="Top Actor" items={report.actors || []} />
          <div className="rule" />

          <CreditedList header="Top Genre" items={report.genres || []} />
          <div className="rule" />

          <CreditedList header="Most Recent" items={recentFilmItems} />
          <div className="rule" />

          <DecadeSection report={report} />

          <div className="fin">— Thank you —</div>
        </div>
      </div>

      <div className="controls">
        <button className="ctrl-btn" onClick={() => navigate("/stats")}>
          ← Back
        </button>
        <button className="ctrl-btn" onClick={() => navigate("/chat")}>
          Chat
        </button>
        <button className="ctrl-btn" onClick={() => navigate("/profile")}>
          Profile
        </button>
        <button className="ctrl-btn" onClick={toggle}>
          {playing ? "⏸ Pause" : "▶ Roll Credits"}
        </button>
      </div>
    </div>
  );
}