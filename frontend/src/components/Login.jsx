import { useState } from "react";
import { api, setSession } from "../api";

export default function Login({ onLogin }) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState("admin");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function submit(e) {
    e.preventDefault();
    if (!email.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.login(email.trim(), name.trim(), role);
      setSession(res);
      onLogin(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-screen">
      <div className="login-card">
        <div className="login-brand">
          <span className="logo lg">◆</span>
          <h1>ADR Agent</h1>
          <p>Cloud Engineering · Architecture Decision Records</p>
        </div>

        <form onSubmit={submit}>
          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              autoFocus
            />
          </label>
          <label>
            Name <span className="opt">(optional)</span>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" />
          </label>

          <div className="role-picker">
            <span className="role-label">Sign in as</span>
            <div className="role-toggle">
              <button
                type="button"
                className={role === "admin" ? "active" : ""}
                onClick={() => setRole("admin")}
              >
                <strong>Admin</strong>
                <small>ADRs + Admin Console</small>
              </button>
              <button
                type="button"
                className={role === "user" ? "active" : ""}
                onClick={() => setRole("user")}
              >
                <strong>User</strong>
                <small>ADR creation only</small>
              </button>
            </div>
          </div>

          {error && <div className="login-error">⚠️ {error}</div>}

          <button className="login-btn" type="submit" disabled={busy || !email.trim()}>
            {busy ? "Signing in…" : "Enter"}
          </button>
        </form>

        <p className="login-note">
          🔓 Temporary free login. Roles here stand in for <strong>SSO group mapping</strong>{" "}
          (Admin group → Admin, others → User) once deployed on GKE.
        </p>
      </div>
    </div>
  );
}
