/** 展示格式化：不重算，只把后端十进制字符串变成文字。 */
export function cmpDecimal(a: string, b: string): number {
  const norm = (s: string) => {
    const neg = s.startsWith("-");
    const [i, f = ""] = s.replace("-", "").split(".");
    return { neg, i: i.replace(/^0+(?=\d)/, ""), f: f.replace(/0+$/, "") };
  };
  const x = norm(a), y = norm(b);
  const zero = (n: ReturnType<typeof norm>) => n.i === "0" && n.f === "";
  if (zero(x) && zero(y)) return 0;
  if (x.neg !== y.neg) return x.neg ? -1 : 1;
  const sgn = x.neg ? -1 : 1;
  if (x.i.length !== y.i.length) return sgn * (x.i.length < y.i.length ? -1 : 1);
  if (x.i !== y.i) return sgn * (x.i < y.i ? -1 : 1);
  const n = Math.max(x.f.length, y.f.length);
  const xf = x.f.padEnd(n, "0"), yf = y.f.padEnd(n, "0");
  return xf === yf ? 0 : sgn * (xf < yf ? -1 : 1);
}

export const fmtPe = (s: string | null) => (s === null ? null : `${Number(s).toFixed(2)} 倍`);

/** 小数 → 两位百分数；极小非零不显示为 0。 */
export function fmtPct(s: string | null): string | null {
  if (s === null) return null;
  const v = Number(s);
  if (v === 0) return "0.00%";
  const p = v * 100;
  if (Math.abs(p) < 0.005) return v > 0 ? "<0.01%" : ">-0.01%";
  return `${p.toFixed(2)}%`;
}

export function fmtPoints(s: string | null): string | null {
  if (s === null) return null;
  const v = Number(s);
  if (v === 0) return "0.00 pt";
  if (Math.abs(v) < 0.005) return v > 0 ? "<0.01 pt" : ">-0.01 pt";
  return `${v.toFixed(2)} pt`;
}

export const REASON: Record<string, string> = {
  MISSING_FIELD: "缺少有效盈利/价格", PATH_CONFLICT: "多路径冲突", BAD_PRICE: "价格无效", PE_ZERO_NOT_ZERO_EARNINGS: "PE=0 不能推导盈利",
  PROFIT_PATH_UNVERIFIED: "利润/市值路径未验证", incomplete: "盈利未完整",
};
export const reasonText = (flags: string[]) => (flags.length ? flags.map((f) => REASON[f] ?? f).join("、") : REASON.MISSING_FIELD);
