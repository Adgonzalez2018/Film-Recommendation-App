import React, { useState, useRef, useEffect } from "react";
import "./Profile.css";
import "../Auth/Auth.css";

import { useNavigate } from "react-router-dom";

import { useAuth } from "../../hooks/useAuth";
import { CSV_FILES, submitCSVImport, submitRSSSync } from "../../api/letterboxd";
import { fetchProfile, saveProfile } from "../../api/profile";

import heroImg from "../../assets/images/la-haine-1.png";


  
export default function Profile() {
  const navigate = useNavigate();
  const { accessToken, isAuthenticating, authError } = useAuth();

  // ── Profile fields ─────────────────────────────────────
  const [name,          setName]          = useState("");
  const [email,         setEmail]         = useState("");
  const [birthday,      setBirthday]      = useState("");
  const [password,      setPassword]      = useState("");
  const [showPassword,  setShowPassword]  = useState(false);

  const [profileLoading, setProfileLoading] = useState(true);
  const [profileError,   setProfileError]   = useState(null);
  const [profileSuccess, setProfileSuccess] = useState(null);
  const [saveLoading,    setSaveLoading]    = useState(false);

  // ── CSV state ──────────────────────────────────────────
  const [files, setFiles] = useState({ reviews: null, watchlist: null, likes: null });
  const fileInputRefs = { reviews: useRef(), watchlist: useRef(), likes: useRef() };
  const [csvLoading, setCsvLoading] = useState(false);
  const [csvError,   setCsvError]   = useState(null);
  const [csvSuccess, setCsvSuccess] = useState(null);

  // ── RSS state ──────────────────────────────────────────
  const [rssInput,        setRssInput]        = useState("");
  const [savedRssUsername, setSavedRssUsername] = useState("");
  const [rssLoading,      setRssLoading]      = useState(false);
  const [rssError,        setRssError]        = useState(null);
  const [rssSuccess,      setRssSuccess]      = useState(null);
  const [syncLoading,     setSyncLoading]     = useState(false);

  // ── Load profile on mount ──────────────────────────────
  useEffect(() => {
    if (!accessToken) {
      setProfileLoading(false);
      return;
    }

    fetchProfile(accessToken)
      .then((data) => {
        setName(data.first_name     ?? "");
        setEmail(data.email         ?? "");
        setBirthday(data.birthday   ?? "");
        const username = data.letterboxd_username ?? "";
        setRssInput(username);
        setSavedRssUsername(username);
      })
      .catch((err) => setProfileError(err.message))
      .finally(() => setProfileLoading(false));
  }, [accessToken]);

  // ── Save profile ───────────────────────────────────────
  const handleSaveProfile = async (e) => {
    e.preventDefault();
    if (!accessToken) { setProfileError("Not authenticated."); return; }

    const cleanName = (name || "").trim();
    if (!cleanName) { setProfileError("Name is Required."); return; }

    setSaveLoading(true);
    setProfileError(null);
    setProfileSuccess(null);
    try {
      const payload = { first_name: cleanName };
      if (birthday) payload.birthday = birthday;
      if (password) payload.password = password;
      await saveProfile(payload, accessToken);
      setProfileSuccess("Profile updated.");
      setPassword("");
    } catch (err) {
      setProfileError(err.message);
    } finally {
      setSaveLoading(false);
    }
  };

  // ── CSV handlers ───────────────────────────────────────
  const handleFileChange = (key, e) => {
    const file = e.target.files?.[0] ?? null;
    setFiles((prev) => ({ ...prev, [key]: file }));
    setCsvError(null);
    setCsvSuccess(null);
  };

  const handleCSVSubmit = async (e) => {
    e.preventDefault();
    if (!Object.values(files).some(Boolean)) { setCsvError("Upload at least one CSV."); return; }
    if (!accessToken) { setCsvError("Not authenticated."); return; }
    setCsvLoading(true); setCsvError(null); setCsvSuccess(null);
    try {
      await submitCSVImport(files, accessToken);
      setCsvSuccess("Imported! All-time stats and initial weekly report are ready.");
    } catch (err) {
      setCsvError(err.message);
    } finally {
      setCsvLoading(false);
    }
  };

  // ── RSS link handler ───────────────────────────────────
  const handleRSSSubmit = async (e) => {
    const u = cleanUsername(rssInput);
    await submitRSSSync(u, accessToken);
    setSavedRssUsername(u);
    setRssInput(u);
    e.preventDefault();
    if (!rssInput.trim()) { setRssError("Enter your Letterboxd username or URL."); return; }
    if (!accessToken)     { setRssError("Not authenticated."); return; }
    setRssLoading(true); setRssError(null); setRssSuccess(null);
    try {
      await submitRSSSync(rssInput, accessToken);
      setRssSuccess("RSS linked — weekly reports will sync automatically.");
      setSavedRssUsername(rssInput.trim());
    } catch (err) {
      setRssError(err.message);
    } finally {
      setRssLoading(false);
    }
  };

  // ── Resync handler ─────────────────────────────────────
  const handleResync = async () => {
    if (!savedRssUsername || !accessToken) return;
    setSyncLoading(true); setRssError(null); setRssSuccess(null);
    try {
      await submitRSSSync(savedRssUsername, accessToken);
      setRssSuccess("Sync complete — your data is up to date.");
    } catch (err) {
      setRssError(err.message);
    } finally {
      setSyncLoading(false);
    }
  };

  // ── Helpers ────────────────────────────────────────────
  const cleanUsername = (val) =>
  val.replace(/^https?:\/\/(www\.)?letterboxd\.com\//i, "").replace(/\/$/, "").trim();

  const letterboxdUsername = cleanUsername(savedRssUsername || "");
  const letterboxdProfileUrl = letterboxdUsername
  ? `https://letterboxd.com/${letterboxdUsername}/`
  : "";
  // ── Auth guards ────────────────────────────────────────
  if (isAuthenticating || profileLoading) {
    return (
      <div className="profile-page" style={{ display:"flex", alignItems:"center", justifyContent:"center", minHeight:"100vh" }}>
        <p style={{ color:"#fff", letterSpacing:"0.1em" }}>Loading…</p>
      </div>
    );
  }

  if (authError) {
    return (
      <div className="profile-page" style={{ display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", minHeight:"100vh", gap:"1rem" }}>
        <div className="profile-error">{authError}</div>
        <button className="profile-save-btn" style={{ maxWidth:300 }} onClick={() => navigate("/signin")}>
          GO TO SIGN IN
        </button>
      </div>
    );
  }

  // ── Render ─────────────────────────────────────────────
  return (
    <div className="profile-page">

      {/* ── HERO ── */}
      <div className="profile-hero">
        <img src={heroImg} alt="" className="profile-hero-img" />
      </div>

      {/* ── TITLE BAND ── */}
      <div className="profile-title-band">
        <span className="profile-title">LE PROFIL</span>
      </div>

      {/* ── BODY ── */}
      <div className="profile-body">
        <div className="profile-inner">

          <p className="profile-tagline">jusqu'ici tout va bien…</p>

          {profileError   && <div className="profile-error">{profileError}</div>}
          {profileSuccess && <div className="profile-success">{profileSuccess}</div>}

          <form onSubmit={handleSaveProfile}>

            {/* ── 01 — Personal Info ── */}
            <div className="profile-section">
              <span className="profile-stack-title">PERSONAL INFO</span>
              <div className="profile-stack">
                <div className="profile-group">
                  <label className="profile-label" htmlFor="profile-name">Name</label>
                  <input
                    id="profile-name"
                    className="neon-field"
                    type="text"
                    placeholder="Your Name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    autoComplete="name"
                  />
                </div>
                <div className="profile-group">
                  <label className="profile-label" htmlFor="profile-email">Email</label>
                  <input
                    id="profile-email"
                    className="neon-field"
                    type="email"
                    value={email}
                    readOnly
                    aria-readonly="true"
                    tabIndex={-1}
                  />
                </div>
                <div className="profile-group">
                  <label className="profile-label" htmlFor="profile-birthday">Birthday</label>
                  <input
                    id="profile-birthday"
                    className="neon-field"
                    type="date"
                    value={birthday}
                    onChange={(e) => setBirthday(e.target.value)}
                  />
                </div>
              </div>
            </div>

            {/* ── 02 — Security ── */}
            <div className="profile-section">
              <div className="profile-password-center">
                <label className="profile-password-title">New Password</label>
                <div className="profile-password-row">
                  <input
                    id="profile-password"
                    className="neon-field"
                    type={showPassword ? "text" : "password"}
                    placeholder="Leave blank to keep current"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="new-password"
                  />
                  <button
                    type="button"
                    className="profile-eye-btn"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                  >
                    {showPassword ? "🙈" : "👁"}
                  </button>
                </div>
              </div>
            </div>

            <button type="submit" className="profile-save-btn" disabled={saveLoading}>
              {saveLoading ? "SAVING…" : "SAVE CHANGES"}
            </button>

          </form>
        </div>
      </div>

      {/* ════════════════════════════════════════════════
          LETTERBOXD STRIP
      ════════════════════════════════════════════════ */}
      <div className="profile-letterboxd-strip">
        <div className="profile-inner">
          <div className="profile-import-row">

            {/* ── CSV Import ── */}
            <div className="profile-import-col">
              <div className="profile-section-header">
                <span className="profile-section-label">Import Your Data</span>
              </div>
              <p className="profile-strip-description">
                For the best film recommendation experience, import your Letterboxd data via{" "}
                <strong>letterboxd.com → Settings → Import &amp; Export → Export Your Data</strong>.
                Upload the three CSV files below to unlock your{" "}
                <strong>all-time stats report</strong> and an{" "}
                <strong>initial weekly stats report</strong>.
              </p>

              {csvError   && <div className="profile-error">{csvError}</div>}
              {csvSuccess && <div className="profile-success">{csvSuccess}</div>}

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
                <button type="submit" className="profile-save-btn" disabled={csvLoading}>
                  {csvLoading ? "IMPORTING…" : "IMPORT DATA"}
                </button>
              </form>
            </div>

            {/* ── Vertical divider ── */}
            <div className="profile-import-divider">
              <span className="profile-import-divider-line" />
              <span className="profile-import-divider-text">OR</span>
              <span className="profile-import-divider-line" />
            </div>

            {/* ── RSS Sync ── */}
            <div className="profile-import-col">
              <div className="profile-section-header">
                <span className="profile-section-label">Weekly Auto Sync</span>
              </div>
              <p className="profile-strip-description">
                For <strong>constant weekly reports</strong> of your movies, link your
                Letterboxd URL. We'll sync your public RSS feed automatically every week.
              </p>

              {rssError   && <div className="profile-error">{rssError}</div>}
              {rssSuccess && <div className="profile-success">{rssSuccess}</div>}

              <form onSubmit={handleRSSSubmit}>
                <div className="profile-group">
                  <label className="profile-label" htmlFor="rss-profile-input">
                    Letterboxd URL or Username
                    {savedRssUsername && (
                      <span style={{ fontWeight: 300, opacity: 0.6, marginLeft: "0.6em", textTransform: "none", letterSpacing: "0.04em" }}>
                        — {cleanUsername(savedRssUsername)}
                      </span>
                    )}
                  </label>
                  <input
                    id="rss-profile-input"
                    className="neon-field"
                    type="text"
                    placeholder={savedRssUsername
                      ? cleanUsername(savedRssUsername)
                      : "e.g.  yourname  or  letterboxd.com/yourname"
                    }
                    value={rssInput}
                    onChange={(e) => { setRssInput(e.target.value); setRssError(null); }}
                    autoComplete="off"
                    spellCheck={false}
                  />
                  <p className="connect-hint">
                    We'll build your RSS feed URL automatically from your username.
                  </p>
                </div>

                <button type="submit" className="profile-save-btn" disabled={rssLoading}>
                  {rssLoading ? "LINKING…" : "LINK FOR WEEKLY REPORTS"}
                </button>

                <button type="button" className="profile-save-btn"
                style={{marginTop:"0.6rem"}} onClick={handleResync}
                disabled={!savedRssUsername || syncLoading}
                title={!savedRssUsername ? "Link your letterboxd first" : "Sync your RSS now"}>
                  {!savedRssUsername
                    ? "SYNC NOW"
                    : syncLoading
                      ? "SYNCING..."
                      : "SYNC NOW"}
                </button>

              </form>
            </div>

          </div>
        </div>
      </div>
    </div>
  );
}