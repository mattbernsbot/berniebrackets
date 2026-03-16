# Model Data Quality Review V3 — Post-V2 Fix Verification

**Reviewer:** Senior Code Reviewer (subagent)  
**Date:** 2026-03-16  
**Scope:** Verify all V2 review issues are fixed; check for regressions and new issues  
**Previous verdict:** FAIL (Barttorvik data garbage, remaining alias issues, D2 contamination)

---

## VERDICT: ❌ FAIL

Two of four V2 issues are fixed. Two critical alias bugs remain unfixed (NC State, Charleston), causing **10 games to be lost** from training — including NC State's entire 2024 Final Four run (5 games, 3 upsets). The original bugs 2–3 remain fixed. The model is improved but cannot pass with known alias bugs dropping high-value upset data.

---

## Previous V2 Issues

### Issue 1: Barttorvik features — ✅ FIXED

**Status:** All 5 Barttorvik features (`efg_diff`, `to_diff`, `or_diff`, `ft_rate_diff`, `efg_x_round`) have been **completely removed** from the model.

**Evidence:**
- `features.py`: `FEATURE_NAMES` contains exactly 16 features — none are Barttorvik-derived
- `extract_features()` returns 16 values, ignoring `team_a_bt`/`team_b_bt` parameters (marked DEPRECATED)
- `train_sklearn.py` header documents "barttorvik_historical.json — NOT USED (data quality issues in 75% of years)"
- Feature importance output shows only the 16 KenPom/LRMC/interaction features
- Model saved with `feature_names: [16 features]` and `training_n: 728`

**Note:** Barttorvik data is still being **joined** in `join_team_stats()` and columns appear in the DataFrame. The bt dicts are still built and passed to `extract_features()`. This is dead code — not harmful, but wasteful. Minor cleanup opportunity.

---

### Issue 2: Remaining alias mismatches — ❌ NOT FIXED (2 of 5 fixed, 2 still broken, 1 new bug)

**Match rate:** 728/798 = 91.2% (was 91.9% per V2 review, but denominator changed from 802→798 after D2 removal and dedup)

**What was fixed:**
- ✅ `Little Rock` → `Arkansas Little Rock` — works
- ✅ `Louisiana` → `Louisiana Lafayette` — works  
- ✅ `NC Asheville` → `UNC Asheville` — works

**What is STILL BROKEN:**

#### NC State — Transitive alias chain (single-pass bug)

The alias dict has:
```python
'NC State': 'N.C. State',        # line ~34
'N.C. State': 'North Carolina St.',  # line ~79
```

The function iterates the dict and **returns on first match**. So:
- `normalize('NC State')` → matches `'NC State'` → returns `'N.C. State'` (stops)
- `normalize('N.C. State')` → matches `'N.C. State'` → returns `'North Carolina St.'`
- KenPom uses `'North Carolina St.'`

The tournament name `NC State` resolves to `N.C. State`, but KenPom's `North Carolina St.` stays as `North Carolina St.`. **They don't match.**

**Fix needed:** Change `'NC State': 'N.C. State'` to `'NC State': 'North Carolina St.'` (skip the intermediate step).

**Games lost:** 7 lookups → **6 games** (NC State appears in 2018 R1, 2023 R1, 2024 R1/R2/R3/R4/R5). Note: 2024 R2 Oakland vs NC State is lost because NC State is team_b.

#### Charleston — Circular alias

The alias dict has:
```python
'Col. of Charleston': 'Charleston',      # line ~63
'Charleston': 'Col. of Charleston',      # line ~80 (V2 fix)
```

These form a **cycle**:
- Tournament `Col. of Charleston` → resolves to `Charleston`
- KenPom `Charleston` (2019+) → resolves to `Col. of Charleston`
- KenPom `College of Charleston` (pre-2019) → resolves to `Col. of Charleston`

Tournament resolves to `Charleston`, KenPom resolves to `Col. of Charleston`. **They never converge.**

**Fix needed:** Remove `'Col. of Charleston': 'Charleston'` (line ~63) so all paths converge on `Col. of Charleston`. Or change it to `'Col. of Charleston': 'Col. of Charleston'` (no-op) but better to just remove.

**Games lost:** 3 lookups → **3 games** (2018 R1, 2023 R1, 2024 R1)

#### Impact Summary

| Team | Games Lost | Upsets Lost | Details |
|------|-----------|-------------|---------|
| NC State | 6 | 3 | Entire 2024 Final Four run (R1–R5), plus 2018 R1, 2023 R1 |
| Charleston | 3 | 0 | 2018 R1, 2023 R1, 2024 R1 (CoC lost all 3) |
| **Total** | **10** | **3** | **1.4% of unequal-seed games** |

**Severity: HIGH** — NC State's 2024 tournament run as an 11-seed beating Texas Tech, Marquette, and Duke is exactly the kind of high-signal upset data the model needs. Losing 3 upsets (especially deep tournament runs by mid-seeds) materially affects training.

---

### Issue 3: D2 game removed — ✅ FIXED

**Evidence:**
- `load_data()` filters out Grand Canyon vs Seattle Pacific 2013 at load time
- Runtime output: `BUG FIX V2: Removed 1 D2 game(s) (Grand Canyon vs Seattle Pacific 2013)`
- After filtering: 798 games (was 799 in raw JSON)

**Note:** The D2 game is still in `ncaa_tournament_real.json` (799 records). It's removed at load time, not from the source file. This works but is fragile — a different script loading the same JSON would get the contaminated data. Ideally the source file should be cleaned.

---

### Issue 4: Duplicates removed — ✅ FIXED

**Evidence:**
- `load_data()` deduplicates Barttorvik records before joining
- Runtime output: `BUG FIX V2: Removed 42 duplicate Barttorvik records`
- Post-join row count: 798 (no inflation, was 802 in V1)
- Total games after join matches total before join: `798 == 798`

---

## Original Bugs (from REVIEW_MODEL_DATA.md)

### Bug 1: Team name mismatches — ⚠️ SUBSTANTIALLY FIXED (same as V2)

Match rate is 91.2%. The 5 alias fixes from V2 added Little Rock, Louisiana, and NC Asheville correctly. But NC State and Charleston fixes introduced new bugs (transitive chain, circular alias). Net result: same 10 games lost, different root cause.

### Bug 2: AdjEM wrong scale for 2011, 2013–2016 — ✅ STILL FIXED

- Runtime: `BUG FIX 2: Fixed AdjEM scale for 1745 records in years: [2011, 2013, 2014, 2015, 2016]`
- AdjEM ranges verified correct for all years:
  - 2011: -36.00 to 36.00 ✅
  - 2013: -51.00 to 36.10 ✅ (Grambling at -51 = adj_o 73.4, adj_d 124.4 — real, just terrible)
  - 2014: -24.10 to 26.80 ✅
  - 2015: -34.40 to 33.90 ✅
  - 2016: -24.10 to 26.90 ✅
  - 2017–2025: all correct (unchanged)

### Bug 3: USC circular alias — ✅ STILL FIXED

- `normalize('USC')` → `'USC'` (passthrough, no alias match)
- `normalize('Southern California')` → `'USC'`
- Both converge. No regression.

---

## Spot Checks

| Check | Expected | Found | Status |
|-------|----------|-------|--------|
| Oakland 2024 AdjEM | ~+2.81 | 2.81 (AdjO=108.9, AdjD=106.1) | ✅ |
| UMBC 2018 in training data | Present | AdjEM=-2.3, found in tournament | ✅ |
| LOO-CV AUC (honest, not in-sample) | Leave-One-Year-Out | 13 folds, correct methodology | ✅ |
| Model file loadable | Yes | sklearn_model.joblib loads, 728 samples, 16 features | ✅ |

---

## Model Performance

| Metric | V1 (21 features) | V2 (16 features) | Change |
|--------|------------------|-------------------|--------|
| Seed baseline AUC | 0.6642 | 0.6672 | +0.0030 |
| Logistic AUC | 0.6901 | 0.6991 | +0.0090 |
| Random Forest AUC | — | 0.6810 | — |
| Gradient Boost AUC | — | 0.6881 | — |
| Ensemble AUC | 0.6819 | 0.6974 | **+0.0155** |
| Lift over baseline | +2.6% | +4.5% | **+1.9pp** |
| Training samples | 737 | 728 | -9 |

**The Barttorvik removal is a clear win.** Ensemble AUC improved by +0.0155 (from 0.6819 to 0.6974) and lift over seed baseline nearly doubled from 2.6% to 4.5%. This confirms the garbled Barttorvik features were actively hurting the model by adding noise.

The Logistic Regression model (AUC 0.6991) outperforms the ensemble (0.6974), which is common in small-data regimes — simpler models generalize better.

---

## New Issues

### 🟡 New Issue 1: Dead Barttorvik Code

Barttorvik data is still loaded, deduplicated, joined, and passed around in `load_data()`, `join_team_stats()`, and `build_feature_matrix()` — even though no features use it. This adds ~20 unnecessary columns to the DataFrame and passes unused `bt` dicts through the pipeline.

**Severity:** Low (no correctness impact). Cleanup opportunity.

### 🟡 New Issue 2: LRMC Missing for 2018 (unchanged from V2)

LRMC has 0 records for 2018. All LRMC features for 2018 tournament teams (65 games) are imputed to defaults (0). This is ~9% of training data with no LRMC signal. Documented but not actionable without sourcing the data.

### 🟡 New Issue 3: 2013 Play-in Round Coding (unchanged from V2)

2013 play-in games are coded as `round_num=1` instead of `round_num=0`. All other years use 0. **No impact** — these are equal-seed games, skipped regardless.

### 🟡 New Issue 4: D2 Game in Source File

The Grand Canyon vs Seattle Pacific 2013 game is still in `ncaa_tournament_real.json`. It's filtered at load time, which works, but any script loading the raw JSON without the filter gets contaminated data.

---

## Summary

| Issue | Status | Confidence |
|-------|--------|------------|
| V2 Issue 1: Barttorvik features | ✅ FIXED — removed from features, not in training | High |
| V2 Issue 2: Alias mismatches (NC State, Charleston) | ❌ NOT FIXED — transitive chain + circular alias | High |
| V2 Issue 3: D2 game | ✅ FIXED — filtered at load time | High |
| V2 Issue 4: Duplicates | ✅ FIXED — deduplicated before join | High |
| Original Bug 1: Team name mismatches | ⚠️ Same — 91.2% match rate, 10 games lost | High |
| Original Bug 2: AdjEM scale | ✅ Still fixed | High |
| Original Bug 3: USC circular alias | ✅ Still fixed | High |
| New issues | Low severity (dead code, LRMC gap, source file cleanup) | — |

---

## Required Fixes for PASS

1. **NC State alias:** Change `'NC State': 'N.C. State'` → `'NC State': 'North Carolina St.'` in the aliases dict. This will recover 6 games including NC State's 2024 Final Four run.

2. **Charleston alias:** Remove `'Col. of Charleston': 'Charleston'` (the original alias at line ~63). Keep `'Charleston': 'Col. of Charleston'` and `'College of Charleston': 'Col. of Charleston'`. All paths will then converge on `Col. of Charleston`. This will recover 3 games.

Both fixes are one-line changes. After applying them, match rate should rise to ~738/798 (92.5%) and the model will have 10 more training samples including 3 valuable upsets.

**VERDICT: FAIL** — Two alias bugs are preventing 10 games (including 3 upsets and an entire Final Four run) from entering training. Fixes are trivial (two one-line edits) but must be applied and verified before production.
