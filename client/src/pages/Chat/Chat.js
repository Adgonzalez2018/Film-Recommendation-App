import React, { useEffect, useMemo, useRef, useState } from "react";
import "./Chat.css";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import { apiFetch } from "../../api/client";

function extractErrorMessage(fallback, data) {
  if (!data) return fallback;
  if (typeof data === "string") return data;

  if (typeof data === "object") {
    if (typeof data.error === "string" && data.error.trim()) return data.error.trim();
    if (typeof data.detail === "string" && data.detail.trim()) return data.detail.trim();

    for (const value of Object.values(data)) {
      if (Array.isArray(value) && typeof value[0] === "string") return value[0];
      if (typeof value === "string" && value.trim()) return value.trim();
    }
  }

  return fallback;
}

const STORAGE_KEY = "filmrec_chats"


async function sendChatMessage(message, token) {
  const res = await apiFetch("/api/chat/recommend/", {
    token,
    method: "POST",
    body: { message },
  });

  const data = await res.json().catch(() => ({}));

  if (!res.ok) {
    throw new Error(extractErrorMessage("Chat request failed.", data));
  }

  return data;
}

async function fetchFilmBank(token, page = 1, pageSize = 50) {
  const res = await apiFetch(`/api/film-bank/?page=${page}&page_size=${pageSize}`, {
    token,
    method: "GET",
  });

  const data = await res.json().catch(() => ({}));

  if (!res.ok) {
    throw new Error(extractErrorMessage("Failed to load film bank.", data));
  }

  return data;
}

async function deleteFilmBankMovie(movieId, token) {
  const res = await apiFetch(`/api/film-bank/${movieId}/`, {
    token,
    method: "DELETE",
  });

  const data = await res.json().catch(() => ({}));

  if (!res.ok) {
    throw new Error(extractErrorMessage("Failed to remove film from bank.", data));
  }

  return data;
}

function normalizeFilmBankItem(item) {
  return {
    id: item?.id,
    movieId: item?.id,
    title: item?.title || "Untitled",
    year: item?.year ?? null,
    poster: item?.poster_url || null,
    tmdbId: item?.tmdb_id ?? null,
    description: item?.description || "",
    avgRating: item?.avg_rating ?? null,
    reason: item?.reason || "",
    queryText: item?.query_text || "",
    createdAt: item?.created_at || null,
  };
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
  };
}

const INITIAL_ASSISTANT_MESSAGE = {
  id: 1,
  role: "assistant",
  content:
    "Hello! I'm your film recommendation AI. I know all about your Letterboxd viewing history. What would you like to know?",
  recommendations: [],
  timestamp: new Date(),
};

const Chat = () => {
  const navigate = useNavigate();
  const { accessToken, isAuthenticating, authError } = useAuth();

  const [messages, setMessages] = useState([INITIAL_ASSISTANT_MESSAGE]);
  const [input, setInput] = useState("");
  const [chatHistory, setChatHistory] = useState([]);
  const [activeChatId, setActiveChatId] = useState(null);

  const [isLoading, setIsLoading] = useState(false);
  const [filmBank, setFilmBank] = useState([]);
  const [bankOpen, setBankOpen] = useState(false);
  const [bankLoading, setBankLoading] = useState(false);
  const [bankError, setBankError] = useState("");

  const messagesEndRef = useRef(null);
  const PROMPT = "user@film:~$";

  const filmBankCount = useMemo(() => filmBank.length, [filmBank]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

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

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  useEffect(() => {
    loadFilmBank();
  }, [accessToken]);

  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      const parsed = JSON.parse(saved);
      setChatHistory(parsed.chats || []);
      setActiveChatId(parsed.activeChatId);

      const activeChat = parsed.chats?.find(c => c.id == parsed.activeChatId);
      setMessages(activeChat?.messages || [INITIAL_ASSISTANT_MESSAGE]);
    } else {
      // first time user
      const initialChat = {
        id: Date.now(),
        title: "New Conversation",
        messages: [INITIAL_ASSISTANT_MESSAGE],
        createdAt: new Date(),
      };
      setChatHistory([initialChat]);
      setActiveChatId(initialChat.id);
      setMessages(initialChat.messages);
    }
  }, []);

  useEffect(() => {
    if (!activeChatId) return;
    
    const updatedChats = chatHistory.map(chat =>
      chat.id === activeChatId ? { ...chat, messages } : chat
    );

    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        chats: updatedChats,
        activeChatId,
      })
    );

  }, [messages, chatHistory, activeChatId]);
  const handleRemoveFromBank = async (movieId) => {
    if (!movieId || !accessToken) return;

    const prev = filmBank;
    setFilmBank((current) => current.filter((film) => film.movieId !== movieId));

    try {
      await deleteFilmBankMovie(movieId, accessToken);
    } catch (err) {
      setFilmBank(prev);
      setBankError(err?.message || "Failed to remove film.");
    }
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();

    const trimmed = input.trim();
    if (!trimmed || isLoading || !accessToken) return;

    const userMessage = {
      id: Date.now(),
      role: "user",
      content: trimmed,
      recommendations: [],
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    setChatHistory(prev => 
      prev.map(chat =>
        chat.id === activeChatId && chat.title === "New conversation"
        ? { ...chat, title: trimmed.slice(0,30) }
        : chat
      )
    );
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
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, assistantMessage]);

      if (recommendations.length > 0) {
        await loadFilmBank();
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 2,
          role: "assistant",
          content: err?.message || "Something went wrong while getting recommendations.",
          recommendations: [],
          timestamp: new Date(),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleNewChat = () => {
    const newChat = {
      id: Date.now(),
      title: "New Conversation",
      messages: [INITIAL_ASSISTANT_MESSAGE],
      createdAt: new Date(),
    };

    setChatHistory(prev => [newChat, ...prev]);
    setActiveChatId(newChat.id);
    setMessages(newChat.messages);
  };

  const handleChatSelect = (chatId) => {
    const selected = chatHistory.find(c => c.id === chatId);
    if (!selected) return;

    setActiveChatId(chatId);
    setMessages(selected.messages);
  };

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

  return (
    <div className="chat-container dark-mode">
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="sidebar-actions">
            <button className="sidebar-action-button" onClick={() => setBankOpen(true)}>
              Film Bank
              {filmBankCount > 0 && <span className="bank-count">{filmBankCount}</span>}
            </button>
            <button className="sidebar-action-button" onClick={() => navigate("/stats")}>
              Stats
            </button>
          </div>
          <button className="new-chat-button" onClick={handleNewChat}>
            + New Chat
          </button>
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

      <main className="chat-main">
        <header className="chat-header">
          <h1 className="header-title">Film-Recommender v1.1</h1>
        </header>

        <div className="messages-container">
          {messages.map((m) => (
            <div key={m.id} className={`message-block ${m.role}`}>
              <div className={`log-line ${m.role}`}>
                <span className="log-prefix">{m.role === "user" ? PROMPT : "ai@film:~#"}</span>
                <span className="log-text">{m.content}</span>
              </div>

              {m.role === "assistant" && Array.isArray(m.recommendations) && m.recommendations.length > 0 && (
                <div className="chat-recommendations-grid">
                  {m.recommendations.map((film) => (
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
                              .map((point) => point.trim())
                              .filter(Boolean)
                              .map((point, idx) => (
                                <li key={idx}>{point}</li>
                              ))}
                          </ul>
                        )}
                      </div>
                    </div>
                  ))}
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
            <button type="submit" className="send-button" disabled={!input.trim() || isLoading}>
              ENTER
            </button>
          </form>
        </div>
      </main>

      {bankOpen && (
        <div className="film-bank-overlay" onClick={() => setBankOpen(false)}>
          <div className="film-bank-modal" onClick={(e) => e.stopPropagation()}>
            <div className="film-bank-header">
              <span className="film-bank-title">FILM BANK</span>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <span className="film-bank-count">{filmBankCount} saved</span>
                <button className="film-bank-close" onClick={() => setBankOpen(false)}>
                  ×
                </button>
              </div>
            </div>

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
                        className="film-card-remove"
                        onClick={() => handleRemoveFromBank(film.movieId)}
                        aria-label={`Remove ${film.title}`}
                      >
                        ×
                      </button>
                    </div>

                    <div className="film-card-info">
                      <div className="film-card-title">{film.title}</div>
                      {film.year && <div className="film-card-year">{film.year}</div>}
                      {!!film.reason && <div className="film-card-description">{film.reason}</div>}
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