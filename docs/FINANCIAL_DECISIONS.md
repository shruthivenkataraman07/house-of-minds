# Financial decisions: July 2025

**Constraints:**

- Budget: $100,000.
- At most three action types.
- Horizon: July 1–30, 2025.
- Prices, lead times and quantity limits come from the official 13-action catalog.

The optimizer is an exact mixed-integer program (`optimization/portfolio.py`, SciPy MILP). The formulas are in [Analytical methods §12](ANALYTICAL_METHODS.md#12-investment-economics).

## Recommended plan (evidence-supported inputs only)

| Action | Qty | Target | Cost | Modeled July net | Main risk | Success measure |
|---|---:|---|---:|---:|---|---|
| Property promotion weekend (A-PROMO) | 2 | Property, Jul 18–20 and Jul 25–27 | $30,000 | +$62,237 | Uplift below $5,281 a day (the weakest past event gives −$1,506) | Mean excess expected win above $5,281 a day against a Holt-Winters past-only counterfactual, net of 7-day displacement |

**Unspent:** $70,000.

**Stop rule (MP-A-PROMO):** if the first weekend's excess falls below break-even and outside the forecast's 80% range, cancel the second weekend before its 14-day lead time closes.

## Alternatives compared

| Plan | Cost | Net | Range | Why not chosen |
|---|---:|---:|---:|---|
| Manager: lease 8 replacements | $27,040 | −$15,843 | −$27,399 to −$4,287 | Loses money in every tested case; 2 of the 10 are already retired |
| Manager: buy 10 machines | $220,000 | — | — | Over budget |
| Conditional: + M-1158 inspection + 2 machine moves | $34,800 | +$69,036 | +$5,292 to +$132,780 | Needs effects nobody has measured (assumptions A01, A09) |
| No action | $0 | $0 | — | Forgoes an evidence-supported positive plan |

## Decision reversals

The **Scenarios → Decision flips** view shows the assumption values at which the choice would change. The promotion decision flips when uplift reaches **$5,281 a day** (`RV-588E258074`). If promotions were prohibited, the conditional plan would net only $6,799.

## What is modeled and what is observed

Every July figure above is **modeled contribution**, not realized profit. The measurement plans are `PLANNED_NOT_STARTED`: no July results exist yet.
