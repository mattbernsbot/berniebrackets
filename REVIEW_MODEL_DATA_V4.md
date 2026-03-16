# Model Data Quality Review V4 — Post-V3 Fix Verification

**Reviewer:** Senior Code Reviewer (subagent)  
**Date:** 2026-03-16  
**Scope:** Verify V3 alias fixes (NC State, Charleston); full checklist verification  
**Previous verdict:** FAIL (NC State transitive alias chain, Charleston circular alias)

---

## VERDICT: ✅ PASS

All critical issues from V1–V3 are resolved. Both alias bugs are fixed correctly, recovering 10 games (including NC State's entire 2024 Final Four run). The model trains cleanly with 738 samples, 16 features, and honestly-reported LOO-CV AUC of 0.6976 (Logistic). Minor cosmetic issues remain but do not block production use.

---

## V3 Issue Verification

### Issue 1: NC State Transitive Alias Chain — ✅ FIXED

**V3 bug:** `'NC State' → 'N.C. State'` then `'N.C. State' → 'North Carolina St.'` — single-pass normalization stopped at the first match, so tournament `NC State` resolved to `N.C. State` while KenPom 2018's `North Carolina St.` never matched.

**V3 fix applied:**
```python
'NC State': 'N.C. State',                # Tournament name → canonical
'North Carolina St.': 'N.C. State',      # Old KenPom name → canonical
```

**Verification:**
- `normalize("NC State")` → `"N.C. State"` ✓
- `normalize("North Carolina St.")` → `"N.C. State"` ✓ (KenPom 2011–2019)
- `normalize("N.C. State")` → `"N.C. State"` (passthrough, KenPom 2021+) ✓
- All three names converge to `"N.C. State"` ✓

**Games recovered (7):**

| Year | Round | Game | Upset? |
|------|-------|------|--------|
| 2018 | R1 | NC State (9) vs Seton Hall (8) | No |
| 2023 | R1 | NC State (11) vs Creighton (6) | No |
| 2024 | R1 | NC State (11) vs Texas Tech (6) | ✓ Upset |
| 2024 | R2 | Oakland (14) vs NC State (11) | No (Oakland lost) |
| 2024 | R3 | NC State (11) vs Marquette (2) | ✓ Upset |
| 2024 | R4 | NC State (11) vs Duke (4) | ✓ Upset |
| 2024 | R5 | NC State (11) vs Purdue (1) | No (NC State lost) |

NC State's 2024 Final Four run — 5 tournament games, 3 upsets — is now fully in training data. ✓

---

### Issue 2: Charleston Circular Alias — ✅ FIXED

**V3 bug:** `'Col. of Charleston' → 'Charleston'` AND `'Charleston' → 'Col. of Charleston'` formed a cycle.

**V3 fix applied:**
```python
'Col. of Charleston': 'Charleston',       # Tournament name → canonical
'College of Charleston': 'Charleston',    # Old KenPom name → canonical
```

The old `'College of Charleston': 'Col. of Charleston'` (line ~149) is overridden by the later `'College of Charleston': 'Charleston'` (Python dict duplicate key: last value wins). The circular `'Charleston' → 'Col. of Charleston'` alias was removed.

**Verification:**
- `normalize("Col. of Charleston")` → `"Charleston"` ✓ (tournament name)
- `normalize("College of Charleston")` → `"Charleston"` ✓ (old KenPom)
- `normalize("Charleston")` → `"Charleston"` (passthrough, new KenPom 2019+) ✓
- No circular reference — all paths converge to `"Charleston"` ✓

**Games recovered (3):**

| Year | Round | Game | Upset? |
|------|-------|------|--------|
| 2018 | R1 | Col. of Charleston (13) vs Auburn (4) | No |
| 2023 | R1 | Col. of Charleston (12) vs San Diego St. (5) | No |
| 2024 | R1 | Col. of Charleston (13) vs Alabama (4) | No |

---

## Full Checklist

### 1. NC State alias — ✅ PASS
NC State 2024: All 5 games (R1–R5, including Final Four) are in training data. Plus 2018 R1 and 2023 R1. Total 7 games recovered.

### 2. Charleston alias — ✅ PASS
No circular reference. All 3 games recovered (2018, 2023, 2024 R1).

### 3. Match rate ≥ 92% — ✅ PASS
- Reported: 738/798 (92.5%)
- Breakdown: 798 total games → 60 equal-seed play-in games (skipped by design) + 738 unequal-seed games
- KenPom match for trainable games: **738/738 (100%)** — zero missing KenPom lookups
- The "92.5%" is `trainable / total`, not a data-loss metric. Every trainable game has KenPom data.

### 4. AdjEM scale fixed for 2011, 2013–2016 — ✅ PASS
Runtime output: `BUG FIX 2: Fixed AdjEM scale for 1745 records in years: [2011, 2013, 2014, 2015, 2016]`

AdjEM ranges verified:
| Year | Min | Max | Status |
|------|-----|-----|--------|
| 2011 | -36.00 | 36.00 | ✅ |
| 2013 | -51.00 | 36.10 | ✅ (Grambling is real) |
| 2014 | -24.10 | 26.80 | ✅ |
| 2015 | -34.40 | 33.90 | ✅ |
| 2016 | -24.10 | 26.90 | ✅ |
| 2017–2025 | normal | normal | ✅ (unchanged) |

### 5. Barttorvik features dropped — ✅ PASS
- `FEATURE_NAMES`: 16 features, zero Barttorvik-derived
- `extract_features()` ignores bt parameters (marked DEPRECATED)
- No `efg_diff`, `to_diff`, `or_diff`, `ft_rate_diff`, `efg_x_round` in model

### 6. D2 games removed — ✅ PASS
Runtime: `BUG FIX V2: Removed 1 D2 game(s) (Grand Canyon vs Seattle Pacific 2013)`

### 7. USC alias — ✅ PASS
- `'Southern California' → 'USC'` (one-way)
- No circular `'USC' → 'Southern California'`
- Verified in code: BUG FIX 3 comment documents the removal

### 8. LOO-CV AUC honestly reported, > 0.65 — ✅ PASS
- Method: `LeaveOneGroupOut` with years as groups (13 folds)
- Implementation verified: test predictions collected out-of-fold, AUC computed on aggregated predictions
- **Not in-sample** — each year's games are predicted by a model that never saw that year

| Model | LOO-CV AUC | > 0.65? |
|-------|-----------|---------|
| Seed-only baseline | 0.6646 | ✓ |
| Logistic Regression | **0.6976** | ✓ |
| Random Forest | 0.6770 | ✓ |
| Gradient Boosting | 0.6666 | ✓ |
| Ensemble | 0.6857 | ✓ |

Best model: Logistic Regression (AUC 0.6976), lift over seed baseline: **+0.0330 (+5.0%)**

### 9. Spot checks — ✅ PASS
- **Oakland 2024:** AdjEM = 2.81, AdjO = 108.9, AdjD = 106.1 ✓ (expected ~+2.81)
- **UMBC 2018:** Found in tournament data, 2 games ✓

### 10. Remaining unmatched teams — ✅ NONE
With the full alias dictionary (50+ aliases), **all 738 unequal-seed games match both teams to KenPom data**. Zero unmatched trainable games.

The 60 "unmatched" games in the 798 total are all equal-seed play-in games, which are correctly skipped (they have no favorite/underdog to predict).

---

## Performance Comparison (V1 → V2 → V3)

| Metric | V1 (21 feat, 737 samp) | V2 (16 feat, 728 samp) | V3 (16 feat, 738 samp) |
|--------|------------------------|------------------------|------------------------|
| Seed baseline | 0.6642 | 0.6672 | 0.6646 |
| Logistic | 0.6901 | 0.6991 | **0.6976** |
| Random Forest | — | 0.6810 | 0.6770 |
| Gradient Boosting | — | 0.6881 | 0.6666 |
| Ensemble | 0.6819 | 0.6974 | 0.6857 |
| Best lift | +2.6% | +4.5% | **+5.0%** |
| Training samples | 737 | 728 | **738** |

**Note on V2→V3 AUC changes:** Ensemble AUC dropped from 0.6974 to 0.6857 (-0.0117) while Logistic held steady (0.6991→0.6976, -0.0015). This is expected — adding 10 games (including NC State's unusual 11-seed Final Four run) changes fold composition, and tree-based models are more sensitive to small data shifts. The Logistic model's stability confirms it's the right production choice for this data size. The best lift over baseline actually **improved** from 4.5% to 5.0% because the seed-only baseline also dropped (new games are harder to predict from seeds alone).

---

## Minor Issues (Non-blocking)

### 🟡 1. Dead Barttorvik Code
Barttorvik data is still loaded, joined, and passed through the pipeline even though no features use it. ~20 unused DataFrame columns. **Cleanup opportunity, no correctness impact.**

### 🟡 2. LRMC Missing for 2018
LRMC has 0 records for 2018; all LRMC features for 65 games are imputed to 0. This is 8.8% of training data with no LRMC signal. **Not actionable without sourcing the data.**

### 🟡 3. Duplicate Charleston Alias Key
`'College of Charleston'` appears twice in the aliases dict (lines ~149 and ~173). Python silently takes the last value. Both now point to `'Charleston'`, so no bug — but the first entry (`→ 'Col. of Charleston'`) is dead code that could confuse future readers. **Trivial cleanup.**

### 🟡 4. D2 Game in Source File
Grand Canyon vs Seattle Pacific 2013 is still in `ncaa_tournament_real.json`. Filtered at load time, but a different script loading the raw JSON would get contaminated data. **Consider cleaning source file.**

### 🟡 5. 2013 Play-in Round Coding
2013 play-in games use `round_num=1` instead of `round_num=0`. No impact — equal-seed games are skipped regardless.

### 🟡 6. `slow_dog_vs_fast_fav` Feature
This binary feature has near-zero importance (below top-15 cutoff). Not harmful, but could be a candidate for removal in a future feature selection pass.

---

## Summary

| Check | Status |
|-------|--------|
| NC State alias (7 games, 3 upsets recovered) | ✅ FIXED |
| Charleston alias (3 games recovered, no circular) | ✅ FIXED |
| Match rate ≥ 92% | ✅ 92.5% (100% of trainable games) |
| AdjEM scale fix | ✅ Still fixed |
| Barttorvik features dropped | ✅ Confirmed |
| D2 games removed | ✅ Confirmed |
| USC alias (no circular) | ✅ Confirmed |
| LOO-CV AUC > 0.65 | ✅ 0.6976 (Logistic) |
| Oakland 2024 spot check | ✅ AdjEM = 2.81 |
| UMBC 2018 spot check | ✅ In data |
| Unmatched teams | ✅ Zero (all trainable games matched) |

---

**VERDICT: ✅ PASS**

The model is ready for production use. All critical data quality issues identified in V1–V3 reviews have been resolved. The 6 minor issues listed above are cosmetic/cleanup items that do not affect model correctness or performance.
