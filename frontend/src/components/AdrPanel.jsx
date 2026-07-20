import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, downloadFile } from "../api";

const stripFrontmatter = (md) =>
  md && md.startsWith("---") ? md.replace(/^---\n[\s\S]*?\n---\n/, "") : md || "";

export default function AdrPanel({ adrs, activeUid, setActiveUid, refreshAdrs }) {
  const [adr, setAdr] = useState(null);
  const [kt, setKt] = useState(null);
  const [docView, setDocView] = useState("adr"); // adr | kt
  const [loading, setLoading] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [publishResults, setPublishResults] = useState(null);

  // inline editing
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState(null);

  // lifecycle
  const [statuses, setStatuses] = useState([]);
  const [showSupersede, setShowSupersede] = useState(false);

  useEffect(() => {
    api.statuses().then((r) => setStatuses(r.statuses)).catch(() => {});
  }, []);

  // earlier ADRs for the same service that this one could supersede
  const supersedable = adr
    ? adrs.filter(
        (a) =>
          a.cloud === adr.cloud &&
          a.service === adr.service &&
          a.uid !== adr.uid &&
          (a.number ?? 0) < (adr.number ?? 0)
      )
    : [];
  const byUid = Object.fromEntries(adrs.map((a) => [a.uid, a]));

  async function changeStatus(status) {
    setSaveMsg(null);
    try {
      const updated = await api.setStatus(activeUid, status);
      setAdr(updated);
      await refreshAdrs();
    } catch (e) {
      setSaveMsg(`Status change failed: ${e.message}`);
    }
  }

  async function doSupersede(oldUid) {
    setSaveMsg(null);
    setShowSupersede(false);
    try {
      const updated = await api.supersede(activeUid, oldUid);
      setAdr(updated);
      await refreshAdrs();
      setSaveMsg("Superseded");
      setTimeout(() => setSaveMsg(null), 2500);
    } catch (e) {
      setSaveMsg(`Supersede failed: ${e.message}`);
    }
  }

  useEffect(() => {
    if (!activeUid) {
      setAdr(null);
      setKt(null);
      return;
    }
    setLoading(true);
    setPublishResults(null);
    setDocView("adr");
    setEditing(false);
    Promise.all([api.adr(activeUid), api.adrKt(activeUid)])
      .then(([a, k]) => {
        setAdr(a);
        setKt(k);
      })
      .catch(() => setAdr(null))
      .finally(() => setLoading(false));
  }, [activeUid]);

  const shownMd = docView === "kt" ? kt?.markdown : adr?.markdown;

  function startEdit() {
    setDraft(shownMd || "");
    setSaveMsg(null);
    setEditing(true);
  }
  function cancelEdit() {
    setEditing(false);
    setDraft("");
  }
  async function saveEdit() {
    setSaving(true);
    setSaveMsg(null);
    try {
      if (docView === "kt") {
        const updated = await api.saveKt(activeUid, draft);
        setKt(updated);
      } else {
        const updated = await api.saveAdr(activeUid, draft);
        setAdr(updated);
        await refreshAdrs(); // title/status may have changed
      }
      setEditing(false);
      setSaveMsg("Saved");
      setTimeout(() => setSaveMsg(null), 2000);
    } catch (e) {
      setSaveMsg(`Save failed: ${e.message}`);
    } finally {
      setSaving(false);
    }
  }

  async function publish(targets) {
    if (!adr) return;
    setPublishing(true);
    setPublishResults(null);
    try {
      const res = await api.publish(adr.uid, targets);
      setPublishResults(res.results);
    } catch (e) {
      setPublishResults([{ target: "error", ok: false, message: e.message }]);
    } finally {
      setPublishing(false);
    }
  }

  async function downloadDocx() {
    try {
      if (docView === "kt" && kt) {
        await downloadFile(api.ktDocxUrl(activeUid), `${kt.id}.docx`);
      } else if (adr) {
        await downloadFile(api.adrDocxUrl(activeUid), `${adr.id}.docx`);
      }
    } catch (e) {
      setPublishResults([{ target: "download", ok: false, message: e.message }]);
    }
  }

  const cloudLabel = { aws: "AWS", gcp: "GCP", azure: "Azure" };

  return (
    <section className="adr-panel">
      <div className="adr-list">
        <div className="adr-list-head">
          <h2>Documents</h2>
          <button className="icon-btn" title="Refresh" onClick={refreshAdrs}>⟳</button>
        </div>
        {adrs.length === 0 && <p className="empty">No ADRs yet. Ask the agent to create one.</p>}
        <ul>
          {adrs.map((a) => (
            <li
              key={a.uid}
              className={a.uid === activeUid ? "active" : ""}
              onClick={() => setActiveUid(a.uid)}
            >
              <div className="adr-row-top">
                <span className="adr-id">{a.id}</span>
                <span className={`cloud-tag ${a.cloud}`}>{cloudLabel[a.cloud] || a.cloud}</span>
              </div>
              <div className={`adr-title ${a.superseded_by ? "struck" : ""}`}>{a.title}</div>
              <div className="adr-row-bottom">
                <span className="adr-path">{a.folder}</span>
                <span className={`status-dot-sm ${a.status?.toLowerCase()}`}>{a.status}</span>
              </div>
            </li>
          ))}
        </ul>
      </div>

      <div className="adr-preview">
        {loading && <p className="empty">Loading…</p>}
        {!loading && !adr && (
          <div className="empty-preview">
            <div className="empty-mark">◆</div>
            <p>Select a document to preview it, or ask the agent to draft one.</p>
          </div>
        )}
        {!loading && adr && (
          <>
            <div className="doc-switch">
              <button
                className={docView === "adr" ? "active" : ""}
                onClick={() => { setDocView("adr"); setEditing(false); }}
              >
                ADR Document
              </button>
              <button
                className={docView === "kt" ? "active" : ""}
                onClick={() => { setDocView("kt"); setEditing(false); }}
                disabled={!kt}
                title={kt ? "Knowledge Transfer for Cloud Operations" : "No KT document"}
              >
                KT · Ops Handover
              </button>
            </div>

            <div className="preview-toolbar">
              <div className="doc-ident">
                <span className="adr-id big">{docView === "kt" ? kt?.id : adr.id}</span>
                {docView === "adr" && !editing && (
                  <select
                    className={`status-select ${adr.status?.toLowerCase()}`}
                    value={adr.status}
                    onChange={(e) => changeStatus(e.target.value)}
                    title="Change status"
                  >
                    {statuses.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                )}
                {docView === "kt" && (
                  <span className={`status-pill ${adr.status?.toLowerCase()}`}>{adr.status}</span>
                )}
                <span className="uid-tag" title="Unique key — display IDs restart per service">
                  {adr.cloud}/{adr.service}
                </span>
              </div>
              <div className="publish-actions">
                {editing ? (
                  <>
                    <button className="primary" disabled={saving} onClick={saveEdit}>
                      {saving ? "Saving…" : "Save"}
                    </button>
                    <button disabled={saving} onClick={cancelEdit}>Cancel</button>
                  </>
                ) : (
                  <>
                    <button onClick={startEdit} title="Edit this document">✎ Edit</button>
                    <button onClick={downloadDocx} title="Download as Word">⬇ Word</button>
                    {docView === "adr" && supersedable.length > 0 && (
                      <button
                        onClick={() => setShowSupersede((v) => !v)}
                        title="Mark an earlier ADR for this service as superseded by this one"
                      >
                        ⤴ Supersede
                      </button>
                    )}
                    {docView === "adr" && (
                      <>
                        <button disabled={publishing} onClick={() => publish(["github"])}>GitHub</button>
                        <button disabled={publishing} onClick={() => publish(["confluence"])}>Confluence</button>
                        <button className="primary" disabled={publishing} onClick={() => publish(["github", "confluence"])}>
                          {publishing ? "Publishing…" : "Publish both"}
                        </button>
                      </>
                    )}
                  </>
                )}
              </div>
            </div>

            {showSupersede && (
              <div className="supersede-picker">
                <div className="supersede-title">
                  Which earlier {adr.service} ADR does <strong>{adr.id}</strong> replace?
                </div>
                {supersedable.map((a) => (
                  <button key={a.uid} className="supersede-option" onClick={() => doSupersede(a.uid)}>
                    <span className="adr-id">{a.id}</span>
                    <span className="supersede-opt-title">{a.title}</span>
                    <span className={`status-pill ${a.status?.toLowerCase()}`}>{a.status}</span>
                  </button>
                ))}
                <button className="supersede-cancel" onClick={() => setShowSupersede(false)}>
                  Cancel
                </button>
              </div>
            )}

            {docView === "adr" && (adr.superseded_by || adr.supersedes) && (
              <div className="lineage">
                {adr.superseded_by && (
                  <button
                    className="lineage-badge superseded"
                    onClick={() => setActiveUid(adr.superseded_by)}
                    title="Open the ADR that replaced this one"
                  >
                    ⚠️ Superseded by {byUid[adr.superseded_by]?.id || adr.superseded_by} →
                  </button>
                )}
                {adr.supersedes && (
                  <button
                    className="lineage-badge supersedes"
                    onClick={() => setActiveUid(adr.supersedes)}
                    title="Open the ADR this one replaced"
                  >
                    ↩️ Supersedes {byUid[adr.supersedes]?.id || adr.supersedes} →
                  </button>
                )}
              </div>
            )}

            {saveMsg && (
              <div className={`save-flag ${saveMsg.includes("failed") ? "err" : "ok"}`}>
                {saveMsg}
              </div>
            )}

            {publishResults && (
              <div className="publish-results">
                {publishResults.map((r, i) => (
                  <div key={i} className={`publish-result ${r.ok ? "ok" : "err"}`}>
                    <strong>{r.target}</strong>
                    {r.mode ? <span className="mode-tag">{r.mode}</span> : null}
                    <span>{r.message}</span>
                    {r.url && <a href={r.url} target="_blank" rel="noreferrer">open ↗</a>}
                  </div>
                ))}
              </div>
            )}

            {docView === "kt" && !editing && (
              <div className="kt-note">
                📘 Knowledge Transfer document — the operations handover for Cloud Operations,
                auto-generated from this ADR.
              </div>
            )}

            {editing ? (
              <div className="editor">
                <div className="editor-hint">
                  Editing raw Markdown (front-matter included). Changes to <code>title:</code> and{" "}
                  <code>status:</code> update the document list. Save before publishing.
                </div>
                <textarea
                  className="editor-area"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  spellCheck={false}
                />
                <div className="editor-preview-label">Live preview</div>
                <div className="markdown-body editor-preview">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{stripFrontmatter(draft)}</ReactMarkdown>
                </div>
              </div>
            ) : (
              <div className="markdown-body">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{stripFrontmatter(shownMd)}</ReactMarkdown>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
