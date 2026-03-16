# Code Review — Bracket Optimizer Iteration 3

**Reviewer:** Senior Code Review (automated)  
**Date:** 2026-03-15  
**Previous Score:** 3/10  

---

## Summary

Iteration 3 shows meaningful progress in `sharp.py` (UPS implementation, κ=13.0, round-dependent seed prior, expanded auto-bid modifier) and `constants.py` (new upset distribution data, UPS weights, strategy-specific constants). However, the core optimizer — the module that actually *builds the brackets* — remains fundamentally unrewritten. The amendment's central requirements (top-down construction, upset distribution targets, strategy differentiation, UPS integration into bracket decisions) are **not implemented in `optimizer.py`**. The result: sharp.py can now compute better probabilities, but the optimizer can't use them.

Tests all pass (49/49), but they don't test any of the amendment's requirements. The tests validate the old behavior, not the new spec.

---

## Verified Known Issues

### ❌ Issue 1: UPS Exists in sharp.py but Is NEVER Used by optimizer.py

**Status: CONFIRMED — Critical**

`compute_upset_propensity_score()` and `apply_upset_propensity_modifier()` are implemented in `sharp.py` and called from `compute_matchup_probability()` — but only for `round_num == 1`. The matchup matrix is built via `build_matchup_matrix()` which calls `compute_matchup_probability(team_a, team_b)` **without passing `round_num`**, so it defaults to 1. This means UPS does influence the matrix entries, but:

1. **The optimizer never calls UPS directly** — zero imports of `compute_upset_propensity_score` or `apply_upset_propensity_modifier` in `optimizer.py`.
2. **No `rank_upset_candidates()` function exists** — the amendment specifies this as a key new function in §6.3.1. Not implemented.
3. **No `select_upsets_by_distribution()` function exists** — amendment §6.3.2. Not implemented.
4. **The optimizer has no concept of "upset tiers"** — Tier 1/2/3 upset candidates from §3.4 are not referenced anywhere in the optimizer.

The UPS is computed *inside the matchup matrix*, which is a static NxN lookup table. This means every 5v12 matchup in the matrix has the UPS baked in at R1 weights, but the optimizer doesn't know *which* upsets are the best picks, doesn't rank them, and can't allocate them by distribution targets.

**Impact:** The amendment's core value proposition — intelligent upset selection based on team-specific factors — is dead on arrival.

### ❌ Issue 2: All Three Strategy Brackets Produce the Same Champion

**Status: CONFIRMED — Critical**

`construct_candidate_bracket()` does not reference `STRATEGY_CHAMPION_SEEDS` (defined in `constants.py`). The champion is not *selected*; it's a *byproduct* of bottom-up construction. The three strategies differ only in threshold parameters (`max_upsets_r1`, `champ_leverage_min`, `upset_leverage_threshold`, `upset_min_prob`), which control Round 1 upset frequency and later-round leverage thresholds. Since the same team tends to survive the probability gauntlet regardless of these thresholds, all three strategies converge on the same champion.

The amendment explicitly requires (§5.2): *"At least 2 of 3 brackets must have different champions."* No enforcement exists.

`STRATEGY_CHAMPION_SEEDS` constrains conservative to seeds 1-2, balanced to 1-4, aggressive to 2-6. The optimizer ignores this entirely.

### ❌ Issue 3: Optimal Bracket Produces Too Few Upsets (~3 vs ~8 target)

**Status: CONFIRMED — Critical**

The amendment specifies upset distribution targets in `UPSET_TARGETS` (now in `constants.py`). For "balanced": at least 1 each of 7/10, 6/11, and 5/12 upsets, plus 1-3 from 8/9. The balanced target is ~8 first-round upsets.

But `construct_candidate_bracket()` uses a flat `max_upsets_r1` counter (5 for balanced) with a single `upset_leverage_threshold` (1.5). It iterates R1 slots sequentially and picks upsets opportunistically. The result:

- It doesn't ensure *any* 12-over-5 upsets (mandatory per amendment: "at least 1 is mandatory given 72% historical frequency")
- It doesn't ensure minimum upset counts per seed matchup type
- The 8/9 "upsets" (near coin flips) count toward the budget, consuming slots that should go to high-value 12/5 or 11/6 upsets
- No region-balancing of upsets (amendment §4.4)

`UPSET_TARGETS` exists in `constants.py` but is never imported or referenced in `optimizer.py`.

### ❌ Issue 4: Aggressive Bracket Has ~0.4% P(1st) — Worse Than Random

**Status: CONFIRMED — Expected Given Other Issues**

Random chance in a 25-person pool is 4%. The aggressive bracket performing at 0.4% means it's actively *anti-optimized*. This is a downstream consequence of:

1. Same champion as other strategies (no differentiation value)
2. Upset picks driven by high leverage thresholds without probability floors that make sense (aggressive uses `upset_min_prob = 0.15` — picking teams with 15% win probability just for leverage)
3. No upset advancement logic — an aggressive 14-seed upset pick that loses in R2 costs points in all subsequent rounds
4. The perturbation search (which could rescue bad initial brackets) doesn't exist

### ❌ Issue 5: construct_candidate_bracket() Is Bottom-Up, Not Top-Down

**Status: CONFIRMED — Critical**

The function proceeds:
1. **R1: Fill chalk + some strategic upsets** (lines ~335-400)  
2. **R2-R6: Build remaining rounds** (lines ~410-500)
3. **Extract champion from slot 63** (lines ~501-503)

The amendment §4.1 requires:
1. Select champion first
2. Select Final Four 
3. Build each FF team's path backward to R1
4. Fill remaining games
5. Apply upset distribution targets
6. Validate consistency

This is a fundamental architectural mismatch. The champion and FF are *outputs* of the current code, not *inputs*. Top-down construction is the single most important structural change in the amendment because it enables:
- Champion-driven path building
- Strategic upset allocation around the champion's region
- Meaningful differentiation between strategies

### ❌ Issue 6: Upset Distribution Targets Not Implemented

**Status: CONFIRMED**

`UPSET_TARGETS`, `EXPECTED_UPSETS_PER_TOURNAMENT`, `P_AT_LEAST_ONE_UPSET`, `UPSET_ADVANCEMENT_RATE` — all defined in `constants.py`, **none referenced in `optimizer.py`**. These are completely dead code.

---

## NEW Issues Found

### ❌ Issue 7: Matchup Matrix Uses R1 Weights for All Rounds

**Severity: High**

`build_matchup_matrix()` calls `compute_matchup_probability(team_a, team_b)` without `round_num`, defaulting to 1. This means:

- The R1-specific seed prior blending weight (w=0.60) is applied to ALL entries in the matrix
- The UPS modifier (which only fires for `round_num == 1`) is baked into ALL matchups
- Late-round games between, say, a 1-seed and a 3-seed use R1 blending weights (60% model / 40% historical) instead of the correct E8+ weight (80% model / 20% historical)

**Fix:** Either compute round-specific probabilities on-the-fly in the optimizer (not via a static matrix), or build multiple matrices per round, or pass round_num as a parameter when looking up probabilities.

### ❌ Issue 8: Off-by-One Bug in generate_public_bracket() — Championship Ownership Lookup

**Severity: High**

In the R2-6 loop of `generate_public_bracket()`, ownership is looked up via `round_ownership.get(round_num + 1, default)`. For the championship game (`round_num = 6`), this looks up `round_ownership.get(7, ...)`. Round 7 doesn't exist in `SEED_OWNERSHIP_CURVES` or any profile.

**Result:** All championship picks in simulated opponent brackets fall back to 0.5 default, regardless of seed. A 16-seed has the same weight as a 1-seed for the championship in opponent brackets. This makes the simulated pool unrealistically random at the most important pick, corrupting P(1st) calculations for all our brackets.

### ❌ Issue 9: Perturbation Search Not Implemented

**Severity: Medium-High**

The PLAN (§7.2, Phase 3) describes perturbation search as a key optimization step. The amendment (§6.3.5) explicitly calls this out as "Currently Missing from Code" and provides the `perturb_bracket()` function spec. Still not implemented. `optimize_bracket()` just builds 3 candidates and picks the best — no neighborhood exploration.

### ❌ Issue 10: update_leverage_with_model() Uses Crude Seed-Based Heuristic

**Severity: Medium**

`update_leverage_with_model()` in `contrarian.py` estimates advancement probability with `seed_factor = (17 - team.seed) / 16.0` raised to successive powers. This is a rough exponential decay that doesn't use the matchup matrix at all. The PLAN says it should run simulations to estimate advancement probability. The function even has a comment: `"A more sophisticated implementation would run simulations"`.

The result: leverage scores are based on seed, not actual team quality. A 5-seed with AdjEM +22 gets the same leverage as a 5-seed with AdjEM +10.

### ❌ Issue 11: Duplicate `assign_confidence_tier()` Function

**Severity: Low**

Defined identically in both `src/optimizer.py` (line 21) and `src/analyst.py` (line 14). Should be defined once and imported. Currently, the optimizer uses its own copy and never references the analyst module's version.

### ❌ Issue 12: generate_public_bracket() Doesn't Ensure Champion Path Consistency

**Severity: Medium**

The function claims to use a "champion-first approach" (docstring line 115, line 131) and does pick a champion first. But it then fills R1 independently, and the R2-6 loop just picks based on ownership weights. There's no logic to ensure the selected champion actually wins their path. The champion is picked but then ignored — later round results may not include them.

This means simulated opponent brackets can have inconsistent champions, making the pool simulation unreliable.

### ❌ Issue 13: construct_candidate_bracket() R1 Iterates Slots in Arbitrary Order

**Severity: Medium**

R1 slots are iterated as-is from `bracket.slots`. The first slots (1-seed matchups) get first crack at the upset budget, and by the time 5/12 or 6/11 matchups come around, the budget may be exhausted. With the standard bracket order `(1v16, 8v9, 5v12, 4v13, 6v11, 3v14, 7v10, 2v15)`, the 8v9 matchup (slot 2) would consume an upset slot before the more valuable 5v12 (slot 3). The amendment explicitly says to rank upset candidates by composite score and select the best ones, not first-come-first-served.

### ❌ Issue 14: No Bracket Consistency Validation

**Severity: Medium**

Neither `construct_candidate_bracket()` nor `optimize_bracket()` validates bracket consistency after construction. The `BracketConsistencyError` exception exists in models.py but is never raised anywhere. The PLAN (§8, Optimizer section) says: *"Bracket consistency validation before and after construction."*

### ❌ Issue 15: Tests Don't Cover Amendment Requirements

**Severity: High**

All 49 tests pass because they test the *old* behavior. None test:
- Different champions across strategies
- Upset distribution matching `UPSET_TARGETS`  
- Top-down construction order
- UPS integration in optimizer decisions
- Minimum differentiation between brackets (§5.2)
- `rank_upset_candidates()` or `select_upsets_by_distribution()` (they don't exist)
- Public bracket champion path consistency
- The off-by-one bug in round_num+1

The `test_bracket_integrity.py` tests are structural assertions against manually-constructed test data, not against actual `construct_candidate_bracket()` output. The `test_advancement_consistency` test creates an inconsistent bracket in `bad_picks` but **never asserts that validation catches it** — it just checks the values exist.

---

## What Improved Since Last Review

1. **κ = 13.0** — Changed from 11.5. This is correct per the amendment and meaningfully compresses probabilities toward 50%.
2. **UPS implementation in sharp.py** — `compute_upset_propensity_score()` and `apply_upset_propensity_modifier()` are well-implemented with correct feature calculations and weighting.
3. **Round-dependent seed prior** — `apply_seed_prior()` now takes `round_num` and uses appropriate weights (0.60 for R1, 0.80 for E8+).
4. **Conference momentum for all conferences** — Auto-bid boost now applies to mid-majors too, not just power conferences.
5. **Experience modifier increased** — From +0.02/cap +0.05 to +0.03/cap +0.06.
6. **Constants added** — `UPSET_TARGETS`, `UPS_WEIGHTS`, `STRATEGY_CHAMPION_SEEDS`, `EXPECTED_UPSETS_PER_TOURNAMENT`, etc. are all correctly defined.
7. **Ownership fallback partially fixed** — Some code paths now attempt to use `SEED_OWNERSHIP_CURVES` instead of raw 0.5 defaults, though issues remain (see #8).

---

## What Still Needs to Happen (Priority Order)

### P0 — Blocking (Must fix before the optimizer produces valid output)

1. **Rewrite `construct_candidate_bracket()` top-down** — Champion first, then FF, then paths, then remaining games. This is the single highest-impact change.
2. **Implement `select_upsets_by_distribution()`** — Use `UPSET_TARGETS` to allocate upsets by seed matchup type instead of a flat counter.
3. **Enforce champion differentiation** — Use `STRATEGY_CHAMPION_SEEDS` and ensure at least 2 of 3 brackets have different champions.
4. **Fix the round_num+1 off-by-one** in `generate_public_bracket()` — Championship ownership lookup reads round 7 instead of round 6.

### P1 — Important (Significant quality impact)

5. **Implement `rank_upset_candidates()`** — Score and rank upsets by composite metric, don't iterate slots sequentially.
6. **Fix matchup matrix to support round-specific probabilities** — Either compute on-the-fly or build per-round matrices.
7. **Add perturbation search** — Try champion swaps, FF swaps, upset toggles on the best bracket.
8. **Fix `generate_public_bracket()` champion path consistency** — Selected champion must actually win through their path in opponent brackets.

### P2 — Medium

9. **Replace crude seed-based leverage** in `update_leverage_with_model()` with simulation-based advancement probabilities.
10. **Add real bracket consistency validation** that raises `BracketConsistencyError`.
11. **Deduplicate `assign_confidence_tier()`**.

### P3 — Testing

12. **Write tests for amendment requirements:** different champions, upset distribution, top-down order, strategy differentiation metrics, off-by-one bug.
13. **Test `test_bracket_integrity` against real `construct_candidate_bracket()` output**, not manual test data.

---

## SCORE: 4/10

**Rationale:** Up from 3/10 because `sharp.py` is genuinely well-done — the probability model improvements (κ, UPS, round-dependent blending, expanded modifiers) are correct and well-coded. The constants infrastructure is solid. But the optimizer — the core module that actually *uses* all this work to build brackets — is essentially unchanged from iteration 2. The amendment's six critical requirements (top-down construction, upset distribution targets, champion differentiation, UPS-driven upset selection, perturbation search, strategy differentiation) are all unimplemented in the optimizer. Good model + broken optimizer = unusable output. The off-by-one bug in public bracket generation (#8) also corrupts the Monte Carlo evaluation, making even the P(1st) numbers unreliable.

The gap is: sharp.py is ~80% done, constants.py is ~95% done, contrarian.py is ~60% done, optimizer.py is ~20% done against the amendment spec.
