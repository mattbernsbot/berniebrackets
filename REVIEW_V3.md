# REVIEW V3 — Bracket Optimizer with Real ESPN Pick Data

**Reviewer:** Senior Code Review (automated)  
**Date:** 2026-03-16  
**Previous Score:** 8/10  
**Run Config:** `python3 main.py full --sims 200 --no-strict-espn`

---

## Summary

The system runs end-to-end and produces 3 coherent, differentiated brackets with zero structural violations. All champion paths are unbroken. The pipeline successfully integrates:

- **Real 2026 NCAA bracket** from ncaa.com (68 teams across 4 regions)
- **Live KenPom ratings** (365 teams scraped from kenpom.com)
- **Real ESPN People's Bracket picks** via Playwright API interception (60 teams, 64 R1 picks captured)
- **Trained sklearn ensemble model** (LR + RF + GB, loaded from `sklearn_model.joblib`)
- **Scenario-based optimization** with EMV-driven upset selection

The output quality is real and meaningful — P(1st) of 8.5% for the optimal bracket in a 25-person pool is a 2.1x edge over baseline (4%). Later-round upsets appear and are marked correctly. The three output brackets have genuinely different champions (Duke / Michigan / Arizona).

However, two data pipeline bugs significantly degrade the quality of the ownership model and, by extension, the EMV calculations that drive the entire optimization strategy.

---

## Issues

### 1. [HIGH] KenPom matching fails for 21 of 68 teams — wrong temp file used

**File:** `main.py:cmd_collect()` (lines ~120-145)  
**Impact:** 21 teams (31%) use fabricated AdjEM/AdjO/AdjD values instead of real KenPom stats.

`collect_all()` calls `merge_team_data()` which selects the **top 68 teams by KenPom rank**. These 68 are saved to `teams_kenpom_temp.json`. Then `load_real_bracket()` tries to match the real bracket's 68 teams against this file — but the real bracket includes 12-16 seeds that are ranked outside the KenPom top 68 (e.g., Siena #200+, Furman, UMBC, Howard).

The fix is trivial: save ALL 365 KenPom teams to the temp file instead of only the merged 68.

```python
# In cmd_collect, change:
save_json([t.to_dict() for t in teams_kenpom], temp_kenpom_file)
# Instead of saving the merged 68:
# save_json([t.to_dict() for t in teams_kenpom], ...)  # <-- currently saves merged
```

Wait — looking more closely, `collect_all()` returns `merged_teams` (68 teams). The actual KenPom scrape result (`teams_kenpom` in `cmd_collect`) is the raw return from `collect_all()` but it's already been through `merge_team_data`. The variable naming is misleading:

```python
teams_kenpom, _, espn_picks = collect_all(config)
# teams_kenpom is actually 68 merged teams, NOT 365 raw KenPom teams
```

**Fix:** Either (a) have `collect_all` return the raw 365-team KenPom list separately, or (b) scrape KenPom directly in `cmd_collect` before calling `collect_all`, and save that full list for `load_real_bracket` to match against.

**Affected teams:** Siena, Northern Iowa, Cal Baptist, North Dakota St., Furman, Long Island, High Point, Hawaii, Kennesaw St., Queens (N.C.), Troy, Penn, Idaho, Prairie View A&M, Lehigh, Hofstra, Wright St., Tennessee St., UMBC, Howard, Miami (Ohio)

All get fabricated stats: `adj_em = 25.0 - (seed * 1.5)`, `adj_o = 110.0`, `adj_d = 110.0 - adj_em`. These affect every matchup involving these teams and cascade through the matchup matrix.

---

### 2. [HIGH] ESPN title pick data nearly empty — geometric interpolation produces garbage R2-R5 ownership

**File:** `src/scout.py:parse_espn_api_response()`  
**Impact:** All teams except Duke have incorrect ownership for rounds 2-6, making EMV calculations unreliable.

The ESPN Gambit API interception captures 64 R1 picks (good!) but only 2 title picks (Duke 98%, Siena 2%). The `displayOrder == 0` proposition apparently only returned the championship game participants, not per-team championship ownership.

With R6 defaulting to `0.01` for 58 of 60 teams, the geometric interpolation `R2 = R1 * (R6/R1)^(1/5)` collapses drastically:

| Team | R1 (real) | R2 (interpolated) | R2 (expected) |
|------|-----------|-------------------|---------------|
| Arizona | 97.4% | 39.0% | ~85% |
| Florida | 98.0% | 39.2% | ~85% |
| Houston | 96.7% | 38.7% | ~80% |
| Illinois | 92.3% | 37.3% | ~70% |

A 1-seed showing 39% R2 ownership means the EMV calculator thinks most of the public *doesn't* pick them past R1, which is absurd. This makes every "chalk" pick look like a high-leverage contrarian play, defeating the purpose of ownership-based optimization.

**Fix options:**
1. **Parse all round propositions**, not just `scoringPeriodId == 1` and `displayOrder == 0`. The Gambit API likely has propositions for each round (R2, S16, E8, FF, Championship). Extract them all.
2. **Fallback to SEED_OWNERSHIP_CURVES** for rounds 2-6 when title data is sparse. The seed-based curves are more accurate than geometric interpolation from bad R6 data.
3. **Validate interpolated values** against seed-curve baselines and clamp to within ±20% of expected range.

---

### 3. [MEDIUM] Safe and aggressive brackets are nearly identical

The "safe_alternate" (Michigan) and "aggressive_alternate" (Arizona) brackets share the same FF (except champion), identical E8, and identical R1 upset sets (13 each). The only difference is which team wins the championship game in slot 63.

From the selection log:
- safe ↔ optimal: 10 weighted picks different
- aggressive ↔ optimal: 11 weighted picks different

But safe ↔ aggressive: the FF and E8 are identical — `['Florida', 'Duke', 'Michigan', 'Arizona']` for both. This violates the stated goal of "meaningfully different" brackets.

**Root cause:** The scenario generator produces 6 scenarios, but `chaos_0` and `chaos_1` have the same FF structure and only differ by champion. `contrarian_0` and `contrarian_1` are also very similar. The `select_diverse_output_brackets` function picked from a pool where most candidates were near-clones.

**Fix:** Enforce that `safe` and `aggressive` differ from each other by ≥8 weighted picks, not just from `optimal`. Also ensure at least 2 of the 3 brackets have different Final Four compositions (not just different champions).

---

### 4. [MEDIUM] 15% upset probability floor is too aggressive for later rounds

**File:** `src/optimizer.py:construct_bracket_from_scenario()` (later-round upset code ~line 620)

The system applies `if p_underdog < 0.15: emv = -999` uniformly across all rounds. This makes sense for R1 (16 seeds at ~1% are bad bets), but in later rounds a 15% threshold eliminates many reasonable upset picks. A 3-seed vs 2-seed in the Elite 8 where the 3-seed has a 42% win probability would NOT be filtered — but edge cases around the boundary are problematic.

More importantly, the R1 EMV formula uses R1 ownership (`round_ownership[1]`), but the later-round EMV formula uses next-round ownership with a scarcity/commonality calculation that doesn't account for the reduced field. This can produce inflated EMV values for later rounds (e.g., R2 EMV of 5.50 for NC State over Gonzaga).

---

### 5. [MEDIUM] `load_real_bracket.py` region case mismatch

The real bracket uses `EAST`, `WEST`, `SOUTH`, `MIDWEST` (uppercase) for regions, while `BracketSlot` in `load_real_bracket.py` uses `East`, `West`, `South`, `Midwest` (title case). The `regions_dict` key is uppercase but the slot `region` is title case. This causes mismatches in `generate_scenarios` which does:

```python
regions = list(set(t.region for t in teams if t.region))
```

This returns `['EAST', 'WEST', 'SOUTH', 'MIDWEST']` but `BracketSlot.region` is `'East'`. The `select_regional_champion` function filters by `t.region == region` which means teams in `EAST` don't match slots in `East`. 

In practice, the system still works because `build_team_path` traces via slot IDs and `feeds_into` chains (not region names), but it means some scenario-level regional logic may be comparing apples to oranges.

---

### 6. [LOW] Dead code: `scrape_espn_bracket()` always fails, gets bypassed

The ESPN Bracketology URL returns 404 (the page doesn't exist anymore post-Selection Sunday). The function then falls through to `generate_bracket_from_kenpom()`, which is itself bypassed by `load_real_bracket()` in `cmd_collect()`. The `scrape_espn_bracket` function has a hardcoded "mock bracket" generator that never returns real data anyway (line: `logger.warning("ESPN bracket scraping is simplified - using mock bracket structure")`).

Similarly, `scrape_espn_picks()` (the non-Playwright version) is dead code — it always returns None and is never called in the live pipeline.

---

### 7. [LOW] Matchup matrix computation is O(n²) with the ensemble model, taking ~2 minutes

Building 2,278 matchup probabilities against the sklearn ensemble takes ~130 seconds (the main bottleneck in the pipeline). With 200 sims, total runtime is ~2.5 minutes. At production-level 10,000 sims, this would take ~12 minutes. The matchup matrix could be precomputed and cached since team stats don't change between runs.

---

### 8. [LOW] `value_picks` in `find_value_picks` uses threshold 1.5 but pool-aware leverage values are 0.01-0.18

The `find_value_picks()` function (contrarian.py) uses `min_leverage=1.5` as default threshold. But after `update_leverage_with_model()`, leverage values are pool-size-aware (range: 0.01–0.18 for a 25-person pool). The function returns an empty list in production. Not a runtime problem (it's only used for logging) but indicates a stale interface.

The `analyst.py` report fixed this by using `> 0.02` threshold (BUG FIX #3 comment), but the contrarian module's function is inconsistent.

---

### 9. [LOW] Unused imports and minor code quality issues

- `src/optimizer.py` imports `median` from `statistics` but never uses it
- `src/sharp.py` imports `os` and `Path` but doesn't use them directly (only through `get_predictor`)
- Several functions have `from src.constants import ...` inside function bodies instead of at module top (UPS features, seed defaults) — works but is non-standard
- `assign_confidence_tier` is defined in both `optimizer.py` and `analyst.py` (exact duplicate)

---

## What Works Well

1. **Zero bracket violations.** All 3 brackets pass coherence validation. Every winner at every round properly advanced from a feeder slot. All 3 champion paths (Duke R1→Championship, Michigan R1→Championship, Arizona R1→Championship) are unbroken.

2. **Real data pipeline is functional.** KenPom live scrape returns 365 teams. ESPN Playwright interception captures 60 teams' R1 picks. The ncaa.com bracket has all 68 teams with correct seeds and regions. These aren't synthetic — verified by checking unique R1 ownership values (50 distinct percentages).

3. **Ensemble upset model works.** The sklearn model (LR + RF + GB average) loads from `sklearn_model.joblib` and produces calibrated probabilities. It's the real trained model on 799 historical games, not a from-scratch retrain. The `predict_from_teams()` bridge handles Team ↔ dict conversion cleanly.

4. **Later-round upsets appear and are marked correctly.** The optimal bracket has 15 total upsets: 8 R1, 4 R2, 2 S16, 1 E8. The `is_upset` flag correctly uses actual team seeds for R2+ (BUG FIX #1 in code). The safe/aggressive brackets have 18 upsets each. This is a reasonable range for contrarian play.

5. **EMV-based upset selection is sound in concept.** The two-gate system (EMV floor + target count range) with region caps and 8/9-game auto-inclusion produces sensible R1 upset slates. Iowa (9) over Clemson (8) at EMV=1.07 is the top pick, which is exactly right — 9-over-8 is nearly a coin flip.

6. **Scenario diversity is present at the champion level.** Three distinct champions (Duke, Michigan, Arizona) from different regions. This is exactly what a pool optimizer should do — hedge across different tournament outcomes.

7. **The ESPN Playwright scraper has proper retry logic (3 attempts), caching (2-hour TTL with timestamped snapshots), and graceful degradation.** The cache hit path is fast and avoids unnecessary browser launches.

8. **The strict-ESPN mode** correctly blocks the pipeline when pick data is unavailable, preventing silent fallback to seed-based estimates in production.

9. **Code documentation** is thorough. Docstrings explain what each function does, its arguments, return values, and edge cases. The `PLAN_V2` references in EMV formulas are traceable.

10. **Test suite passes** (9/9 tests, 0.24s). Tests use the backward-compatibility wrappers correctly.

---

## Score Breakdown

| Category | Max | Score | Notes |
|----------|-----|-------|-------|
| ESPN picks integration | 15 | 10 | R1 works; R2-R6 interpolation is broken (Issue #2) |
| Real bracket integration | 15 | 11 | 47/68 matched; 21 use fabricated stats (Issue #1) |
| Upset model | 15 | 14 | Ensemble loads and works correctly |
| Bracket coherence | 15 | 15 | Zero violations, champion paths unbroken |
| Later-round upsets | 10 | 9 | Present, marked, reasonable counts |
| Output quality / differentiation | 10 | 6 | Safe ≈ aggressive is a problem (Issue #3) |
| No fake data | 10 | 6 | 21 teams have fabricated stats; R2-R6 ownership is synthetic |
| Code quality | 10 | 8 | Some dead code, duplicates, but overall clean |

---

## SCORE: 7.5/10

**Down from 8/10** because the two HIGH-severity bugs (#1 KenPom matching, #2 ESPN title data) mean the ownership model — the core differentiator that makes this an *optimizer* rather than just a bracket *generator* — is operating on substantially inaccurate data. The system *works* end-to-end, but the quality of its contrarian recommendations is degraded.

**Path to 9/10:**
1. Fix the KenPom temp file to include all 365 teams (30 min fix)
2. Fix ESPN R2-R6 interpolation — either parse all round propositions or fall back to seed curves when title data is sparse (1-2 hour fix)
3. Enforce safe ↔ aggressive differentiation in bracket selection

**Path to 10/10:**
4. Normalize region case throughout the pipeline
5. Remove dead code (old ESPN scraper, mock bracket generator)
6. Cache the matchup matrix to avoid 2-minute recompute
7. Add integration test that validates all 68 teams have real (non-fabricated) KenPom stats
