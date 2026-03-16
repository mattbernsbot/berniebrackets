# Bracket Optimizer V2 — Code Review

**Reviewer:** Senior Code Reviewer (AI)  
**Date:** 2026-03-15  
**Scope:** Full pipeline review — correctness, coherence, output fidelity  
**Run Config:** `python3 main.py full --sims 200`  
**Pipeline Status:** Runs to completion, produces 3 brackets, no crashes ✅

---

## Summary

The V2 optimizer is a substantial, well-architected system with a sound 7-component pipeline: champion evaluation → scenario generation → bracket construction → EMV upset selection → Monte Carlo evaluation → output selection. The core logic is largely correct — **bracket coherence is maintained** (verified: zero coherence errors across all 3 output brackets), and later-round upsets **are actually being injected into the brackets** (R2-R5 picks reflect underdog winners). The ensemble upset model works and integrates cleanly.

However, several bugs cause the output to **misrepresent what the brackets actually contain**, making it appear that later-round upsets are missing when they're not. The most critical issue is `is_upset=False` for all R2-R6 picks, which causes the analysis report and bracket.txt to hide every later-round upset from the user. Combined with a region mismatch bug in the data pipeline, a broken leverage metric, and a dead Key Differentiators section in the report, the output layer significantly undermines the otherwise-solid optimization engine.

---

## Issues

### 1. [CRITICAL] `is_upset` is always `False` for R2-R6 picks

**File:** `src/optimizer.py`, `construct_bracket_from_scenario()`, ~line 610-615  
**Root cause:** R2-R6 bracket slots have `seed_a=0` and `seed_b=0` (populated only for R1 slots). The upset detection logic compares `slot.seed_a < slot.seed_b`, which is `0 < 0 → False` for every later-round game.

```python
# Current broken code:
is_upset = (winner == slot.team_b and slot.seed_a < slot.seed_b) or \
           (winner == slot.team_a and slot.seed_b < slot.seed_a)
```

**Impact:** This is the primary reason "later-round upsets don't appear in final output." The upsets ARE in the bracket (verified: Connecticut over Florida in R4, Florida St. over Saint Mary's in R2, Arkansas over Michigan in R3, etc.), but they're all marked `is_upset=False`. The analysis report only shows `[UPSET]` tags for R1 games. The bracket.txt never shows `[UPSET]` for later rounds.

**Fix:** For R2+ picks, determine upset by comparing the two feeder teams' seed numbers (already available via `team_seeds` dict):

```python
if slot.round_num >= 2:
    feeders = [s for s in bracket.slots if s.feeds_into == slot_id]
    if len(feeders) == 2:
        team_a = existing_picks.get(feeders[0].slot_id)
        team_b = existing_picks.get(feeders[1].slot_id)
        if team_a and team_b:
            seed_a = team_map.get(team_a, Team(name=team_a)).seed
            seed_b = team_map.get(team_b, Team(name=team_b)).seed
            winner_seed = team_map.get(winner, Team(name=winner)).seed
            loser = team_b if winner == team_a else team_a
            loser_seed = team_map.get(loser, Team(name=loser)).seed
            is_upset = winner_seed > loser_seed
```

---

### 2. [HIGH] Region mismatch between `team.region` and bracket slot region

**Files:** `src/scout.py`, `generate_bracket_from_kenpom()` and `merge_team_data()`  
**Root cause:** The S-curve distribution in `generate_bracket_from_kenpom()` correctly assigns regions using S-curve reversal (seed 1: E,W,S,MW; seed 2: MW,S,W,E). But `merge_team_data()` uses a simple `region_names[idx % 4]` formula that doesn't follow the S-curve, so `team.region` attributes disagree with the bracket slot regions for **all non-1-seeds** (32 out of 68 teams affected).

**Impact:** 
- Scenario generation uses `team.region` to group teams into regions for FF selection via `select_regional_champion()`. A team assigned `team.region="West"` might actually play in the South bracket region. 
- Champion path computation might traverse wrong bracket slots.
- The FF team selections may be internally consistent (they happen to work because path building uses slot-level navigation, not `team.region`), but the semantic layer is wrong.
- Verified: The optimal bracket has `Iowa St.` (team.region=West, actually in South bracket) and `Illinois` (team.region=South, actually in West bracket) in the Final Four. The bracket is coherent at the pick level, but the scenario's intent doesn't match bracket reality.

**Fix:** `merge_team_data()` should read the actual region from the bracket slots, or better: just use the team's bracket slot region, not a re-computed one.

---

### 3. [HIGH] Leverage scores are all < 0.25 — "Key Differentiators" section always empty

**File:** `src/contrarian.py`, `calculate_pool_leverage()` and `update_leverage_with_model()`  
**Root cause:** Pool-size-aware leverage formula `prob / ((pool_size - 1) * ownership + 1)` produces values in the range [0.01, 0.22] for a 25-person pool. The `analyst.py` report then filters for `leverage > 1.5`, which matches zero picks.

Example: A 1-seed in R1 with 97% ownership: `1.0 / (24 * 0.97 + 1) = 0.04`. A 12-seed upset with 35% ownership: `0.35 / (24 * 0.35 + 1) = 0.037`. These are never > 1.5.

**Impact:** The "Key Differentiators" section of analysis.md is permanently empty. This is the most valuable section for the user — they need to know which picks make their bracket special.

**Fix:** Either:
1. Change the threshold in `analyst.py` from `1.5` to something pool-size-appropriate (e.g., `1.0 / pool_size` as baseline, highlight picks above 2× baseline), OR
2. Use a relative metric: show the top N picks ranked by leverage regardless of threshold, OR
3. Use simple `prob / ownership` ratio for reporting purposes while keeping pool-aware leverage for optimization.

---

### 4. [MEDIUM] Output selector saves 3 brackets correctly, but 2 of 3 are often very similar

**File:** `src/optimizer.py`, `select_diverse_output_brackets()`  
**Observed:** The selector correctly saves 3 brackets (optimal, safe_alternate, aggressive_alternate). However:
- Optimal and safe_alternate often share the same champion (Duke in both during this run).
- chalk_0 and chalk_1 scenarios produce near-identical R1 upsets (same 8 upsets each).
- The "8 picks different" threshold for safe_alternate is met via later-round differences, but the R1 selections are identical.
- The safe_alternate has `is_upset` counts identical to optimal (8 R1 upsets, 0 marked R2+) — the user can't tell them apart from the report.

**Root cause:** The 6 scenarios only use 3 champion candidates (Duke, Florida, Arizona) because the 8% title probability threshold is too aggressive. With only 3 candidates, chalk_0 and chalk_1 are near-clones, and contrarian_0 ≈ chaos_0 (both use Florida).

**Fix:** Lower the `CHAMPION_MIN_TITLE_PROB["small"]` threshold from `0.08` to `0.04-0.05` to allow Michigan (7.3%), Illinois (6.7%), etc. as champion candidates. This would increase scenario diversity and output bracket differentiation.

---

### 5. [MEDIUM] Duplicate title probability estimation

**File:** `main.py`, `cmd_analyze()` and `src/optimizer.py`, `evaluate_champions()`  
**Root cause:** `cmd_analyze()` calls `estimate_title_probabilities()` with 2000 sims, then passes the results to `update_leverage_with_model()`. But `optimize_bracket()` → `evaluate_champions()` calls `estimate_title_probabilities()` **again** with the same 2000 sims and same base seed, producing identical results.

**Impact:** Performance waste — the matchup matrix computation takes ~69 seconds (the bottleneck), but the duplicate 2000-sim title estimation is unnecessary overhead. More importantly, the first title_probs result (used for leverage) and the second (used for champion evaluation) are always identical, which is correct but accidental — if seeds diverged, you'd get inconsistent behavior.

**Fix:** Pass `title_probs` from `cmd_analyze()` into `optimize_bracket()` and thread it through to `evaluate_champions()`, avoiding the second call.

---

### 6. [MEDIUM] R1 upset EMV candidates are identical across most scenarios

**Observed:** chalk_0, chalk_1, contrarian_1, chaos_0, and chaos_1 all share the exact same R1 upset candidates (same 8 or 10 upsets). This is because `locked_slots` only protects the champion and FF paths, but most R1 games aren't on those paths. The EMV calculation doesn't incorporate any scenario-specific information (chaos_level only affects EMV floor and target count, not the EMV values themselves).

**Impact:** Bracket differentiation relies almost entirely on champion selection and later-round upsets, not R1. Since R1 is worth the most total points (32 games × 10 points), having identical R1 across most scenarios reduces the diversity of the evaluated brackets.

**Fix:** Consider adding a small random jitter to EMV scores per scenario, or varying the region_cap per scenario, or rotating which 8/9 upsets are "forced" between scenarios.

---

### 7. [LOW] Ensemble model deserialization is O(n_trees) per prediction

**File:** `upset_model/ensemble.py`, `predict_ensemble()`  
**Root cause:** `predict_ensemble()` calls `DecisionNode.from_dict(d)` for all 300 trees on **every single prediction call**. With 2278 matchup pairs, that's 2278 × 300 = 683,400 tree deserializations.

**Impact:** The matchup matrix computation takes ~69 seconds. Most of this is likely tree deserialization overhead. Caching the deserialized trees after the first call would likely reduce this to under 5 seconds.

**Fix:** Deserialize trees once in `UpsetPredictor.__init__()` and store them as `self.trees`. Change `predict_ensemble()` to accept pre-deserialized trees.

---

### 8. [LOW] `analysis.md` R2-R6 round breakdown shows no upsets and no matchup details

**File:** `src/analyst.py`, `generate_analysis_report()`  
**Root cause:** The round breakdown only displays `upsets = [p for p in round_picks if p.is_upset]`. Since `is_upset` is always `False` for R2+ (Issue #1), these sections are empty. Additionally, the report doesn't show which teams played each other in later rounds — just the winners.

**Impact:** The analysis report is incomplete and misleading. It suggests the bracket has zero later-round upsets when it actually has 7 (in the optimal bracket: Florida St. over Saint Mary's, BYU over Gonzaga, Missouri over Texas Tech, Nebraska over Louisville in R2; Connecticut over Houston, Arkansas over Michigan in R3; Connecticut over Florida in R4).

---

### 9. [LOW] Monte Carlo opponent brackets may not be realistic enough

**File:** `src/optimizer.py`, `generate_opponent_bracket()`  
**Observed:** Opponents are generated using ownership-weighted random selections, which is a reasonable approximation. However, there's no coherence enforcement for opponent brackets — an opponent might pick a team to advance to the S16 without picking them to win R1 or R2. The `round_ownership` weights used for later rounds don't condition on previous picks.

**Impact:** Opponent brackets are slightly easier to beat than real human brackets (which have structural coherence). This may inflate P(1st) estimates by 1-3%. At 200 sims, the Monte Carlo variance is already ±2%, so this is a minor concern.

---

### 10. [INFO] The 200-sim run has high variance

**Observed:** P(1st) values range from 4.5% to 6.5% across the 6 brackets. With 200 sims, the standard error for a 6% estimate is `sqrt(0.06 * 0.94 / 200) ≈ 1.7%`, meaning the 95% CI is roughly [2.7%, 9.3%]. The difference between 4.5% and 6.5% is well within noise.

**Impact:** At 200 sims, you can't reliably distinguish between scenarios. The "optimal" bracket was selected by what might be noise. The default 10,000 sims would give SE ≈ 0.24%, making the rankings meaningful.

**Not a bug:** This is just the --sims 200 test configuration. The system correctly supports higher sim counts.

---

## What Works Well

1. **Bracket coherence is perfect.** All 3 output brackets pass the validate_bracket_coherence check — no team wins a game they didn't play in. The path builder fix is solid.

2. **Later-round upsets ARE being generated and injected.** The construct_bracket_from_scenario two-pass system (fill chalk, then overlay EMV upsets) works correctly. The re-propagation after later-round upsets is a smart fix that avoids orphaned picks.

3. **The EMV calculation is mathematically sound.** The formula correctly balances scarcity value (picking a team nobody else has) against cost (missing a popular pick), weighted by upset probability. The probability floor (< 15% → kill candidate) prevents absurd picks like 16-over-1.

4. **Scenario diversity is well-designed.** The chalk/contrarian/chaos tiers with different chaos_levels create meaningfully different bracket archetypes. Amendment 4 (force different champions for contrarian/chaos) works correctly.

5. **The ensemble upset model integrates cleanly.** AUC 0.733 on real data is solid. The fallback to seed-based probabilities when the model is unavailable is correct. The extreme seed clamping (Issue: 1v16, 2v15) prevents model miscalibration.

6. **The pool-size-aware optimization is conceptually correct.** Champion evaluation, EMV calculation, and leverage all properly account for pool size, which is the key insight for bracket pool strategy.

7. **Code quality is high.** Clear module boundaries, comprehensive dataclass models, good logging, proper error handling. The codebase is well-documented with docstrings explaining the math.

---

## SCORE: 6/10

**Why not higher:** The `is_upset` bug (#1) makes the system's output actively misleading — it tells the user they have 8 R1 upsets when they actually have 15 total upsets including 7 later-round ones. The region mismatch (#2) means scenarios are built with incorrect regional assumptions. The empty Key Differentiators (#3) removes the most valuable section of the report. These three issues undermine the user's ability to understand and trust the brackets.

**Why not lower:** The optimization engine itself is fundamentally sound. Bracket coherence is flawless. The EMV-based upset selection works. The Monte Carlo evaluation is correctly implemented. The architecture is clean and extensible. Fixing issues #1-3 would lift this to an 8/10.
