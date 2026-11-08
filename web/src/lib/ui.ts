"use client";
/**
 * Navigation state: identifiers only (numbers always come from the API). A history stack lets
 * evidence and detail drawers return to the previous view with its selection intact.
 */
import { create } from "zustand";

export const OFFICIAL = { from: "2025-01-01", to: "2025-06-30" } as const;

export type ViewId = "overview" | "machines" | "operations" | "council" | "scenarios" | "investment"
  | "evidence" | "validation";
export const VIEWS: { id: ViewId; label: string }[] = [
  { id: "overview", label: "Overview" }, { id: "machines", label: "Machines" },
  { id: "operations", label: "Operations" }, { id: "council", label: "Council" },
  { id: "scenarios", label: "Scenarios" }, { id: "investment", label: "Investment" },
  { id: "evidence", label: "Evidence" }, { id: "validation", label: "Validation" },
];

export interface UIState {
  view: ViewId;
  tab: string | null;
  machineId: string | null;
  bankId: string | null;
  zoneId: string | null;
  tier: string | null;
  period: { from: string; to: string };
  evidenceId: string | null;
  askOpen: boolean;
  history: Omit<UIState, "history" | "askOpen">[];
}

interface Actions {
  go: (view: ViewId, patch?: Partial<Omit<UIState, "history" | "view">>) => void;
  set: (patch: Partial<Omit<UIState, "history">>) => void;
  back: () => void;
  openEvidence: (id: string) => void;
}

export const initialUI: UIState = {
  view: "overview", tab: null, machineId: null, bankId: null, zoneId: null, tier: null,
  period: { ...OFFICIAL }, evidenceId: null, askOpen: false, history: [],
};

function snap(s: UIState) {
  const { history: _h, askOpen: _a, ...rest } = s;
  void _h; void _a;
  return rest;
}

export const useUI = create<UIState & Actions>()((set, get) => ({
  ...initialUI,
  go: (view, patch) => set((s) => ({ history: [...s.history.slice(-19), snap(s)], view, tab: null,
    evidenceId: null, ...patch })),
  set: (patch) => set(patch),
  back: () => {
    const h = get().history;
    if (!h.length) return;
    set({ ...h[h.length - 1], history: h.slice(0, -1) });
  },
  openEvidence: (id) => set((s) => ({ history: [...s.history.slice(-19), snap(s)], evidenceId: id })),
}));
