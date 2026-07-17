import { useState } from "react";
import { api } from "../api";
import Modal from "./Modal.jsx";

export default function Sidebar({ catalog, skills, knowledge, onPickService }) {
  const [tab, setTab] = useState("catalog");
  const [doc, setDoc] = useState(null);

  return (
    <aside className="sidebar">
      <div className="tabs">
        <button className={tab === "catalog" ? "active" : ""} onClick={() => setTab("catalog")}>
          Catalog
        </button>
        <button className={tab === "skills" ? "active" : ""} onClick={() => setTab("skills")}>
          Skills
        </button>
        <button className={tab === "knowledge" ? "active" : ""} onClick={() => setTab("knowledge")}>
          Knowledge
        </button>
      </div>

      <div className="sidebar-body">
        {tab === "catalog" && <Catalog catalog={catalog} onPickService={onPickService} />}
        {tab === "skills" && <Skills skills={skills} />}
        {tab === "knowledge" && (
          <Knowledge
            knowledge={knowledge}
            onOpen={async (k) => {
              const d = await api.knowledgeDoc(k.key);
              setDoc({ title: k.title, content: d.content });
            }}
          />
        )}
      </div>

      {doc && (
        <Modal title={doc.title} onClose={() => setDoc(null)}>
          <pre className="doc-pre">{doc.content}</pre>
        </Modal>
      )}
    </aside>
  );
}

function Catalog({ catalog, onPickService }) {
  const [openCloud, setOpenCloud] = useState("gcp");
  const [q, setQ] = useState("");
  return (
    <div className="catalog">
      <input
        className="search"
        placeholder="Search services…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      {catalog.map((cloud) => (
        <div key={cloud.slug} className="cloud">
          <button
            className="cloud-head"
            onClick={() => setOpenCloud(openCloud === cloud.slug ? null : cloud.slug)}
          >
            <span className={`chev ${openCloud === cloud.slug ? "open" : ""}`}>▸</span>
            {cloud.name}
          </button>
          {openCloud === cloud.slug &&
            cloud.categories.map((cat) => {
              const services = cat.services.filter(
                (s) =>
                  !q ||
                  s.name.toLowerCase().includes(q.toLowerCase()) ||
                  (s.aliases || []).some((a) => a.includes(q.toLowerCase()))
              );
              if (!services.length) return null;
              return (
                <div key={cat.slug} className="category">
                  <div className="category-label">{cat.label}</div>
                  {services.map((s) => (
                    <button
                      key={s.slug}
                      className="service"
                      title={`adrs/${cloud.slug}/${s.folder}/`}
                      onClick={() => onPickService(cloud.name, s.name)}
                    >
                      <span className="svc-name">{s.name}</span>
                      <span className="svc-folder">{s.folder}</span>
                    </button>
                  ))}
                </div>
              );
            })}
        </div>
      ))}
    </div>
  );
}

function Skills({ skills }) {
  return (
    <div className="skills">
      <p className="hint">
        Modular guidance the agent loads. <strong>Cloud-scoped</strong> skills apply only to
        that cloud's ADRs — admins add more in the Admin Console.
      </p>
      {skills.map((s) => (
        <div key={s.scope + s.name} className="skill-card">
          <div className="skill-name">
            <span>🧩 {s.name}</span>
            <span className={`scope-tag ${s.scope}`}>{s.scope}</span>
          </div>
          <div className="skill-desc">{s.description}</div>
          {s.when_to_use && <div className="skill-when">When: {s.when_to_use}</div>}
        </div>
      ))}
    </div>
  );
}

function Knowledge({ knowledge, onOpen }) {
  return (
    <div className="knowledge">
      <p className="hint">
        Standards mirrored from Confluence, scoped per cloud so the agent never mixes them.
        Admins upload more in the Admin Console.
      </p>
      {knowledge.map((k) => (
        <button key={k.key} className="doc-item" onClick={() => onOpen(k)}>
          <span className="doc-topic">
            <span className={`scope-tag ${k.scope}`}>{k.scope}</span>
            <span>{k.category}</span>
          </span>
          <span className="doc-title">{k.title}</span>
        </button>
      ))}
    </div>
  );
}
