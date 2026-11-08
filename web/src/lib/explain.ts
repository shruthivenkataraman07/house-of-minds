/**
 * Plain-language explanations for a casino manager. One source for every term the dashboard
 * uses, so the same idea is always described the same way. Definitions follow the data
 * contracts (contracts/dashboard_contracts.json); none of this text carries numbers.
 */
export interface Term { term: string; plain: string; example?: string }

export const GLOSSARY: Record<string, Term> = {
  wagered: { term: "Amount wagered", plain: "All the money players bet into the machines (the industry calls this coin-in)." },
  casino_win: { term: "Casino win", plain: "What the casino actually kept: amount wagered minus prizes paid out. It moves with luck from day to day." },
  expected_win: { term: "Expected casino win", plain: "What the casino should win on average, given how much was bet and each game’s built-in payout rate (the industry calls this theo). Luck cancels out, so it is the fairest measure of how busy a machine really was.", example: "$100,000 wagered on a game that pays back 92% has an expected win of $8,000." },
  payout_rate: { term: "Expected payout rate", plain: "The share of each dollar bet that a game is designed to pay back to players over time (RTP)." },
  share_kept: { term: "Share of wagers kept", plain: "Casino win divided by amount wagered (hold). We add up all the days first and divide once, so busy days count more than quiet ones." },
  machine_hour: { term: "Available machine-hour", plain: "One hour in which a machine was switched on and playable. Measuring per available hour removes the effect of machines being broken, removed or newly installed." },
  luck: { term: "Payout luck", plain: "The difference between what a machine actually won and what it should have won. Over months it averages out; in the short run it can be large." },
  luck_z: { term: "Luck score (z-score)", plain: "Payout luck measured in typical swings. Between −2 and +2 is ordinary; beyond ±3 is rare enough to look into.", example: "−4.6 means the machine paid out far more than chance would normally allow." },
  p_value: { term: "p-value", plain: "How likely a result this extreme would be if nothing unusual were going on. Below 0.001 means less than a 1-in-1,000 chance." },
  multiple_testing: { term: "Correction for checking many machines", plain: "With 310 machines, a few will look odd by pure chance. We therefore require stronger evidence before flagging any single one (Bonferroni correction: the p-value is multiplied by the number of machines)." },
  paying_spins: { term: "Paying-spin test", plain: "Compares how often a machine paid out anything with how often its game is designed to. A large, consistent gap points to a meter or paytable problem, not luck (an exact binomial test)." },
  comparable: { term: "Comparable machines", plain: "Machines with the same game in the same zone, leaving out the machine itself. 1.00× means it earns exactly like its comparable machines; 0.90× means 10% less." },
  fair_rank: { term: "Rank vs comparable machines", plain: "Where a machine stands among all 310 on expected win per available hour against its comparable machines. 1 is the weakest, 310 the strongest." },
  simulation: { term: "Payout simulation", plain: "We replay the six months 2,000 times with fresh random payouts, keeping how much was played fixed, and count how often each machine still lands in the lowest 10. It shows how much of the ranking is luck (a Monte Carlo simulation)." },
  gap_breakdown: { term: "Earnings gap breakdown", plain: "Splits the difference between a machine and a typical machine into luck, time on the floor, location, game choice and the machine itself. The parts add up exactly to the total, but they describe where the gap sits, not what caused it." },
  gap_capture: { term: "Gap capture", plain: "How much of the difference between a machine and the best machine in its zone a new title would win back. Nobody has measured this, so we test 25%, 50% and 100%." },
  cannibalization: { term: "Cannibalization", plain: "The share of a new machine’s extra play that is simply taken from the machines next to it." },
  net_benefit: { term: "Estimated net benefit", plain: "The extra July earnings an action is expected to bring, after its cost, revenue share and comp costs. It is a planning estimate, not booked profit." },
  break_even: { term: "Break-even", plain: "The value at which a plan earns back exactly what it costs. Below it, the plan loses money." },
  ci: { term: "95% confidence range", plain: "The range that very likely contains the true effect, given the data. A narrow range means a precise estimate." },
  event_study: { term: "Before/during/after comparison", plain: "Compares the affected area with the rest of the casino before, during and after an event, so casino-wide ups and downs (season, weekday) cancel out." },
  holdout: { term: "Holdout test", plain: "Data the forecast never saw while it was being built (May–June). Testing on it shows how the model would do on future days." },
  baseline: { term: "Baseline forecast", plain: "A simple rule to beat: predict each day as the average of the same weekday so far." },
  mae: { term: "Average miss (MAE)", plain: "On average, how many dollars the forecast was off per day, ignoring whether it was too high or too low." },
  rmse: { term: "Big-miss measure (RMSE)", plain: "Like the average miss, but large misses count much more. Useful when a few bad days matter most." },
  bias: { term: "Bias", plain: "Whether the forecast runs too high or too low on average: forecast minus actual. Positive means the forecast was too high; negative means actual days came in above it." },
  coverage: { term: "80% range hit rate", plain: "The model gives a range it expects to contain the real value 80% of the time. This shows how often it actually did; well below 80% means the ranges are too narrow." },
  regret: { term: "Regret", plain: "How much more the best plan for a scenario would earn than the plan we chose. Zero means our plan was already the best." },
  contribution: { term: "Contribution", plain: "Expected win after revenue share with game vendors and the cost of loyalty rewards." },
  tracked: { term: "Tracked play", plain: "Play by guests who used a loyalty card. It is about two-thirds of all wagering, so these figures are never mixed with whole-floor totals." },
};

/** Plain names for the optimizer's assumption IDs. */
export const ASSUMPTION: Record<string, string> = {
  A01_inspect_fix_probability: "Chance the inspection fixes M-1158",
  A02_m1158_loss_per_day: "Daily loss from M-1158’s fault",
  A03_wayfinding_net_uplift: "Extra Back Forty play from better signage",
  A04_preventive_effectiveness: "Downtime prevented by maintenance sweeps",
  A05_tech_downtime_reduction: "Downtime saved by an extra technician",
  A06_comp_play_response: "Play lost if comps are cut",
  A07_comp_saving_rate: "Comp cost saved by a comp change",
  A08_promo_excess_theo_per_day: "Extra expected win per promotion day",
  A09_move_location_transfer: "Share of demand that follows a moved machine",
  A10_replacement_gap_capture: "Gap a new title wins back",
};

/** Plain wording for the evidence registry's classifications. */
export const EVIDENCE_KIND: Record<string, string> = {
  VERIFIED_ARITHMETIC: "Recalculated from source data",
  VERIFIED_OBSERVATION: "Observed in source data",
  STATISTICAL_ESTIMATE: "Estimated from past data",
  "STATISTICAL_ESTIMATE (associational)": "Estimated from past data (association, not proven cause)",
  PLANNING_ASSUMPTION: "Planning assumption (not measured)",
  MODELED_SCENARIO: "Modeled what-if",
  CAUSAL_EFFECT_NOT_IDENTIFIED: "Cause not proven",
  UNRESOLVED: "Not yet resolved",
  RETRACTED: "Withdrawn after review",
};
export const evidenceKind = (k: string | null | undefined) =>
  !k ? "—" : EVIDENCE_KIND[k] ?? EVIDENCE_KIND[k.replace(/_/g, "_")] ?? k.replaceAll("_", " ").toLowerCase();

/** Each council check, phrased as the question it answers. */
export const CHECK_QUESTION: Record<string, string> = {
  "review:luck": "Is the low total just payout luck?",
  "review:location": "Is it the location rather than the machine?",
  "review:exposure": "Was it on the floor long enough to judge?",
  "review:hit_rate": "Does it pay out as often as its game should?",
  "review:economics": "Would a replacement pay for itself in July?",
};
