import React, { useState, useRef } from "react";
import "./LetterboxdConnect.css";
import "../Auth/Auth.css";
import { useNavigate } from "react-router-dom";
import backgroundImg from "../../assets/images/shining.png";
import { useAuth } from "../../hooks/useAuth";

// ─── CSV file definitions ─────────────────────────────────

const CSV_FILES = [
  {
    key: "reviews",
    label: "reviews.csv",
    hint: "Your film ratings & written reviews",
    icon: "🎬",
  },
  {
    key: "watchlist",
    label: "watchlist.csv",
    hint: "Films you want to watch",
    icon: "📋",
  },
  {
    key: "likes",
    label: "films.csv",
    hint: "Your liked films",
    icon: "❤️",
  },
];

// ─── API calls ────────────────────────────────────────────

async function submitCSVImport(files, accessToken) {
  const formData = new FormData();
  if (files.reviews) formData.append("reviews", files.reviews);
  if (files.watchlist) formData.append("watchlist", files.watchlist);
  if (files.likes) formData.append("likes", files.likes);

  const response = await fetch("/api/letterboxd/import/", {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
    body: formData,
  });

  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Import failed");
  return data;
}

async function submitRSSSync(rssInput, accessToken) {
  const response = await fetch("/api/letterboxd/rss/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ rss: rssInput.trim() }),
  });

  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "RSS sync failed");
  return data;
}

// ─── Component ────────────────────────────────────────────

export default function LetterboxdConnect() {
  const navigate = useNavigate();
  const { isAuthenticating, authError, accessToken } = useAuth();

  // CSV state
  const [files, setFiles] = useState({ reviews: null, watchlist: null, likes: null });
  const fileInputRefs = {
    reviews: useRef(),
    watchlist: useRef(),
    likes: useRef(),
  };
  const [csvLoading, setCsvLoading] = useState(false);
  const [csvError, setCsvError] = useState(null);
  const [csvSuccess, setCsvSuccess] = useState(null);

  // RSS state
  const [rssInput, setRssInput] = useState("");
  const [rssLoading, setRssLoading] = useState(false);
  const [rssError, setRssError] = useState(null);
  const [rssSuccess, setRssSuccess] = useState(null);

  // ── Handlers ──────────────────────────────────────────

  const handleFileChange = (key, e) => {
    const file = e.target.files?.[0] ?? null;
    setFiles((prev) => ({ ...prev, [key]: file }));
    setCsvError(null);
    setCsvSuccess(null);
  };

  const handleCSVSubmit = async (e) => {
    e.preventDefault();
    if (!Object.values(files).some(Boolean)) {
      setCsvError("Please upload at least one CSV file.");
      return;
    }
    if (!accessToken) {
      setCsvError("Not authenticated. Please sign in again.");
      return;
    }
    setCsvLoading(true);
    setCsvError(null);
    setCsvSuccess(null);
    try {
      await submitCSVImport(files, accessToken);
      setCsvSuccess("Data imported! Your all-time stats and initial weekly report are ready.");
    } catch (err) {
      setCsvError(err.message);
    } finally {
      setCsvLoading(false);
    }
  };

  const handleRSSSubmit = async (e) => {
    e.preventDefault();
    if (!rssInput.trim()) {
      setRssError("Please enter your Letterboxd username or profile URL.");
      return;
    }
    if (!accessToken) {
      setRssError("Not authenticated. Please sign in again.");
      return;
    }
    setRssLoading(true);
    setRssError(null);
    setRssSuccess(null);
    try {
      await submitRSSSync(rssInput, accessToken);
      setRssSuccess("RSS linked! Weekly watch reports will sync automatically.");
    } catch (err) {
      setRssError(err.message);
    } finally {
      setRssLoading(false);
    }
  };

  const handleContinue = () => navigate("/chat");

  // ── Auth guards ───────────────────────────────────────

  if (isAuthenticating) {
    return (
      <div className="connect-container">
        <div
          className="connect-background"
          style={{ backgroundImage: `url(${backgroundImg})` }}
        />
        <div className="connect-box">
          <p className="connect-subtitle">Authenticating…</p>
        </div>
      </div>
    );
  }

  if (authError) {
    return (
      <div className="connect-container">
        <div
          className="connect-background"
          style={{ backgroundImage: `url(${backgroundImg})` }}
        />
        <div className="connect-box">
          <div className="connect-error">{authError}</div>
          <button className="auth-button" onClick={() => navigate("/signin")}>
            GO TO SIGN IN
          </button>
        </div>
      </div>
    );
  }

  // ── Render ────────────────────────────────────────────

  return (
    <div className="connect-container">
      <div
        className="connect-background"
        style={{ backgroundImage: `url(${backgroundImg})` }}
      />

      <div className="connect-box">
        <h1 className="connect-title">LETTERBOXD</h1>
        <p className="connect-subtitle">Connect your film data to get started</p>

        {/* ── SECTION 1: CSV Import ── */}
        <div className="connect-section">
          <div className="connect-section-header">
            <span className="connect-section-badge">01</span>
            <span className="connect-label">Import Your Data</span>
          </div>

          <p className="connect-description">
            For the best film recommendation experience, it's highly encouraged that
            you import your Letterboxd data. Head to{" "}
            <strong>letterboxd.com → Settings → Import &amp; Export → Export Your Data</strong>,
            then upload the three CSV files below. This unlocks your{" "}
            <strong>all-time stats report</strong> and generates an{" "}
            <strong>initial weekly stats report</strong> right away.
          </p>

          {csvError   && <div className="connect-error">{csvError}</div>}
          {csvSuccess && <div className="connect-success">{csvSuccess}</div>}

          <form onSubmit={handleCSVSubmit}>
            <div className="csv-upload-list">
              {CSV_FILES.map(({ key, label, hint, icon }) => (
                <div
                  key={key}
                  className={`csv-row ${files[key] ? "has-file" : ""}`}
                  onClick={() => fileInputRefs[key].current.click()}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) =>
                    e.key === "Enter" && fileInputRefs[key].current.click()
                  }
                >
                  <input
                    type="file"
                    accept=".csv"
                    ref={fileInputRefs[key]}
                    onChange={(e) => handleFileChange(key, e)}
                  />
                  <span className="csv-icon">{icon}</span>
                  <div className="csv-info">
                    <div className="csv-name">{label}</div>
                    <div className="csv-file-name">
                      {files[key] ? files[key].name : hint}
                    </div>
                  </div>
                  <span className="csv-status">{files[key] ? "✅" : "＋"}</span>
                </div>
              ))}
            </div>

            <button type="submit" className="auth-button" disabled={csvLoading}>
              {csvLoading ? "IMPORTING…" : "IMPORT DATA"}
            </button>
          </form>
        </div>

        {/* ── Divider ── */}
        <div className="connect-divider">
          <span className="connect-divider-line" />
          <span className="connect-divider-text">AND / OR</span>
          <span className="connect-divider-line" />
        </div>

        {/* ── SECTION 2: RSS Sync ── */}
        <div className="connect-section">
          <div className="connect-section-header">
            <span className="connect-section-badge">02</span>
            <span className="connect-label">Weekly Auto Sync</span>
          </div>

          <p className="connect-description">
            For <strong>constant weekly reports</strong> of your movies, insert your
            Letterboxd URL below. We'll hook into your public RSS feed and
            automatically re-sync your recent watches every week — no repeat exports
            needed.
          </p>

          {rssError   && <div className="connect-error">{rssError}</div>}
          {rssSuccess && <div className="connect-success">{rssSuccess}</div>}

          <form onSubmit={handleRSSSubmit}>
            <div className="connect-group">
              <label className="connect-label" htmlFor="rss-input">
                Letterboxd URL or Username
              </label>
              <input
                id="rss-input"
                className="neon-field"
                type="text"
                placeholder="e.g.  yourname  or  letterboxd.com/yourname"
                value={rssInput}
                onChange={(e) => {
                  setRssInput(e.target.value);
                  setRssError(null);
                }}
                autoComplete="off"
                spellCheck={false}
              />
              <p className="connect-hint">
                We'll build your RSS feed URL automatically from your username.
              </p>
            </div>

            <button type="submit" className="auth-button" disabled={rssLoading}>
              {rssLoading ? "LINKING…" : "LINK FOR WEEKLY REPORTS"}
            </button>
          </form>
        </div>

        {/* ── Continue / Skip ── */}
        <div className="connect-skip">
          <button className="connect-skip-link" onClick={handleContinue}>
            {csvSuccess || rssSuccess ? "Continue →" : "Skip for now"}
          </button>
        </div>
      </div>
    </div>
  );
}