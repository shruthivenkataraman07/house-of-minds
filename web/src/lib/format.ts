/** Display formatting only. All figures come from the API unchanged. */
export const usd = (v: number | null | undefined, digits = 0): string => {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const s = Math.abs(v).toLocaleString("en-US", { style: "currency", currency: "USD",
    minimumFractionDigits: digits, maximumFractionDigits: digits });
  return v < 0 ? `−${s}` : s;
};
export const signed = (v: number | null | undefined): string =>
  v === null || v === undefined ? "—" : v > 0 ? `+${usd(v)}` : usd(v);
export const compact = (v: number | null | undefined): string => {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const a = Math.abs(v);
  const s = a >= 1e6 ? `$${(a / 1e6).toFixed(1)}M` : a >= 1e3 ? `$${(a / 1e3).toFixed(1)}K` : `$${a.toFixed(0)}`;
  return v < 0 ? `−${s}` : s;
};
export const pct = (v: number | null | undefined, d = 1) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : `${v < 0 && Math.abs(v * 100).toFixed(d) !== (0).toFixed(d) ? "−" : ""}${Math.abs(v * 100).toFixed(d)}%`;
/** A value already in percentage points (e.g. -13.04 → "−13.0%"), with a true minus sign. */
export const pp = (v: number | null | undefined, d = 1, plus = false) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : `${v < 0 ? "−" : plus && v > 0 ? "+" : ""}${Math.abs(v).toFixed(d)}%`;
/** Display-only typography for recorded text: hyphen-minus before a number becomes a true minus. */
export const typo = (s: unknown): string => String(s ?? "").replace(/(^|[\s([,=:])-(?=[$\d.])/g, "$1−");
export const num = (v: number | null | undefined, d = 0) =>
  v === null || v === undefined || Number.isNaN(v) ? "—"
    : v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
export const n = (v: unknown): number => (typeof v === "number" ? v : Number(v));
export const tone = (v: number | null | undefined) =>
  v === null || v === undefined || v === 0 ? "" : v > 0 ? "text-pos" : "text-neg";

export const VERDICT: Record<string, string> = {
  REPLACE_NONE: "Replace none", REPLACE_ALL: "Replace all", REPLACE_SOME: "Replace some",
  INSUFFICIENT_EVIDENCE: "Insufficient evidence", RETIRED_ALREADY: "Retired",
  DO_NOT_REPLACE_INSPECT: "Inspect", DO_NOT_REPLACE_NOT_ECONOMIC: "Not economic",
  DO_NOT_REPLACE_EXPOSURE: "Limited exposure", REPLACE_JUSTIFIED_CONDITIONAL: "Replace (conditional)",
};
export const verdict = (v: string | null | undefined) =>
  v ? VERDICT[v] ?? v.replaceAll("_", " ").toLowerCase() : "—";

export const OPTION: Record<string, string> = {
  manager_proposal_lease: "Manager · lease", manager_proposal_buy: "Manager · buy 10",
  house_of_minds_evidence: "Recommended", house_of_minds_conditional: "Conditional upside",
  house_of_minds_with_replacements_allowed: "Replacements allowed", no_action: "No action",
};
const ACTION: Record<string, string> = {
  "INV-PROMO": "Promotion weekend", "INV-INSPECT-M1158": "Inspect M-1158",
  "INV-MOVE-M-1154-Z-PIT": "Move M-1154 → Center Pit", "INV-MOVE-M-1184-Z-PIT": "Move M-1184 → Center Pit",
};
export function allocation(a: string | null | undefined): string {
  if (!a || a === "HOLD") return "Hold";
  const parts = a.split(";").map((x) => {
    const m = x.match(/^(.*)x(\d+)$/);
    return m ? { id: m[1], q: +m[2] } : { id: x, q: 1 };
  });
  const leases = parts.filter((p) => p.id.startsWith("INV-REPLACE-LEASE")).length;
  const buys = parts.filter((p) => p.id.includes("REPLACE-BUY")).reduce((s, p) => s + p.q, 0);
  const rest = parts.filter((p) => !p.id.includes("REPLACE"))
    .map((p) => `${ACTION[p.id] ?? p.id.replace(/^INV-/, "")}${p.q > 1 ? ` ×${p.q}` : ""}`);
  return [...(leases ? [`Lease ${leases} replacements`] : []), ...(buys ? [`Buy ${buys} machines`] : []), ...rest]
    .join(" · ") || a;
}
