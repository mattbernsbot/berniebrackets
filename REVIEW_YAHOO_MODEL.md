# Code Review: Yahoo Picks Integration + 16-Feature Model Revert

**Reviewer:** AI Senior Code Reviewer  
**Date:** 2026-03-16  
**Scope:** Yahoo pick distribution integration (Change 1), 16-feature model revert (Change 2), end-to-end pipeline (Change 3)

---

## VERDICT: ⚠️ CONDITIONAL PASS — One Critical Bug

The Yahoo integration and 16-feature model revert are both **individually correct**, but there is a **call-site mismatch** in `predict.py` that causes the ensemble model to **never be used** during the full pipeline. The pipeline completes successfully only because it silently falls back to seed-based predictions for every matchup.

---

## Change 1: Yahoo Picks Integration — ✅ PASS

### What was verified:
1. **Yahoo scraper returns real data for all 6 rounds:**
   - 68 teams scraped from Yahoo Bracket Mayhem
   - All 6 rounds (R1–R6) present for all teams
   - Sample: Duke R1=98.2%, R2=93.6%, R6=30.2%; Kansas R1=94.2%, R2=43.8%, R6=1.6%

2. **ESPN removed from active pipeline:**
   - `main.py` has zero references to `scrape_espn_picks` or ESPN pick functions
   - `collect_all()` in `scout.py` calls only `scrape_yahoo_picks()` for ownership data
   - ESPN functions (`scrape_espn_picks_playwright`, `scrape_espn_picks`, `build_espn_name_mapping`) remain as dead code in scout.py but are never called from the active pipeline
   - Only ESPN reference in main.py is the `--espn-bracket-file` CLI arg and help text string "Scrape data from KenPom and ESPN" (cosmetic)

3. **R2-R6 data is REAL (not decay estimates):**
   - R2/R1 ratio range: **0.041 to 0.953** (std dev: 0.290)
   - If using a flat decay of 0.85, all ratios would cluster near 0.85 — they don't
   - Examples of wild variation:
     - TCU: R2/R1 = 0.041 (9-seed, most pickers dropping after R1)
     - Duke: R2/R1 = 0.953 (1-seed, strong carry-through)
     - Kansas: R2/R1 = 0.465 (4-seed in a tough bracket region)
   - **Confirmed: real per-round Yahoo data, not synthetic decay**

4. **Collect step runs cleanly:**
   - `python3 main.py collect --year 2026 --no-strict-yahoo` → 68 teams, 0 unmatched, Yahoo picks saved

### Minor notes:
- Dead ESPN code (500+ lines) should be cleaned up eventually, but doesn't affect correctness
- Cache works properly (4h TTL, int-key restoration from JSON)

---

## Change 2: 16-Feature Model Revert — ✅ PASS

### What was verified:
1. **Saved model has exactly 16 features:**
   ```
   Features: 16
   ['seed_diff', 'round_num', 'adj_em_diff', 'adj_o_diff', 'adj_d_diff', 'adj_t_diff',
    'seed_x_adj_em', 'round_x_seed', 'round_x_adj_em', 'luck_diff', 'favorite_luck',
    'tempo_mismatch', 'slow_dog_vs_fast_fav', 'top25_winpct_diff', 'dog_top25_winpct',
    'luck_x_seed_diff']
   ```
   - No Barttorvik features (`efg_off_diff`, `efg_def_diff`, `tov_pct_diff`, `oreb_pct_diff`) present ✓
   - Assert `len(features) == 16` passes ✓
   - Assert `'efg_off_diff' not in features` passes ✓

2. **Training produces expected AUC:**
   - LR AUC = **0.6976** (matches expected)
   - RF AUC = 0.6770, GB AUC = 0.6666, Ensemble AUC = 0.6857
   - Improvement over seed-only baseline: +0.0210 (+3.2%)
   - Training samples: 738, match rate: 92.5%

3. **features.py has no Barttorvik references in active code:**
   - Zero mentions of `barttorvik`, `bart_torvik`, `efg_off`, `efg_def`, `tov_pct`, or `oreb_pct`
   - Function signature: `extract_features(team_a, team_b, round_num, team_a_lrmc=None, team_b_lrmc=None)` — 5 params
   - `FEATURE_NAMES` list has exactly 16 entries matching the model

---

## Change 3: End-to-End Pipeline — ⚠️ FAIL (Bug)

### Critical Bug: `predict.py` call-site mismatch

**File:** `upset_model/predict.py`, line 74  
**Error:** `extract_features() takes from 3 to 5 positional arguments but 7 were given`

**Root cause:** When Barttorvik was removed from `features.py`, the call site in `predict.py` was **not updated**. The `predict()` method still passes 7 args:
```python
# predict.py:74 — BROKEN
x = extract_features(team_a, team_b, round_num, team_a_bt, team_b_bt, team_a_lrmc, team_b_lrmc)
```

But `features.py` now only accepts 5:
```python
# features.py — CORRECT
def extract_features(team_a, team_b, round_num, team_a_lrmc=None, team_b_lrmc=None):
```

**Impact:** The ensemble model (LR + RF + GB) is **never used** for any matchup prediction during the pipeline. Every call to `UpsetPredictor.predict()` throws `TypeError`, gets caught by the caller's `try/except`, and falls back to **seed-based probability** (the KenPom/historical seed baseline). The pipeline completes without error, but:
- The 16-feature model with AUC 0.6976 is completely bypassed
- All 2,278+ matchup probabilities use the fallback
- The optimization is working, but with degraded predictions

**Additionally:** `predict_from_teams()` (lines 91-164) still constructs Barttorvik dicts (`fav_bt`, `dog_bt`) and passes them to `predict()`, which passes them to `extract_features()`. This entire Barttorvik extraction path is dead code that triggers the error.

### Fix required:
```python
# predict.py line 74 — should be:
x = extract_features(team_a, team_b, round_num, team_a_lrmc, team_b_lrmc)

# predict.py predict() signature — remove team_a_bt, team_b_bt params
# predict.py predict_from_teams() — remove Barttorvik dict construction
```

### Pipeline output (despite bug):
- Pipeline completes with exit code 0 ✓
- Yahoo picks used for ownership (not ESPN) ✓
- 3 optimized brackets generated ✓
- Champion candidates: Michigan (9.8%), Arizona (9.4%), Duke (8.8%)
- Optimal bracket P(1st) = 8.0% — reasonable for pool-25
- Output files generated in `output/` ✓

---

## Summary

| Component | Status | Notes |
|-----------|--------|-------|
| Yahoo scraper | ✅ PASS | Real data, all 6 rounds, 68 teams |
| ESPN removed from pipeline | ✅ PASS | Dead code remains but never called |
| R2-R6 data authenticity | ✅ PASS | Ratios vary 0.04–0.95 (confirmed real) |
| Collect step | ✅ PASS | Clean run, 0 unmatched teams |
| 16-feature model | ✅ PASS | Correct features, AUC = 0.6976 |
| features.py clean | ✅ PASS | No Barttorvik references |
| **predict.py call site** | **❌ FAIL** | **7 args passed to 5-param function** |
| Pipeline completion | ⚠️ WARN | Completes but uses seed-based fallback |

### Action Required
1. **[BLOCKER]** Fix `predict.py` to remove Barttorvik params from `extract_features()` call and from `predict()` / `predict_from_teams()` signatures
2. **[Nice-to-have]** Clean up dead ESPN code in `scout.py` (~500 lines)
3. **[Nice-to-have]** Update CLI help text "Scrape data from KenPom and ESPN" → "...and Yahoo"
