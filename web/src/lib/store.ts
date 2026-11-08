"use client";
/**
 * Shared decision context (Step 6 DASHBOARD_DATA_CONTRACT). Every view reads and writes the
 * same selection so cross-view navigation (and Ask the House actions) stay consistent.
 * The store holds identifiers only; numbers always come from the verified snapshot.
 */
import { create } from "zustand";

export type View =
  | "command_center"
  | "council_chamber"
  | "whisper_network"
  | "evidence_observatory"
  | "parallel_universes"
  | "verdict";

export interface DecisionContext {
  snapshotId: string | null;
  view: View;
  period: { from: string; to: string };
  zoneId: string | null;
  machineId: string | null;
  portfolioIds: string[];
  scenarioId: string | null;
  claimId: string | null;
  councilEventId: string | null;
  evaluationRunId: string | null;
}

export interface DecisionActions {
  setSnapshot: (id: string) => void;
  navigate: (view: View) => void;
  select: (patch: Partial<Omit<DecisionContext, "snapshotId">>) => void;
  reset: () => void;
}

export const initialContext: DecisionContext = {
  snapshotId: null,
  view: "command_center",
  period: { from: "2025-01-01", to: "2025-06-30" },
  zoneId: null,
  machineId: null,
  portfolioIds: [],
  scenarioId: null,
  claimId: null,
  councilEventId: null,
  evaluationRunId: null,
};

export const useDecisionStore = create<DecisionContext & DecisionActions>()((set) => ({
  ...initialContext,
  setSnapshot: (id) => set({ snapshotId: id }),
  navigate: (view) => set({ view }),
  select: (patch) => set(patch),
  reset: () => set((s) => ({ ...initialContext, snapshotId: s.snapshotId })),
}));
