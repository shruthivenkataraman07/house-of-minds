# House of Minds: write-up

**Question.** The Gilded Ace's manager wants to replace the ten lowest-earning slot machines. Is that the best use of $100,000 in July 2025?

**Data and method.**

- The official six-month dataset (181 gaming days) is reconciled on Databricks: 14 arithmetic checks, all passing. House win equals coin-in minus payout on 56,110 machine-days, giving $23,638,155 kept on $248,905,219 wagered.
- Machines are compared on expected casino win per *available* hour against comparable machines (same game, same zone, the machine itself left out).
- Payout luck is separated with a luck score, an exact paying-spin test corrected for checking 310 machines, and 2,000 luck-only replays.
- Each machine's gap to a typical machine splits exactly into luck, exposure, location, game and machine.

**Findings.**

- None of the ten should be replaced. Two are already retired, one was on the floor only 49 days, and six lose money on a July lease even if the new title matched the zone's best machine.
- M-1158 pays out on 38.6% of spins against a designed 31.5% (z = 124). It needs an inspection, not a replacement.
- A walkway closure cut Back Forty demand by 31.2% (95% range −32.5% to −29.9%), and demand recovered after reopening.
- Comp points per dollar halved on May 1, while comp cost per tracked expected win rose from 1.11% to 1.32%.

**Model.** A Holt-Winters forecast beat a weekday-average baseline on an untouched May–June holdout: average miss $5,552 against $6,699, 17.1% better. It is worse on event days, and we disclose that. Used as a past-only counterfactual, it informs the promotion uplift.

**Recommendation.**

- An exact optimizer over the official catalog chooses **two promotion weekends**: $30,000 for a modeled July net of +$62,237, with $70,000 unspent.
- The manager's lease plan nets −$15,843.
- The promotion pays only if each promotion day adds $5,281 of expected win. At the weakest past event's uplift it would net −$1,506.
- A stop rule cancels the second weekend if the first falls short.
- A conditional plan adds the inspection and two machine moves (+$69,036), but those effects are unmeasured.

**What is distinctive.**

- Six rule-based specialist agents and a verifier challenge every claim; one false causal claim was retracted.
- Every recommendation opens to an evidence passport with its typeset formula, the recorded numbers, source tables, alternative explanation and limitation.
- No LLM is used at runtime.
