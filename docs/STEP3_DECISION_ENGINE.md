# Step 3: Evidence-constrained $100K decision engine

Regenerate: `uv run python scripts/run_step3.py --backend databricks` or the Databricks job `house-of-minds-step3-decision-engine` (ID 670548312985484). Tables live in `workspace.house_of_minds`. Every number below comes from those runs.

## The decision

| | Evidence-supported decision | Conditional decision (assumption-labelled) |
| --- | --- | --- |
| Portfolio | 2 property promotion weekends (Jul 18–20, Jul 25–27) | M-1158 inspection + move M-1154 and M-1184 from Back Forty to Center Pit + 2 promotion weekends |
| Cost | $30,000 | $34,800 |
| Unspent | $70,000 | $65,200 |
| Modeled net contribution (Jul 1–30) | $62,237 | $69,036 |
| Basis | Only inputs computed from data | Adds labelled planning values for unmeasured effects |

Most of the budget stays unspent because no other action clears its cost on the evidence. Keeping budget is a valid answer under the guide.

## Why: what the evidence supports and what it doesn't

| Status | Candidates |
| --- | --- |
| Evidence estimate | Promotions: past property promotions added $5,016–$27,458 theo per Fri–Sun day (2 events, associational) |
| Assumption required (labelled, range-tested) | Inspection fix probability; wayfinding uplift; Ridgeline maintenance effectiveness; machine-move demand transfer; comp play response; new-title performance |
| Negative at best case (excluded on evidence) | Northwind maintenance, technician shift (even if a technician eliminated *all* floor downtime), buying a machine (only 9 operating days) |
| Not identifiable (excluded, not zero) | Comp pilot, guest survey (information value only) |
| Ineligible | Bank move (no empty bank-sized space) |

**Money basis:** benefits are incremental contribution, not revenue. Theo gains are multiplied by a contribution factor (0.947 floor-wide: 20% revenue share on 22% of theo, plus 0.86% comps). Avoided repair costs are added, install downtime is subtracted, and the official catalog cost (GUIDE formula, lead-time days) is charged in full.

## Decision reversals (each verified by re-running the optimiser on both sides)

| Assumption | Planning value | Decision flips at | Risk | What changes |
| --- | --- | --- | --- | --- |
| Promotion excess theo/day (**evidence**) | $16,237 | **$5,281** (interval $5,281.1–5,281.3) | **HIGH** | Below it: HOLD instead of 2 promotions. The weaker observed promotion ($5,016) is below the threshold, so **the evidence-supported decision is not robust** |
| Wayfinding net uplift (Back Forty) | 2.5% | 4.2% | HIGH | Above it: wayfinding replaces the inspection (3-action-type limit) |
| Inspection fix probability | 0.50 | 0.221 | MEDIUM | Below it: drop the inspection |
| Ridgeline maintenance effectiveness | 0.50 | 0.861 | MEDIUM | Above it: maintenance replaces the inspection |
| Move demand transfer | 0.50 | 0.200 and 0.210 (two reversals) | MEDIUM | 0, 1 or 2 machine moves |

Confirmed non-reversals across the full tested range: M-1158 loss/day ($114–$285), technician effect (0–100%), comp play response (0–5%), comp cost saving, new-title performance.

## Scenarios and regret (13 scenarios; probabilities unknown)

- The baseline stays optimal in 10 of 13 scenarios. Median regret is $0, the unweighted mean is $490, and the maximum is $3,636 (moved machines keep their old demand).
- Other scenarios with regret: weakest observed promotion ($1,506) and inspection fails ($1,224).
- With a 7-day implementation delay, only one promotion weekend fits. The baseline is then flagged infeasible, and the re-optimised plan drops to one weekend.
- The minimax-regret portfolio is the baseline itself, so a more conservative choice costs nothing among the tested portfolios. This robustness is relative to the tested scenarios; it does not make the assumptions true.

## Evidence passport and invalidation

- `decision_evidence_links` ties every portfolio line to its assumption, the Step 2 evidence ID, the source tables, the dataset fingerprint, the code hash, and claim/challenge IDs for the Step 4 council. All evidence IDs resolve to `evidence_ledger`.
- **Invalidation:** marking the promotion evidence invalid blocks the promotions and turns the evidence-supported decision into HOLD. Marking the inspection or move assumptions invalid removes those lines. None is silently kept.

## Limitations

- The promotion effect comes from 2 past promotions and is associational: no control group, and seasonal confounding is possible.
- All assumption-required effects are planning values, not estimates. Their ranges are exploratory.
- Lost or gained theo assumes play at average rates. Theo is not realised win: luck adds variance within one month.
- Overlap between promotions and other actions is second-order and not modelled. Moves exclude M-1158, and the wayfinding base excludes move candidates, to prevent double counting.
