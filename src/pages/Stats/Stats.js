import { useEffect, useRef, useState } from "react";
import "./Stats.css";

const report = {
  totalWatches: 383,
  percentChange: 28,
  days: ["Fri", "Sat", "Sun", "Mon", "Tue", "Wed", "Thu"],
  thisWeek: [18, 27, 32, 55, 82, 41, 48],
  lastWeek: [24, 22, 74, 60, 19, 22, 21],
  directors: [
    { name: "David Fincher" },
    { name: "Michael Mann" },
    { name: "Wong Kar-wai" },
    { name: "Denis Villeneuve" },
    { name: "Christopher Nolan" },
  ],
  actors: [
    { name: "Al Pacino" },
    { name: "Robert De Niro" },
    { name: "Scarlett Johansson" },
    { name: "Ryan Gosling" },
    { name: "J.K. Simmons" },
  ],
  genres: [
    { name: "Crime" },
    { name: "Drama" },
    { name: "Thriller" },
    { name: "Sci-Fi" },
    { name: "Action" },
  ],
  recentFilms: [
    { name: "Heat" },
    { name: "The Social Network" },
    { name: "Chungking Express" },
    { name: "Blade Runner 2049" },
    { name: "Whiplash" },
  ],
  byDecade: [
    { label: "Pre-60s", count: 4 },
    { label: "60s", count: 7 },
    { label: "70s", count: 11 },
    { label: "80s", count: 18 },
    { label: "90s", count: 34 },
    { label: "00s", count: 29 },
    { label: "10s", count: 41 },
    { label: "20s", count: 22 },
  ],
};

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

  return (
    <div ref={ref} className={`credited${vis ? " vis" : ""}`}>
      {children}
    </div>
  );
}

/* ─── Generic ranked list (directors, actors, etc.) ───── */
function CreditedList({ header, items }) {
  return (
    <Credited>
      <div className="cr-header">{header}</div>
      <ul className="cr-list">
        {items.slice(0, 5).map((item, i) => (
          <li className="cr-item" key={i}>
            <span className="cr-ord">{ORD[i]}</span>
            <span className="cr-name">{item.name}</span>
          </li>
        ))}
      </ul>
    </Credited>
  );
}

/* ─── Movies by decade ────────────────────────────────── */
function DecadeSection() {
  const max = maxOf(report.byDecade.map((d) => d.count));
  return (
    <Credited>
      <div className="cr-header">Movies by Decade</div>
      <ul className="decade-list">
        {report.byDecade.map((d, i) => (
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

/* ─── Weekly bar chart ────────────────────────────────── */
function BarChart() {
  const maxBar = Math.max(maxOf(report.thisWeek), maxOf(report.lastWeek));
  return (
    <div className="s-chart">
      <div className="s-chart-label">Day by Day</div>
      <div className="chart-bars">
        {report.days.map((d, i) => {
          const hT = (report.thisWeek[i] / maxBar) * 90;
          const hL = (report.lastWeek[i] / maxBar) * 90;
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
          <span
            className="leg-dot"
            style={{ background: "rgba(226,221,212,.18)" }}
          />
          Last week
        </span>
      </div>
    </div>
  );
}

/* ─── Main component ──────────────────────────────────── */
export default function Stats() {
  const portRef = useRef(null);
  const rafRef = useRef(null);
  const [playing, setPlaying] = useState(false);
  const speed = 0.55; // px per frame

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

  useEffect(() => () => cancelAnimationFrame(rafRef.current), []);

  return (
    <div className="root">
      <div className="fade-top" />
      <div className="fade-bottom" />

      <div className="scrollport" ref={portRef}>
        <div className="stage">
          {/* ── Section 1: total watches ── */}
          <div className="s-watches">
            <div className="s-watches-label">Films Watched</div>
            <div className="s-watches-num">{report.totalWatches}</div>
            <div className="s-watches-unit">watches this week</div>
            <div className="s-watches-change">
              ↑ {report.percentChange}% vs last week
            </div>
          </div>

          <div className="rule" />

          {/* ── Section 2: bar chart ── */}
          <BarChart />

          <div className="rule" />

          {/* ── Credited sections ── */}
          <CreditedList header="Top Director" items={report.directors} />
          <div className="rule" />

          <CreditedList header="Top Actor" items={report.actors} />
          <div className="rule" />

          <CreditedList header="Top Genre" items={report.genres} />
          <div className="rule" />

          <CreditedList header="Most Recent" items={report.recentFilms} />
          <div className="rule" />

          <DecadeSection />

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
