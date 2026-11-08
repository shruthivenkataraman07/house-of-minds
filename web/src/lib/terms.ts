/**
 * Business-language terminology. One place for every user-facing metric name, checked
 * against the data definitions (contracts/dashboard_contracts.json).
 */
export const TERM = {
  coin_in: "Amount wagered",
  house_win: "Casino win after payouts",          // observed, not profit
  theo: "Expected casino win",                     // coin-in x (1 - expected payout rate)
  theo_per_hour: "Expected win per available hour",
  rtp: "Expected payout rate",
  hold: "Share of wagers kept",
  downtime: "Machine downtime",
  availability: "Time machines were available",
  fair_rank: "Rank vs comparable machines",
  earnings_rank: "Rank by casino win",
  net: "Estimated additional net benefit",         // modeled July contribution minus cost
  contribution: "Estimated additional contribution",
  comp_cost: "Cost of loyalty rewards",
  theo_at_risk: "Expected win at risk",            // modeled opportunity, not observed loss
  luck: "Payout luck",
  lease_net: "July lease net benefit",
} as const;

/** Weakness position on one shared scale: 1 = weakest of 310. */
export const weaknessFromEarnings = (rankRaw: number) => rankRaw;           // 1 = lowest casino win
export const weaknessFromFair = (rankVsPeers: number) => rankVsPeers;      // 1 = weakest vs comparable machines
