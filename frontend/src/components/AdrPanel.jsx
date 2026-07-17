import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, downloadFile } from "../api";

const stripFrontmatter = (md) =>
  md && md.startsWith("---") ? md.replace(/^---\n[\s\S]*?\n---\n/, "") : md || "";

export default function AdrPanel({ adrs, activeAdrId, setActiveAdrId, refreshAdrs }) {
  const [adr, setAdr] = useState(null);
  const [kt, setKt] = useState(null);
  const [docView, setDocView] = useState("adr"); // adr | kt
  const [loading, setLoading] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [publishResults, setPublishResults] = useState(null);

  useEffect(() => {
    if (!activeAdrId) {
      setAdr(null);
      setKt(null);
      return;
    }
    setLoading(true);
    setPublishResults(null);
    setDocView("adr");
    Promise.all([api.adr(activeAdrId), api.adrKt(activeAdrId)])
      .then(([a, k]) => {
        setAdr(a);
        setKt(k);
      })
      .catch(() => setAdr(null))
      .finally(() => setLoading(false));
  }, [activeAdrId]);

  async function publish(targets) {
    if (!adr) return;
    setPublishing(true);
    setPublishResults(null);
    try {
      const res = await api.publish(adr.id, targets);
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
        await downloadFile(api.ktDocxUrl(kt.id), `${kt.id}.docx`);
      } else if (adr) {
        await downloadFile(api.adrDocxUrl(adr.id), `${adr.id}.docx`);
      }
    } catch (e) {
      setPublishResults([{ target: "download", ok: false, message: e.message }]);
    }
  }

  const cloudLabel = { aws: "AWS", gcp: "GCP", azure: "Azure" };
  const shownMd = docView === "kt" ? kt?.markdown : adr?.markdown;

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
            <li key={a.id} className={a.id === activeAdrId ? "active" : ""} onClick={() => setActiveAdrId(a.id)}>
              <div className="adr-row-top">
                <span className="adr-id">{a.id}</span>
                <span className={`cloud-tag ${a.cloud}`}>{cloudLabel[a.cloud] || a.cloud}</span>
              </div>
              <div className="adr-title">{a.title}</div>
              <div className="adr-path">{a.folder}</div>
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
              <button className={docView === "adr" ? "active" : ""} onClick={() => setDocView("adr")}>
                ADR Document
              </button>
              <button
                className={docView === "kt" ? "active" : ""}
                onClick={() => setDocView("kt")}
                disabled={!kt}
                title={kt ? "Knowledge Transfer for Cloud Operations" : "No KT document"}
              >
                KT · Ops Handover
              </button>
            </div>

            <div className="preview-toolbar">
              <div>
                <span className="adr-id big">{docView === "kt" ? kt?.id : adr.id}</span>
                {docView === "adr" && (
                  <span className={`status-pill ${adr.status?.toLowerCase()}`}>{adr.status}</span>
                )}
              </div>
              <div className="publish-actions">
                <button onClick={downloadDocx} title="Download as Word">⬇ Word</button>
                {docView === "adr" && (
                  <>
                    <button disabled={publishing} onClick={() => publish(["github"])}>GitHub</button>
                    <button disabled={publishing} onClick={() => publish(["confluence"])}>Confluence</button>
                    <button className="primary" disabled={publishing} onClick={() => publish(["github", "confluence"])}>
                      {publishing ? "Publishing…" : "Publish both"}
                    </button>
                  </>
                )}
              </div>
            </div>

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

            {docView === "kt" && (
              <div className="kt-note">
                📘 Knowledge Transfer document — the operations handover for Cloud Operations,
                auto-generated from this ADR.
              </div>
            )}

            <div className="markdown-body">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{stripFrontmatter(shownMd)}</ReactMarkdown>
            </div>
          </>
        )}
      </div>
    </section>
  );
}
