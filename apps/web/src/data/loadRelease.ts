import type { LocalRelease } from "./types";

const FILES = ["manifest", "observations", "method", "status", "checks"] as const;

async function getJson(url: string, signal: AbortSignal): Promise<any> {
  const r = await fetch(url, { signal, cache: "no-store" });
  if (!r.ok) throw new Error(`${url} → HTTP ${r.status}`);
  return r.json();
}

/** 取当前发布 ID；无发布返回 null。 */
export async function loadCurrentId(signal: AbortSignal): Promise<string | null> {
  const j = await getJson("/api/current", signal);
  return j.release_id ?? null;
}

/** 一次性读取同一 release 的全部文件并校验；任一失败整体失败，绝不混合版本。 */
export async function loadRelease(releaseId: string, signal: AbortSignal): Promise<LocalRelease> {
  const base = `/releases/${releaseId}`;
  const parts = await Promise.all(FILES.map((f) => getJson(`${base}/${f}.json`, signal)));
  const [manifest, observations, method, status, checks] = parts;
  if (manifest.release_id !== releaseId) throw new Error("release_id 不一致");
  if (!Array.isArray(observations?.series)) throw new Error("observations 结构错误");
  if (!Array.isArray(checks?.checks)) throw new Error("checks 结构错误");
  return { manifest, observations, method, status, checks };
}
