import { useEffect, useState } from "react";
import { ReleaseProvider, useRelease, type Loader } from "./data/ReleaseProvider";
import { ResearchProvider, useResearch, type ResearchLoader } from "./data/research";
import { PublishedPage } from "./pages/PublishedPage";
import { ResearchPage } from "./pages/ResearchPage";
import "./styles.css";

function useHash() {
  const [h, setH] = useState(() => window.location.hash || "#/");
  useEffect(() => {
    const f = () => setH(window.location.hash || "#/");
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  return h;
}

function Header({ research }: { research: boolean }) {
  const pub = useRelease().release;
  const res = useResearch().release;
  const modes = (research ? res : pub)?.manifest.data_modes ?? [];
  const mode = modes.length === 0 ? null : modes.includes("synthetic") ? "演示数据" : "真实数据";
  return (
    <header className="header">
      <h1>纳指100估值看板</h1>
      <div className="badges">
        <span className="badge">本机个人使用</span>
        {mode && <span className={`badge ${mode === "演示数据" ? "demo" : ""}`}>{mode}</span>}
      </div>
      <nav aria-label="主导航">
        <a href="#/" aria-current={research ? undefined : "page"}>整体估值参考</a>
        <a href="#/research" aria-current={research ? "page" : undefined}>自主计算研究</a>
      </nav>
    </header>
  );
}

function Expose({ fn }: { fn?: (reload: () => void) => void }) {
  const { reload } = useRelease();
  useEffect(() => { fn?.(reload); }, [fn, reload]);
  return null;
}

function ExposeResearch({ fn }: { fn?: (reload: () => void) => void }) {
  const { reload } = useResearch();
  useEffect(() => { fn?.(reload); }, [fn, reload]);
  return null;
}

export default function App({ loader, researchLoader, now, exposeReload, exposeResearchReload }: {
  loader?: Loader; researchLoader?: ResearchLoader; now?: Date; exposeReload?: (r: () => void) => void; exposeResearchReload?: (r: () => void) => void }) {
  const hash = useHash();
  const research = hash.startsWith("#/research");
  return (
    <ReleaseProvider loader={loader}>
      <ResearchProvider loader={researchLoader}>
        <Expose fn={exposeReload} />
        <ExposeResearch fn={exposeResearchReload} />
        <Header research={research} />
        <main>{research ? <ResearchPage /> : <PublishedPage now={now ?? new Date()} />}</main>
      </ResearchProvider>
    </ReleaseProvider>
  );
}
