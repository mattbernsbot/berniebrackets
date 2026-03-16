# Bracket Optimizer V2B — Re-Review After Bug Fixes

**Reviewer:** Senior Code Reviewer (AI)  
**Date:** 2026-03-15  
**Scope:** Verification of 3 bug fixes + full pipeline correctness re-assessment  
**Run Config:** `python3 main.py full --sims 200`  
**Pipeline Status:** Runs to completion, produces 3 brackets, no crashes ✅  
**Tests:** 9/9 passed ✅

---

## Summary

All three critical/high bugs identified in REVIEW_V2 have been fixed correctly. The system now accurately reports upsets across all rounds, maintains a single source of truth for regions, and populates the Key Differentiators section with meaningful data. The output layer no longer misrepresents the bracket contents — what the optimizer builds is now what the user sees. The pipeline produces 3 differentiated brackets with different champions (Florida, Arizona, Duke), P(1st) values of 8.5%, 8.5%, and 7.0%, and a total upset distribution of 19 (well within the 15–20 target range).

---

## Verification of Previous Fixes

### Fix #1: `is_upset` for R2+ picks — ✅ FIXED

**Previous Bug:** `is_upset` was always `False` for R2-R6 because `slot.seed_a` and `slot.seed_b` are 0 for later rounds.

**Fix Applied (optimizer.py ~line 610):**
```python
# BUG FIX #1: For R2+ rounds, determine upset using ACTUAL team seeds
team_a_obj = team_map.get(team_a)
team_b_obj = team_map.get(team_b)
winner_obj = team_map.get(winner)
loser_obj = team_map.get(loser)
if winner_obj and loser_obj:
    is_upset = (winner_obj.seed > loser_obj.seed)
```

**Verification — Optimal bracket upset distribution:**

| Round | Picks | Upsets | Examples |
|-------|-------|--------|---------|
| R1    | 32    | 10     | Clemson(9), Texas(10), Missouri(13), VCU(12), Virginia Tech(14), etc. |
| R2    | 16    | 4      | Virginia Tech over SMU, VCU over Nebraska, Auburn over Iowa St., Missouri over Texas Tech |
| R3    | 8     | 3      | Michigan St.(3) over Purdue(2), Arkansas(5) over Michigan(1), Connecticut(3) over Houston(2) |
| R4    | 4     | 2      | Vanderbilt(3) over Arizona(1), Michigan St.(3) over Duke(1) |
| R5    | 2     | 0      | (higher seeds won correctly) |
| R6    | 1     | 0      | (higher seed won correctly) |
| **Total** | **63** | **19** | |

- R1 upsets: 10 (target 8–13) ✅
- R2+ upsets: 9 (target 5–9) ✅
- Total: 19 (target 15–20) ✅
- `bracket.txt` shows `[UPSET]` tags correctly in all rounds ✅
- `analysis.md` round breakdown shows upset counts for R1–R4 ✅

**Verdict:** Fully fixed. Later-round upsets are now correctly detected, tagged, and displayed.

---

### Fix #2: Region mismatch — ✅ FIXED

**Previous Bug:** `merge_team_data()` used `region_names[idx % 4]` to assign regions, conflicting with the S-curve distribution in `generate_bracket_from_kenpom()`.

**Fix Applied (scout.py, `merge_team_data()`):**
```python
# BUG FIX #2: Do NOT assign regions here - let generate_bracket_from_kenpom()
# be the single source of truth. It uses S-curve distribution which is correct.
for idx, team in enumerate(tournament_teams):
    seed_in_region = (idx // 4) + 1
    team.seed = min(seed_in_region, 16)
    team.bracket_position = idx + 1
    # team.region is intentionally NOT set here - will be set by bracket generator
```

**Verification:**
- `generate_bracket_from_kenpom()` correctly applies S-curve distribution (seed 1: E,W,S,MW; seed 2: MW,S,W,E reversal) and sets `team.region` on each team object.
- `merge_team_data()` no longer touches `team.region`, preserving the correct S-curve assignments.
- Scenarios use `team.region` for FF team selection via `select_regional_champion()`, which now correctly maps to the actual bracket regions.
- The seed assignment in `merge_team_data()` (`(idx // 4) + 1`) produces identical values to `generate_bracket_from_kenpom()` (`seed_line + 1`), so seeds remain consistent.

**Verdict:** Fully fixed. Single source of truth for regions established.

---

### Fix #3: Leverage threshold — ✅ FIXED

**Previous Bug:** Pool-aware leverage values ranged 0.01–0.22 but the analysis report filtered at `> 1.5`, producing an always-empty Key Differentiators section.

**Fix Applied (analyst.py):**
```python
# BUG FIX #3: Pool-aware leverage produces values like 0.04-0.10, not 1.5+
# Adjusted threshold from 1.5 to 0.02 to match actual scale
high_leverage_picks = [p for p in bracket.picks if p.leverage_score > 0.02]
```

**Verification (from analysis.md):**

Key Differentiators now shows 12 picks:
1. Virginia Tech to R64 (Leverage: 0.2185, 14-seed)
2. Illinois to F4 (Leverage: 0.1861, 2-seed)
3. Vanderbilt to E8 (Leverage: 0.1781, 3-seed)
4. Michigan St. to E8 (Leverage: 0.1781, 3-seed)
5. South Florida to R64 (Leverage: 0.1676, 13-seed)
6. _(+7 more picks)_

The section is populated with meaningful, diverse picks spanning R1 through FF. The picks make strategic sense — high-seed upsets (Virginia Tech, South Florida) and deep runs by non-chalk teams (Vanderbilt, Michigan St.) are exactly the kind of differentiators a pool player needs to see.

**Verdict:** Fully fixed. Key Differentiators populated and useful.

---

## Bracket Coherence — ✅ VERIFIED

Traced the full optimal bracket path:
- Every R2 winner appeared as an R1 winner (32 R1 → 16 R2, all feed correctly)
- Every S16 winner appeared as an R2 winner
- Every E8 winner appeared as an S16 winner
- Every FF winner appeared as an E8 winner
- Champion won their FF game
- `validate_bracket_coherence()` runs without exceptions for all 6 scenario brackets
- Zero orphaned picks, zero phantom teams

---

## Output Bracket Differentiation — ✅ GOOD

| Bracket | Champion | P(1st) | P(Top 3) | Upsets | Picks diff from Optimal |
|---------|----------|--------|----------|--------|------------------------|
| Optimal | Florida (1) | 8.5% | 20.0% | 19 | — |
| Safe Alternate | Arizona (1) | 8.5% | 15.5% | 20 | 13 |
| Aggressive Alternate | Duke (1) | 7.0% | 22.0% | 15 | 15 |

- 3 different champions ✅
- Meaningful pick differentiation (13–15 picks different) ✅
- All P(1st) > 4.5% ✅
- Distinct strategic profiles: Florida (contrarian upset-heavy), Arizona (different-region contrarian), Duke (chalky but high E[score]) ✅

---

## Remaining Issues (from V2, not addressed in this fix cycle)

### 1. [MEDIUM] R1 upset candidates identical across most scenarios

chalk_0 and chalk_1 have **byte-identical** R1 upsets (same 8 upsets, same EMV values, same order) and identical R2-R5 upsets. They're effectively the same bracket. Two of six scenario slots are wasted on duplicates.

**Root cause:** EMV calculation has no scenario-specific inputs beyond `chaos_level`. The same EMV floor and region caps produce the same top-N ranking. 

**Impact:** Reduces effective scenario count from 6 to ~4. Still produces 3 differentiated output brackets because the output selector picks from different scenario types (contrarian_0, contrarian_1, chalk_1), but the search space is smaller than intended.

### 2. [MEDIUM] Only 3 champion candidates due to 8% threshold

With `CHAMPION_MIN_TITLE_PROB["small"] = 0.08`, only Duke (9.9%), Florida (8.8%), and Arizona (8.1%) qualify. Michigan (7.3%) and Illinois (6.7%) are excluded despite being viable contenders. This limits scenario diversity.

**Suggested fix:** Lower to 0.05 for small pools to include 5+ candidates.

### 3. [MEDIUM] Duplicate title probability estimation

`estimate_title_probabilities()` is called twice with identical parameters — once in `cmd_analyze()` and once in `evaluate_champions()`. Both run 2000 simulations with the same base seed, producing identical results. ~3 seconds of unnecessary computation.

### 4. [LOW] FF/Championship sections empty in analysis.md when no upsets

The round breakdown only renders upset picks. For rounds with no upsets (common in FF/Championship where higher seeds tend to win), the section is blank — the user doesn't see who plays whom. Should show all picks, highlighting upsets.

### 5. [LOW] Ensemble model deserialization overhead

Still deserializes 300 trees per prediction call (2278 calls = 683,400 deserializations). Matchup matrix takes ~68 seconds. Caching would reduce to <5 seconds.

### 6. [LOW] Opponent bracket coherence

Opponent brackets are generated round-by-round with ownership weights, but a team can be picked to advance in R3 without necessarily being picked in R1/R2 (the forward propagation handles this, but the ownership weights for later rounds don't condition on earlier picks being consistent). Minor impact at 200 sims.

### 7. [INFO] 200-sim variance

SE for P(1st)=8.5% is ~2.0%, so 95% CI is [4.6%, 12.4%]. The difference between the top brackets (8.5% vs 7.0%) is within noise. Default 10,000 sims would resolve this. Not a bug — expected behavior for test configuration.

---

## What Works Well

1. **All three critical bugs fixed correctly.** The output now accurately represents the optimizer's work. Users can trust the upset tags, region assignments, and leverage metrics.

2. **Bracket coherence remains perfect.** Zero violations across all 6 scenario brackets and all 3 output brackets.

3. **Upset distribution is realistic and well-calibrated.** 10 R1 + 9 R2-R4 = 19 total upsets. Historically, NCAA tournaments average ~12 R1 upsets and ~7 later-round upsets. The optimizer is in the right ballpark.

4. **Key Differentiators section is now the most valuable part of the report.** Shows concrete, actionable picks with leverage scores, seeds, and ownership percentages. This is exactly what a pool player needs.

5. **Output brackets have genuine strategic differentiation.** Three different champions, 13–15 pick differences, different risk profiles. A user can meaningfully choose between them.

6. **EMV-based upset selection produces sensible picks.** The R1 upsets are concentrated in the historically upset-prone matchups (8/9, 5/12, 4/13, 7/10, 6/11). No absurd picks (no 16-over-1, no 15-over-2).

7. **The later-round upset injection + re-propagation system works correctly.** Adding an R2 upset correctly ripples through R3-R6, updating non-locked slots with the new matchup favorite. This was a hard problem to get right.

8. **Code quality is high.** Clean module separation, comprehensive dataclasses with serialization, good logging, proper error handling, helpful comments explaining the math and the bug fixes.

9. **Test suite passes cleanly.** 9/9 tests, 0.27 seconds.

---

## SCORE: 8/10

**Improvement from V2:** +2 points (6 → 8)

**Why 8:** The three fixes addressed the most impactful issues — the system's output was actively misleading before (hiding 9 upsets, misreporting regions, empty key section), and now it's accurate and useful. The optimization engine, bracket coherence, EMV math, and Monte Carlo evaluation were already solid; the fixes brought the presentation layer up to match. The output is now trustworthy and actionable.

**Why not 9:** Scenario diversity remains limited (chalk_0 ≈ chalk_1, only 3 champion candidates). The performance issues (duplicate sim, tree deserialization) are annoying but not blocking. The analysis report could show all picks per round, not just upsets. These are polish items, not correctness bugs.

**Why not 7:** No remaining correctness bugs that affect output quality. All output files (summary.json, bracket.txt, analysis.md) are consistent, coherent, and well-structured. The system reliably produces viable bracket pool entries.
