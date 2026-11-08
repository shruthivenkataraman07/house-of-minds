import katex from "katex";
import { describe, expect, it } from "vitest";

import { F, tn } from "../lib/formulas";

const withValues = [
  F.machineWin(519610, 503813.75, 15796.25, 0.9, 51961), F.actionNet(2, 15000, 92237, 62237, 0, 0), F.actionNet(1, 1200, 2773.133133, 1549.394537, 23.738596, 0), F.portfolioNet(11197, 27040, -15843, -27399, -4287),
  F.casinoWin(), F.expectedWin(), F.perHour(1000, 10, 100), F.luckZ(15796, 51961, 7913, -4.57), F.payingSpins(260144, 674454, 0.31544, 0),
  F.peerIndex(1.088, 9), F.decomposition(-62810.6, [-36164.75, 181.4, -27987.8, -2623.4, 3783.95]), F.simulation(0.014),
  F.leaseNet(-2720, -1993, 3380), F.promotion(5800, 5281), F.downtime(1234, 5678), F.comps(), F.gini(0.81),
  F.forecastErrors(5552, 7316, 1459, 0.689, 61), F.improvement(6699, 5552, 17.1), F.netBenefit(), F.eventStudy(-31.2), F.decisionFlip(5015.87, 62237.36), F.noiseRatio(5015.87, 4649, 1.08),
];

describe("formula templates", () => {
  it("every template, variable symbol and substitution is valid TeX", () => {
    for (const s of withValues) {
      for (const tex of [s.tex, s.calc, ...s.vars.map((v) => v[0])].filter(Boolean) as string[]) {
        expect(() => katex.renderToString(tex, { throwOnError: true, strict: "ignore", displayMode: true }), `${s.title}: ${tex}`).not.toThrow();
      }
      expect(s.fallback.length).toBeGreaterThan(10);
    }
  });

  it("omits the substituted calculation when an operand is missing", () => {
    expect(F.luckZ().calc).toBeNull();
    expect(F.luckZ(1, 2, undefined, 3).calc).toBeNull();
    expect(F.decomposition(-10, [1, 2, 3]).calc).toBeNull();
    expect(F.payingSpins(1, undefined, 0.3).calc).toBeNull();
    expect(F.forecastErrors(1, 2, 3).calc).toBeNull();
    expect(F.luckZ().result).toBeUndefined();
  });

  it("substitutes the recorded values unchanged", () => {
    const z = F.luckZ(15796.25, 51961, 7913.26, -4.5701);
    expect(z.calc).toContain("15{,}796");
    expect(z.calc).toContain("-4.57");
    expect(F.actionNet(2, 15000, 92237.36, 62237.36, 0, 0).calc).toContain("62{,}237");
    // M-1158 inspection: the downtime term reconciles contribution − cost to the recorded net
    expect(F.actionNet(1, 1200, 2773.133133, 1549.394537, 23.738596, 0).calc).toContain("23.74");
    expect(F.actionNet(1, 1200, 2773.133133, 1549.394537).calc).toBeNull();
    expect(tn(-1234.5, 1)).toBe("-1{,}234.5");
    expect(tn(undefined)).toBe("?");
  });

  it("escapes nothing from outside: templates contain no HTML", () => {
    for (const s of withValues) expect(`${s.tex}${s.calc ?? ""}`).not.toMatch(/[<>]/);
  });
});
