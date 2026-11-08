# Step 4: the Whisper Network council

**Execution mode: RULE_BASED.** No LLM is configured (`LLM_PROVIDER=none`), and paid LLM calls need approval. The six specialists are deterministic, role-specific analyses of verified data. The messaging, provenance, verification and optimiser integration are real and exercised. A tested LLM adapter (`council/llm.py`, with timeout, retries, token cap and schema validation) exists but is not called. This is **not** a council of six autonomous LLM agents.

Run: `uv run python scripts/run_step4.py --backend databricks` or the Databricks job `house-of-minds-step4-whisper-council`.

## Architecture

Verified Databricks evidence → six independent investigations (allowlisted, parameterised, read-only tools) → Whisper Network (≤2 rounds, ≤2 messages per agent per round) → deterministic verifier (six dimensions) → admissibility → **existing Step 3 optimiser** (versioned scenarios; baselines never edited) → immutable records (8 tables, common `snapshot_id`).

| Agent | Falsifiable hypothesis | Tools |
| --- | --- | --- |
| Statistician | Two promotion observations cannot support a reliable uplift estimate | promo_event_excess, weekend_noise_sd, comp_change_date |
| Demand Strategist | Moving machines into Center Pit redistributes existing play | zone_occupancy, zone_count_elasticity |
| Operations Chief | Inspection or maintenance needs unrealistic success rates | machine_monthly_hit_z, tech_staffing, maintenance_fault_effect |
| Guest Analyst | Promotion gains are displaced visits | post_event_carded_change |
| Loyalty Strategist | Extra comps erase the promotion advantage | promo_comp_ratio, comp_change_date |
| CFO | The $34,800 conditional portfolio is not worth its extra uncertainty | portfolio_comparison, reoptimise_with |

## What the council found (all numbers reproduced by the verifier)

| Agent | Finding | Verdict | Decision relevance |
| --- | --- | --- | --- |
| Statistician | The weaker promotion's +$5,016/day is **1.08 SD** of ordinary weekend variation (SD $4,649/day, 60 days) and below the $5,281 break-even | VERIFIED | **Relevant**: proposed scenario A08 = $5,016 |
| Guest Analyst | Carded theo fell **3.4%** in the week after both promotions; displacement-adjusted excess ≈ $9,511/day | INCONCLUSIVE (2 events) | Not relevant: promotions stay funded at $9,511 |
| Loyalty Strategist | Comp cost per theo on promotion days is 0.881% vs a modeled 0.863%: about $9 per weekend | VERIFIED | Supports promotion economics |
| Loyalty Strategist | *Hypothesis:* the 7.6% comp increase was caused by promotions | **Retracted** after a counterclaim | n/a |
| Operations Chief | M-1158's fault is significant in 6 of 6 months; technicians at 93.4% of planned shifts; inspection feasible | VERIFIED | Fix probability still unidentified |
| Operations Chief | Only 3 machines ever had scheduled maintenance, too few to support >86% recovery | VERIFIED | Not relevant: Ridgeline is already excluded |
| Demand Strategist | Center Pit is 44.7% occupied; historically +1 machine added 0.93× mean theo (3 distinct counts only) | VERIFIED (as uncertainty) | Relevant: 20–21% boundary unresolved |
| CFO | Conditional portfolio: +$4,800 cost for +$6,799 modeled, entirely from assumption-required lines | VERIFIED | Relevant |

**Optimiser consequence (real re-runs, constraints verified):** the Statistician's admitted scenario (A08 = $5,016, `VERIFIED_SCENARIO`) changes the evidence portfolio from **2 promotions → HOLD** (−$62,237 modeled), and drops the promotions from the conditional portfolio. The Guest Analyst's exploratory scenario leaves both portfolios unchanged. The Step 3 baselines are untouched, and invalidating the promotion evidence gives HOLD (PASS).

**Council conclusion:** the promotion uplift is decision-relevant and unresolved, so the $30,000 evidence-supported portfolio remains **conditional on promotion evidence the data cannot confirm**.

## Gossip OFF vs gossip ON (same evidence, verifier, optimiser)

| Metric | OFF | ON |
| --- | ---: | ---: |
| Claims (verified / inconclusive) | 10 (7 / 3) | 13 (10 / 3) |
| Independent decision-relevant objections (deduplicated by origin) | 3 | 3 |
| Unresolved hypotheses | 2 | **1** (one retracted) |
| Messages delivered / duplicates suppressed / budget-blocked | 0 / 0 / 0 | 13 / 1 / 2 |
| Messages flagged by retraction | 0 | 4 |
| New evidence queries | 0 | 3 |
| Decision-changing verified challenges | 1 | 1 |
| Portfolio outcomes | identical | identical |
| LLM tokens / cost | 0 / $0 | 0 / $0 |

**Verdict on gossip:** in this run it improved evidence hygiene, catching and retracting a false causal hypothesis before it could spread. It did **not** find additional independent objections or change any decision. Rule-based execution is deterministic, so repeated trials are identical: this is one configuration comparison, not a statistical sample. The network should stay optional, and its value should be re-measured once LLM specialists (non-deterministic, broader search) are approved.

## Safety

Agent text is never executed. Tools are allowlisted and parameterised, with IDs validated by pattern and by the data. Injection-like content is quarantined, and its proposed changes are not admissible. Only `ADMISSIBLE_SCENARIO` verdicts reach the optimiser, and agents cannot pick portfolios. 21 negative and edge-case tests pass (see `council_validation_summary`).

## Known weaknesses

- Rule-based specialists explore only their coded checks: no open-ended discovery.
- Routing weights are hand-set; message budgets cut two lower-priority whispers.
- The displacement and Center Pit elasticity findings rest on 2 events and 3 machine counts.
- Step 1 code (`analytics/investigations.py`) still uses the deprecated pandas `dt.dayofweek`. It was left unchanged to preserve Step 1.
