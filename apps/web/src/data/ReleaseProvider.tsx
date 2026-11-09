import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { loadCurrentId, loadRelease } from "./loadRelease";
import type { LocalRelease } from "./types";

export interface ReleaseState {
  phase: "loading" | "ready" | "empty" | "error";
  /** 当前整屏使用的唯一 release；失败时保留上一可核实版本 */
  release: LocalRelease | null;
  error: string | null;
  reload: () => void;
}

const Ctx = createContext<ReleaseState | null>(null);

export interface Loader {
  currentId: (s: AbortSignal) => Promise<string | null>;
  load: (id: string, s: AbortSignal) => Promise<LocalRelease>;
}
const defaultLoader: Loader = { currentId: loadCurrentId, load: loadRelease };

export function ReleaseProvider({ children, loader = defaultLoader }: { children: ReactNode; loader?: Loader }) {
  const [state, setState] = useState<Omit<ReleaseState, "reload">>({ phase: "loading", release: null, error: null });
  const seq = useRef(0);
  const ctl = useRef<AbortController | null>(null);

  const reload = useCallback(() => {
    const my = ++seq.current;
    ctl.current?.abort();
    const ac = new AbortController();
    ctl.current = ac;
    setState((s) => ({ ...s, phase: s.release ? s.phase : "loading", error: null }));
    (async () => {
      try {
        const id = await loader.currentId(ac.signal);
        if (my !== seq.current) return; // 迟到响应丢弃
        if (id === null) return setState({ phase: "empty", release: null, error: null });
        const rel = await loader.load(id, ac.signal);
        if (my !== seq.current) return;
        setState({ phase: "ready", release: rel, error: null }); // 一次性提交给全部组件
      } catch (e) {
        if (my !== seq.current || (e as Error).name === "AbortError") return;
        setState((s) => ({ ...s, phase: s.release ? "ready" : "error", error: (e as Error).message }));
      }
    })();
  }, [loader]);

  useEffect(() => {
    reload();
    return () => ctl.current?.abort();
  }, [reload]);

  const value = useMemo(() => ({ ...state, reload }), [state, reload]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useRelease(): ReleaseState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useRelease 需在 ReleaseProvider 内使用");
  return v;
}
