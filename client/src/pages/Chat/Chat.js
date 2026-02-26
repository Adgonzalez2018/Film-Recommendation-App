import React, { useState, useRef, useEffect } from "react";
import "./Chat.css";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";

// ─── TMDB poster fetching ────────────────────────────────
// Put your TMDB read-access token in .env as REACT_APP_TMDB_TOKEN
const TMDB_TOKEN = process.env.REACT_APP_TMDB_TOKEN;

async function fetchPoster(title, year) {
  if (!TMDB_TOKEN) return null;
  try {
    const query = encodeURIComponent(title);
    const yearParam = year ? `&primary_release_year=${year}` : "";
    const res = await fetch(
      `https://api.themoviedb.org/3/search/movie?query=${query}${yearParam}&page=1`,
      { headers: { Authorization: `Bearer ${TMDB_TOKEN}` } }
    );
    const data = await res.json();
    const hit = data.results?.[0];
    if (hit?.poster_path) {
      return `https://image.tmdb.org/t/p/w300${hit.poster_path}`;
    }
  } catch {}
  return null;
}

// ─── Parse movie recommendations from AI text ───────────
function parseMovies(text) {
  const results = [];
  const seen = new Set();

  const patterns = [
    /(?:^|\n)\s*(?:\d+\.|[-*])\s+\*{1,2}([^*\n(]+?)\*{1,2}\s*(?:\((\d{4})\))?/gm,
    /(?:^|\n)\s*(?:\d+\.|[-*])\s+"([^"\n(]+?)"\s*(?:\((\d{4})\))?/gm,
    /\*{1,2}([A-Z][^*\n(]{2,50}?)\*{1,2}\s*\((\d{4})\)/gm,
    /"([A-Z][^"\n(]{2,50}?)"\s*\((\d{4})\)/gm,
  ];

  for (const pat of patterns) {
    let m;
    while ((m = pat.exec(text)) !== null) {
      const title = m[1].trim();
      const year = m[2] || null;
      const key = title.toLowerCase();
      if (!seen.has(key) && title.length > 1) {
        seen.add(key);
        results.push({ title, year, poster: null, id: `${key}-${Date.now()}` });
      }
    }
  }

  return results.slice(0, 3);
}

const Chat = () => {
  const navigate = useNavigate();
  const { isAuthenticating, authError } = useAuth();

  const [messages, setMessages] = useState([
    {
      id: 1,
      role: "assistant",
      content:
        "Hello! I'm your film recommendation AI. I know all about your Letterboxd viewing history. What would you like to know?",
      timestamp: new Date(),
    },
  ]);

  const [input, setInput] = useState("");
  const [chatHistory, setChatHistory] = useState([
    { id: 1, title: "New conversation", date: "Today", active: true },
  ]);
  const [isLoading, setIsLoading] = useState(false);

  // ── Film bank ────────────────────────────────────────
  const [filmBank, setFilmBank] = useState([]);
  const [bankOpen, setBankOpen] = useState(false);

  const messagesEndRef = useRef(null);
  const PROMPT = "user@film:~$";

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // ── Add movies from AI response to film bank ─────────
  const addToFilmBank = async (text) => {
    const movies = parseMovies(text);
    if (!movies.length) return;

    setFilmBank((prev) => {
      const existingTitles = new Set(prev.map((f) => f.title.toLowerCase()));
      const fresh = movies.filter((m) => !existingTitles.has(m.title.toLowerCase()));
      return [...prev, ...fresh];
    });

    for (const movie of movies) {
      const poster = await fetchPoster(movie.title, movie.year);
      if (poster) {
        setFilmBank((prev) =>
          prev.map((f) =>
            f.title.toLowerCase() === movie.title.toLowerCase()
              ? { ...f, poster }
              : f
          )
        );
      }
    }
  };

  const removeFromBank = (title) => {
    setFilmBank((prev) => prev.filter((f) => f.title !== title));
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMessage = {
      id: messages.length + 1,
      role: "user",
      content: input,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    // TODO: replace with your backend call to /api/chat/recommend/
    setTimeout(() => {
      const aiResponse =
        'Based on your history, I recommend:\n\n1. **Breathless** (1960) — Godard\'s jump-cut debut.\n2. **La Haine** (1995) — A single day in the banlieues.\n3. **Bande à part** (1964) — Outsiders running through the Louvre.';

      const aiMessage = {
        id: messages.length + 2,
        role: "assistant",
        content: aiResponse,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, aiMessage]);
      addToFilmBank(aiResponse);
      setIsLoading(false);
    }, 800);
  };

  const handleNewChat = () => {
    const newChat = {
      id: chatHistory.length + 1,
      title: "New conversation",
      date: "Today",
      active: true,
    };
    setChatHistory([newChat, ...chatHistory.map((c) => ({ ...c, active: false }))]);
    setMessages([
      {
        id: 1,
        role: "assistant",
        content: "Hello! I'm your film recommendation AI. What would you like to know?",
        timestamp: new Date(),
      },
    ]);
  };

  const handleChatSelect = (chatId) => {
    setChatHistory((prev) => prev.map((c) => ({ ...c, active: c.id === chatId })));
  };

  if (isAuthenticating) {
    return (
      <div className="chat-container dark-mode">
        <div className="auth-loading"><p>Authenticating...</p></div>
      </div>
    );
  }

  if (authError) {
    return (
      <div className="chat-container dark-mode">
        <div className="auth-error-container">
          <div className="error-message">{authError}</div>
          <button className="retry-button" onClick={() => window.location.reload()}>RETRY</button>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-container dark-mode">
      {/* ── Left Sidebar ── */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <button className="new-chat-button" onClick={handleNewChat}>+ New Chat</button>
        </div>

        <div className="chat-history">
          {chatHistory.map((chat) => (
            <div
              key={chat.id}
              className={`chat-history-item ${chat.active ? "active" : ""}`}
              onClick={() => handleChatSelect(chat.id)}
            >
              <div className="history-title">{chat.title}</div>
              <div className="chat-date">{chat.date}</div>
            </div>
          ))}
        </div>

        <button
          type="button"
          className="profile-section"
          onClick={() => navigate("/profile")}
          aria-label="Go to profile"
        >
          <div className="profile-avatar">U</div>
          <div className="profile-info">
            <div className="profile-name">Profile</div>
            <div className="profile-email">Account</div>
          </div>
        </button>
      </aside>

      {/* ── Main chat ── */}
      <main className="chat-main">
        <header className="chat-header">
          <h1 className="header-title">Film-Recommender v0.1</h1>
          <div className="chat-header-nav">
            <button className="stats-button" onClick={() => setBankOpen(true)}>
              Film Bank
              {filmBank.length > 0 && <span className="bank-count">{filmBank.length}</span>}
            </button>
            <button className="stats-button" onClick={() => navigate("/stats")}>Stats</button>
          </div>
        </header>

        <div className="messages-container">
          {messages.map((m) => (
            <div key={m.id} className={`log-line ${m.role}`}>
              <span className="log-prefix">{m.role === "user" ? PROMPT : "ai@film:~#"}</span>
              <span className="log-text">{m.content}</span>
            </div>
          ))}
          {isLoading && (
            <div className="log-line assistant">
              <span className="log-prefix">ai@film:~#</span>
              <span className="log-text typing">typing...</span>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div className="input-container">
          <form onSubmit={handleSendMessage} className="input-form">
            <span className="prompt-label">{PROMPT}</span>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask your query..."
              className="message-input"
              rows="1"
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSendMessage(e);
                }
              }}
            />
            <button type="submit" className="send-button" disabled={!input.trim()}>ENTER</button>
          </form>
        </div>
      </main>

      {/* ── Film Bank modal ── */}
      {bankOpen && (
        <div className="film-bank-overlay" onClick={() => setBankOpen(false)}>
          <div className="film-bank-modal" onClick={(e) => e.stopPropagation()}>
            <div className="film-bank-header">
              <span className="film-bank-title">FILM BANK</span>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <span className="film-bank-count">{filmBank.length} saved</span>
                <button className="film-bank-close" onClick={() => setBankOpen(false)}>×</button>
              </div>
            </div>

            {filmBank.length === 0 ? (
              <div className="film-bank-empty">
                <span className="film-bank-empty-icon">⬚</span>
                <p>Films recommended by the AI will appear here.</p>
              </div>
            ) : (
              <div className="film-bank-grid">
                {filmBank.map((film) => (
                  <div key={film.id} className="film-card" title={`${film.title}${film.year ? ` (${film.year})` : ""}`}>
                    <div className="film-card-poster">
                      {film.poster ? (
                        <img src={film.poster} alt={film.title} />
                      ) : (
                        <div className="film-card-placeholder">
                          <span>{film.title.charAt(0)}</span>
                        </div>
                      )}
                      <button
                        className="film-card-remove"
                        onClick={() => removeFromBank(film.title)}
                        aria-label={`Remove ${film.title}`}
                      >
                        ×
                      </button>
                    </div>
                    <div className="film-card-info">
                      <div className="film-card-title">{film.title}</div>
                      {film.year && <div className="film-card-year">{film.year}</div>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default Chat;