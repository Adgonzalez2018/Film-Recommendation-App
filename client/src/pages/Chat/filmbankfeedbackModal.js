import React, { useState } from "react";
import { submitFilmBankFeedback } from "../../api/chat";

/**
 * Feedback modal for a single Film Bank entry.
 *
 * Props:
 *   film       — normalized film bank item (needs film.movieId and film.title)
 *   token      — access token
 *   onDone     — called with the movieId after a successful submission
 *   onClose    — called when the user cancels without submitting
 */
const RATINGS = [
  { value: "good",    label: "👍 Good" },
  { value: "neutral", label: "😐 Neutral" },
  { value: "bad",     label: "👎 Bad" },
];

const FilmBankFeedbackModal = ({ film, token, onDone, onClose }) => {
  const [rating, setRating]   = useState(null);      // "good" | "neutral" | "bad"
  const [watched, setWatched] = useState(null);      // true | false | null
  const [text, setText]       = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError]     = useState("");

  const canSubmit = rating !== null && !submitting;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setError("");
    try {
      await submitFilmBankFeedback(film.movieId, token, { rating, watched, text });
      onDone(film.movieId);
    } catch (err) {
      setError(err?.message || "Failed to submit feedback.");
      setSubmitting(false);
    }
  };

  return (
    <div className="fb-feedback-overlay" onClick={onClose}>
      <div className="fb-feedback-modal" onClick={(e) => e.stopPropagation()}>

        <div className="fb-feedback-header">
          <span className="fb-feedback-title">RATE RECOMMENDATION</span>
          <button className="film-bank-close" onClick={onClose} aria-label="Close">×</button>
        </div>

        <div className="fb-feedback-film">
          {film.poster
            ? <img src={film.poster} alt={film.title} className="fb-feedback-poster" />
            : <div className="fb-feedback-poster-placeholder">{film.title.charAt(0)}</div>
          }
          <div>
            <div className="fb-feedback-film-title">{film.title}</div>
            {film.year && <div className="fb-feedback-film-year">{film.year}</div>}
          </div>
        </div>

        <div className="fb-feedback-section">
          <div className="fb-feedback-label">Was this a good recommendation?</div>
          <div className="fb-feedback-rating-row">
            {RATINGS.map((r) => (
              <button
                key={r.value}
                className={`fb-rating-btn ${rating === r.value ? "active" : ""}`}
                onClick={() => setRating(r.value)}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>

        <div className="fb-feedback-section">
          <div className="fb-feedback-label">Did you watch it?</div>
          <div className="fb-feedback-watched-row">
            {[
              { value: true,  label: "Yes" },
              { value: false, label: "No"  },
              { value: null,  label: "Skip" },
            ].map((opt) => (
              <button
                key={String(opt.value)}
                className={`fb-watched-btn ${watched === opt.value ? "active" : ""}`}
                onClick={() => setWatched(opt.value)}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        <div className="fb-feedback-section">
          <div className="fb-feedback-label">Anything else? <span className="fb-optional">(optional)</span></div>
          <textarea
            className="fb-feedback-textarea"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Tell us why..."
            rows={3}
            maxLength={500}
          />
          <div className="fb-char-count">{text.length}/500</div>
        </div>

        {error && <div className="fb-feedback-error">{error}</div>}

        <div className="fb-feedback-actions">
          <button className="fb-cancel-btn" onClick={onClose} disabled={submitting}>
            CANCEL
          </button>
          <button
            className={`fb-submit-btn ${!canSubmit ? "disabled" : ""}`}
            onClick={handleSubmit}
            disabled={!canSubmit}
          >
            {submitting ? "SAVING..." : "SUBMIT"}
          </button>
        </div>
      </div>
    </div>
  );
};

export default FilmBankFeedbackModal;