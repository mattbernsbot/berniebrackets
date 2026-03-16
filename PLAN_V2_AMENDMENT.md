# PLAN V2 AMENDMENT: Calibration Fixes

**Status:** Ready for Implementation  
**Date:** 2026-03-15  
**Scope:** 5 targeted fixes to the V2 optimizer — no architectural changes  
**Prerequisite:** Read PLAN_V2.md §7-§8 and optimizer.py before implementing

---

## Amendment 1: R1 Upset Thresholds Are Too Tight

### The Bug

In `construct_bracket_from_scenario()`, R1 upsets are filtered by a flat EMV threshold:

```python
emv_thresholds = {"low": 0.5, "medium": 0.0, "high": -1.0}
```

These thresholds are miscalibrated because the EMV formula produces near-zero values for most games. Here's why:

```
EMV = p_upset × R1_points × fav_ownership − p_chalk × R1_points × (1 − fav_ownership)
```

When public ownership tracks actual probability (which it does — a 5-seed has ~65% win probability AND ~65% public ownership), the two terms cancel:

| Matchup | p_upset | fav_ownership | EMV |
|---------|---------|---------------|-----|
| 8 vs 9  | 0.48 | 0.52 | **0.00** |
| 7 vs 10 | 0.39 | 0.61 | **-0.04** |
| 6 vs 11 | 0.37 | 0.63 | **-0.20** |
| 5 vs 12 | 0.35 | 0.65 | **0.00** |
| 4 vs 13 | 0.21 | 0.79 | **-1.16** |
| 3 vs 14 | 0.15 | 0.85 | **-1.40** |

With `LOW` threshold at 0.5: **zero upsets pass**. Only when the model strongly disagrees with public ownership (e.g., model says 42% upset while public says 35%) does an EMV exceed 0.5. That's a ~7% gap — rare.

The `MEDIUM` threshold at 0.0 allows 8/9 coin flips and the occasional undervalued 12-seed. Result: 4-5 upsets. Still short of the historical ~8.

### The Fix

Replace the flat threshold with a **two-gate system**: an EMV floor *plus* a target count with EMV-ranked selection.

**New thresholds (Gate 1 — minimum EMV to be considered at all):**

| Chaos Level | EMV Floor | Rationale |
|-------------|-----------|-----------|
| LOW | > −1.0 | Admits 8/9, 7/10, 6/11, 5/12 games; excludes 14+ seeds |
| MEDIUM | > −2.0 | Also admits 4/13, marginal 3/14 |
| HIGH | > −3.5 | Admits everything except 1/16 |

**Target upset counts (Gate 2 — sort passing candidates by EMV descending, take top N):**

| Chaos Level | Target R1 Upsets | Region Max |
|-------------|-----------------|------------|
| LOW | 6–8 | 3 per region |
| MEDIUM | 8–10 | 3 per region |
| HIGH | 10–13 | 4 per region |

**Selection algorithm:**
1. Compute EMV for all non-locked R1 games
2. Filter by EMV floor (Gate 1)
3. Sort remaining by EMV descending
4. Always include all 8/9 games where EMV ≥ −0.2 (they're coin flips; historical rate is ~2 upsets per 4 games)
5. Take the top N remaining candidates up to the target count, respecting region caps
6. If below target minimum after filtering, relax EMV floor by 0.5 and retry

This replaces the current inline threshold block (lines in PHASE 3 of `construct_bracket_from_scenario`). Factor the logic into the `select_upsets()` function that PLAN_V2 §8.3 already specifies but was never implemented.

---

## Amendment 2: Add Upset Selection for Rounds 2–6

### The Bug

`construct_bracket_from_scenario()` Phase 4 ("Fill remaining rounds with chalk") picks the higher-probability team for every R2–R6 game:

```python
prob_a = matchup_matrix.get(team_a, {}).get(team_b, 0.5)
winner = team_a if prob_a >= 0.5 else team_b
```

This produces **zero upsets** in rounds 2–6. Historical data shows ~9 more upsets across these rounds:

| Round | Games | Historical Upsets | Current Output |
|-------|-------|-------------------|----------------|
| R2 (32) | 16 | ~5 | 0 |
| S16 (16) | 8 | ~2.5 | 0 |
| E8 (8) | 4 | ~1 | 0 |
| FF | 2 | ~0.5 | 0 |
| Championship | 1 | ~0.3 | 0 |

A bracket with zero later-round upsets is unrealistically chalky and sacrifices differentiation.

### The Fix

Add a **Phase 3.5: Later-Round Upset Selection** between the current Phase 3 (R1 upsets) and Phase 4 (fill with chalk). Process rounds 2–6 sequentially — each round depends on the prior round's picks.

**For each non-locked game in round R (2 through 5):**

1. Determine the two teams meeting (from existing picks of feeder slots)
2. Identify the favorite (higher matchup probability) and underdog
3. Compute the round-adjusted EMV:

```
EMV_R = p_underdog × round_points[R] × fav_round_ownership
      − p_favorite × round_points[R] × (1 − fav_round_ownership)
```

Where `fav_round_ownership` = `SEED_OWNERSHIP_CURVES[fav_seed][R+1]` (ownership for advancing *past* round R). This is the fraction of the public picking the favorite at this stage.

4. Apply round-specific thresholds:

| Round | EMV Threshold (LOW) | EMV Threshold (MEDIUM) | EMV Threshold (HIGH) | Max upsets |
|-------|--------------------|-----------------------|---------------------|------------|
| R2 | > 0.0 | > −2.0 | > −5.0 | 4 of 16 |
| S16 | > 0.0 | > −3.0 | > −8.0 | 2 of 8 |
| E8 | > 0.0 | > −5.0 | > −10.0 | 1 of 4 |
| FF | > 0.0 | > −5.0 | > −15.0 | 1 of 2 |

**Why the thresholds scale with round points:** Later rounds have higher scoring (R2=20, S16=40, E8=80, FF=160), so the EMV magnitude is naturally larger. The thresholds are calibrated as approximately 0.0 (LOW = only truly positive value), or −0.1× to −0.15× the round points (MEDIUM), or −0.25× to −0.3× (HIGH).

**Why this works for differentiation:** In R2, a 5-seed has ~38% ownership advancing to S16, while a 12-seed has ~12.5%. The differentiation multiplier is enormous — almost nobody picks the 12-seed in S16. When the 12-seed actually beats the 4-seed in R2, you gain 20 points that 87.5% of the field doesn't get.

**Special handling for R1 upset winners:** If we picked an R1 upset (e.g., 12 over 5), evaluate their R2 game with a bonus:
- The R2 opponent may be weaker than expected (e.g., 4-seed instead of facing the 5-seed)
- The differentiation is extreme (almost nobody has the 12-seed in S16)
- Apply a +20% EMV bonus for advancing an R1 upset pick (stacking contrarian value)

**Do NOT touch locked slots.** FF paths and the champion path are locked — those are set by the scenario. Only evaluate non-locked, non-skeleton games.

**Cinderella advancement:** If the scenario has a Cinderella with a target round, advance them to that round regardless of EMV (the scenario demands it). Mark those slots as locked.

---

## Amendment 3: Fix Backward-Compatibility Wrapper for Tests

### The Bug

`construct_candidate_bracket()` calls `optimize_bracket()`, which fails on small test brackets:

1. `estimate_title_probabilities()` searches for `round_num == 6` (championship slot). Test brackets use round 3 as championship → returns empty dict → no candidates
2. `generate_scenarios()` gets empty candidates → returns empty list → no brackets
3. `select_diverse_output_brackets([])` → `sorted_by_p_first[0]` → **IndexError**

Three tests fail: `test_construct_candidate_bracket_completeness`, `test_bracket_consistency`, `test_leverage_scores_not_all_one`.

### The Fix

Modify `construct_candidate_bracket()` to detect non-standard brackets and fall back to chalk:

```
def construct_candidate_bracket(teams, matchup_matrix, ownership_profiles, bracket, config, strategy="balanced"):
    """Backward compat wrapper. Detects non-standard brackets and falls back gracefully."""
    
    # Detect if this is a full tournament bracket (has round 6 championship slot)
    has_championship = any(s.round_num == 6 for s in bracket.slots)
    
    if not has_championship:
        # Small test bracket — skip full pipeline, return chalk fallback
        return _create_simple_chalk_bracket(teams, matchup_matrix, bracket, config, ownership_profiles)
    
    try:
        brackets = optimize_bracket(teams, matchup_matrix, ownership_profiles, bracket, config)
        return brackets[0] if brackets else _create_simple_chalk_bracket(...)
    except (IndexError, ValueError, KeyError):
        return _create_simple_chalk_bracket(teams, matchup_matrix, bracket, config, ownership_profiles)
```

Additionally, fix `_create_simple_chalk_bracket()` to handle variable bracket sizes:
- Detect the maximum round number dynamically (`max(s.round_num for s in bracket.slots)`) instead of hardcoding round 6
- Set champion from the max-round slot's winner
- Set final_four from the appropriate round (max_round - 2), or empty list if bracket is too small
- Set elite_eight similarly, or empty list

This makes the fallback work for any bracket size (3-slot test brackets through full 63-slot brackets).

---

## Amendment 4: Enforce Meaningful Bracket Differentiation

### The Bug

`select_diverse_output_brackets()` uses a threshold of only **3 different picks** to accept the "safe" bracket:

```python
if diff_count >= 3:  # Lowered threshold - just needs some differentiation
    safe = candidate
    break
```

Result: safe and optimal have the same champion, nearly identical FF, same ~4 upsets. The aggressive bracket also defaults to the same champion when no alternative-champion bracket exists.

Root cause: all 6 scenarios often produce the same champion (e.g., Duke dominates with 24% title prob). The scenario generator doesn't force enough champion diversity.

### The Fix — Two Parts

**Part A: Force champion diversity in scenario generation**

In `generate_scenarios()`, enforce this invariant:
- The 2 chalk scenarios use champion_candidate[0]
- The 2 contrarian scenarios MUST use champion_candidate[1] (or [2] if [1] is same region)
- The 2 chaos scenarios MUST use a candidate that is NOT champion_candidate[0]

If fewer than 3 candidates exist, the chaos scenarios can reuse contrarian's champion but MUST have different FF composition (at least 2 different FF teams).

**Part B: Raise differentiation thresholds in `select_diverse_output_brackets()`**

| Comparison | Current Threshold | New Threshold |
|-----------|-------------------|---------------|
| Optimal vs Safe | 3 picks | 8 picks |
| Optimal vs Aggressive | (no minimum) | 15 picks |
| Safe vs Aggressive | (no minimum) | 8 picks |

**Selection algorithm (revised):**

1. **Optimal:** Highest P(1st) across all brackets. Label "optimal".

2. **Safe:** Among brackets with P(1st) > 50% of optimal's P(1st) AND ≥ 8 different picks from optimal:
   - Pick the one with highest P(top 3)
   - Prefer same champion as optimal (this is the "safe" play — same core bet, different details)
   - If no bracket qualifies, relax to ≥ 5 different picks

3. **Aggressive:** Among brackets with a **different champion** from optimal AND ≥ 15 different picks from optimal:
   - Pick the one with highest P(1st)
   - If no bracket with a different champion qualifies, relax to ≥ 10 different picks but STILL require different champion
   - If literally no bracket has a different champion, take the bracket with the most different picks from optimal

**Additional enforcement:** Count "weighted differences" — a pick difference in R5/R6 (FF/Championship) counts as 3 differences. A pick difference in R3/R4 (S16/E8) counts as 2. R1/R2 count as 1. This ensures the brackets differ in meaningful high-impact games, not just trivial R1 swaps.

---

## Amendment 5: Fix Confidence Tier Assignment for Upsets

### The Bug

In `construct_bracket_from_scenario()`, every pick is hardcoded to `"Lock"`:

```python
picks.append(BracketPick(
    ...
    confidence="Lock",   # ← HARDCODED for ALL picks including upsets
    ...
))
```

The `assign_confidence_tier()` function exists and is correct:
```python
def assign_confidence_tier(win_prob):
    if win_prob >= 0.75:   return "🔒 Lock"
    elif win_prob >= 0.55: return "👍 Lean"
    else:                  return "🎲 Gamble"
```

But it's never called during bracket construction.

### The Fix

Replace the hardcoded `confidence="Lock"` with a computed value. For each pick:

1. **R1 games:** Determine the winner's win probability from the matchup matrix.
   - If the winner is team_a: `win_prob = matchup_matrix[team_a][team_b]`
   - If the winner is team_b: `win_prob = matchup_matrix[team_b][team_a]`
   - Pass `win_prob` to `assign_confidence_tier()`

2. **R2–R6 games (non-locked):** Look up the matchup probability between the two teams that fed into this slot (based on existing picks). Use that win probability for the tier.

3. **Locked path games (champion/FF paths):** The win probability is the path opponent's probability from `build_team_path()`. The `opponents` list in PathInfo contains `(slot_id, opponent_name, win_prob)` tuples — use `win_prob` for the tier.

**Expected behavior after fix:**

| Pick Type | Typical win_prob | Confidence |
|-----------|-----------------|------------|
| 1-seed over 16-seed | 0.99 | 🔒 Lock |
| 2-seed over 15-seed | 0.94 | 🔒 Lock |
| 3-seed over 14-seed | 0.85 | 🔒 Lock |
| 5-seed over 12-seed | 0.65 | 👍 Lean |
| 8-seed over 9-seed | 0.52 | 🎲 Gamble |
| 12-seed over 5-seed (upset!) | 0.35 | 🎲 Gamble |
| 10-seed over 7-seed (upset!) | 0.39 | 🎲 Gamble |
| 9-seed over 8-seed (upset!) | 0.48 | 🎲 Gamble |

Upsets will correctly display as 🎲 Gamble. Chalk picks against weak opponents display as 🔒 Lock. Close matchups display as 👍 Lean or 🎲 Gamble.

---

## Implementation Order

These 5 fixes are independent and can be implemented in any order. Recommended sequence:

1. **Amendment 5** (confidence tiers) — 5 minutes, trivial, zero risk
2. **Amendment 3** (test wrapper) — 10 minutes, unblocks test suite
3. **Amendment 1** (R1 thresholds) — 30 minutes, biggest impact on bracket quality
4. **Amendment 2** (R2–R6 upsets) — 45 minutes, second biggest impact
5. **Amendment 4** (differentiation) — 30 minutes, requires amendments 1–2 to be meaningful

After all 5: re-run Monte Carlo. Expected improvement:
- R1 upsets: 4–5 → 7–9 ✓
- R2–R6 upsets: 0 → 5–8 ✓
- Total upsets per bracket: ~4 → ~14 (historically realistic)
- Bracket differentiation: optimal vs aggressive should differ in 15+ picks with different champions
- Confidence labels: upsets show 🎲, chalk shows 🔒

---

## What This Amendment Does NOT Change

- Champion Evaluator formula (correct)
- Monte Carlo simulation (correct)
- Matchup matrix / sharp.py (correct)
- Scoring logic (correct)
- Top-down construction architecture (correct)
- Scenario types (correct — just forcing more champion diversity)

The architecture is right. These are calibration knobs and a missing feature (R2+ upsets).
