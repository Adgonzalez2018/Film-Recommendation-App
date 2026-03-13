import "./Imports.css";
import "../Auth/Auth.css";

import React, { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import { useRequest } from "../../hooks/useRequest";

// Assets
import personImg from "../../assets/images/Fargo_person.png";
import carImg from "../../assets/images/Fargo_car.png";

// Border
import PageFrame from "../../components/layout/PageFrame";

// API
import { CSV_FILES, submitCSVImport, submitRSSSync, markOnboardingSkipped } from "../../api/import";

export default function LetterboxdConnect() {
  const navigate = useNavigate();
  const { isAuthenticating, 
    authError, 
    accessToken, 
    isOnboarded, 
    onboardingStatus, 
    refreshOnboarding,
  } = useAuth();

  useEffect(() => {
    if (isOnboarded) {
      navigate("/chat", { replace: true});
    }
  }, [isOnboarded, navigate]);


  // CSV state
  const [files, setFiles] = useState({
    watched: null,
    reviews: null,
    watchlist: null,
    likes: null,
  });

  const fileInputRefs = {
    watched: useRef(),
    reviews: useRef(),
    watchlist: useRef(),
    likes: useRef(),
  };

  const [csvSuccess, setCsvSuccess] = useState(null);
  const [csvError, setCsvError] = useState(null);

  // RSS state
  const [rssInput, setRssInput] = useState("");
  const [rssLoading, setRssLoading] = useState(false);
  const [rssError, setRssError] = useState(null);
  const [rssSuccess, setRssSuccess] = useState(null);

  const handleFileChange = (key, e) => {
    const file = e.target.files?.[0] ?? null;
    setFiles((prev) => ({ ...prev, [key]: file }));
    setCsvError(null);
    setCsvSuccess(null);
  };

  // check if user imported or linked 
  const hasImportedOrLinked =
    Boolean(onboardingStatus?.has_manual_import) ||
    Boolean(onboardingStatus?.has_rss_import) ||
    Boolean(csvSuccess) ||
    Boolean(rssSuccess);

  const {
    run: runCsvImport,
    loading: csvLoading,
    error: csvRequestError,
  } = useRequest(async () => {
    if (!Object.values(files).some(Boolean)) {
      throw new Error("Please upload at least one csv file.");
    }

    if (!accessToken) {
      throw new Error("Not authenticated. Please sign in again.");
    }

    await submitCSVImport(files, accessToken);
    await refreshOnboarding();
    setCsvSuccess("Data imported! Your all-time stats and initial weekly report are ready!");
  });

  const handleCSVSubmit = (e) => {
    e.preventDefault();
    setCsvSuccess(null);
    setCsvError(null);
    runCsvImport();
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
      await refreshOnboarding();
      setRssSuccess("RSS linked! Weekly watch reports will sync automatically.");
    } catch (err) {
      setRssError(err?.message || "RSS link failed.");
    } finally {
      setRssLoading(false);
    }
  };

  const handleContinue = async () => {
    try {
      if (!accessToken){
        throw new Error("Not authenticated. Please sign in again.");
      }

      // only mark skip if user hasn't imported anything
      if (!hasImportedOrLinked && !isOnboarded) {
        await markOnboardingSkipped(accessToken);
        await refreshOnboarding();
      }

      navigate("/chat");
    } catch (err) {
      setCsvError(err?.message || "Could not continue.");
    }
  };

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

  return (
    <div className="connect-container">
      <PageFrame />
      <img src={personImg} alt="" className="connect-person" />
      <img src={carImg} alt="" className="connect-car" />

      <div className="connect-box">
        <h1 className="connect-title">Letterboxd Import</h1>
        <p className="connect-subtitle">Connect your film data to get started</p>

        <div className="connect-import-row">
          <div className="connect-import-col">
            <div className="connect-section-header">
              <span className="connect-label">Manual Import</span>
            </div>

            <p className="connect-description">
              For the best film recommendation experience, it's highly encouraged that you import
              your Letterboxd data. Head to{" "}
              <strong>letterboxd.com → Settings → Import &amp; Export → Export Your Data</strong>,
              then upload your CSV files below. The <strong>watched export</strong> helps recover
              your full watch history, while reviews, likes/films, and watchlist fill in the rest
              of your profile. This unlocks your <strong>all-time stats report</strong> and
              generates an <strong>initial weekly stats report</strong> right away.
            </p>

            {(csvError || csvRequestError) && (
              <div className="connect-error">{csvError || csvRequestError}</div>
            )}
            {csvSuccess && <div className="connect-success">{csvSuccess}</div>}

            <form onSubmit={handleCSVSubmit}>
              <div className="csv-upload-list">
                {CSV_FILES.map(({ key, label, hint, icon }) => (
                  <div
                    key={key}
                    className={`csv-row ${files[key] ? "has-file" : ""}`}
                    onClick={() => fileInputRefs[key].current?.click()}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        fileInputRefs[key].current?.click();
                      }
                    }}
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

          <div className="connect-import-divider">
            <span className="connect-import-divider-line" />
            <span className="connect-import-divider-text"></span>
            <span className="connect-import-divider-line" />
          </div>

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
                <p className="connect-hint">
                  We'll build your RSS feed URL automatically from your username.
                </p>
              </div>

              <button type="submit" className="auth-button" disabled={rssLoading}>
                {rssLoading ? "LINKING…" : "Link For Weekly Reports"}
              </button>
            </form>
          </div>
        </div>

        <div className="connect-skip">
          <button className="connect-skip-link" onClick={handleContinue}>
            {hasImportedOrLinked ? "Continue to Chat" : "Skip for now"}
          </button>
        </div>
      </div>
    </div>
  );
}