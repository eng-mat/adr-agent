import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "../api";

const WELCOME = {
  role: "assistant",
  text:
    "Hi! I'm your ADR agent. Tell me what you want to document — e.g. " +
    "**\"I need an ADR for a GCS bucket\"** — and I'll draft a standards-compliant " +
    "ADR, file it in the right cloud folder, and get it ready to publish.",
};

export default function Chat({ seed, onSaved, providerReady, keyEnv }) {
  const [display, setDisplay] = useState([WELCOME]); // {role, text} for the UI
  const [history, setHistory] = useState([]); // raw agent messages for the API
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const scrollRef = useRef(null);

  useEffect(() => {
    if (seed?.text) setInput(seed.text);
  }, [seed]);

  useEffect(() => {
    scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight);
  }, [display, busy]);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setError(null);
    setInput("");
    setDisplay((d) => [...d, { role: "user", text }]);
    setBusy(true);
    try {
      const res = await api.chat(text, history);
      setHistory(res.messages);
      const events = res.tool_events || [];
      setDisplay((d) => [
        ...d,
        ...(events.length ? [{ role: "tools", events }] : []),
        { role: "assistant", text: res.reply || "(no response)" },
      ]);
      if (res.saved_adrs && res.saved_adrs.length) onSaved(res.saved_adrs);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function onKey(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <main className="chat">
      <div className="chat-scroll" ref={scrollRef}>
        {display.map((m, i) => (
          <Message key={i} m={m} />
        ))}
        {busy && (
          <div className="msg assistant">
            <div className="avatar">◆</div>
            <div className="bubble typing">
              <span></span><span></span><span></span>
            </div>
          </div>
        )}
      </div>

      {!providerReady && (
        <div className="warn-bar">
          ⚠️ The LLM provider isn't ready. Add your <code>{keyEnv}</code> to{" "}
          <code>backend/.env</code> and restart the backend.
        </div>
      )}
      {error && <div className="error-bar">⚠️ {error}</div>}

      <div className="composer">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKey}
          placeholder="Describe the resource you need an ADR for…"
          rows={2}
        />
        <button className="send" onClick={send} disabled={busy || !input.trim()}>
          {busy ? "…" : "Send"}
        </button>
      </div>
    </main>
  );
}

function Message({ m }) {
  if (m.role === "tools") {
    return (
      <div className="tool-trace">
        {m.events.map((e, i) => (
          <div key={i} className="tool-line">
            <span className="tool-badge">{labelFor(e.tool)}</span>
            <span className="tool-detail">{summarize(e)}</span>
          </div>
        ))}
      </div>
    );
  }
  const isUser = m.role === "user";
  return (
    <div className={`msg ${isUser ? "user" : "assistant"}`}>
      {!isUser && <div className="avatar">◆</div>}
      <div className="bubble">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.text}</ReactMarkdown>
      </div>
    </div>
  );
}

function labelFor(tool) {
  return (
    {
      search_catalog: "🔎 catalog",
      get_knowledge: "📖 knowledge",
      save_adr: "💾 save ADR",
    }[tool] || tool
  );
}

function summarize(e) {
  if (e.tool === "search_catalog") {
    const n = e.result?.matches?.length ?? 0;
    return `“${e.input?.query}” → ${n} match${n === 1 ? "" : "es"}`;
  }
  if (e.tool === "get_knowledge") {
    return e.input?.key || e.input?.query || "listed standards";
  }
  if (e.tool === "save_adr") {
    const kt = e.result?.kt_id ? ` (+ ${e.result.kt_id})` : "";
    return `${e.result?.id || ""} → ${e.result?.rel_path || ""}${kt}`;
  }
  return "";
}
