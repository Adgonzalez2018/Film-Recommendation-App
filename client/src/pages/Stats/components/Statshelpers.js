// statsHelpers.js — shared subcomponents for WeeklyStats & AllStats
import { useEffect, useRef, useState } from "react";

export const ORD = ["1st", "2nd", "3rd", "4th", "5th"];

export function maxOf(arr) {
  return arr.reduce((m, v) => (v > m ? v : m), 0);
}

/* ── Intersection-aware fade-in wrapper ─────────────────── */
export function Credited({ children }) {
  const ref = useRef(null);
  const [vis, setVis] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([e]) => { if (e.isIntersecting) setVis(true); },
      { threshold: 0.12 }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  return (
    <div ref={ref} className={`credited${vis ? " vis" : ""}`}>
      {children}
    </div>
  );
}

/* ── Generic ranked list ────────────────────────────────── */
export function CreditedList({ header, items = [] }) {
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

/* ── Movies by decade ───────────────────────────────────── */
export function DecadeSection({ report }) {
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

/* ── Weekly bar chart ───────────────────────────────────── */
export function BarChart({ report }) {
  const days     = report?.days     || [];
  const thisWeek = report?.thisWeek || [];
  const lastWeek = report?.lastWeek || [];
  const maxBar   = Math.max(maxOf(thisWeek.length ? thisWeek : [0]), maxOf(lastWeek.length ? lastWeek : [0]), 1);

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

/* ── Auth / loading guards (reusable) ───────────────────── */
export function StatsLoading({ message = "Generating your report…" }) {
  return (
    <div className="root" style={{ display:"flex", alignItems:"center", justifyContent:"center" }}>
      <p style={{ fontFamily:"'Cinzel',serif", fontSize:"0.65rem", letterSpacing:"0.3em",
                  color:"rgba(226,221,212,0.4)", textTransform:"uppercase" }}>
        {message}
      </p>
    </div>
  );
}

export function StatsError({ message, onRetry }) {
  return (
    <div className="root" style={{ display:"flex", flexDirection:"column", alignItems:"center",
                                   justifyContent:"center", gap:"1.5rem" }}>
      <p style={{ fontFamily:"'EB Garamond',serif", fontStyle:"italic",
                  color:"rgba(226,221,212,0.5)", fontSize:"1rem" }}>
        {message}
      </p>
      {onRetry && (
        <button className="ctrl-btn" onClick={onRetry}>Retry</button>
      )}
    </div>
  );
}