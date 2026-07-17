const BASE = "/api";

// --- session (free login; replaced by SSO later) ---
const SESSION_KEY = "adr.session";

export function getSession() {
  try {
    return JSON.parse(localStorage.getItem(SESSION_KEY) || "null");
  } catch {
    return null;
  }
}
export function setSession(s) {
  localStorage.setItem(SESSION_KEY, JSON.stringify(s));
}
export function clearSession() {
  localStorage.removeItem(SESSION_KEY);
}

function authHeaders() {
  const s = getSession();
  if (!s?.user) return {};
  return {
    "X-User-Email": s.user.email || "",
    "X-User-Role": s.user.role || "user",
    "X-User-Name": s.user.name || "",
  };
}

async function req(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json", ...authHeaders() },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  // meta
  health: () => req("/health"),
  catalog: () => req("/catalog"),
  skills: (scope) => req(`/skills${scope ? `?scope=${scope}` : ""}`),
  knowledge: (scope) => req(`/knowledge${scope ? `?scope=${scope}` : ""}`),
  knowledgeDoc: (key) => req(`/knowledge/${key}`),

  // auth
  login: (email, name, role) =>
    req("/auth/login", { method: "POST", body: JSON.stringify({ email, name, role }) }),

  // adrs
  adrs: () => req("/adrs"),
  adr: (id) => req(`/adrs/${id}`),
  adrKt: (id) => req(`/adrs/${id}/kt`).catch(() => null),
  adrDocxUrl: (id) => `${BASE}/adrs/${id}/export.docx`,

  // kt
  ktList: () => req("/kt"),
  kt: (id) => req(`/kt/${id}`),
  ktDocxUrl: (id) => `${BASE}/kt/${id}/export.docx`,

  // agent
  chat: (message, history) =>
    req("/chat", { method: "POST", body: JSON.stringify({ message, history }) }),
  publish: (adr_id, targets) =>
    req("/publish", { method: "POST", body: JSON.stringify({ adr_id, targets }) }),

  // admin
  adminConfig: () => req("/admin/config"),
  adminUpdateConfig: (patch) =>
    req("/admin/config", { method: "PUT", body: JSON.stringify(patch) }),
  adminKnowledge: () => req("/admin/knowledge"),
  adminAddKnowledge: (doc) =>
    req("/admin/knowledge", { method: "POST", body: JSON.stringify(doc) }),
  adminDeleteKnowledge: (key) =>
    req(`/admin/knowledge?key=${encodeURIComponent(key)}`, { method: "DELETE" }),
  adminSkills: () => req("/admin/skills"),
  adminAddSkill: (skill) =>
    req("/admin/skills", { method: "POST", body: JSON.stringify(skill) }),
  adminDeleteSkill: (scope, name) =>
    req(`/admin/skills?scope=${scope}&name=${encodeURIComponent(name)}`, { method: "DELETE" }),
};

// Trigger a browser download for file endpoints (adds auth headers via fetch->blob).
export async function downloadFile(url, filename) {
  const res = await fetch(url, { headers: authHeaders() });
  if (!res.ok) throw new Error(`Download failed (${res.status})`);
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(a.href);
}
