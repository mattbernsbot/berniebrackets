# Model Data Quality Review V2 — Post-Fix Verification

**Reviewer:** Senior Code Reviewer (subagent)  
**Date:** 2026-03-16  
**Scope:** Verify 3 bugs from REVIEW_MODEL_DATA.md are fixed; identify remaining issues  
**Files:** `train_sklearn.py`, `features.py`, `data/*.json`, `models/sklearn_model.joblib`

---

## VERDICT: ❌ FAIL (conditional)

The three original bugs have been **partially fixed**. Bug 2 is fully fixed. Bug 1 is substantially improved but incomplete. Bug 3 is fixed in code but the regex check initially looked alarming because the removed alias remains in a comment. More importantly, **new issues were discovered** that are as severe as the originals.

---

## Bug 1: Team Name Mismatches — PARTIALLY FIXED ⚠️

**Evidence:**
- Match rate improved from 79.6% → 91.9% (638 → 737 of 802 games)
- All years now ≥88% match rate (was as low as <70%)
- 99 games recovered

**But 6 games (5 real + 1 D2 contamination) are still dropped due to unfinished alias work:**

| Year | Tournament Name | Normalized | KenPom Name | Fix Needed |
|------|----------------|------------|-------------|------------|
| 2018 | `NC State` | `N.C. State` | `North Carolina St.` | Alias target wrong |
| 2018 | `Col. of Charleston` | `Charleston` | `College of Charleston` → `Col. of Charleston` | Alias chain broken |
| 2011 | `UNC Asheville` | `UNC Asheville` | `NC Asheville` | Missing 2011-specific alias |
| 2011 | `Little Rock` | `Little Rock` | `Arkansas Little Rock` | Missing alias |
| 2014 | `Louisiana` | `Louisiana` | `Louisiana Lafayette` | Missing alias |
| 2013 | Grand Canyon vs Seattle Pacific | — | — | **D2 game contamination** (see New Issue 1) |

### Specific Alias Bugs Still Present:

1. **NC State → N.C. State** but KenPom uses **North Carolina St.** They don't match. Need: `'NC State': 'North Carolina St.'` and `'N.C. State': 'North Carolina St.'`

2. **Col. of Charleston** alias chain is broken:
   - `'College of Charleston'` → `'Col. of Charleston'` (alias A)
   - `'Col. of Charleston'` → `'Charleston'` (alias B)
   - These resolve to different canonical names! KenPom's `College of Charleston` → `Col. of Charleston`, but tournament's `Col. of Charleston` → `Charleston`. Both sides should resolve to the same canonical name.

3. **UNC Asheville / NC Asheville**: The alias `'UNC Asheville': 'UNC Asheville'` is a no-op. KenPom 2011 uses `NC Asheville`. Need: `'NC Asheville': 'UNC Asheville'`

**Impact:** 5 real games lost (0.6% of training data). Low severity individually, but shows the alias approach is fragile.

---

## Bug 2: AdjEM Wrong Scale for 2011, 2013-2016 — ✅ FIXED

**Evidence:**

The raw data file (`kenpom_historical.json`) still has percentile values:
```
2011: AdjEM range [0.02, 0.98], mean=0.48
2016: AdjEM range [0.07, 0.95], mean=0.49
```

But the training pipeline (`load_data()`) correctly detects and fixes this:
```python
if record['year'] in {2011, 2013, 2014, 2015, 2016} and 0 <= record['adj_em'] <= 1.0:
    record['adj_em'] = record['adj_o'] - record['adj_d']
```

After fix, AdjEM ranges are correct:
```
2011: -36.00 to  36.00  ✅
2013: -51.00 to  36.10  ✅
2014: -24.10 to  26.80  ✅
2015: -34.40 to  33.90  ✅
2016: -24.10 to  26.90  ✅
2017: -30.25 to  33.11  ✅ (was already correct)
```

**Note:** 2013 min of -51.00 is suspicious (most years cap around -42). Could be a `adj_o - adj_d` artifact for a very bad team, but worth a spot check. The fix logic (`adj_em = adj_o - adj_d`) is sound since adj_o and adj_d were confirmed correct in the V1 review.

**1,745 records corrected.** AdjEM features (`adj_em_diff`, `seed_x_adj_em`, `round_x_adj_em`) are now top-3 in Random Forest importance, confirming the fix has real signal impact.

---

## Bug 3: USC Circular Alias — ✅ FIXED

**Evidence:**

The circular alias (`'USC': 'Southern California'`) has been removed. Only the forward mapping remains:
```python
'Southern California': 'USC',  # Canonical: USC
# BUG FIX 3: REMOVED circular 'USC': 'Southern California'
```

Runtime verification:
```
normalize('Southern California') → 'USC'
normalize('USC') → 'USC'  (no alias match, returned as-is)
```

Both converge to `'USC'`. Fix is correct.

---

## New Issues Found

### 🔴 New Issue 1: Barttorvik Data Is Mostly Garbage

**Severity: CRITICAL** — Same class of bug as the original AdjEM scale issue, but undetected.

Barttorvik four-factors data (`efg`, `to_rate`, `or_pct`, `ft_rate`) has **three different failure modes**:

| Years | eFG Range | to_rate | Status |
|-------|-----------|---------|--------|
| 2011-2018 | [0.02, 0.98] (percentile) | ALL ZEROS | **Garbled scrape** |
| 2019, 2022, 2024 | [40.0, 59.8] (correct %) | [12.0, 25.1] | ✅ Real data |
| 2021, 2023 | No records | No records | **Missing entirely** |
| 2025 | ALL ZEROS | ALL ZEROS | **Placeholder / failed scrape** |

**Impact on training:**
- **50% of games** (398/799) use garbled eFG (0-1 range) with zero turnover rate
- **25% of games** (200/799) have no Barttorvik data at all (imputed to D-I averages)
- **Only 25% of games** (201/799) have real four-factors data

The features `efg_diff`, `to_diff`, `or_diff`, `ft_rate_diff` are corrupted. The `to_diff` feature is essentially noise (zero for 75% of games). Despite this, `efg_diff` shows up as feature #6 in importance — which may mean the model is overfitting to the 25% of games with real data, or the percentile version (0-1 range) provides weak directional signal.

**No fix was applied.** Unlike the KenPom AdjEM fix, there's no `adj_o - adj_d` equivalent to reconstruct Barttorvik values. Options:
1. Drop Barttorvik features entirely (safest)
2. Only use Barttorvik for years with real data (2019, 2022, 2024)
3. Scale-correct 2011-2018 eFG by multiplying by ~55 (risky — other fields are still broken)

### 🟡 New Issue 2: LRMC Missing for 2018

LRMC data has no records for 2018 (65 tournament games that year). All LRMC features for 2018 teams are imputed to defaults (0). This is ~9% of training data with no LRMC signal. Not critical since LRMC features are lower importance, but worth noting.

### 🟡 New Issue 3: D2 Game Contamination

The game `2013: #6 Grand Canyon vs #3 Seattle Pacific` is from the **NCAA Division II tournament**, not D1. Both teams were D2 in 2013 (Grand Canyon transitioned to D1 in 2013-14; Seattle Pacific is still D2). This game should be removed from the training data.

Additionally, the 2013 play-in games are coded as `round_num=1` instead of `round_num=0` (all other years use 0 for play-in). This creates 4 games with equal seeds (16v16, 11v11, 13v13) in round 1, which the model skips (equal seeds → no favorite/underdog). Not harmful but inconsistent.

### 🟡 New Issue 4: Barttorvik Duplicate Keys Inflate Game Count

42 Barttorvik team-year combinations have duplicate records. The left join creates extra rows, inflating the game count from 799 → 802. The training script reports `737/802 (91.9%)` when the true denominator is 799. This slightly understates the real match rate.

Fix: Deduplicate Barttorvik data before joining (`drop_duplicates(subset=['key'], keep='first')`).

### 🟡 New Issue 5: 2025 Barttorvik Is All Zeros

The current year (2025) has 364 Barttorvik records but every field is zero. This means the model trained on 2025 data has garbage Barttorvik features. More importantly, **predictions for the 2026 bracket** using 2025 KenPom data will have useless Barttorvik features unless this is fixed.

---

## Check 4: Spot Checks

| Team | Year | Expected | Found | Status |
|------|------|----------|-------|--------|
| Oakland | 2024 (14-seed) | AdjEM ~+2.81 | AdjEM = 2.81, AdjO = 108.9, AdjD = 106.1 | ✅ Real data |
| UMBC | 2018 (16-seed) | In training data | 2 games found | ✅ Present |
| Siena | 2025 (16-seed in 2026 bracket) | Real KenPom stats | AdjEM = -7.44, rank = 254, conference = MAAC | ✅ Real data |

All spot-checked teams have real, non-fabricated statistics.

---

## Check 5: Model Quality

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| LOO-CV AUC (Ensemble) | 0.6819 | > 0.65 | ✅ Pass |
| LOO-CV AUC (LR) | 0.6901 | > 0.65 | ✅ Pass (best model) |
| Seed baseline AUC | 0.6642 | — | Reference |
| Lift over baseline | +2.6% (LR) | Positive | ✅ |
| Training samples | 737 | — | — |
| Model file loadable | Yes | — | ✅ |

**The CV methodology is correct** — Leave-One-Year-Out ensures no temporal leakage. Each fold trains on 12 years and tests on 1. This is honest out-of-sample evaluation.

**However:** The AUC improvement over the old model is only +0.0011 despite fixing major bugs. This suggests either:
1. The model architecture (21 features, LR/RF/GB) has hit a ceiling
2. The garbled Barttorvik features are adding noise that offsets the AdjEM fix gains
3. The real improvement is in calibration (not discrimination), which AUC doesn't capture

---

## Check 6: Remaining Data Issues Summary

| Issue | Severity | Games Affected | Status |
|-------|----------|---------------|--------|
| 5 team names still unmatched | Low | 5 games (0.6%) | Alias gaps |
| Barttorvik garbled for 2011-2018 | **High** | 398 games (50%) | **Unfixed** |
| Barttorvik missing for 2021, 2023 | Medium | ~133 games (17%) | Imputed to defaults |
| Barttorvik all-zeros for 2025 | Medium | 67 games (8%) | **Unfixed** |
| LRMC missing for 2018 | Low | 65 games (8%) | Imputed to defaults |
| D2 game in 2013 | Low | 1 game | Should remove |
| Barttorvik duplicate keys | Low | 3 extra rows | Should deduplicate |
| 2013 play-in round_num coding | Low | 4 games | Inconsistent but harmless |

---

## Recommendations

### Must Fix Before Production:
1. **Drop or quarantine Barttorvik features** — They're contaminated for 75% of training years. Either remove features 14-17 (`efg_diff`, `to_diff`, `or_diff`, `ft_rate_diff`) and feature 21 (`efg_x_round`), or apply the same detect-and-correct pattern used for KenPom AdjEM.

2. **Fix remaining 5 alias gaps** — Specifically `NC State`→`North Carolina St.` and the Charleston chain.

3. **Remove D2 game** — Grand Canyon vs Seattle Pacific 2013.

### Should Fix:
4. Deduplicate Barttorvik before join to prevent row inflation
5. Scrape or source real 2025 Barttorvik data for current-year predictions
6. Add LRMC 2018 data or document the gap

### Consider:
7. Retrain without Barttorvik features and compare AUC — may actually improve
8. The modest AUC improvement (+0.0011) after fixing critical bugs suggests the model may benefit more from better features than cleaner versions of mediocre ones

---

## Final Assessment

| Bug | Status | Confidence |
|-----|--------|------------|
| Bug 1: Team name mismatches | **SUBSTANTIALLY FIXED** (91.9% match rate, 5 remaining gaps) | High |
| Bug 2: AdjEM wrong scale | **FIXED** (pipeline corrects at load time) | High |
| Bug 3: USC circular alias | **FIXED** (circular removed, both resolve to 'USC') | High |

**VERDICT: FAIL** — The three original bugs are addressed, but the Barttorvik data quality issue (New Issue 1) is the same class of bug as Bug 2 (wrong scale / garbled scrape) and affects 4 of the model's 21 features across 75% of training data. The model should not go to production until Barttorvik features are either fixed or removed.

If Barttorvik features are dropped and the 5 remaining alias gaps are fixed, this would be a **PASS**.
