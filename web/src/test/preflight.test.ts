import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { loadDataset, loadManifest } from "../lib/data";
import { type Contract, route } from "../lib/nlp/router";
import { DATASET_SCHEMAS, type DatasetName, Passport, PortfolioLine } from "../lib/schemas";
import { initialContext, useDecisionStore } from "../lib/store";

const contract = JSON.parse(
  readFileSync(path.join(process.cwd(), "public/data/current/ask_the_house_contract.json"), "utf8"),
) as Contract;

describe("snapshot contracts", () => {
  it("manifest is valid and matches the warehouse", () => {
    const m = loadManifest();
    expect(m.snapshot_id).toMatch(/^chf-v1:/);
    expect(m.files.every((f) => f.rows === f.warehouse_rows)).toBe(true);
  });

  it.each(Object.keys(DATASET_SCHEMAS) as DatasetName[])("%s parses with its schema", (name) => {
    expect(loadDataset(name).length).toBeGreaterThan(0);
  });

  it("financial invariants hold across datasets", () => {
    const lines = loadDataset("dash_investment_portfolios");
    const byPf = new Map<string, { cost: number; total: number }>();
    for (const l of lines) {
      const k = `${l.run_id}|${l.portfolio_id}|${l.role}`;
      const e = byPf.get(k) ?? { cost: 0, total: l.total_cost };
      e.cost += l.line_cost;
      byPf.set(k, e);
    }
    for (const v of byPf.values()) expect(Math.abs(v.cost - v.total)).toBeLessThan(0.01);
    const pp = loadDataset("dash_decision_passports");
    const evid = pp.filter((p) => p.portfolio_mode === "evidence_supported");
    expect(evid.map((p) => p.action_type_id)).toEqual(["A-PROMO"]);
    expect(new Set(pp.filter((p) => p.portfolio_mode === "conditional").map((p) => p.action_type_id)).size)
      .toBeLessThanOrEqual(3);
  });

  it("schemas reject corrupted financial rows", () => {
    const good = loadDataset("dash_decision_passports")[0];
    expect(Passport.safeParse({ ...good, portfolio_total_cost: 120_000 }).success).toBe(false);
    const line = loadDataset("dash_investment_portfolios")[0];
    expect(PortfolioLine.safeParse({ ...line, line_cost: line.line_cost + 1 }).success).toBe(false);
  });
});

describe("shared decision context", () => {
  it("selects, navigates and resets while keeping the snapshot", () => {
    const s = useDecisionStore.getState();
    s.setSnapshot("chf-v1:bc5e8ccc5d88a490");
    s.select({ machineId: "M-1158", zoneId: "Z-B40" });
    s.navigate("evidence_observatory");
    expect(useDecisionStore.getState().machineId).toBe("M-1158");
    useDecisionStore.getState().reset();
    const r = useDecisionStore.getState();
    expect(r.machineId).toBe(initialContext.machineId);
    expect(r.snapshotId).toBe("chf-v1:bc5e8ccc5d88a490");
  });
});

describe("Ask the House router (deterministic)", () => {
  it.each(contract.test_contracts)("$question", (tc) => {
    const r = route(tc.question, contract);
    if (tc.expected.startsWith("UNAVAILABLE")) expect(r.status).toBe("UNAVAILABLE");
    else if (tc.expected.startsWith("UNCERTAIN")) expect(r.status).toBe("UNCERTAIN");
    else {
      expect(r.status).toBe("OK");
      if (r.status === "OK") expect(r.intent).toBe(tc.intent);
    }
  });

  it("never invents ids and rejects unknown entities", () => {
    expect(route("Show M-0000", contract).status).toBe("UNAVAILABLE");
    expect(route("Evidence for CLM-NOT-REAL", contract).status).toBe("UNAVAILABLE");
    expect(route("What is the weather in Paris?", contract).status).toBe("UNSUPPORTED");
    const ok = route("Show machines in back forty", contract);
    expect(ok.status === "OK" && ok.params.zone).toBe("Z-B40");
  });
});
