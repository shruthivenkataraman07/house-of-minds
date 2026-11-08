import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, getJSON, postJSON } from "../lib/api";
import { allocation, compact, pct, signed, usd, verdict } from "../lib/format";
import { OFFICIAL, VIEWS, initialUI, useUI } from "../lib/ui";

afterEach(() => vi.unstubAllGlobals());

describe("API client", () => {
  it("calls the versioned API, caches identical GETs and surfaces structured errors", async () => {
    const calls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      calls.push(url);
      if (url.includes("missing")) {
        return { ok: false, status: 404, statusText: "Not Found",
          json: async () => ({ error: "request_failed", detail: "machine M-9999 not found", recovery: "Check the identifier" }) };
      }
      return { ok: true, status: 200, json: async () => ({ meta: { snapshot_id: "chf-v1:x" }, data: { ok: 1 } }) };
    }));
    const a = await getJSON<{ data: { ok: number } }>("/executive");
    const b = await getJSON<{ data: { ok: number } }>("/executive");
    expect(a).toBe(b);
    expect(calls).toEqual(["/api/v1/executive"]);
    await expect(getJSON("/machines/missing")).rejects.toMatchObject({ status: 404, detail: "machine M-9999 not found" });
    await expect(getJSON("/machines/missing")).rejects.toBeInstanceOf(ApiError); // failed requests are not cached
    expect(calls.filter((c) => c.includes("missing"))).toHaveLength(2);
  });

  it("posts questions to /api/v1/ask", async () => {
    const f = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ status: "OK" }) }));
    vi.stubGlobal("fetch", f);
    await postJSON("/ask", { question: "Explain M-5076" });
    expect(f).toHaveBeenCalledWith("/api/v1/ask", expect.objectContaining({ method: "POST", body: JSON.stringify({ question: "Explain M-5076" }) }));
  });
});

describe("formatting preserves units and signs", () => {
  it("formats money, percentages and verdicts", () => {
    expect(usd(-15843.0161)).toBe("−$15,843");
    expect(signed(62237.36)).toBe("+$62,237");
    expect(compact(248905219.25)).toBe("$248.9M");
    expect(pct(0.0949684991, 2)).toBe("9.50%");
    expect(usd(null)).toBe("—");
    expect(verdict("REPLACE_NONE")).toBe("Replace none");
  });
  it("describes allocations without inventing actions", () => {
    expect(allocation("INV-PROMOx2")).toBe("Promotion weekend ×2");
    expect(allocation("HOLD")).toBe("Hold");
    expect(allocation("INV-REPLACE-LEASE-M-1017x1;INV-REPLACE-LEASE-M-1035x1")).toBe("Lease 2 replacements");
  });
});

describe("navigation state", () => {
  it("has nine views with Answers last and Overview first", () => {
    expect(VIEWS.map((v) => v.id)).toEqual(["overview", "machines", "operations", "council", "scenarios", "investment", "evidence", "validation", "answers"]);
  });
  it("evidence drawer returns to the previous view and selection", () => {
    useUI.setState({ ...initialUI });
    useUI.getState().go("machines", { machineId: "M-1017" });
    useUI.getState().openEvidence("M-1017");
    expect(useUI.getState().evidenceId).toBe("M-1017");
    useUI.getState().back();
    expect(useUI.getState().view).toBe("machines");
    expect(useUI.getState().machineId).toBe("M-1017");
    expect(useUI.getState().evidenceId).toBeNull();
  });
  it("defaults to the official window", () => {
    expect(initialUI.period).toEqual(OFFICIAL);
  });
});

describe("missing values are never shown as zero", () => {
  it("renders an em dash for null, undefined and NaN", () => {
    for (const v of [null, undefined, Number.NaN]) {
      expect(usd(v)).toBe("—");
      expect(signed(v as number | null | undefined)).not.toBe("$0");
      expect(pct(v)).toBe("—");
      expect(compact(v)).toBe("—");
    }
  });
});
