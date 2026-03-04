import "./Imports.css";
import "../Auth/Auth.css";

import React, { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";

// Assets
import personImg from "../../assets/images/Fargo_person.png";
import carImg from "../../assets/images/Fargo_car.png";

// Border
import PageFrame from "../../components/layout/PageFrame";

// API (your real import layer)
import { CSV_FILES, submitCSVImport, submitRSSSync } from "../../api/import";

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

      // Most users will want to jump into the app immediately.
      // If your centralized useAuth re-checks onboarding, it will allow chat or bounce back here.
      navigate("/chat");
    } catch (err) {
      setCsvError(err?.message || "Import failed.");
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
      // Don’t auto-navigate here unless RSS alone makes you “onboarded” in backend.
    } catch (err) {
      setRssError(err?.message || "RSS link failed.");
    } finally {
      setRssLoading(false);
    }
  };

  const handleContinue = () => navigate("/chat");

  // ── Auth guards ───────────────────────────────────────

  if (isAuthenticating) {
    return (
      <div className="connect-container">
        <div className="connect-box">
          <p className="connect-subtitle">Authenticating…</p>
        </div>
      </div>
    );
  }

  if (authError) {
    return (
      <div className="connect-container">
        <PageFrame />
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
      <PageFrame />
      <img src={personImg} alt="" className="connect-person" />
      <img src={carImg} alt="" className="connect-car" />

      <div className="connect-box">
        <h1 className="connect-title">Letterboxd Import</h1>
        <p className="connect-subtitle">Connect your film data to get started</p>

        <div className="connect-import-row">
          {/* ── SECTION 1: CSV Import ── */}
          <div className="connect-import-col">
            <div className="connect-section-header">
              <span className="connect-label">Manual Import</span>
            </div>

            <p className="connect-description">
              For the best film recommendation experience, it's highly encouraged that you import
              your Letterboxd data. Head to{" "}
              <strong>letterboxd.com → Settings → Import &amp; Export → Export Your Data</strong>,
              then upload the three CSV files below. This unlocks your{" "}
              <strong>all-time stats report</strong> and generates an{" "}
              <strong>initial weekly stats report</strong> right away.
            </p>

            {csvError && <div className="connect-error">{csvError}</div>}
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
                    onKeyDown={(e) => e.key === "Enter" && fileInputRefs[key].current.click()}
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
                      <div className="csv-file-name">{files[key] ? files[key].name : hint}</div>
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

          {/* ── Vertical divider ── */}
          <div className="connect-import-divider">
            <span className="connect-import-divider-line" />
            <span className="connect-import-divider-text"></span>
            <span className="connect-import-divider-line" />
          </div>

          {/* ── SECTION 2: RSS Sync ── */}
          <div className="connect-import-col">
            <div className="connect-section-header">
              <span className="connect-label">Weekly Auto Sync</span>
            </div>

            <p className="connect-description">
              For <strong>constant weekly reports</strong> of your movies, insert your Letterboxd
              URL below. We'll hook into your public RSS feed and automatically re-sync your recent
              watches every week — no repeat exports needed.
            </p>

            {rssError && <div className="connect-error">{rssError}</div>}
            {rssSuccess && <div className="connect-success">{rssSuccess}</div>}

            <form onSubmit={handleRSSSubmit}>
              <div className="connect-group">
                <label className="connect-label" htmlFor="rss-input">
                  Letterboxd url or Username
                </label>
                <input
                  id="rss-input"
                  className="neon-field"
                  type="text"
                  placeholder="e.g. username or letterboxd.com/username"
                  value={rssInput}
                  onChange={(e) => {
                    setRssInput(e.target.value);
                    setRssError(null);
                  }}
                  autoComplete="off"
                  spellCheck={false}
                />
                <p className="connect-hint">We'll build your RSS feed URL automatically from your username.</p>
              </div>

              <button type="submit" className="auth-button" disabled={rssLoading}>
                {rssLoading ? "LINKING…" : "Link For Weekly Reports"}
              </button>
            </form>
          </div>
        </div>

        {/* ── Continue / Skip ── */}
        <div className="connect-skip">
          <button className="connect-skip-link" onClick={handleContinue}>
            {csvSuccess || rssSuccess ? "Continue to Chat" : "Skip for now"}
          </button>
        </div>
      </div>
    </div>
  );
}