# Final submission readiness

| Requirement | Status | Note |
|---|---|---|
| Public interactive dashboard | FINAL DASHBOARD PHASE | data contracts + exports ready (Step 7) |
| Video walkthrough (<=2 min) | PARTIALLY READY | storyboard below; not recorded |
| Written summary (<=400 words) | READY | draft below (247 words) |
| ML/time-series vs baseline on holdout, informing a decision | READY | Holt-Winters vs weekday mean, May-Jun holdout, linked to A08 |
| All code and transformations | READY | repo + REPRODUCIBILITY_GUIDE.md (no git commits yet; must be pushed/published before submission) |
| Up to 3 priced action types | READY | A-PROMO (evidence); + A-INSPECT, A-MOVE-MACHINE (conditional); costs, effects, uncertainty, measurement |
| AI-use disclosure | READY | AI_USE_DISCLOSURE.md |
| Claims & Evidence appendix | READY | 83 claims |

## Blockers

- Public dashboard and recorded video: Step 7.
- Repository has no commits: code must be committed and published (needs your approval).
- Causal promotion uplift, inspection fix probability and move transfer remain unmeasured (planning assumptions).

## Written summary draft (247 words)

THE HOUSE OF MINDS turns the Gilded Ace's six months of data into an auditable $100,000 decision. Every figure reconciles: house win equals coin-in minus payout on all machine-days (14/14 checks; $23,638,155 house win on $248,905,219 coin-in). The manager's bottom-10 list mixes four problems: nine sit in Back Forty, the weakest zone; most run low-edge games; two were new; and M-1158 pays out far more often than its game math allows (hit-rate z = 124). It needs an inspection, not a replacement. A walkway closure cut Back Forty demand by about 31%, and the comp points price halved on May 1. An exact optimiser over the official catalog recommends two promotion weekends ($30,000, modeled net $62,237) and keeping $70,000. A conditional plan adds the inspection and two machine moves ($34,800, $69,036), but those effects are unmeasured. Our Decision-Reversal Engine shows when the choice flips: promotions need $5,281/day of extra theo, and the weaker past promotion measured $5,016 under a symmetric baseline. A Holt-Winters forecast beat a weekday-mean baseline on an untouched May-June holdout (MAE $5,552 vs $6,699). Used as a past-only counterfactual, it puts that promotion above break-even, so the decision is defensible but its causal basis is unproven (two events, no control). Six rule-based specialists and a Whisper Network challenged every assumption. Gossip retracted a false causal claim but did not change the portfolio. Each claim traces to a table, query, alternative explanation and limitation, and each action has a measurement plan with a stop rule.

## Video storyboard (2:00)

| Time | Screen | Narration (evidence) |
|---|---|---|
| 0:00-0:15 | Command Center KPIs | Data reconciles (CLM-REC-R01, R03) |
| 0:15-0:40 | Machine Intelligence | Bottom 10 = four problems; M-1158 leak (CLM-EV-1C684B792E7B) |
| 0:40-1:05 | $100K Verdict | 2 promotions, $70k kept; conditional plan (CLM-PF-*) |
| 1:05-1:25 | Parallel Universes | $5,281 vs $5,016 reversal; forecast counterfactual (CLM-FORECAST-DECISION) |
| 1:25-1:45 | Council Chamber / Whisper Network | Statistician challenge; retraction; gossip did not change decision (CLM-WHISPER-EVAL) |
| 1:45-2:00 | Evidence Observatory | Every claim traceable; measurement plans and stop rules |
