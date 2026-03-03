import { useState, useEffect, useCallback, useRef } from "react";

const API = "http://localhost:8000";

const COLORS = {
  bg: "#0a0e17",
  surface: "#111827",
  border: "#1e293b",
  borderActive: "#3b82f6",
  text: "#e2e8f0",
  textMuted: "#64748b",
  textDim: "#475569",
  accent: "#3b82f6",
  accentGlow: "rgba(59, 130, 246, 0.15)",
  success: "#10b981",
  successGlow: "rgba(16, 185, 129, 0.12)",
  danger: "#ef4444",
  dangerGlow: "rgba(239, 68, 68, 0.12)",
  warning: "#f59e0b",
  warningGlow: "rgba(245, 158, 11, 0.12)",
};

function StatusDot({ ok }) {
  const color = ok ? COLORS.success : COLORS.danger;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      <span style={{ width: 8, height: 8, borderRadius: "50%", background: color, boxShadow: `0 0 8px ${color}`, animation: "pulse 2s infinite" }} />
      <span style={{ color, fontSize: 13, fontWeight: 500, textTransform: "uppercase", letterSpacing: 1 }}>
        {ok ? "connected" : "offline"}
      </span>
    </span>
  );
}

function Spinner({ size = 14 }) {
  return (
    <span style={{ width: size, height: size, border: `2px solid #fff3`, borderTopColor: "#fff", borderRadius: "50%", animation: "spin 0.8s linear infinite", display: "inline-block" }} />
  );
}

function MessageBubble({ msg }) {
  const isHuman = msg.type === "human";
  return (
    <div style={{ display: "flex", justifyContent: isHuman ? "flex-end" : "flex-start", marginBottom: 12, animation: "fadeIn 0.3s ease" }}>
      <div
        style={{
          maxWidth: "85%", padding: "12px 16px",
          borderRadius: isHuman ? "14px 14px 4px 14px" : "14px 14px 14px 4px",
          background: isHuman ? COLORS.accent : COLORS.surface,
          border: isHuman ? "none" : `1px solid ${COLORS.border}`,
          color: COLORS.text, fontSize: 14, lineHeight: 1.65,
          whiteSpace: "pre-wrap", wordBreak: "break-word",
        }}
      >
        {msg.content}
      </div>
    </div>
  );
}

function ThreadItem({ thread, active, onClick }) {
  const updated = thread.updated_at ? new Date(thread.updated_at).toLocaleTimeString() : "";
  return (
    <button
      onClick={onClick}
      style={{
        width: "100%", padding: "10px 14px",
        background: active ? COLORS.accentGlow : "transparent",
        border: "none", borderLeft: active ? `2px solid ${COLORS.accent}` : "2px solid transparent",
        cursor: "pointer", textAlign: "left", transition: "all 0.15s",
      }}
    >
      <div style={{ fontSize: 13, fontWeight: active ? 600 : 400, color: active ? COLORS.text : COLORS.textMuted, fontFamily: "'JetBrains Mono', monospace" }}>
        {thread.thread_id.slice(0, 8)}
      </div>
      <div style={{ fontSize: 11, color: COLORS.textDim, marginTop: 2 }}>{updated}</div>
    </button>
  );
}

export default function DocVerifyDashboard() {
  const [connected, setConnected] = useState(false);
  const [threads, setThreads] = useState([]);
  const [activeThread, setActiveThread] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);
  const [assistantId, setAssistantId] = useState(null);
  const messagesEnd = useRef(null);

  useEffect(() => { messagesEnd.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const init = useCallback(async () => {
    try {
      const r = await fetch(`${API}/assistants/search`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ graph_id: "agent" }),
      });
      if (!r.ok) throw new Error();
      const data = await r.json();
      if (data.length > 0) setAssistantId(data[0].assistant_id);
      setConnected(true);
      setError(null);
    } catch {
      setConnected(false);
      setError("Cannot connect to Aegra at " + API);
    }
  }, []);

  useEffect(() => { init(); }, [init]);

  const loadThreads = useCallback(async () => {
    try {
      const r = await fetch(`${API}/threads/search`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ limit: 20 }),
      });
      if (r.ok) setThreads(await r.json());
    } catch {}
  }, []);

  useEffect(() => { if (connected) loadThreads(); }, [connected, loadThreads]);

  const loadMessages = useCallback(async (threadId) => {
    try {
      const r = await fetch(`${API}/threads/${threadId}/state`);
      if (r.ok) {
        const state = await r.json();
        setMessages(state.values?.messages || []);
      }
    } catch {}
  }, []);

  useEffect(() => { if (activeThread) loadMessages(activeThread); }, [activeThread, loadMessages]);

  const send = async () => {
    if (!input.trim() || !assistantId || running) return;

    let threadId = activeThread;
    if (!threadId) {
      try {
        const r = await fetch(`${API}/threads`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) });
        const thread = await r.json();
        threadId = thread.thread_id;
        setActiveThread(threadId);
      } catch (e) { setError("Failed to create thread"); return; }
    }

    const userMsg = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { type: "human", content: userMsg }]);
    setRunning(true);
    setError(null);

    try {
      const r = await fetch(`${API}/threads/${threadId}/runs/wait`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ assistant_id: assistantId, input: { messages: [{ type: "human", content: userMsg }] } }),
      });
      if (!r.ok) {
        const errData = await r.json().catch(() => ({}));
        throw new Error(errData.detail || errData.message || `HTTP ${r.status}`);
      }
      const result = await r.json();
      setMessages(result.values?.messages || result.messages || []);
      await loadThreads();
    } catch (e) {
      setError(e.message);
      setMessages((prev) => [...prev, { type: "ai", content: `Error: ${e.message}` }]);
    }
    setRunning(false);
  };

  return (
    <div style={{ display: "flex", height: "100vh", background: COLORS.bg, color: COLORS.text, fontFamily: "'Inter', -apple-system, sans-serif" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap');
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes spin { to { transform: rotate(360deg); } }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        input:focus, button:focus { outline: none; }
        ::selection { background: ${COLORS.accent}40; }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: ${COLORS.border}; border-radius: 3px; }
      `}</style>

      {/* Sidebar */}
      <div style={{ width: 240, borderRight: `1px solid ${COLORS.border}`, display: "flex", flexDirection: "column", flexShrink: 0 }}>
        <div style={{ padding: "16px 16px 12px", borderBottom: `1px solid ${COLORS.border}` }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 32, height: 32, borderRadius: 8, background: `linear-gradient(135deg, ${COLORS.accent}, #8b5cf6)`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16, fontWeight: 700, color: "#fff", boxShadow: `0 0 16px ${COLORS.accent}30` }}>
              D
            </div>
            <div>
              <div style={{ fontSize: 15, fontWeight: 700, letterSpacing: -0.3 }}>DocVerify</div>
              <div style={{ fontSize: 10, color: COLORS.textDim, letterSpacing: 0.8, marginTop: 1 }}>AEGRA AGENT</div>
            </div>
          </div>
          <div style={{ marginTop: 12 }}><StatusDot ok={connected} /></div>
        </div>

        <div style={{ padding: "12px 12px 8px" }}>
          <button
            onClick={async () => {
              try {
                const r = await fetch(`${API}/threads`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) });
                const thread = await r.json();
                setActiveThread(thread.thread_id);
                setMessages([]);
                await loadThreads();
              } catch {}
            }}
            style={{ width: "100%", padding: "8px 12px", fontSize: 13, fontWeight: 600, color: COLORS.accent, background: COLORS.accentGlow, border: `1px solid ${COLORS.accent}30`, borderRadius: 8, cursor: "pointer" }}
          >
            + New Thread
          </button>
        </div>

        <div style={{ flex: 1, overflow: "auto", padding: "4px 0" }}>
          {threads.map((t) => (
            <ThreadItem key={t.thread_id} thread={t} active={activeThread === t.thread_id} onClick={() => setActiveThread(t.thread_id)} />
          ))}
          {threads.length === 0 && <div style={{ padding: "20px 16px", fontSize: 12, color: COLORS.textDim, textAlign: "center" }}>No threads yet</div>}
        </div>

        <div style={{ padding: "12px 16px", borderTop: `1px solid ${COLORS.border}`, fontSize: 11, color: COLORS.textDim }}>
          {assistantId && <div style={{ fontFamily: "'JetBrains Mono', monospace" }}>agent: {assistantId.slice(0, 8)}</div>}
        </div>
      </div>

      {/* Main */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        {/* Header */}
        <div style={{ padding: "12px 24px", borderBottom: `1px solid ${COLORS.border}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <span style={{ fontSize: 14, fontWeight: 600 }}>{activeThread ? `Thread ${activeThread.slice(0, 8)}` : "DocVerify Agent"}</span>
            {running && <span style={{ marginLeft: 12, fontSize: 12, color: COLORS.warning }}><Spinner size={10} /> Processing...</span>}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            {[{ label: "▶ Evaluate", cmd: "evaluate" }, { label: "📊 Status", cmd: "status" }].map((qc) => (
              <button
                key={qc.cmd}
                onClick={() => { setInput(qc.cmd); }}
                style={{ padding: "6px 14px", fontSize: 12, fontWeight: 500, color: COLORS.textMuted, background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 6, cursor: "pointer", transition: "all 0.15s" }}
                onMouseEnter={(e) => { e.target.style.borderColor = COLORS.accent; e.target.style.color = COLORS.accent; }}
                onMouseLeave={(e) => { e.target.style.borderColor = COLORS.border; e.target.style.color = COLORS.textMuted; }}
              >
                {qc.label}
              </button>
            ))}
          </div>
        </div>

        {/* Messages */}
        <div style={{ flex: 1, overflow: "auto", padding: "24px 24px 12px" }}>
          {error && (
            <div style={{ background: COLORS.dangerGlow, border: `1px solid ${COLORS.danger}30`, borderRadius: 10, padding: "10px 14px", marginBottom: 16, fontSize: 12, color: COLORS.danger, animation: "fadeIn 0.3s ease" }}>
              {error}
            </div>
          )}

          {messages.length === 0 && !error && (
            <div style={{ textAlign: "center", paddingTop: "15vh", animation: "fadeIn 0.5s ease" }}>
              <div style={{ width: 64, height: 64, borderRadius: 16, margin: "0 auto 20px", background: `linear-gradient(135deg, ${COLORS.accent}20, #8b5cf620)`, border: `1px solid ${COLORS.accent}20`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 28 }}>
                ◇
              </div>
              <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>DocVerify Agent</div>
              <div style={{ fontSize: 13, color: COLORS.textMuted, maxWidth: 400, margin: "0 auto", lineHeight: 1.6 }}>
                Ask questions about your documentation, or type <strong style={{ color: COLORS.accent }}>evaluate</strong> to run the full verification pipeline.
              </div>
              <div style={{ display: "flex", gap: 8, justifyContent: "center", marginTop: 20, flexWrap: "wrap" }}>
                {["How does authentication work?", "evaluate", "status"].map((ex) => (
                  <button
                    key={ex}
                    onClick={() => setInput(ex)}
                    style={{ padding: "8px 14px", fontSize: 12, color: COLORS.textMuted, background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, cursor: "pointer", transition: "all 0.15s" }}
                    onMouseEnter={(e) => { e.target.style.borderColor = COLORS.accent; }}
                    onMouseLeave={(e) => { e.target.style.borderColor = COLORS.border; }}
                  >
                    {ex}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, i) => <MessageBubble key={i} msg={msg} />)}
          <div ref={messagesEnd} />
        </div>

        {/* Input */}
        <div style={{ padding: "12px 24px 20px", borderTop: `1px solid ${COLORS.border}` }}>
          <div style={{ display: "flex", gap: 10, maxWidth: 720 }}>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && send()}
              placeholder="Ask a question or type 'evaluate'..."
              disabled={running}
              style={{ flex: 1, padding: "12px 16px", fontSize: 14, color: COLORS.text, background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 12, fontFamily: "inherit", transition: "border-color 0.2s", opacity: running ? 0.5 : 1 }}
              onFocus={(e) => (e.target.style.borderColor = COLORS.borderActive)}
              onBlur={(e) => (e.target.style.borderColor = COLORS.border)}
            />
            <button
              onClick={send}
              disabled={running || !input.trim()}
              style={{
                padding: "12px 20px", fontSize: 14, fontWeight: 600, color: "#fff",
                background: running || !input.trim() ? COLORS.textDim : `linear-gradient(135deg, ${COLORS.accent}, #6366f1)`,
                border: "none", borderRadius: 12,
                cursor: running || !input.trim() ? "not-allowed" : "pointer",
                boxShadow: running || !input.trim() ? "none" : `0 0 16px ${COLORS.accent}25`,
                transition: "all 0.2s", display: "flex", alignItems: "center", gap: 8,
              }}
            >
              {running ? <Spinner /> : "Send"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
