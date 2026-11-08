# Council and decision logic

The council is six **deterministic, rule-based** analytical agents (`council/agents.py`) plus a verifier (`council/verifier.py`) and a message network, the "Whisper Network" (`council/network.py`).

- The agents call only allowlisted, read-only tools (`council/tools.py`).
- An LLM adapter exists (`council/llm.py`), but nothing calls it and no provider is configured. The product makes **0 LLM calls**.

| Agent | Question | Inputs | Example check (paraphrased) |
|---|---|---|---|
| Statistician | Is a low total luck or signal? | Luck score, paying-spin test, 310-machine correction | "Shortfall is within ordinary luck" |
| Demand Strategist | Is it the location or game rather than the machine? | Zone rates, foot traffic, same-game comparable machines | "Back Forty demand fell 31% during the walkway closure" |
| Operations Chief | Was it on the floor long enough? Is downtime or a payout fault involved? | Active days, downtime, hit rate | "M-1158 needs an inspection, not a replacement" |
| Guest Analyst | What does tracked play show? | Tier aggregates only | "Tracked play is 65.8% of wagering; do not scale it up" |
| Loyalty Strategist | What do comps cost? | Comp ledger, point-of-sale cost | "Points per dollar halved on May 1; the play effect is unknown" |
| CFO | Does it pay in July within budget? | Lease economics, optimizer, regret | "Lease loses money even at 100% gap capture" |

## How a claim moves through the council

1. An agent makes a claim with its evidence IDs.
2. The verifier recomputes the claim from the tables. Each claim ends `VERIFIED` or `CHALLENGED`, or is `RETRACTED`.
3. The Whisper Network routes the claim to the agents it affects, suppresses duplicates and passes retractions on.
4. The CFO's economics can only use claims that passed verification. A retracted claim cannot change the plan.

**Real outcomes in this snapshot:**

- 49 of 49 manager-review claims were verified.
- The council's verdict matched the replacement analysis on all 10 of the manager's machines.
- One false causal claim was retracted, and the portfolio did not change.

## Ask the House

`backend/services/ask.py` is a deterministic intent router.

- It answers only from the same API data and names its period and evidence.
- It returns `UNSUPPORTED`, `AMBIGUOUS`, `UNAVAILABLE` or `REFUSED` instead of guessing.
- It makes no LLM calls.
