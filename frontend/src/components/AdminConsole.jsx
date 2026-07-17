import { useEffect, useState } from "react";
import { api } from "../api";

const TABS = [
  { key: "integrations", label: "Integrations" },
  { key: "general", label: "General" },
  { key: "knowledge", label: "Knowledge" },
  { key: "skills", label: "Skills" },
];

export default function AdminConsole({ onClose, onChanged }) {
  const [tab, setTab] = useState("integrations");
  return (
    <div className="admin">
      <div className="admin-head">
        <div>
          <h2>Admin Console</h2>
          <p>Platform configuration — visible to the Admin group only.</p>
        </div>
        <button className="ghost-btn" onClick={onClose}>
          ← Back to workspace
        </button>
      </div>
      <div className="admin-tabs">
        {TABS.map((t) => (
          <button key={t.key} className={tab === t.key ? "active" : ""} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>
      <div className="admin-body">
        {tab === "integrations" && <Integrations onChanged={onChanged} />}
        {tab === "general" && <General onChanged={onChanged} />}
        {tab === "knowledge" && <KnowledgeAdmin />}
        {tab === "skills" && <SkillsAdmin />}
      </div>
    </div>
  );
}

function useConfig() {
  const [cfg, setCfg] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    api.adminConfig().then(setCfg).catch((e) => setErr(e.message));
  }, []);
  return [cfg, setCfg, err];
}

function Saved({ show }) {
  return show ? <span className="saved-flag">✓ Saved</span> : null;
}

function Integrations({ onChanged }) {
  const [cfg, setCfg, err] = useConfig();
  const [saved, setSaved] = useState(false);
  const [msg, setMsg] = useState(null);
  if (err) return <div className="admin-error">{err}</div>;
  if (!cfg) return <div className="admin-loading">Loading…</div>;

  const set = (section, key, val) =>
    setCfg({ ...cfg, [section]: { ...cfg[section], [key]: val } });

  async function save() {
    setMsg(null);
    try {
      const res = await api.adminUpdateConfig({ github: cfg.github, confluence: cfg.confluence });
      setCfg(res);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
      onChanged?.();
    } catch (e) {
      setMsg(e.message);
    }
  }

  return (
    <div className="admin-section">
      <div className="card">
        <div className="card-title">
          <h3>GitHub</h3>
          <StatusDot on={cfg.github.configured} />
        </div>
        <p className="card-sub">ADRs are committed to this repository when configured.</p>
        <Field label="Repository (owner/repo)">
          <input value={cfg.github.repo || ""} onChange={(e) => set("github", "repo", e.target.value)} placeholder="my-org/cloud-adrs" />
        </Field>
        <Field label="Branch">
          <input value={cfg.github.branch || ""} onChange={(e) => set("github", "branch", e.target.value)} placeholder="main" />
        </Field>
        <Field label="Access token">
          <input type="password" value={cfg.github.token || ""} onChange={(e) => set("github", "token", e.target.value)} placeholder="ghp_…" />
        </Field>
      </div>

      <div className="card">
        <div className="card-title">
          <h3>Confluence</h3>
          <StatusDot on={cfg.confluence.configured} />
        </div>
        <p className="card-sub">ADRs are published as pages in the configured space.</p>
        <Field label="Base URL">
          <input value={cfg.confluence.base_url || ""} onChange={(e) => set("confluence", "base_url", e.target.value)} placeholder="https://org.atlassian.net/wiki" />
        </Field>
        <Field label="User (email)">
          <input value={cfg.confluence.user || ""} onChange={(e) => set("confluence", "user", e.target.value)} placeholder="you@org.com" />
        </Field>
        <Field label="Space key">
          <input value={cfg.confluence.space_key || ""} onChange={(e) => set("confluence", "space_key", e.target.value)} placeholder="ARCH" />
        </Field>
        <Field label="API token">
          <input type="password" value={cfg.confluence.api_token || ""} onChange={(e) => set("confluence", "api_token", e.target.value)} placeholder="•••" />
        </Field>
      </div>

      {msg && <div className="admin-error">{msg}</div>}
      <div className="admin-actions">
        <button className="primary" onClick={save}>Save integrations</button>
        <Saved show={saved} />
      </div>
    </div>
  );
}

function General({ onChanged }) {
  const [cfg, setCfg, err] = useConfig();
  const [emails, setEmails] = useState("");
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    if (cfg) setEmails((cfg.admin_emails || []).join(", "));
  }, [cfg]);
  if (err) return <div className="admin-error">{err}</div>;
  if (!cfg) return <div className="admin-loading">Loading…</div>;

  async function save() {
    const list = emails.split(",").map((s) => s.trim()).filter(Boolean);
    const res = await api.adminUpdateConfig({
      author: cfg.author,
      admin_emails: list,
      features: cfg.features,
    });
    setCfg(res);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
    onChanged?.();
  }

  return (
    <div className="admin-section">
      <div className="card">
        <div className="card-title"><h3>Authoring</h3></div>
        <Field label="Author (shown on every ADR/KT)">
          <input value={cfg.author || ""} onChange={(e) => setCfg({ ...cfg, author: e.target.value })} placeholder="Cloud Engineering" />
        </Field>
      </div>

      <div className="card">
        <div className="card-title"><h3>Access — Admin group</h3></div>
        <p className="card-sub">
          Emails here always resolve to the Admin role. Later, SSO groups map here
          (Admin group → admin, others → user).
        </p>
        <Field label="Admin emails (comma-separated)">
          <input value={emails} onChange={(e) => setEmails(e.target.value)} placeholder="a@org.com, b@org.com" />
        </Field>
      </div>

      <div className="card">
        <div className="card-title"><h3>Features</h3></div>
        <Toggle label="Auto-generate KT documents" checked={cfg.features?.kt_docs !== false}
          onChange={(v) => setCfg({ ...cfg, features: { ...cfg.features, kt_docs: v } })} />
        <Toggle label="Enable DOCX export" checked={cfg.features?.docx_export !== false}
          onChange={(v) => setCfg({ ...cfg, features: { ...cfg.features, docx_export: v } })} />
      </div>

      <div className="admin-actions">
        <button className="primary" onClick={save}>Save settings</button>
        <Saved show={saved} />
      </div>
    </div>
  );
}

function KnowledgeAdmin() {
  const [data, setData] = useState(null);
  const [form, setForm] = useState({ scope: "global", category: "security", title: "", content: "" });
  const [msg, setMsg] = useState(null);

  const load = () => api.adminKnowledge().then(setData).catch((e) => setMsg(e.message));
  useEffect(() => { load(); }, []);
  if (!data) return <div className="admin-loading">Loading…</div>;

  async function add() {
    setMsg(null);
    if (!form.title.trim() || !form.content.trim()) return setMsg("Title and content are required.");
    try {
      await api.adminAddKnowledge(form);
      setForm({ ...form, title: "", content: "" });
      load();
    } catch (e) { setMsg(e.message); }
  }
  async function del(key) {
    await api.adminDeleteKnowledge(key);
    load();
  }

  const grouped = {};
  for (const d of data.docs) (grouped[d.scope] ||= []).push(d);

  return (
    <div className="admin-section">
      <div className="card">
        <div className="card-title"><h3>Upload a document</h3></div>
        <p className="card-sub">
          Security, architecture, engineering, or a write-up. Scope it to a cloud so the
          agent never mixes it into another cloud's ADR.
        </p>
        <div className="row">
          <Field label="Scope (cloud)">
            <select value={form.scope} onChange={(e) => setForm({ ...form, scope: e.target.value })}>
              {data.scopes.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </Field>
          <Field label="Category">
            <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
              {data.categories.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </Field>
        </div>
        <Field label="Title">
          <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="e.g. AWS Data Encryption Standard" />
        </Field>
        <Field label="Content (Markdown)">
          <textarea rows={7} value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} placeholder="Paste or type the document. You can also paste real Confluence links here." />
        </Field>
        {msg && <div className="admin-error">{msg}</div>}
        <div className="admin-actions"><button className="primary" onClick={add}>Add document</button></div>
      </div>

      <div className="card">
        <div className="card-title"><h3>Existing documents ({data.docs.length})</h3></div>
        {Object.entries(grouped).map(([scope, docs]) => (
          <div key={scope} className="doc-group">
            <div className="doc-group-head"><span className={`scope-tag ${scope}`}>{scope}</span></div>
            {docs.map((d) => (
              <div key={d.key} className="doc-line">
                <span className="doc-cat">{d.category}</span>
                <span className="doc-name">{d.title}</span>
                <button className="del-btn" onClick={() => del(d.key)} title="Delete">✕</button>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function SkillsAdmin() {
  const [data, setData] = useState(null);
  const [form, setForm] = useState({ scope: "global", name: "", description: "", when_to_use: "", body: "" });
  const [msg, setMsg] = useState(null);

  const load = () => api.adminSkills().then(setData).catch((e) => setMsg(e.message));
  useEffect(() => { load(); }, []);
  if (!data) return <div className="admin-loading">Loading…</div>;

  async function add() {
    setMsg(null);
    if (!form.name.trim() || !form.body.trim()) return setMsg("Name and body are required.");
    try {
      await api.adminAddSkill(form);
      setForm({ ...form, name: "", description: "", when_to_use: "", body: "" });
      load();
    } catch (e) { setMsg(e.message); }
  }
  async function del(scope, name) {
    await api.adminDeleteSkill(scope, name);
    load();
  }

  const grouped = {};
  for (const s of data.skills) (grouped[s.scope] ||= []).push(s);

  return (
    <div className="admin-section">
      <div className="card">
        <div className="card-title"><h3>Add a skill</h3></div>
        <p className="card-sub">
          Guidance the agent loads. Cloud-scoped skills apply only to that cloud's ADRs.
        </p>
        <div className="row">
          <Field label="Scope">
            <select value={form.scope} onChange={(e) => setForm({ ...form, scope: e.target.value })}>
              {data.scopes.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </Field>
          <Field label="Name">
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. aws-network-guardrails" />
          </Field>
        </div>
        <Field label="Description">
          <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="One line about what this skill does" />
        </Field>
        <Field label="When to use">
          <input value={form.when_to_use} onChange={(e) => setForm({ ...form, when_to_use: e.target.value })} placeholder="e.g. Only for AWS networking ADRs" />
        </Field>
        <Field label="Body (Markdown instructions)">
          <textarea rows={7} value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} placeholder="The guidance the agent should follow…" />
        </Field>
        {msg && <div className="admin-error">{msg}</div>}
        <div className="admin-actions"><button className="primary" onClick={add}>Add skill</button></div>
      </div>

      <div className="card">
        <div className="card-title"><h3>Existing skills ({data.skills.length})</h3></div>
        {Object.entries(grouped).map(([scope, skills]) => (
          <div key={scope} className="doc-group">
            <div className="doc-group-head"><span className={`scope-tag ${scope}`}>{scope}</span></div>
            {skills.map((s) => (
              <div key={s.scope + s.name} className="doc-line">
                <span className="doc-name">🧩 {s.name}</span>
                <span className="doc-desc">{s.description}</span>
                <button className="del-btn" onClick={() => del(s.scope, s.name)} title="Delete">✕</button>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

// --- small shared bits ---
function Field({ label, children }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}
function StatusDot({ on }) {
  return <span className={`status-dot ${on ? "on" : "off"}`}>{on ? "Live" : "Not configured"}</span>;
}
function Toggle({ label, checked, onChange }) {
  return (
    <label className="switch-row">
      <span>{label}</span>
      <button type="button" className={`switch ${checked ? "on" : ""}`} onClick={() => onChange(!checked)}>
        <span className="knob" />
      </button>
    </label>
  );
}
