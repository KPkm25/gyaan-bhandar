import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "./App.css";

const API_BASE = "http://localhost:5000";

// ── Copy Button ───────────────────────────────────────────────
function CopyButton({ text, small = false }) {
  const [copied, setCopied] = useState(false);
  const handle = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <button className={`copy-btn ${small ? "copy-btn--small" : ""} ${copied ? "copy-btn--copied" : ""}`} onClick={handle} title="Copy">
      {copied ? (
        <>
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path d="M2 6.5l2.5 2.5 5.5-5.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          {!small && "Copied!"}
        </>
      ) : (
        <>
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <rect x="4" y="4" width="7" height="7" rx="1" stroke="currentColor" strokeWidth="1.3"/>
            <path d="M8 4V2.5a.5.5 0 0 0-.5-.5h-5a.5.5 0 0 0-.5.5v5a.5.5 0 0 0 .5.5H4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
          </svg>
          {!small && "Copy"}
        </>
      )}
    </button>
  );
}

// ── Source Tag ────────────────────────────────────────────────
function SourceTag({ source, page }) {
  const filename = source?.split(/[/\\]/).pop() || source;
  return (
    <span className="source-tag">
      <svg width="10" height="12" viewBox="0 0 10 12" fill="none">
        <path d="M1 1h5.5l2.5 2.5V11H1V1z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/>
        <path d="M6 1v3h3" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/>
      </svg>
      {filename}
      {page && <span className="source-tag__page">p.{page}</span>}
    </span>
  );
}

// ── Chunk Card ────────────────────────────────────────────────
function ChunkCard({ chunk, index }) {
  const [expanded, setExpanded] = useState(false);
  const limit = 160;
  const truncated = chunk.text.length > limit;
  return (
    <div className="chunk-card" style={{ "--delay": `${index * 55}ms` }}>
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
          {expanded ? "▲ less" : "▼ more"}
        </button>
      )}
    </div>
  );
}

// ── Typing Dots ───────────────────────────────────────────────
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

// ── Confidence Badge ──────────────────────────────────────────
function ConfidenceBadge({ score }) {
  const pct = Math.round(score * 100);
  const isLow = score < 0.35;
  const isMid = score >= 0.35 && score < 0.6;
  return (
    <span className={`confidence-badge ${isLow ? "confidence-badge--low" : isMid ? "confidence-badge--mid" : "confidence-badge--high"}`}>
      <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
        <circle cx="5" cy="5" r="4" stroke="currentColor" strokeWidth="1.2"/>
        <path d="M5 3v2.5L6.5 7" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
      </svg>
      {pct}% confidence
    </span>
  );
}

// ── Chat Message ──────────────────────────────────────────────
function ChatMessage({ msg, onForce }) {
  const isUser = msg.role === "user";
  return (
    <div className={`message message--${isUser ? "user" : "ai"}`}>
      {!isUser && <div className="message__avatar">AI</div>}
      <div className="message__content">
        <div className={`message__bubble ${isUser ? "message__bubble--user" : "message__bubble--ai"}`}>
          {isUser ? (
            <p className="message__text">{msg.text}</p>
          ) : (
            <div className="message__text">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  code({ node, inline, className, children, ...props }) {
                    const code = String(children).replace(/\n$/, "");
                    const isBlock = !inline && className?.startsWith("language-");
                    if (!isBlock) {
                      return <code className="inline-code" {...props}>{children}</code>;
                    }
                    return (
                      <div className="code-block">
                        <div className="code-block__header">
                          <span className="code-block__lang">
                            {className.replace("language-", "")}
                          </span>
                          <CopyButton text={code} small />
                        </div>
                        <pre><code className={className} {...props}>{children}</code></pre>
                      </div>
                    );
                  }
                }}
              >{msg.text}</ReactMarkdown>
            </div>
          )}
          {/* Confidence badge shown on all AI messages */}
          {!isUser && msg.confidence !== undefined && (
            <div className="message__meta">
              <ConfidenceBadge score={msg.confidence} />
            </div>
          )}
        </div>

        {/* "Ask anyway" button — only shown when backend signals can_force */}
        {msg.canForce && (
          <button
            className="force-btn"
            onClick={() => onForce(msg.originalQuery)}
          >
            <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
              <circle cx="6.5" cy="6.5" r="5.5" stroke="currentColor" strokeWidth="1.3"/>
              <path d="M4.5 6.5h4M7 4.5l2 2-2 2" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            Generate best-effort answer anyway
          </button>
        )}

        {/* GitHub issue link — shown on low confidence responses */}
        {msg.issueUrl && (
          <a className="issue-link" href={msg.issueUrl} target="_blank" rel="noreferrer">
            <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
              <circle cx="6.5" cy="6.5" r="5.5" stroke="currentColor" strokeWidth="1.3"/>
              <path d="M6.5 4v3M6.5 8.5v.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
            </svg>
            Documentation gap flagged — GitHub issue created
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
              <path d="M2 8L8 2M8 2H4M8 2v4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </a>
        )}

        {msg.chunks && msg.chunks.length > 0 && (
          <div className="context-panel">
            <div className="context-panel__label">
              <svg width="11" height="11" viewBox="0 0 11 11" fill="none">
                <circle cx="5.5" cy="5.5" r="4.5" stroke="currentColor" strokeWidth="1.2"/>
                <path d="M5.5 4.5v3M5.5 3.2v.3" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
              </svg>
              Retrieved context
            </div>
            <div className="context-panel__chunks">
              {msg.chunks.map((c, i) => <ChunkCard key={i} chunk={c} index={i} />)}
            </div>
          </div>
        )}
      </div>
      {isUser && <div className="message__avatar message__avatar--user">U</div>}
    </div>
  );
}

// ── Documents Panel ───────────────────────────────────────────
function DocumentsPanel({ onIndexUpdated }) {
  const [docs, setDocs] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [collapsed, setCollapsed] = useState(false);
  const fileRef = useRef(null);

  const fetchDocs = () => {
    fetch(`${API_BASE}/documents`)
      .then(r => r.json())
      .then(setDocs)
      .catch(() => {});
  };

  useEffect(() => { fetchDocs(); }, []);

  const handleUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await fetch(`${API_BASE}/upload`, { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) {
        setUploadError(data.error || "Upload failed");
      } else {
        fetchDocs();
        onIndexUpdated();
      }
    } catch {
      setUploadError("Upload failed — is the backend running?");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const handleDelete = async (name) => {
    if (!window.confirm(`Delete "${name}"?`)) return;
    await fetch(`${API_BASE}/documents/${encodeURIComponent(name)}`, { method: "DELETE" });
    fetchDocs();
    onIndexUpdated();
  };

  return (
    <div className={`docs-panel ${collapsed ? "docs-panel--collapsed" : ""}`}>
      <div className="docs-panel__header" onClick={() => setCollapsed(!collapsed)}>
        <span className="docs-panel__title">
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
            <path d="M2 2h6l3 3v6H2V2z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/>
            <path d="M8 2v3h3" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/>
          </svg>
          Documents
          <span className="docs-panel__count">{docs.length}</span>
        </span>
        <div className="docs-panel__actions" onClick={e => e.stopPropagation()}>
          <button
            className="docs-panel__upload-btn"
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
          >
            {uploading ? (
              <span className="docs-panel__spinner" />
            ) : (
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                <path d="M6 9V3M3 6l3-3 3 3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            )}
            {uploading ? "Uploading…" : "Upload"}
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.txt,.docx"
            style={{ display: "none" }}
            onChange={handleUpload}
          />
        </div>
        <svg className="docs-panel__chevron" width="12" height="12" viewBox="0 0 12 12" fill="none">
          <path d="M3 4.5l3 3 3-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </div>

      {!collapsed && (
        <div className="docs-panel__body">
          {uploadError && <p className="docs-panel__error">{uploadError}</p>}
          {docs.length === 0 ? (
            <p className="docs-panel__empty">No documents yet — upload a PDF, TXT, or DOCX</p>
          ) : (
            docs.map(doc => (
              <div key={doc.name} className="docs-panel__item">
                <div className="docs-panel__item-info">
                  <span className="docs-panel__item-name">{doc.name}</span>
                  <span className="docs-panel__item-meta">{doc.size_kb} KB · {doc.modified}</span>
                </div>
                <button className="docs-panel__delete" onClick={() => handleDelete(doc.name)} title="Delete">
                  <svg width="11" height="11" viewBox="0 0 11 11" fill="none">
                    <path d="M2 2l7 7M9 2L2 9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                  </svg>
                </button>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

// ── Sidebar ───────────────────────────────────────────────────
function Sidebar({ sessions, activeSession, onNew, onLoad, onDelete }) {
  return (
    <div className="sidebar">
      <div className="sidebar__brand">
        <div className="sidebar__logo">
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <circle cx="7.5" cy="7.5" r="5" stroke="currentColor" strokeWidth="1.8"/>
            <path d="M11.5 11.5L16 16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
            <path d="M5 7.5h5M7.5 5v5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
          </svg>
        </div>
        <div>
          <p className="sidebar__app-name">Gyaan Bhandar</p>
          <p className="sidebar__app-sub">RAG Assistant</p>
        </div>
      </div>

      <button className="sidebar__new-btn" onClick={onNew}>
        <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
          <path d="M6.5 2v9M2 6.5h9" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
        </svg>
        New Chat
      </button>

      <p className="sidebar__section-label">Recent</p>

      <div className="sidebar__list">
        {sessions.length === 0 && (
          <p className="sidebar__empty">No chats yet</p>
        )}
        {sessions.map(s => (
          <div
            key={s.id}
            className={`sidebar__item ${activeSession?.id === s.id ? "sidebar__item--active" : ""}`}
            onClick={() => onLoad(s)}
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
              <path d="M1 2.5h10v7a.5.5 0 0 1-.5.5h-9A.5.5 0 0 1 1 9.5v-7z" stroke="currentColor" strokeWidth="1.2"/>
              <path d="M4 2.5V1.5a.5.5 0 0 1 .5-.5h3a.5.5 0 0 1 .5.5v1" stroke="currentColor" strokeWidth="1.2"/>
            </svg>
            <span className="sidebar__item-title">{s.title}</span>
            <button
              className="sidebar__delete"
              onClick={e => { e.stopPropagation(); onDelete(s.id); }}
              title="Delete"
            >
              <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                <path d="M1.5 1.5l7 7M8.5 1.5l-7 7" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
              </svg>
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main App ──────────────────────────────────────────────────
export default function App() {
  const [messages, setMessages] = useState([
    { role: "ai", text: "Hello! Upload a document and ask me anything about it." }
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [health, setHealth] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [activeSession, setActiveSession] = useState(null);

  const chatEndRef = useRef(null);
  const textareaRef = useRef(null);

  const refreshHealth = () => {
    fetch(`${API_BASE}/health`)
      .then(r => r.json())
      .then(setHealth)
      .catch(() => setHealth(null));
  };

  useEffect(() => {
    refreshHealth();
    fetch(`${API_BASE}/sessions`)
      .then(r => r.json())
      .then(setSessions)
      .catch(() => {});
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

  const newSession = async () => {
    const res = await fetch(`${API_BASE}/sessions`, { method: "POST" });
    const session = await res.json();
    setSessions(s => [session, ...s]);
    setActiveSession(session);
    setMessages([{ role: "ai", text: "New chat started! Ask me anything about your documents." }]);
  };

  const loadSession = async (session) => {
    const res = await fetch(`${API_BASE}/sessions/${session.id}`);
    const data = await res.json();
    setActiveSession(data);
    const restored = data.messages.flatMap(m => ([
      { role: "user", text: m.user },
      { role: "ai", text: m.assistant, chunks: m.chunks, confidence: m.confidence, issueUrl: m.issue_url }
    ]));
    setMessages(
      restored.length > 0
        ? restored
        : [{ role: "ai", text: "No messages in this session yet." }]
    );
  };

  const deleteSession = async (sessionId) => {
    await fetch(`${API_BASE}/sessions/${sessionId}`, { method: "DELETE" });
    setSessions(s => s.filter(s => s.id !== sessionId));
    if (activeSession?.id === sessionId) {
      setActiveSession(null);
      setMessages([{ role: "ai", text: "Hello! Upload a document and ask me anything about it." }]);
    }
  };

  const send = async () => {
    const q = input.trim();
    if (!q || loading) return;

    // Auto-create session if none active
    let sessionId = activeSession?.id;
    if (!sessionId) {
      const res = await fetch(`${API_BASE}/sessions`, { method: "POST" });
      const session = await res.json();
      setSessions(s => [session, ...s]);
      setActiveSession(session);
      sessionId = session.id;
    }

    setMessages(m => [...m, { role: "user", text: q }]);
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q, session_id: sessionId })
      });
      const data = await res.json();
      if (!res.ok) {
        setMessages(m => [...m, { role: "ai", text: `⚠️ ${data.error}` }]);
      } else {
        setMessages(m => [...m, {
          role: "ai",
          text: data.answer,
          chunks: data.chunks,
          confidence: data.confidence,
          issueUrl: data.issue_url,
          canForce: data.can_force || false,
          originalQuery: q
        }]);
        setSessions(prev => prev.map(s =>
          s.id === sessionId
            ? { ...s, title: q.slice(0, 45) + (q.length > 45 ? "…" : "") }
            : s
        ));
      }
    } catch {
      setMessages(m => [...m, { role: "ai", text: "⚠️ Could not reach the backend. Make sure Flask is running on port 5000." }]);
    } finally {
      setLoading(false);
    }
  };

  const forceSend = async (originalQuery) => {
    // Disable the canForce button on the previous message
    setMessages(m => m.map(msg =>
      msg.canForce ? { ...msg, canForce: false } : msg
    ));

    setMessages(m => [...m, { role: "user", text: "Generate answer anyway →" }]);
    setLoading(true);

    let sessionId = activeSession?.id;

    try {
      const res = await fetch(`${API_BASE}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: originalQuery,
          session_id: sessionId,
          force_answer: true
        })
      });
      const data = await res.json();
      if (!res.ok) {
        setMessages(m => [...m, { role: "ai", text: `⚠️ ${data.error}` }]);
      } else {
        setMessages(m => [...m, {
          role: "ai",
          text: data.answer,
          chunks: data.chunks,
          confidence: data.confidence,
          issueUrl: data.issue_url,
          canForce: false
        }]);
      }
    } catch {
      setMessages(m => [...m, { role: "ai", text: "⚠️ Could not reach the backend." }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <Sidebar
        sessions={sessions}
        activeSession={activeSession}
        onNew={newSession}
        onLoad={loadSession}
        onDelete={deleteSession}
      />

      <div className="chat-area">
        <header className="header">
          <div className="header__left">
            <h1 className="header__title">
              {activeSession?.title && activeSession.title !== "New Chat"
                ? activeSession.title
                : "Ask your documents"}
            </h1>
          </div>
          <div className={`status-badge ${health ? "status-badge--online" : "status-badge--offline"}`}>
            <span className="status-pulse" />
            {health
              ? `${health.chunks_loaded} chunks · ${health.documents} doc${health.documents !== 1 ? "s" : ""}`
              : "Backend offline"}
          </div>
        </header>

        <DocumentsPanel onIndexUpdated={refreshHealth} />

        <main className="chat">
          <div className="chat__inner">
            {messages.map((m, i) => <ChatMessage key={i} msg={m} onForce={forceSend} />)}
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
              placeholder={health?.chunks_loaded > 0
                ? "Ask anything about your documents…"
                : "Upload a document to get started…"}
              onChange={e => { setInput(e.target.value); autoResize(); }}
              onKeyDown={e => {
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
              }}
            />
            <button
              className="composer__send"
              onClick={send}
              disabled={!input.trim() || loading}
              aria-label="Send"
            >
              <svg width="17" height="17" viewBox="0 0 17 17" fill="none">
                <path d="M8.5 13V4M4 8.5l4.5-4.5 4.5 4.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
          </div>
          <p className="composer__hint">Enter to send · Shift+Enter for new line</p>
        </footer>
      </div>
    </div>
  );
}