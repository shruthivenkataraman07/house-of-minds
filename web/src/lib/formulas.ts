/**
 * Controlled formula templates. Each mirrors the backend calculation it describes
 * (analytics/*.py, backend/services/*.py). Substituted values are passed in from API fields
 * only; nothing here computes a business result.
 */
import type { FormulaSpec } from "@/components/math";

/** Number for TeX: thousands separators as {,}, true minus sign. */
export function tn(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "?";
  const s = Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits }).replace(/,/g, "{,}");
  return v < 0 ? `-${s}` : s;
}
const usd = (v: number | null | undefined, d = 0) => `\\$${tn(v, d)}`.replace("\\$-", "-\\$");
const fmtUsd = (v: number) => `${v < 0 ? "−" : ""}$${Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
const has = (...v: (number | null | undefined)[]) => v.every((x) => x !== null && x !== undefined && !Number.isNaN(x));

export const F = {
  machineWin: (coinIn?: number, payout?: number, W?: number, rtp?: number, E?: number): FormulaSpec => ({
    title: "Casino win and expected casino win",
    tex: String.raw`\begin{gathered}W=C-P\\ E=C\times(1-r)\end{gathered}`,
    vars: [["C", "amount wagered on this machine"], ["P", "prizes it paid out"], ["r", "its game’s expected payout rate (RTP)"], ["W", "casino win (what was actually kept)"], ["E", "expected casino win (what the game is built to keep)"]],
    calc: has(coinIn, payout, W, rtp, E)
      ? String.raw`\begin{aligned}W&=${usd(coinIn)}-${usd(payout, 2)}\\&=${usd(W, 2)}\\[4pt] E&=${usd(coinIn)}\times(1-${tn(rtp, 2)})\\&=${usd(E)}\end{aligned}` : null,
    meaning: "Expected win is the fairer measure of play: it does not move with payout luck.",
    fallback: "Casino win = wagered − paid out; expected win = wagered × (1 − payout rate).",
  }),
  actionNet: (q?: number, k?: number, g?: number, net?: number, d?: number, a?: number): FormulaSpec => {
    const D = d ?? 0, A = a ?? 0, terms = has(d);
    const gap = has(q, k, g, net) ? g! + A - D - q! * k! - net! : NaN;
    const ok = Math.abs(gap) <= 0.5;
    return {
      title: "Net benefit of this action",
      tex: String.raw`N=G+A-D-q\times k`,
      vars: [["G", "modeled extra July contribution (after revenue share and comps)"], ["A", "costs avoided by the action"],
        ["D", "expected win lost while the machine is offline for the action (installation, inspection or move downtime)"],
        ["q", "quantity"], ["k", "catalog cost per unit"], ["N", "estimated net benefit"]],
      calc: terms && ok ? String.raw`N=${usd(g)}+${usd(A)}-${usd(D, 2)}-${tn(q)}\times${usd(k)}=${usd(net)}` : null,
      result: !has(q, k, g, net) ? undefined
        : terms && ok ? `Estimated July net ${net! < 0 ? "loss" : "gain"} of ${fmtUsd(Math.abs(net!))}${D > 0 ? `, after ${fmtUsd(Math.round(D * 100) / 100)} of downtime` : ""}.`
        : `Recorded: contribution ${fmtUsd(g!)}, cost ${fmtUsd(q! * k!)}, net ${fmtUsd(net!)}. The cost components needed to reconcile these are not available, so no substitution is shown.`,
      meaning: D > 0 ? "The action takes the machine offline for part of a day; the expected win lost in that time is subtracted. A planning estimate for July, not booked profit."
        : "A planning estimate for July, not booked profit. Its size depends on the listed assumptions.",
      fallback: "Net = contribution + avoided costs − downtime cost − quantity × unit cost.",
    };
  },
  portfolioNet: (g?: number, cost?: number, net?: number, lo?: number, hi?: number, feasible = true): FormulaSpec => ({
    title: "Net benefit of this plan",
    tex: String.raw`\begin{gathered}N=G-K\\ K\le\$100{,}000\end{gathered}`,
    vars: [["G", "modeled extra July contribution of all its actions"], ["K", "total catalog cost"], ["N", "estimated net benefit"]],
    calc: has(g, cost, net) ? String.raw`N=${usd(g)}-${usd(cost)}=${usd(net)}` : null,
    result: !feasible ? `Not modeled: its cost of ${has(cost) ? fmtUsd(cost!) : "?"} exceeds the $100,000 budget, so the optimizer cannot select it.`
      : has(net) ? `${net! < 0 ? `Estimated July net loss of ${fmtUsd(-net!)}` : net! > 0 ? `Estimated July net gain of ${fmtUsd(net!)}` : "No change: $0"}${has(lo, hi) && lo !== hi ? `; range across tested assumptions ${fmtUsd(lo!)} to ${fmtUsd(hi!)}` : ""}.` : undefined,
    meaning: !feasible ? "The exact net is not recorded because the plan breaks the budget constraint."
      : has(net) && net! < 0 ? "The plan is projected to cost more than the extra contribution it brings in July."
      : has(net) && net! > 0 ? "The plan's modeled extra contribution exceeds its cost in July. Modeled, not booked profit."
      : "Nothing is spent and nothing changes; the baseline every plan is compared with.",
    fallback: "Net = modeled contribution − total cost, within the $100,000 budget.",
  }),
  casinoWin: (): FormulaSpec => ({
    title: "Casino win and share of wagers kept",
    tex: String.raw`\begin{gathered}W=\sum_{d}\left(C_d-P_d\right)\\ h=\frac{\sum_{d}W_d}{\sum_{d}C_d}\end{gathered}`,
    vars: [["C_d", "amount wagered on gaming day d"], ["P_d", "prizes paid out on day d"], ["W", "casino win"], ["h", "share of wagers kept (hold)"]],
    meaning: "Totals are added up first and divided once, so busy days count more than quiet ones.",
    fallback: "Casino win = wagered − paid out; share kept = total casino win ÷ total wagered.",
  }),
  expectedWin: (): FormulaSpec => ({
    title: "Expected casino win",
    tex: String.raw`E=\sum_{i} b_i\,\bigl(1-r_{g(i)}\bigr)`,
    vars: [["b_i", "amount bet on spin i"], ["r_g", "expected payout rate of game g (RTP)"], ["E", "expected casino win"]],
    meaning: "What the games are designed to keep on the amount bet. Payout luck averages out of it.",
    fallback: "Expected win = each bet × (1 − the game’s payout rate), added up.",
  }),
  perHour: (wagered?: number, hours?: number, result?: number): FormulaSpec => ({
    title: "Demand per available machine-hour",
    tex: String.raw`\text{demand per hour}=\frac{\sum_{d} C_d}{\sum_{d} A_d}`,
    vars: [["C_d", "amount wagered on day d"], ["A_d", "hours machines were switched on and playable on day d"]],
    calc: has(wagered, hours, result) ? String.raw`\frac{${usd(wagered)}}{${tn(hours)}\ \text{h}}=${usd(result, 2)}\ \text{per hour}` : null,
    meaning: "Removes the effect of machines being broken, removed or newly installed.",
    fallback: "Total wagered ÷ total available machine-hours.",
  }),
  luckZ: (W?: number, E?: number, sd?: number, z?: number): FormulaSpec => ({
    title: "Luck score",
    tex: String.raw`\begin{gathered}z=\frac{W-E}{\sigma}\\ \sigma=\sqrt{\sum_{i} b_i^{2}\,\operatorname{Var}\!\left(m_{g(i)}\right)}\end{gathered}`,
    vars: [["W", "actual casino win"], ["E", "expected casino win"], ["\\sigma", "size of a normal luck swing for this machine"], ["b_i", "bet on spin i"], ["m_g", "payout multiplier of game g (its variance comes from the game’s design)"]],
    calc: has(W, E, sd, z) ? String.raw`z=\frac{${usd(W)}-${usd(E)}}{${usd(sd)}}=${tn(z, 2)}` : null,
    result: has(z) ? `${Math.abs(z!).toFixed(2)} normal swings ${z! < 0 ? "below" : "above"} expectation` : undefined,
    meaning: "Between −2 and +2 is ordinary luck; beyond ±3 is rare enough to investigate. Assumes spins are independent.",
    fallback: "Luck score = (actual win − expected win) ÷ the machine’s normal luck swing.",
  }),
  payingSpins: (hits?: number, spins?: number, p?: number, pAdj?: number): FormulaSpec => ({
    title: "Paying-spin test",
    tex: String.raw`\begin{gathered}H\sim\operatorname{Binomial}(n,\,p_g)\\ p_{\text{adjusted}}=\min\!\left(1,\;310\times p\right)\end{gathered}`,
    vars: [["H", "spins that paid anything"], ["n", "spins played"], ["p_g", "share of spins the game is designed to pay"], ["p", "chance of a result this extreme with nothing wrong"], ["310", "machines checked (correction for testing many)"]],
    calc: has(hits, spins, p) ? String.raw`\begin{gathered}\frac{H}{n}=\frac{${tn(hits)}}{${tn(spins)}}=${tn((hits! / spins!) * 100, 2)}\%\\ \text{designed: }p_g=${tn(p! * 100, 2)}\%\end{gathered}` : null,
    result: has(pAdj) ? (pAdj! < 0.001 ? "adjusted p < 0.001: almost impossible by chance" : `adjusted p = ${pAdj!.toFixed(3)}: within chance`) : undefined,
    fallback: "Paying spins ÷ spins played, compared with the game’s design rate using an exact binomial test.",
  }),
  peerIndex: (idx?: number, n?: number): FormulaSpec => ({
    title: "Performance vs comparable machines",
    tex: String.raw`I_i=\frac{E_i/A_i}{\sum_{j\neq i}E_j\Big/\sum_{j\neq i}A_j}`,
    vars: [["E_i", "expected casino win of this machine"], ["A_i", "its available machine-hours"], ["j\\neq i", "the comparable machines: same game, same zone, excluding this one"]],
    result: has(idx) ? `${idx!.toFixed(2)}× its ${n ?? "?"} comparable machines` : undefined,
    meaning: "1.00 means it earns exactly like identical machines nearby; leaving itself out stops it from pulling its own benchmark.",
    fallback: "This machine’s expected win per hour ÷ the same for comparable machines (excluding itself).",
  }),
  decomposition: (total?: number, parts?: number[]): FormulaSpec => ({
    title: "Earnings gap breakdown",
    tex: String.raw`\begin{aligned}W-W_{\text{ref}}={}&\underbrace{(W-E)}_{\text{luck}}+\underbrace{(A-\bar A)\,\bar r}_{\text{exposure}}\\&+\underbrace{(r_z-\bar r)A}_{\text{location}}+\underbrace{(r_{zg}-r_z)A}_{\text{game}}\\&+\underbrace{(r-r_{zg})A}_{\text{machine}}\end{aligned}`,
    vars: [["W_{\\text{ref}}=\\bar r\\,\\bar A", "a typical machine: median rate × median hours"], ["r", "this machine’s expected win per hour"], ["r_z,\\ r_{zg}", "its zone’s rate, and same-game-in-zone rate"], ["A", "its available hours"]],
    calc: total !== undefined && parts && parts.length === 5 && has(total, ...parts)
      ? String.raw`\begin{aligned}${["luck", "exposure", "location", "game", "machine"].map((l, i) => `&${i ? (parts[i] < 0 ? "-" : "+") : "\\phantom{+}"}\\,${i ? usd(Math.abs(parts[i])) : usd(parts[i])}&&\\text{${l}}`).join("\\\\")}\\ \hline &=\,${usd(total)}&&\text{total gap}\end{aligned}` : null,
    meaning: "The five parts add up exactly to the total. They show where the gap sits, not what caused it.",
    fallback: "Gap to a typical machine = luck + exposure + location + game + machine.",
  }),
  simulation: (pB?: number): FormulaSpec => ({
    title: "Ranking stability (payout replays)",
    tex: String.raw`\begin{gathered}W^{(k)}=E+\sigma\,\varepsilon_k,\quad \varepsilon_k\sim\mathcal N(0,1)\\ P(\text{lowest }10)=\frac{1}{2000}\sum_{k=1}^{2000}\mathbf 1\!\left[\operatorname{rank}_k\le 10\right]\end{gathered}`,
    vars: [["W^{(k)}", "casino win in replay k"], ["\\varepsilon_k", "a fresh random luck draw"], ["\\mathbf 1[\\cdot]", "1 if the machine lands in the lowest 10, else 0"]],
    result: has(pB) ? `${(pB! * 100).toFixed(1)}% of replays` : undefined,
    meaning: "Only payout luck changes between replays; how much was played stays fixed.",
    fallback: "Share of 2,000 luck-only replays in which the machine lands in the lowest 10.",
  }),
  leaseNet: (planning?: number, best?: number, cost?: number): FormulaSpec => ({
    title: "July lease net benefit",
    tex: String.raw`\begin{aligned}N={}&\theta\,\bigl(r^{*}-r\bigr)\times 24\times 16\times c\\&-D-\bigl(\$2{,}500+\$55\times 16\bigr)\end{aligned}`,
    vars: [["\\theta", "share of the gap a new title wins back (25%, 50% or 100%)"], ["r^{*}", "expected win per hour of the zone’s best machine"], ["r", "this machine’s expected win per hour"], ["16", "operating days left in July after the 14-day lead time"], ["c", "share kept after revenue share and comps"], ["D", "earnings lost during 6 hours of installation"]],
    calc: has(cost) ? String.raw`\$2{,}500+\$55\times 16=${usd(cost)}\ \text{lease cost}` : null,
    result: has(planning, best) ? `${fmtUsd(planning!)} in the planning case; ${fmtUsd(best!)} even if a new title wins back 100% of the gap` : undefined,
    fallback: "Net = share of gap won back × hourly gap × hours in July × contribution − installation loss − lease cost.",
  }),
  promotion: (u?: number, breakEven?: number): FormulaSpec => ({
    title: "Promotion weekends: net and break-even",
    tex: String.raw`\begin{gathered}N=2\times\bigl(3\,u\,c-\$15{,}000\bigr)\\ u^{*}=\frac{\$15{,}000}{3\,c}\end{gathered}`,
    vars: [["u", "extra expected win per promotion day"], ["3", "promotion days per weekend (Fri–Sun)"], ["c", "share kept after revenue share and comps"], ["\\$15{,}000", "cost of one weekend"], ["u^{*}", "break-even uplift"]],
    calc: has(u, breakEven) ? String.raw`\begin{gathered}\text{estimated }u=${usd(u)}/\text{day}\\ \text{break-even }u^{*}=${usd(breakEven)}/\text{day}\end{gathered}` : null,
    meaning: "If the real uplift is below the break-even, the weekends lose money.",
    fallback: "Net = 2 weekends × (3 days × uplift × contribution − $15,000); break-even uplift = $15,000 ÷ (3 × contribution).",
  }),
  downtime: (hours?: number, risk?: number): FormulaSpec => ({
    title: "Downtime and expected win at risk",
    tex: String.raw`\begin{gathered}D=\sum_{i,d}\bigl(S_{id}-A_{id}\bigr)\\ R=\sum_{i,d}\bigl(S_{id}-A_{id}\bigr)\,r_i\end{gathered}`,
    vars: [["S_{id}", "hours machine i was scheduled on day d"], ["A_{id}", "hours it was actually available"], ["r_i", "its normal expected win per available hour"]],
    calc: has(hours, risk) ? String.raw`\begin{gathered}D=${tn(hours)}\ \text{h}\\ R=${usd(risk)}\end{gathered}` : null,
    meaning: "An upper estimate: some guests just move to a nearby machine.",
    fallback: "Downtime = scheduled − available hours; at risk = downtime hours × the machine’s normal hourly expected win.",
  }),
  comps: (): FormulaSpec => ({
    title: "Loyalty reward measures",
    tex: String.raw`\begin{gathered}\text{points per \$}=\frac{\text{points redeemed}}{\text{menu value of comps}}\\[6pt] \text{cost ratio}=\frac{\text{comp cost}}{\sum \text{tracked expected win}}\end{gathered}`,
    vars: [["\\text{cost ratio}", "share of each tracked expected dollar given back as rewards"]],
    fallback: "Points per dollar = points redeemed ÷ menu value; cost ratio = comp cost ÷ tracked expected win.",
  }),
  gini: (g?: number): FormulaSpec => ({
    title: "Concentration of play (Gini)",
    tex: String.raw`G=\frac{\sum_{i=1}^{n}\left(2i-n-1\right)x_{(i)}}{n\sum_{i=1}^{n}x_{i}}`,
    vars: [["x_{(i)}", "expected win from the i-th smallest tracked guest"], ["n", "tracked guests"]],
    result: has(g) ? `G = ${g!.toFixed(2)}` : undefined,
    meaning: "0 means everyone plays the same; 1 means one guest does all the play.",
    fallback: "Gini coefficient of tracked expected win.",
  }),
  forecastErrors: (mae?: number, rmse?: number, bias?: number, cov?: number, n?: number): FormulaSpec => ({
    title: "Forecast error measures",
    tex: String.raw`\begin{aligned}\text{MAE}&=\frac{1}{n}\sum_{t=1}^{n}\lvert y_t-\hat y_t\rvert\\ \text{RMSE}&=\sqrt{\frac{1}{n}\sum_{t=1}^{n}(y_t-\hat y_t)^2}\\ \text{bias}&=\frac{1}{n}\sum_{t=1}^{n}(\hat y_t-y_t)\\ \text{coverage}&=\frac{1}{n}\sum_{t=1}^{n}\mathbf 1\!\left[L_t\le y_t\le U_t\right]\end{aligned}`,
    vars: [["y_t", "actual expected casino win on holdout day t"], ["\\hat y_t", "forecast for day t"], ["L_t,\\,U_t", "the model’s 80% range for day t"], ["n", "holdout days"]],
    calc: has(mae, rmse, bias, cov, n) ? String.raw`\begin{aligned}n&=${tn(n)}\ \text{days}\\ \text{MAE}&=${usd(mae)}\\ \text{RMSE}&=${usd(rmse)}\\ \text{bias}&=${usd(bias)}\\ \text{coverage}&=${tn(cov! * 100, 0)}\%\end{aligned}` : null,
    meaning: "MAE is the typical daily miss; RMSE weighs big misses more; positive bias means the forecast ran high; coverage should be near 80%.",
    fallback: "MAE = average absolute miss; RMSE = root of average squared miss; bias = average (forecast − actual); coverage = share of days inside the 80% range.",
  }),
  improvement: (base?: number, model?: number, pctv?: number): FormulaSpec => ({
    title: "Improvement over the baseline",
    tex: String.raw`\Delta=\frac{\text{MAE}_{\text{baseline}}-\text{MAE}_{\text{model}}}{\text{MAE}_{\text{baseline}}}\times 100\%`,
    vars: [["\\text{MAE}_{\\text{baseline}}", "average miss of the weekday-average rule"]],
    calc: has(base, model, pctv) ? String.raw`\Delta=\frac{${usd(base)}-${usd(model)}}{${usd(base)}}\times 100\%=${tn(pctv, 1)}\%` : null,
    meaning: "Positive means the model misses less than the simple rule.",
    fallback: "Improvement = (baseline miss − model miss) ÷ baseline miss.",
  }),
  eventStudy: (pctv?: number): FormulaSpec => ({
    title: "Walkway closure effect (before/during/after)",
    tex: String.raw`\begin{gathered}\ln\frac{R^{\text{B40}}_d}{R^{\text{rest}}_d}=\alpha+\beta\,\text{closed}_d+\gamma\,\text{after}_d+\text{weekday}_d+\varepsilon_d\\[4pt] \text{effect}=\left(e^{\beta}-1\right)\times 100\%\end{gathered}`,
    vars: [["R_d", "expected casino win per available machine-hour on day d (machines that never moved)"], ["\\beta", "change in Back Forty vs the rest of the floor while the walkway was closed"], ["\\gamma", "the same after it reopened"], ["\\varepsilon_d", "day-to-day noise (errors allowed to be correlated for up to 7 days)"]],
    calc: has(pctv) ? String.raw`\text{effect}=${tn(pctv, 1)}\%` : null,
    meaning: "Comparing with the rest of the floor on the same days removes seasons and weekends; it is an estimate, not proof of cause.",
    fallback: "Effect = how much Back Forty fell relative to the rest of the floor while the walkway was closed.",
  }),
  decisionFlip: (u?: number, before?: number, breakEven?: number): FormulaSpec => ({
    title: "Effect of the assumption on the recommended plan",
    tex: String.raw`\begin{gathered}\Delta N=N_{\text{after}}-N_{\text{before}}\\ \text{promotions pay only if } u\ge u^{*}\end{gathered}`,
    vars: [["u", "promotion uplift tested (extra expected win per promotion day)"], ["u^{*}", "break-even uplift"], ["N_{\\text{before}}", "modeled July net of the plan with two promotion weekends"], ["N_{\\text{after}}", "modeled net of the plan chosen instead (hold: no spend, $0)"]],
    calc: has(u, before) ? String.raw`\begin{gathered}u=${usd(u)}/\text{day}${has(breakEven) ? String.raw`\;<\;u^{*}=${usd(breakEven)}/\text{day}` : ""}\\ \Delta N=\$0-${usd(before)}=${usd(-before!)}\end{gathered}` : null,
    meaning: "Below break-even the weekends would lose money, so the optimizer holds the budget instead; the plan’s modeled net falls by the full promotion value.",
    fallback: "Change in modeled net = net of the plan chosen instead − net of the promotion plan.",
  }),
  noiseRatio: (x?: number, sd?: number, z?: number): FormulaSpec => ({
    title: "Promotion uplift compared with ordinary weekend noise",
    tex: String.raw`z=\frac{x}{s}`,
    vars: [["x", "excess expected win per day at the weaker promotion event"], ["s", "standard deviation of ordinary Fri–Sun days (non-event weekends)"]],
    calc: has(x, sd, z) ? String.raw`z=\frac{${usd(x)}}{${usd(sd)}}=${tn(z, 2)}` : null,
    meaning: "About one ordinary swing: a single event this size cannot be told apart from normal weekend variation.",
    fallback: "Excess per day ÷ ordinary weekend standard deviation.",
  }),
  netBenefit: (): FormulaSpec => ({
    title: "Estimated net benefit of a plan",
    tex: String.raw`\begin{gathered}N=\sum_{a\in\text{plan}}\Bigl(q_a\,g_a\,c-q_a\,k_a\Bigr)\\ \sum_a q_a k_a\le\$100{,}000,\quad \text{at most 3 kinds of action}\end{gathered}`,
    vars: [["q_a", "quantity of action a"], ["g_a", "its modeled extra expected win in July"], ["c", "share kept after revenue share and comps"], ["k_a", "its catalog cost"]],
    meaning: "Modeled July contribution minus cost, within the $100,000 budget and at most three action types.",
    fallback: "Net = Σ (quantity × modeled gain × contribution − quantity × cost), within budget and three action types.",
  }),
};
