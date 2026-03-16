import { useState, useRef, useEffect } from "react";
import ReactMarkdown from 'react-markdown';
import "./App.css";

const API_BASE = "http://localhost:5000";

// ── Sub-components ──────────────────────────────────────────────

function StatusBadge({ health }) {
  return (
    <div className={`status-badge ${health ? "status-badge--online" : "status-badge--offline"}`}>
      <span className="status-pulse" />
      {health ? `${health.chunks_loaded} chunks loaded` : "Backend offline"}
    </div>
  );
}

function SourceTag({ source, page }) {
  const filename = source?.split(/[/\\]/).pop() || source;
  return (
    <span className="source-tag">
      <svg width="11" height="13" viewBox="0 0 11 13" fill="none">
        <path d="M1 1h6l3 3v8H1V1z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/>
        <path d="M7 1v3h3" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/>
        <path d="M3 6h5M3 8h4M3 10h3" stroke="currentColor" strokeWidth="1" strokeLinecap="round"/>
      </svg>
      {filename}
      {page && <span className="source-tag__page">pg. {page}</span>}
    </span>
  );
}

function ChunkCard({ chunk, index }) {
  const [expanded, setExpanded] = useState(false);
  const limit = 180;
  const truncated = chunk.text.length > limit;

  return (
    <div className="chunk-card" style={{ "--delay": `${index * 60}ms` }}>
      <div className="chunk-card__header">
        <span className="chunk-card__index">#{String(index + 1).padStart(2, "0")}</span>
        <SourceTag source={chunk.source} page={chunk.page} />
      </div>
      <p className="chunk-card__body">
        {expanded ? chunk.text : chunk.text.slice(0, limit)}
        {truncated && !expanded && "…"}
      </p>
      {truncated && (
        <button className="chunk-card__toggle" onClick={() => setExpanded(!expanded)}>
          {expanded ? "▲ collapse" : "▼ expand"}
        </button>
      )}
    </div>
  );
}

function TypingDots() {
  return (
    <div className="message message--ai">
      <div className="message__avatar">AI</div>
      <div className="message__bubble message__bubble--typing">
        <span /><span /><span />
      </div>
    </div>
  );
}

function ChatMessage({ msg }) {
  const isUser = msg.role === "user";
  return (
    <div className={`message message--${isUser ? "user" : "ai"}`}>
      {!isUser && <div className="message__avatar">AI</div>}
      <div className="message__content">
        <div className={`message__bubble ${isUser ? "message__bubble--user" : "message__bubble--ai"}`}>
          <div className="message__text">
            <ReactMarkdown>{msg.text}</ReactMarkdown>
          </div>        
        </div>
        {msg.chunks && msg.chunks.length > 0 && (
          <div className="context-panel">
            <div className="context-panel__label">
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                <circle cx="6" cy="6" r="5" stroke="currentColor" strokeWidth="1.2"/>
                <path d="M6 5v4M6 3.5v.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
              </svg>
              Retrieved context
            </div>
            <div className="context-panel__chunks">
              {msg.chunks.map((c, i) => (
                <ChunkCard key={i} chunk={c} index={i} />
              ))}
            </div>
          </div>
        )}
      </div>
      {isUser && <div className="message__avatar message__avatar--user">U</div>}
    </div>
  );
}

// ── Main App ─────────────────────────────────────────────────────

export default function App() {
  const [messages, setMessages] = useState([
    {
      role: "ai",
      text: "Hello! I'm your document assistant. Ask me anything about the loaded PDF and I'll retrieve the most relevant context to answer you.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [health, setHealth] = useState(null);
  const chatEndRef = useRef(null);
  const textareaRef = useRef(null);

  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const autoResize = () => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
  };

  const send = async () => {
    const q = input.trim();
    if (!q || loading) return;

    setMessages((m) => [...m, { role: "user", text: q }]);
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q }),
      });
      const data = await res.json();
      setMessages((m) => [...m, { role: "ai", text: data.answer, chunks: data.chunks }]);
    } catch {
      setMessages((m) => [
        ...m,
        { role: "ai", text: "⚠️ Could not reach the backend. Make sure Flask is running on port 5000." },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <header className="header">
        <div className="header__brand">
          <div className="header__logo">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <circle cx="8" cy="8" r="5.5" stroke="currentColor" strokeWidth="1.8"/>
              <path d="M12.5 12.5L17 17" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
              <path d="M5.5 8h5M8 5.5v5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
            </svg>
          </div>
          <div>
            <h1 className="header__title">RAG Explorer</h1>
            <p className="header__subtitle">FAISS · Groq · LLaMA 3.1</p>
          </div>
        </div>
        <StatusBadge health={health} />
      </header>

      <main className="chat">
        <div className="chat__inner">
          {messages.map((m, i) => (
            <ChatMessage key={i} msg={m} />
          ))}
          {loading && <TypingDots />}
          <div ref={chatEndRef} />
        </div>
      </main>

      <footer className="composer">
        <div className="composer__box">
          <textarea
            ref={textareaRef}
            className="composer__input"
            rows={1}
            value={input}
            placeholder="Ask anything about the document…"
            onChange={(e) => { setInput(e.target.value); autoResize(); }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
            }}
          />
          <button
            className="composer__send"
            onClick={send}
            disabled={!input.trim() || loading}
            aria-label="Send"
          >
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
              <path d="M9 14V4M4 9l5-5 5 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
        </div>
        <p className="composer__hint">Enter to send · Shift+Enter for new line</p>
      </footer>
    </div>
  );
}