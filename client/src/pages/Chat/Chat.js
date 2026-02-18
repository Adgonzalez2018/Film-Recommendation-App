// filepath: /Users/adgonzalez2018/Desktop/Agent/Film-Recommendation-App/client/src/pages/Chat/Chat.js
import React, { useState, useRef, useEffect } from "react";
import "./Chat.css";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import AuthForm from "../Auth/components/AuthForm";

const Chat = ({ onNavigate }) => {
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
  const [isDarkMode, setIsDarkMode] = useState(true);
  const [isLoading, setIsLoading] = useState(false);

  const messagesEndRef = useRef(null);
  const username = localStorage.getItem("username") || "User";

  // Auto-scroll to bottom when new messages arrive
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMessage = {
      id: messages.length + 1,
      role: "user",
      content: input,
      timestamp: new Date(),
    };

    setMessages([...messages, userMessage]);
    setInput("");
    setIsLoading(true);

    setTimeout(() => {
      const aiMessage = {
        id: messages.length + 2,
        role: "assistant",
        content:
          "This is a placeholder response. Soon I'll be powered by your actual AI backend!",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, aiMessage]);
      setIsLoading(false);
    }, 1000);
  };

  const handleNewChat = () => {
    const newChat = {
      id: chatHistory.length + 1,
      title: "New conversation",
      date: "Today",
      active: true,
    };

    const updatedHistory = chatHistory.map((chat) => ({
      ...chat,
      active: false,
    }));
    setChatHistory([newChat, ...updatedHistory]);

    setMessages([
      {
        id: 1,
        role: "assistant",
        content:
          "Hello! I'm your film recommendation AI. What would you like to know?",
        timestamp: new Date(),
      },
    ]);
  };

  const handleChatSelect = (chatId) => {
    const updatedHistory = chatHistory.map((chat) => ({
      ...chat,
      active: chat.id === chatId,
    }));
    setChatHistory(updatedHistory);
  };

  const toggleTheme = () => {
    setIsDarkMode(!isDarkMode);
  };

  // Show loading screen while authenticating
  if (isAuthenticating) {
    return (
      <div className="chat-container dark-mode">
        <div className="auth-loading">
          <p>Authenticating...</p>
        </div>
      </div>
    );
  }

  // Show error screen if auth failed with server error
  if (authError) {
    return (
      <div className="chat-container dark-mode">
        <div className="auth-error-container">
          <div className="error-message">{authError}</div>
          <button 
            className="retry-button"
            onClick={() => window.location.reload()}
          >
            RETRY
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-container dark-mode">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-header">
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

        {/* Profile section at bottom */}
        <div className="profile-section">
          <div className="profile-avatar">
            {username.charAt(0).toUpperCase()}
          </div>
          <div className="profile-info">
            <div className="profile-name">{username}</div>
            <div className="profile-email">Letterboxd User</div>
          </div>
        </div>
      </aside>

      {/* Main chat area */}
      <main className="chat-main">
        <header className="chat-header">
          <h1 className="header-title">Film-Recommender v0.1</h1>
          <button className="stats-button" onClick={() => navigate("/stats")}>
            Statistics
          </button>
        </header>

        {/* Messages */}
        <div className="messages-container">
          {messages.map((m) => (
            <div key={m.id} className={`log-line ${m.role}`}>
              <span className="log-prefix">
                {m.role === "user"
                  ? `${username.toLowerCase()}@film:~$`
                  : "ai@film:~#"}
              </span>
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

        {/* Input area */}
        <div className="input-container">
          <form onSubmit={handleSendMessage} className="input-form">
            <span className="prompt-label">
              {username.toLowerCase()}@film:~$
            </span>

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
              disabled={!input.trim()}
            >
              ENTER
            </button>
          </form>
        </div>
      </main>
    </div>
  );
};

export default Chat;