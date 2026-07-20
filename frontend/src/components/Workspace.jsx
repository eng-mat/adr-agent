import { useEffect, useState, useCallback, useRef } from "react";
import { api } from "../api";
import Sidebar from "./Sidebar.jsx";
import Chat from "./Chat.jsx";
import AdrPanel from "./AdrPanel.jsx";

const LS_KEY = "adr.panes";
const DEFAULTS = { left: 300, right: 460 };
const MIN = { left: 200, right: 320 };
const MAX = { left: 520, right: 760 };

function loadPanes() {
  try {
    return { ...DEFAULTS, ...(JSON.parse(localStorage.getItem(LS_KEY) || "{}")) };
  } catch {
    return { ...DEFAULTS };
  }
}

export default function Workspace({ health }) {
  const [catalog, setCatalog] = useState([]);
  const [skills, setSkills] = useState([]);
  const [knowledge, setKnowledge] = useState([]);
  const [references, setReferences] = useState([]);
  const [adrs, setAdrs] = useState([]);
  const [activeUid, setActiveUid] = useState(null);
  const [seed, setSeed] = useState(null);

  const [panes, setPanes] = useState(loadPanes());
  const [collapsed, setCollapsed] = useState({ left: false, right: false });
  const [isNarrow, setIsNarrow] = useState(false);
  const drag = useRef(null);

  const refreshAdrs = useCallback(async () => {
    const { adrs } = await api.adrs();
    setAdrs(adrs);
  }, []);

  useEffect(() => {
    api.catalog().then((r) => setCatalog(r.clouds)).catch(() => {});
    api.skills().then((r) => setSkills(r.skills)).catch(() => {});
    api.knowledge().then((r) => setKnowledge(r.docs)).catch(() => {});
    api.references().then((r) => setReferences(r.references)).catch(() => {});
    refreshAdrs().catch(() => {});
  }, [refreshAdrs]);

  // responsive: below 1000px stack vertically, disable resizing
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 1000px)");
    const onChange = () => setIsNarrow(mq.matches);
    onChange();
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  // dragging a resizer
  useEffect(() => {
    function onMove(e) {
      if (!drag.current) return;
      const { side, startX, startW } = drag.current;
      const dx = e.clientX - startX;
      const raw = side === "left" ? startW + dx : startW - dx;
      const w = Math.max(MIN[side], Math.min(MAX[side], raw));
      setPanes((p) => ({ ...p, [side]: w }));
    }
    function onUp() {
      if (drag.current) {
        drag.current = null;
        document.body.classList.remove("resizing");
        setPanes((p) => {
          localStorage.setItem(LS_KEY, JSON.stringify(p));
          return p;
        });
      }
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  function startDrag(side, e) {
    drag.current = { side, startX: e.clientX, startW: panes[side] };
    document.body.classList.add("resizing");
  }

  const onSaved = useCallback(
    async (saved) => {
      await refreshAdrs();
      if (saved && saved.length) setActiveUid(saved[saved.length - 1].uid);
    },
    [refreshAdrs]
  );

  const requestService = useCallback((cloudName, serviceName) => {
    setSeed({ text: `I need an ADR for ${serviceName} on ${cloudName}.`, ts: Date.now() });
  }, []);

  const leftStyle = isNarrow || collapsed.left ? {} : { width: panes.left, flex: "0 0 auto" };
  const rightStyle = isNarrow || collapsed.right ? {} : { width: panes.right, flex: "0 0 auto" };

  return (
    <div className={`layout ${isNarrow ? "narrow" : ""}`}>
      {!collapsed.left && (
        <div className="pane pane-left" style={leftStyle}>
          <Sidebar catalog={catalog} skills={skills} knowledge={knowledge} references={references} onPickService={requestService} />
        </div>
      )}

      {!isNarrow && (
        <Resizer
          side="left"
          collapsed={collapsed.left}
          onToggle={() => setCollapsed((c) => ({ ...c, left: !c.left }))}
          onDown={(e) => startDrag("left", e)}
        />
      )}

      <div className="pane pane-center">
        <Chat
          seed={seed}
          onSaved={onSaved}
          providerReady={health?.llm_ready ?? false}
          keyEnv={health?.llm_key_env || "API key"}
        />
      </div>

      {!isNarrow && (
        <Resizer
          side="right"
          collapsed={collapsed.right}
          onToggle={() => setCollapsed((c) => ({ ...c, right: !c.right }))}
          onDown={(e) => startDrag("right", e)}
        />
      )}

      {!collapsed.right && (
        <div className="pane pane-right" style={rightStyle}>
          <AdrPanel
            adrs={adrs}
            activeUid={activeUid}
            setActiveUid={setActiveUid}
            refreshAdrs={refreshAdrs}
          />
        </div>
      )}
    </div>
  );
}

function Resizer({ side, collapsed, onToggle, onDown }) {
  return (
    <div className="resizer">
      <div className="resizer-bar" onMouseDown={onDown} title="Drag to resize" />
      <button
        className="collapse-btn"
        onClick={onToggle}
        title={collapsed ? "Expand" : "Collapse"}
      >
        {side === "left" ? (collapsed ? "›" : "‹") : collapsed ? "‹" : "›"}
      </button>
    </div>
  );
}
