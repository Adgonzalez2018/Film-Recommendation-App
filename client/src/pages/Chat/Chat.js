import React, { useEffect, useMemo, useReducer, useRef, useState } from "react";
import "./Chat.css";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import {
  sendChatMessage,
  fetchFilmBank,
  dismissFilmBankMovie,
} from "../../api/chat";
import ModalShell from "./ModalShell";
import UpdatesModal from "./UpdatesModal";
import ConfirmDeleteModal from "./confirmdeleteModal";
import FilmBankFeedbackModal from "./filmbankfeedbackModal";

const UPDATES_VERSION = "V1.4";
const UPDATES_STORAGE_KEY = "filmrec_updates_seen_version";
const UPDATES_BULLETS = [
  "Film Bank recommendations can now be rated without being auto-dismissed.",
  "Recommendation cards now keep Letterboxd links first, with TMDB as fallback.",
  "Chat history delete flow has been cleaned up and made more stable.",
  "General UI polish and recommendation modal improvements.",
];

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function makeChatTitle(text) {
  const clean = text.trim().replace(/\s+/g, " ");
  if (!clean) return "New Conversation";
  return clean.length > 36 ? `${clean.slice(0, 36)}…` : clean;
}

const STORAGE_KEY = "filmrec_chats";

function normalizeLetterboxd(url) {
  if (!url) return null;
  if (url.startsWith("http")) return url;
  return `https://letterboxd.com${url}`;
}

function normalizeFilmBankItem(item) {
  const movie = item?.movie || {};
  return {
    id: item?.id,
    movieId: movie?.id,
    title: movie?.title || "Untitled",
    year: movie?.year ?? null,
    poster: movie?.poster_url || null,
    tmdbId: movie?.tmdb_id ?? null,
    letterboxd_uri: movie?.letterboxd_uri || movie?.letterboxd || null,
    description: movie?.description || "",
    avgRating: movie?.avg_rating ?? null,
    reason: item?.why || item?.reason || "",
    queryText: item?.query_text || "",
    createdAt: item?.created_at || null,
  };  
}

function getMovieLink(film) {
  if (film?.letterboxd_uri) return normalizeLetterboxd(film.letterboxd_uri);
  if (film?.tmdbId) return `https://www.themoviedb.org/movie/${film.tmdbId}`;
  return null;
}

function normalizeRecommendation(movie) {
  return {
    id: `rec-${movie?.id ?? movie?.tmdb_id ?? Math.random().toString(36).slice(2)}`,
    movieId: movie?.id ?? null,
    title: movie?.title || "Untitled",
    year: movie?.year ?? null,
    poster: movie?.poster_url || null,
    tmdbId: movie?.tmdb_id ?? null,
    description: movie?.description || "",
    avgRating: movie?.avg_rating ?? null,
    why: movie?.why || "",
    letterboxd_uri: movie?.letterboxd_uri || movie?.letterboxd || null,
  };
}

const INITIAL_ASSISTANT_MESSAGE = {
  id: 1,
  role: "assistant",
  content:
    "Hello! I'm your film recommendation AI. I know all about your Letterboxd viewing history. What would you like to know?",
  recommendations: [],
  timestamp: new Date().toISOString(),
};

function makeNewChat() {
  return {
    id: Date.now() + Math.floor(Math.random() * 1000),
    title: "New Conversation",
    messages: [INITIAL_ASSISTANT_MESSAGE],
    createdAt: new Date().toISOString(),
  };
}

// ---------------------------------------------------------------------------
// Reducer
// ---------------------------------------------------------------------------

const INITIAL_CHAT_STATE = {
  chatHistory: [],
  activeChatId: null,
  deleteTarget: null,
};

function chatReducer(state, action) {
  switch (action.type) {
    case "INIT_FROM_STORAGE": {
      const chats = Array.isArray(action.payload?.chats) ? action.payload.chats : [];
      const activeChatId = action.payload?.activeChatId ?? null;

      if (chats.length === 0) {
        const newChat = makeNewChat();
        return {
          chatHistory: [newChat],
          activeChatId: newChat.id,
          deleteTarget: null,
        };
      }

      const validActiveId = chats.some((c) => c.id === activeChatId)
        ? activeChatId
        : chats[0].id;

      return {
        chatHistory: chats,
        activeChatId: validActiveId,
        deleteTarget: null,
      };
    }

    case "NEW_CHAT": {
      const newChat = makeNewChat();
      return {
        ...state,
        chatHistory: [newChat, ...state.chatHistory],
        activeChatId: newChat.id,
        deleteTarget: null,
      };
    }

    case "SELECT_CHAT": {
      if (!state.chatHistory.some((c) => c.id === action.chatId)) return state;
      return {
        ...state,
        activeChatId: action.chatId,
      };
    }

    case "OPEN_DELETE_MODAL":
      return {
        ...state,
        deleteTarget: action.chat,
      };

    case "CLOSE_DELETE_MODAL":
      return {
        ...state,
        deleteTarget: null,
      };

    case "DELETE_CHAT": {
      const remaining = state.chatHistory.filter((c) => c.id !== action.chatId);

      if (remaining.length === 0) {
        const newChat = makeNewChat();
        return {
          chatHistory: [newChat],
          activeChatId: newChat.id,
          deleteTarget: null,
        };
      }

      const nextActiveId =
        state.activeChatId === action.chatId
          ? remaining[0].id
          : remaining.some((c) => c.id === state.activeChatId)
            ? state.activeChatId
            : remaining[0].id;

      return {
        chatHistory: remaining,
        activeChatId: nextActiveId,
        deleteTarget: null,
      };
    }

    case "APPEND_USER_MESSAGE": {
      return {
        ...state,
        chatHistory: state.chatHistory.map((chat) =>
          chat.id === state.activeChatId
            ? {
                ...chat,
                title:
                  chat.title === "New Conversation"
                    ? makeChatTitle(action.message.content)
                    : chat.title,
                messages: [...(Array.isArray(chat.messages) ? chat.messages : []), action.message],
              }
            : chat
        ),
      };
    }

    case "APPEND_ASSISTANT_MESSAGE": {
      return {
        ...state,
        chatHistory: state.chatHistory.map((chat) =>
          chat.id === state.activeChatId
            ? {
                ...chat,
                messages: [...(Array.isArray(chat.messages) ? chat.messages : []), action.message],
              }
            : chat
        ),
      };
    }

    default:
      return state;
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const Chat = () => {
  const navigate = useNavigate();
  const { accessToken, isAuthenticating, authError } = useAuth();
  const [updatesOpen, setUpdatesOpen] = useState(false);
  const [chatState, dispatch] = useReducer(chatReducer, INITIAL_CHAT_STATE);
  const [input, setInput] = useState("");

  const [isLoading, setIsLoading] = useState(false);
  const [filmBank, setFilmBank] = useState([]);
  const [bankOpen, setBankOpen] = useState(false);
  const [bankLoading, setBankLoading] = useState(false);
  const [bankError, setBankError] = useState("");

  const [feedbackFilm, setFeedbackFilm] = useState(null);
  const messagesEndRef = useRef(null);
  const PROMPT = "user@film:~$";

  const activeChat =
    chatState.chatHistory.find((c) => c.id === chatState.activeChatId) || null;

  const messages = Array.isArray(activeChat?.messages)
    ? activeChat.messages
    : [INITIAL_ASSISTANT_MESSAGE];

  const filmBankCount = useMemo(() => filmBank.length, [filmBank]);

  // -------------------------------------------------------------------------
  // Film Bank
  // -------------------------------------------------------------------------

  const loadFilmBank = async () => {
    if (!accessToken) return;
    setBankLoading(true);
    setBankError("");
    try {
      const data = await fetchFilmBank(accessToken);
      const items = Array.isArray(data?.results)
        ? data.results.map(normalizeFilmBankItem)
        : [];
      setFilmBank(items);
    } catch (err) {
      setBankError(err?.message || "Failed to load Film Bank.");
    } finally {
      setBankLoading(false);
    }
  };

  const handleRemoveFromBank = async (movieId) => {
    if (!movieId || !accessToken) return;
    const prev = filmBank;
    setFilmBank((current) => current.filter((f) => f.movieId !== movieId));
    try {
      await dismissFilmBankMovie(movieId, accessToken);
    } catch (err) {
      setFilmBank(prev);
      setBankError(err?.message || "Failed to remove film.");
    }
  };

  const handleFeedbackDone = async () => {
    setFeedbackFilm(null);
    await loadFilmBank();
  };

  // -------------------------------------------------------------------------
  // Scroll
  // -------------------------------------------------------------------------

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  // -------------------------------------------------------------------------
  // Effects
  // -------------------------------------------------------------------------

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  useEffect(() => {
    loadFilmBank();
  }, [accessToken]);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);

      if (!saved) {
        dispatch({
          type: "INIT_FROM_STORAGE",
          payload: { chats: [], activeChatId: null },
        });
        return;
      }

      const parsed = JSON.parse(saved);
      dispatch({ type: "INIT_FROM_STORAGE", payload: parsed });
    } catch (err) {
      console.error("Failed to restore chats from localStorage:", err);
      localStorage.removeItem(STORAGE_KEY);
      dispatch({
        type: "INIT_FROM_STORAGE",
        payload: { chats: [], activeChatId: null },
      });
    }
  }, []);

  useEffect(() => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        chats: chatState.chatHistory,
        activeChatId: chatState.activeChatId,
      })
    );
  }, [chatState.chatHistory, chatState.activeChatId]);

  useEffect(() => {
    try {
      const seenVersion = localStorage.getItem(UPDATES_STORAGE_KEY);

      if (seenVersion !== UPDATES_VERSION){
        setUpdatesOpen(true);
        localStorage.setItem(UPDATES_STORAGE_KEY, UPDATES_VERSION);
      }
    } catch (err) {
      console.error("Failed to read updates version localStorage:", err);
    }
  })

  // -------------------------------------------------------------------------
  // Messaging
  // -------------------------------------------------------------------------

  const handleSendMessage = async (e) => {
    e.preventDefault();
    const trimmed = input.trim();

    if (!trimmed || isLoading || !accessToken || !chatState.activeChatId) return;

    const userMessage = {
      id: Date.now(),
      role: "user",
      content: trimmed,
      recommendations: [],
      timestamp: new Date().toISOString(),
    };

    dispatch({ type: "APPEND_USER_MESSAGE", message: userMessage });
    setInput("");
    setIsLoading(true);

    try {
      const data = await sendChatMessage(trimmed, accessToken);
      const recommendations = Array.isArray(data?.recommendations)
        ? data.recommendations.map(normalizeRecommendation)
        : [];

      const assistantMessage = {
        id: Date.now() + 1,
        role: "assistant",
        content: data?.assistant || "Here are a few picks.",
        recommendations,
        timestamp: new Date().toISOString(),
      };

      dispatch({ type: "APPEND_ASSISTANT_MESSAGE", message: assistantMessage });

      if (recommendations.length > 0) {
        await loadFilmBank();
      }
    } catch (err) {
      const errorMessage = {
        id: Date.now() + 2,
        role: "assistant",
        content: err?.message || "Something went wrong while getting recommendations.",
        recommendations: [],
        timestamp: new Date().toISOString(),
      };

      dispatch({ type: "APPEND_ASSISTANT_MESSAGE", message: errorMessage });
    } finally {
      setIsLoading(false);
    }
  };

  // -------------------------------------------------------------------------
  // Chat history
  // -------------------------------------------------------------------------

  const handleNewChat = () => {
    dispatch({ type: "NEW_CHAT" });
  };

  const handleChatSelect = (chatId) => {
    dispatch({ type: "SELECT_CHAT", chatId });
  };

  const handleDeleteChat = (chatId) => {
    dispatch({ type: "DELETE_CHAT", chatId });
  };

  // -------------------------------------------------------------------------
  // Auth guards
  // -------------------------------------------------------------------------

  if (isAuthenticating) {
    return (
      <div className="chat-container dark-mode">
        <div className="auth-loading">
          <p>Authenticating...</p>
        </div>
      </div>
    );
  }

  if (authError) {
    return (
      <div className="chat-container dark-mode">
        <div className="auth-error-container">
          <div className="error-message">{authError}</div>
          <button className="retry-button" onClick={() => window.location.reload()}>
            RETRY
          </button>
        </div>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <div className="chat-container dark-mode">
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="sidebar-actions">
            <button
              className="sidebar-action-button terminal-btn"
              onClick={() => setBankOpen(true)}
            >
              Film Bank
              {filmBankCount > 0 && <span className="bank-count">{filmBankCount}</span>}
            </button>
            <button
              className="sidebar-action-button terminal-btn"
              onClick={() => navigate("/stats")}
            >
              Stats
            </button>
          </div>
          <button className="new-chat-button terminal-btn" onClick={handleNewChat}>
            + New Chat
          </button>
        </div>

        <div className="chat-history">
          {chatState.chatHistory.map((chat) => (
            <div
              key={chat.id}
              className={`chat-history-item ${
                chat.id === chatState.activeChatId ? "active" : ""
              }`}
              onClick={() => handleChatSelect(chat.id)}
            >
              <div className="chat-history-row">
                <div className="history-title">{chat.title}</div>
                <button
                  className="chat-history-delete"
                  onClick={(e) => {
                    e.stopPropagation();
                    dispatch({ type: "OPEN_DELETE_MODAL", chat });
                  }}
                >
                  ×
                </button>
              </div>

              <div className="chat-date">
                {chat.createdAt
                  ? new Date(chat.createdAt).toLocaleDateString(undefined, {
                      month: "short",
                      day: "numeric",
                    })
                  : ""}
              </div>
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

      <main className="chat-main">
        <header className="chat-header">
          <h1 className="header-title">Film-Recommender {UPDATES_VERSION}</h1>

          <button
            type="button"
            className="updates-link-btn"
            onClick={() => setUpdatesOpen(true)}
          >
            Updates
          </button>
        </header>

        <div className="messages-container">
          {messages.map((m) => (
            <div key={m.id} className={`message-block ${m.role}`}>
              <div className={`log-line ${m.role}`}>
                <span className="log-prefix">
                  {m.role === "user" ? PROMPT : "ai@film:~#"}
                </span>
                <span className="log-text">{m.content}</span>
              </div>

              {m.role === "assistant" &&
                Array.isArray(m.recommendations) &&
                m.recommendations.length > 0 && (
                  <div className="chat-recommendations-grid">
                    {m.recommendations.map((film) => {
                      const movieLink = getMovieLink(film);

                      const card = (
                        <>
                          <div className="film-card-poster">
                            {film.poster ? (
                              <img src={film.poster} alt={film.title} />
                            ) : (
                              <div className="film-card-placeholder">
                                <span>{film.title.charAt(0)}</span>
                              </div>
                            )}
                          </div>

                          <div className="film-card-info">
                            <div className="film-card-title">{film.title}</div>
                            {film.year && <div className="film-card-year">{film.year}</div>}

                            {!!film.description && (
                              <div className="film-card-description">{film.description}</div>
                            )}

                            {!!film.why && (
                              <ul className="film-card-why">
                                {film.why
                                  .split(/[.•]\s+|(?<=\.)\s+/)
                                  .map((p) => p.trim())
                                  .filter(Boolean)
                                  .map((point, idx) => (
                                    <li key={idx}>{point}</li>
                                  ))}
                              </ul>
                            )}
                          </div>
                        </>
                      );

                      return movieLink ? (
                        <a
                          key={film.id}
                          href={movieLink}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="film-card"
                          title={`${film.title}${film.year ? ` (${film.year})` : ""}`}
                        >
                          {card}
                        </a>
                      ) : (
                        <div
                          key={film.id}
                          className="film-card"
                          title={`${film.title}${film.year ? ` (${film.year})` : ""}`}
                        >
                          {card}
                        </div>
                      );
                    })}
                  </div>
                )}
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
            <button
              type="submit"
              className="send-button"
              disabled={!input.trim() || isLoading}
            >
              ENTER
            </button>
          </form>
        </div>
      </main>

      {bankOpen && (
        <ModalShell
          title="FILM BANK"
          onClose={() => setBankOpen(false)}
          className="film-bank-modal"
        >
          {bankLoading ? (
            <div className="film-bank-empty">
              <p>Loading Film Bank...</p>
            </div>
          ) : bankError ? (
            <div className="film-bank-empty">
              <p>{bankError}</p>
            </div>
          ) : filmBank.length === 0 ? (
            <div className="film-bank-empty">
              <span className="film-bank-empty-icon">⬚</span>
              <p>Films recommended by the AI will appear here.</p>
            </div>
          ) : (
            <div className="film-bank-grid">
              {filmBank.map((film) => (
                <div
                  key={film.id}
                  className="film-card"
                  title={`${film.title}${film.year ? ` (${film.year})` : ""}`}
                >
                  <div className="film-card-poster">
                    {film.poster ? (
                      <img src={film.poster} alt={film.title} />
                    ) : (
                      <div className="film-card-placeholder">
                        <span>{film.title.charAt(0)}</span>
                      </div>
                    )}

                    <button
                      className="film-card-rate"
                      onClick={() => setFeedbackFilm(film)}
                      aria-label={`Rate ${film.title}`}
                    >
                      ★
                    </button>

                    <button
                      className="film-card-remove"
                      onClick={() => {
                        if (!film.movieId) return;
                        handleRemoveFromBank(film.movieId);
                      }}
                      aria-label={`Remove ${film.title}`}
                    >
                      ×
                    </button>
                  </div>

                  <div className="film-card-info">
                    <div className="film-card-title">{film.title}</div>
                    {film.year && <div className="film-card-year">{film.year}</div>}
                    {!!film.reason && (
                      <div className="film-card-description">{film.reason}</div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </ModalShell>
      )}

      {updatesOpen && (
        <UpdatesModal
          version={UPDATES_VERSION}
          updates={UPDATES_BULLETS}
          onClose={() => setUpdatesOpen(false)}
        />
      )}

      {feedbackFilm && (
        <FilmBankFeedbackModal
          film={feedbackFilm}
          token={accessToken}
          onDone={handleFeedbackDone}
          onClose={() => setFeedbackFilm(null)}
        />
      )}

      {chatState.deleteTarget && (
        <ConfirmDeleteModal
          title="DELETE CHAT"
          message={`Are you sure you want to delete "${chatState.deleteTarget.title}"?`}
          onCancel={() => dispatch({ type: "CLOSE_DELETE_MODAL" })}
          onConfirm={() => handleDeleteChat(chatState.deleteTarget.id)}
        />
      )}
    </div>
  );
};

export default Chat;