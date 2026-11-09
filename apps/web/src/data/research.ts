import { createContext, createElement, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { ResearchRelease } from "./types";

export interface ResearchLoader {
  currentId: (s: AbortSignal) => Promise<string | null>;
  load: (id: string, s: AbortSignal) => Promise<ResearchRelease>;
}

async function getJson(url: string, signal: AbortSignal) {
  const r = await fetch(url, { signal, cache: "no-store" });
  if (!r.ok) throw new Error(`${url} → HTTP ${r.status}`);
  return r.json();
}

export const defaultResearchLoader: ResearchLoader = {
  currentId: async (s) => (await getJson("/api/current", s)).research_release_id ?? null,
  load: async (id, s) => {
    const [manifest, research, method, status] = await Promise.all(
      ["manifest", "research", "method", "status"].map((f) => getJson(`/releases/${id}/${f}.json`, s)));
    if (manifest.release_id !== id || !Array.isArray(research?.snapshots)) throw new Error("研究发布结构错误");
    return { manifest, research, method, status };
  },
};

export interface ResearchState {
  phase: "loading" | "ready" | "empty" | "error";
  release: ResearchRelease | null;
  error: string | null;
  reload: () => void;
}
const Ctx = createContext<ResearchState | null>(null);

export function ResearchProvider({ children, loader = defaultResearchLoader }: { children: ReactNode; loader?: ResearchLoader }) {
  const [st, setSt] = useState<Omit<ResearchState, "reload">>({ phase: "loading", release: null, error: null });
  const seq = useRef(0);
  const ctl = useRef<AbortController | null>(null);
  const reload = useCallback(() => {
    const my = ++seq.current;
    ctl.current?.abort();
    const ac = new AbortController();
    ctl.current = ac;
    (async () => {
      try {
        const id = await loader.currentId(ac.signal);
        if (my !== seq.current) return;
        if (id === null) return setSt({ phase: "empty", release: null, error: null });
        const rel = await loader.load(id, ac.signal);
        if (my !== seq.current) return;
        setSt({ phase: "ready", release: rel, error: null });
      } catch (e) {
        if (my !== seq.current || (e as Error).name === "AbortError") return;
        setSt((s) => ({ ...s, phase: s.release ? "ready" : "error", error: (e as Error).message }));
      }
    })();
  }, [loader]);
  useEffect(() => { reload(); return () => ctl.current?.abort(); }, [reload]);
  const value = useMemo(() => ({ ...st, reload }), [st, reload]);
  return createElement(Ctx.Provider, { value }, children);
}

export function useResearch(): ResearchState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useResearch 需在 ResearchProvider 内使用");
  return v;
}
