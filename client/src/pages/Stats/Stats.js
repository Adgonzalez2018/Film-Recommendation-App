import { useEffect, useRef, useState } from "react";
import "./Stats.css";
import { useAuth } from "../../hooks/useAuth";
import { fetchStats } from "../../api/stats";

const ORD = ["1st", "2nd", "3rd", "4th", "5th"];

function maxOf(arr) {
  return arr.reduce((m, v) => (v > m ? v : m), 0);
}

/* ─── Intersection-aware fade-in wrapper ──────────────── */
function Credited({ children }) {
  const ref = useRef(null);
  const [vis, setVis] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) setVis(true);
      },
      { threshold: 0.12 }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  return <div ref={ref} className={`credited${vis ? " vis" : ""}`}>{children}</div>;
}

/* ─── Generic ranked list ───── */
function CreditedList({ header, items = [] }) {
  return (
    <Credited>
      <div className="cr-header">{header}</div>
      <ul className="cr-list">
        {items.slice(0, 5).map((item, i) => (
          <li className="cr-item" key={`${header}-${i}`}>
            <span className="cr-ord">{ORD[i]}</span>
            <span className="cr-name">{item?.name}</span>
          </li>
        ))}
      </ul>
    </Credited>
  );
}

/* ─── Movies by decade ───── */
function DecadeSection({ report }) {
  const list = report?.byDecade || [];
  const max = list.length ? maxOf(list.map((d) => d.count)) : 1;

  return (
    <Credited>
      <div className="cr-header">Movies by Decade</div>
      <ul className="decade-list">
        {list.map((d, i) => (
          <li className="decade-item" key={i}>
            <span className="decade-lbl">{d.label}</span>
            <div className="decade-bar-wrap">
              <div
                className="decade-bar-fill"
                style={{ width: `${(d.count / max) * 100}%` }}
              />
            </div>
            <span className="decade-count">{d.count}</span>
          </li>
        ))}
      </ul>
    </Credited>
  );
}

/* ─── Weekly bar chart ───── */
function BarChart({ report }) {
  const days = report?.days || [];
  const thisWeek = report?.thisWeek || [];
  const lastWeek = report?.lastWeek || [];

  const maxBar = Math.max(maxOf(thisWeek || [0]), maxOf(lastWeek || [0]), 1);

  return (
    <div className="s-chart">
      <div className="s-chart-label">Day by Day</div>
      <div className="chart-bars">
        {days.map((d, i) => {
          const hT = ((thisWeek[i] || 0) / maxBar) * 90;
          const hL = ((lastWeek[i] || 0) / maxBar) * 90;
          return (
            <div className="chart-col" key={d}>
              <div className="bar-pair">
                <div className="bar bar-this" style={{ height: hT }} />
                <div className="bar bar-last" style={{ height: hL }} />
              </div>
              <div className="chart-day">{d}</div>
            </div>
          );
        })}
      </div>
      <div className="chart-legend">
        <span>
          <span className="leg-dot" style={{ background: "#e2ddd4" }} />
          This week
        </span>
        <span>
          <span className="leg-dot" style={{ background: "rgba(226,221,212,.18)" }} />
          Last week
        </span>
      </div>
    </div>
  );
}

/* ─── Main component ───── */
export default function Stats() {
  const { isAuthenticating, authError, accessToken } = useAuth();

  const [report, setReport] = useState(null);
  const [loadingStats, setLoadingStats] = useState(true);
  const [statsError, setStatsError] = useState(null);

  const portRef = useRef(null);
  const rafRef = useRef(null);
  const [playing, setPlaying] = useState(false);
  const speed = 0.55;

  // cleanup for RAF
  useEffect(() => {
    return () => cancelAnimationFrame(rafRef.current);
  }, []);

  // fetch stats once auth is good
  useEffect(() => {
    if (isAuthenticating) return;
    if (authError) return;
    if (!accessToken) return;

    let cancelled = false;

    async function load() {
      try {
        setLoadingStats(true);
        setStatsError(null);

        const data = await fetchStats(accessToken);
        if (cancelled) return;

        setReport(data);
      } catch (err) {
        console.error("Stats fetch error:", err);
        if (cancelled) return;
        setStatsError(err?.message || "Could not load stats.");
      } finally {
        if (!cancelled) setLoadingStats(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [isAuthenticating, authError, accessToken]);

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

  // ---- Renders (now safe because hooks are above) ----
  if (isAuthenticating) {
    return (
      <div className="root">
        <div className="auth-loading">
          <p>Authenticating...</p>
        </div>
      </div>
    );
  }

  if (authError) {
    return (
      <div className="root">
        <div className="auth-error-container">
          <div className="error-message">{authError}</div>
          <button className="retry-button" onClick={() => window.location.reload()}>
            RETRY
          </button>
        </div>
      </div>
    );
  }

  if (loadingStats) {
    return (
      <div className="root">
        <div className="auth-loading">
          <p>Generating your film report...</p>
        </div>
      </div>
    );
  }

  if (statsError) {
    return (
      <div className="root">
        <div className="auth-error-container">
          <div className="error-message">{statsError}</div>
        </div>
      </div>
    );
  }

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
            <div className="s-watches-unit">watches this week</div>
            <div className="s-watches-change">↑ {report.percentChange}% vs last week</div>
          </div>

          <div className="rule" />

          <BarChart report={report} />

          <div className="rule" />

          <CreditedList header="Top Director" items={report.directors} />
          <div className="rule" />

          <CreditedList header="Top Actor" items={report.actors} />
          <div className="rule" />

          <CreditedList header="Top Genre" items={report.genres} />
          <div className="rule" />

          <CreditedList header="Most Recent" items={report.recentFilms} />
          <div className="rule" />

          <DecadeSection report={report} />

          <div className="fin">— fin —</div>
        </div>
      </div>

      <div className="controls">
        <button className="ctrl-btn" onClick={toggle}>
          {playing ? "⏸ Pause" : "▶ Roll Credits"}
        </button>
      </div>
    </div>
  );
}
