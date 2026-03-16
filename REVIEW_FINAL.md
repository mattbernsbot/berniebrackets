# BRACKET OPTIMIZER — FINAL COMPREHENSIVE REVIEW
**Reviewer:** Senior Code Review Agent  
**Date:** 2026-03-16  
**Run Timestamp:** Output files dated 2026-03-16 16:49 UTC  

---

## OVERALL VERDICT: ❌ FAIL

**The bracket is usable but NOT fully correct.** A KenPom scraper column-mapping bug feeds garbage values into ~19% of the model's feature importance. The bracket's core signal (AdjEM differentials) is intact, and extreme-seed matchups are rescued by clamping — but mid-seed predictions (5v12, 6v11, 4v13) have errors of 3–13 percentage points. **Must fix the scraper before full confidence.**

---

## 1. Source Data Verification

### ✅ KenPom data is scraped fresh
- `data/teams.json` timestamp: `2026-03-16 16:47:19 UTC` (today)
- 68 teams present with KenPom stats (AdjEM, AdjO, etc.)
- AdjEM range: -10.69 to +38.9 (realistic)
- AdjO range: 101.2 to 131.6 (realistic)
- **However: see critical adj_d/adj_t bug below in Section 2.**

### ✅ Yahoo picks are REAL (not flat decay)
- `data/yahoo_picks_cache.json` timestamp: `2026-03-16 16:47:19 UTC`
- Source: `yahoo`, URL: `https://tournament.fantasysports.yahoo.com/mens-basketball-bracket/pickdistribution`
- **68 teams, 6 rounds** per team
- R2/R1 ratio analysis:
  - Mean: 0.3882, StdDev: **0.2514** (wide variation = real data)
  - Min: 0.0413, Max: 0.9529
  - Example: Kansas R2/R1 = 0.4652, Duke = 0.9529, Michigan St. = 0.7729
- **NOT flat 0.85 decay** ✅

### ✅ Real bracket from ncaa.com
- `data/real_bracket_2026.json`: source=`ncaa.com`, year=2026
- 4 regions (EAST/WEST/SOUTH/MIDWEST) with play-in games
- 68 total teams across regions
- `data/bracket_structure.json`: 63 slots, 32 R1 matchups, all properly seeded (1v16, 8v9, 5v12, etc.)
- Play-in games: 4 (UMBC/Howard, Texas/NC State, Prairie View A&M/Lehigh, Miami Ohio/SMU)

### ⚠️ ESPN data in codebase but NOT in active pipeline
- ESPN functions exist in `src/scout.py` (scrape_espn_bracket, scrape_espn_picks_playwright, etc.)
- ESPN URLs in `config.json`
- **BUT:** The active pipeline uses `scrape_yahoo_picks()` for pick data, confirmed by:
  - `main.py` lines 103-134: calls `scrape_yahoo_picks()`, saves to `public_picks.json`
  - `yahoo_picks_cache.json` is the source, not ESPN
  - Config has `strict_yahoo` mode enforced
- **Yahoo is the SOLE pick source in the active run** ✅
- ESPN code is dead weight but not harmful

---

## 2. Model Verification

### ✅ 16-feature model (no Barttorvik)
- `sklearn_model.joblib` contains: scaler (16 features), LogisticRegression (16 features), RandomForest, GradientBoosting
- LR coefficient shape: (1, 16)
- **Feature names confirmed:** seed_diff, round_num, adj_em_diff, adj_o_diff, adj_d_diff, adj_t_diff, seed_x_adj_em, round_x_seed, round_x_adj_em, luck_diff, favorite_luck, tempo_mismatch, slow_dog_vs_fast_fav, top25_winpct_diff, dog_top25_winpct, luck_x_seed_diff
- **No efg/to/or/ft/barttorvik features** ✅

### ✅ AUC verified at ~0.6976
- Retrained from scratch: **Logistic AUC = 0.6976** ✅ (matches exactly)
- Ensemble AUC = 0.6857
- Baseline (seed-only): 0.6646
- Training: 738 games, 216 upsets (29.3%), 13 years (2011-2025, excluding 2012/2020)
- Bug fixes confirmed: D2 game removed, AdjEM scale fixed for 2011/2013-2016

### ✅ predict.py has NO Barttorvik params
- `predict()` signature: `team_a, team_b, round_num, team_a_lrmc, team_b_lrmc`
- `predict_from_teams()` signature: `favorite, underdog, round_num`
- **No team_a_bt or team_b_bt anywhere** ✅

### ✅ Model is ACTUALLY USED (not seed fallback)
- `sharp.py` loads `UpsetPredictor` via `get_predictor()` 
- `compute_matchup_probability()` confirmed using `ensemble_model` modifier (verified live)
- Test prediction: 5v12 → **P(upset) = 0.189** (seed-only baseline ~0.33) — model clearly differs ✅
- 1v16 → P(upset) = 0.045 (reasonable) ✅
- 2v15 → P(upset) = 0.047 (reasonable) ✅
- Matchup probabilities in `matchup_probabilities.json` all differ from historical seed rates ✅

---

## 3. Output Verification

### ✅ Output files from THIS run (2026-03-16)
- `output/summary.json`: 2026-03-16 16:49:42 UTC
- `output/bracket.txt`: 2026-03-16 16:49 UTC
- `output/analysis.md`: 2026-03-16 16:49 UTC
- All data files also from today

### ✅ Bracket is coherent
- 32 R1 winners → 16 R2 winners → 8 S16 winners → 4 E8 winners → 2 FF winners → 1 champion
- Every R2+ winner was a winner in all prior rounds ✅
- Champion (Florida) is in Final Four ✅
- Final Four (Florida, Michigan St., Iowa St., Purdue) all in Elite Eight ✅

### ✅ No 16-over-1 upsets, no absurd picks
- R1 upsets (10): UCF(10), Utah St.(9), High Point(12), NC State(11), Iowa(9), Troy(13), VCU(11), Saint Louis(9), SMU(11), Santa Clara(10)
- No 15-seed or 16-seed upsets in the bracket
- Iowa St. correctly beats Tennessee St. (15-seed) ✅
- All upsets are in 9-13 seed range — reasonable

### ⚠️ Only 3 scenarios (not 6)
- Optimal: Florida champion (EMV 685, P1st 12.2%)
- Safe alternate: Michigan champion (EMV 732, P1st 10.8%)
- Aggressive alternate: Arizona champion (EMV 710, P1st 10.0%)
- Task mentioned "6 scenarios" but pipeline produces 3. This may be by design.

### ✅ Scenarios are genuinely diverse
- Optimal vs Safe: **16 picks differ** (different champion, different FF)
- Optimal vs Aggressive: **9 picks differ**
- Safe vs Aggressive: **15 picks differ**
- Different champions, different Final Fours, different upset profiles ✅

---

## 4. Pipeline Integrity

### ✅ Yahoo picks feed directly into contrarian scoring
- Verified data flow: `yahoo_picks_cache.json` → `public_picks.json` → `ownership.json`
- **All values match exactly** across all 3 files for 6 sampled teams across all 6 rounds
- Example: Duke R3 ownership = 0.787747 in Yahoo, public_picks, AND ownership.json ✅

### ✅ Ownership uses REAL Yahoo R2-R6 data (not flat decay)
- `contrarian.py:build_ownership_profiles()` uses Yahoo data directly when available:
  ```python
  if public_picks and team.name in public_picks:
      round_ownership = public_picks[team.name]
  ```
- Seed-based estimation is only fallback when Yahoo data is missing
- Verified: ownership values for all rounds match Yahoo's per-team percentages ✅

### ✅ Monte Carlo uses ensemble model
- `sharp.py:compute_matchup_probability()` calls `predictor.predict_from_teams()`
- Confirmed `modifiers_applied = ["ensemble_model"]` in live test
- `optimizer.py:simulate_tournament()` uses the pre-computed `matchup_matrix` which was built with the ensemble model
- Seed-based fallback only triggers if model load fails

---

## 5. Specific Concerns from Previous Reviews

### ✅ 15-seed calibration — Tennessee St. does NOT upset Iowa St.
- In the bracket output, Iowa St. wins R1 with "🔒 Lock" confidence
- P(Tennessee St. upset) = 15% in stored matrix (clamped to floor)
- Raw model gives 15.3% (with buggy features) or 5.0% (with correct features)
- **The clamp at seed_gap ≥ 12 prevents the model from making wild 15-seed picks** ✅
- Tennessee St. does NOT appear as a winner anywhere in any scenario ✅

### ✅ Scenario diversity confirmed
- 3 scenarios with different champions (Florida, Michigan, Arizona)
- 3 different Final Fours
- 9-16 pick differences between scenarios
- R1 upset profiles differ (8-10 upsets per scenario, partially overlapping)

---

## 🚨 CRITICAL BUG: KenPom Scraper Column Mapping

### The Bug
The KenPom HTML table has **rank columns interspersed** between value columns. The scraper reads consecutive cells but the table structure is:

| Cell | Scraper maps to | Actually contains |
|------|----------------|-------------------|
| [4]  | adj_em         | AdjEM ✅           |
| [5]  | adj_o          | AdjO ✅            |
| [6]  | **adj_d**      | **AdjO RANK** ❌   |
| [7]  | **adj_t**      | **AdjD value** ❌  |
| [9]  | **sos**        | **AdjT value** ❌  |

**Evidence:**
- `adj_d` values range 1–310 (clearly ranks, not pts/100 poss)
- Sorting teams by `adj_o` gives ascending `adj_d` values (Purdue: adj_o=131.6, adj_d=1.0)
- `adj_t` values = AdjO − AdjEM for every team (confirmed exact match for 15 teams)
- `sos` values range 62–73 (exactly the expected range for real KenPom AdjT/tempo)
- Historical training data has correct values: adj_d ∈ [81, 125], adj_t ∈ [57.6, 82.3]

### Impact
- **4 of 16 model features receive wrong values:** adj_d_diff, adj_t_diff, tempo_mismatch, slow_dog_vs_fast_fav
- These account for **19.1% of Random Forest feature importance**
- **Luck is not scraped** (defaults to 0.0) — affects 3 more features (18.6% importance)
- Combined: **~37.7%** of feature importance is degraded or zeroed

### Impact on Actual Bracket Picks
R1 predictions have errors of **3–13 percentage points** vs correct features:
- Most upset picks (8/10) are actually **more justified** with correct features (error is conservative)
- Two picks become less justified:
  - **High Point(12) over Wisconsin(5):** 25.8% → 14.5% (still viable for contrarian, but riskier)
  - **Troy(13) over Nebraska(4):** 18.4% → 8.7% (marginal pick becomes very aggressive)
- Later-round propagation likely amplifies these errors

### Mitigation
- The **extreme_seed_clamp** (seed_gap ≥ 12) correctly bounds 1v16, 2v15, 2v14, 1v13 matchups
- AdjEM differentials (the #1-#2 most important features) are **correct**
- The bracket is **directionally reasonable** but not optimally calibrated

---

## What MUST Be Fixed Before Using This Bracket

### 🔴 Fix NOW (blocks deployment):
1. **Fix `scrape_kenpom()` column mapping** in `src/scout.py`:
   - Cell [6] is AdjO rank → skip it
   - Cell [7] is AdjD value → map to `adj_d`
   - Cell [8] is AdjD rank → skip it  
   - Cell [9] is AdjT value → map to `adj_t`
   - Cell [10+] contains Luck → map to `luck`
   
   Quick fix: change lines 134-136 in scout.py:
   ```python
   adj_o = parse_float(5)
   adj_d = parse_float(7)   # was parse_float(6) — that's AdjO rank!
   adj_t = parse_float(9)   # was parse_float(7) — that's AdjD value!
   luck = parse_float(10)   # NEW: was not scraped
   ```

2. **Re-run the full pipeline** after the fix to get correct predictions

### 🟡 Non-blocking warnings:
- Only 3 scenarios generated (task mentioned 6 — may be by design)
- ESPN code remains in codebase (dead code, not harmful but should be cleaned up)
- `tournament_appearances` field is always 0 (not used by model, cosmetic only)

---

## Summary

| Category | Status | Notes |
|----------|--------|-------|
| KenPom data freshness | ✅ PASS | Scraped today, 68 teams |
| Yahoo picks real | ✅ PASS | Real per-team data, not flat decay |
| Bracket structure | ✅ PASS | 68 teams, 4 regions, correct seeds |
| No ESPN in pipeline | ✅ PASS | Yahoo is sole source |
| 16-feature model | ✅ PASS | No Barttorvik features |
| AUC ~0.6976 | ✅ PASS | Exact match on retrain |
| No Barttorvik params | ✅ PASS | Clean API |
| Model actually used | ✅ PASS | Ensemble model, not fallback |
| Output from today | ✅ PASS | 2026-03-16 16:49 UTC |
| Bracket coherent | ✅ PASS | All teams advance properly |
| No absurd upsets | ✅ PASS | No 15/16-seed upsets |
| 15-seed calibration | ✅ PASS | Tennessee St. doesn't upset Iowa St. |
| Scenario diversity | ✅ PASS | 3 genuinely different brackets |
| Yahoo → ownership flow | ✅ PASS | Data flows correctly |
| Monte Carlo uses model | ✅ PASS | Ensemble model confirmed |
| **KenPom column mapping** | **❌ FAIL** | **adj_d = AdjO rank, adj_t = AdjD, sos = AdjT, luck missing** |

**Bottom line:** The pipeline architecture is solid. The model is correctly trained and deployed. The data flow from Yahoo through ownership to EMV calculations is correct. But the KenPom scraper has a column-shift bug that feeds wrong values into 19% of feature importance, producing prediction errors of 3–13% on mid-seed matchups. Fix the scraper and re-run.
