import { useEffect, useState, useCallback } from "react";
import { api, getSession, clearSession } from "./api";
import { getTheme, applyTheme, initTheme } from "./theme";
import Login from "./components/Login.jsx";
import Workspace from "./components/Workspace.jsx";
import AdminConsole from "./components/AdminConsole.jsx";

export default function App() {
  const [session, setSessionState] = useState(getSession());
  const [health, setHealth] = useState(null);
  const [theme, setTheme] = useState(getTheme());
  const [view, setView] = useState("workspace"); // workspace | admin

  useEffect(() => { initTheme(); }, []);

  const loadHealth = useCallback(() => {
    api.health().then(setHealth).catch(() => setHealth({ status: "down" }));
  }, []);
  useEffect(() => { if (session) loadHealth(); }, [session, loadHealth]);

  function toggleTheme() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    applyTheme(next);
  }
  function logout() {
    clearSession();
    setSessionState(null);
    setView("workspace");
  }

  if (!session) {
    return <Login onLogin={(s) => setSessionState(s)} />;
  }

  const isAdmin = session.user?.role === "admin";

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">◆</span>
          <div>
            <h1>ADR Agent</h1>
            <p className="tagline">Cloud Engineering · AWS · GCP · Azure</p>
          </div>
        </div>

        <div className="topbar-right">
          <div className="status">
            {health && (
              <>
                <Badge label={`LLM: ${health.model || health.llm_provider || "?"}`} tone={health.llm_ready ? "ok" : "err"} />
                <Badge label={`GitHub: ${health.github || "?"}`} tone={health.github === "live" ? "ok" : "muted"} />
                <Badge label={`Confluence: ${health.confluence || "?"}`} tone={health.confluence === "live" ? "ok" : "muted"} />
              </>
            )}
          </div>

          {isAdmin && (
            <button
              className={`nav-btn ${view === "admin" ? "active" : ""}`}
              onClick={() => setView(view === "admin" ? "workspace" : "admin")}
            >
              {view === "admin" ? "◆ Workspace" : "⚙ Admin"}
            </button>
          )}

          <button className="icon-toggle" onClick={toggleTheme} title="Toggle day / night">
            {theme === "dark" ? "☀️" : "🌙"}
          </button>

          <div className="user-chip" title={session.user.email}>
            <span className={`role-badge ${session.user.role}`}>{session.user.role}</span>
            <span className="user-name">{session.user.name || session.user.email}</span>
            <button className="logout" onClick={logout} title="Sign out">⎋</button>
          </div>
        </div>
      </header>

      {view === "admin" && isAdmin ? (
        <AdminConsole onClose={() => setView("workspace")} onChanged={loadHealth} />
      ) : (
        <Workspace health={health} />
      )}
    </div>
  );
}

function Badge({ label, tone }) {
  return <span className={`badge badge-${tone}`}>{label}</span>;
}
