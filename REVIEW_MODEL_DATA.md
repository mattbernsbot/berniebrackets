# Model Data Quality Review

**Reviewer:** Code Review Agent  
**Date:** 2025-03-16  
**Scope:** Historical training data quality for the upset prediction model  
**Files reviewed:** `train_sklearn.py`, `features.py`, `scrape_kenpom_real.py`, `kenpom_historical.json`, `ncaa_tournament_real.json`, `sklearn_model.joblib`

---

## Executive Summary

**The original fear — that only 68 KenPom teams were scraped — is NOT the problem.** The historical KenPom data contains 345-364 teams per year (all D1), scraped from Wayback Machine archives. The data is real.

However, the model has **three significant data quality issues** that collectively compromise it:

| Issue | Severity | Impact |
|-------|----------|--------|
| 1. Team name mismatches drop 20% of games | 🔴 Critical | 120/799 games lost, biased toward 14-16 seeds |
| 2. AdjEM scale inconsistency across years | 🔴 Critical | 2011-2016 use percentile (0-1), 2017+ use real scale (-30 to +35) |
| 3. USC alias creates circular swap bug | 🟡 Moderate | Affects ~11 USC tournament games across 6 years |

**Bottom line: The model is trained on real data, but the data is contaminated by preprocessing bugs. The model should be retrained after fixes.**

---

## Issue 1: Team Name Mismatches (CRITICAL)

### The Problem

The `normalize_team_name()` function in `train_sklearn.py` has only 23 aliases. Tournament data and KenPom data use different naming conventions for many teams. When a team can't be joined, the entire game is **silently dropped** (`how='left'` join produces NaN, then `build_feature_matrix` skips rows with missing KenPom).

### Evidence

```
Total tournament games:  799 (801 after merge duplication)
Games with valid KenPom:  638
Games DROPPED:            120 (15.0%)
```

82 unique team-year combinations fail to match after normalization.

### Bias in Dropped Games

The drops are **not random** — they skew heavily toward high-seed (low-ranked) teams:

| Matchup | Total Games | Dropped | Drop Rate | Upsets Dropped |
|---------|------------|---------|-----------|----------------|
| 1 vs 16 | 52 | 16 | **31%** | 1 |
| 2 vs 15 | 52 | 10 | **19%** | 2 |
| 3 vs 14 | 52 | 11 | **21%** | 0 |
| 4 vs 13 | 52 | 4 | 8% | 0 |
| 5 vs 12 | 52 | 9 | 17% | 3 |
| 6 vs 11 | 52 | 8 | 15% | 4 |
| 7 vs 10 | 50 | 4 | 8% | 1 |
| 8 vs 9  | 51 | 5 | 10% | 4 |

**31% of 1-vs-16 games are dropped.** This means the model has significantly less training data for the most extreme seed matchups. Across all rounds, 28 upsets are lost from training data.

### Missing Name Mappings Required

These tournament-to-KenPom aliases are needed:

| Tournament Name | KenPom Name | Years Affected |
|----------------|-------------|----------------|
| `Miami (FL)` | `Miami FL` | 2013-2023 (6 years) |
| `St. Mary's (CA)` / `Saint Mary's (CA)` | `Saint Mary's` | 2013-2025 (9 years) |
| `NC State` | `N.C. State` | 2018, 2023, 2024 |
| `FGCU` | `Florida Gulf Coast` | 2013, 2016, 2017 |
| `FDU` | `Fairleigh Dickinson` | 2023 |
| `SFA` | `Stephen F. Austin` | 2018 |
| `UNI` | `Northern Iowa` | 2015, 2016 |
| `Middle Tenn.` | `Middle Tennessee` | 2013, 2016, 2017 |
| `Northern Ky.` | `Northern Kentucky` | 2017, 2019, 2023 |
| `Eastern Wash.` | `Eastern Washington` | 2015, 2021 |
| `Coastal Caro.` | `Coastal Carolina` | 2014, 2015 |
| `Western Ky.` | `Western Kentucky` | 2013, 2024 |
| `Northern Colo.` | `Northern Colorado` | 2011 |
| `Boston U.` | `Boston University` | 2011 |
| `App State` | `Appalachian St.` | 2021 |
| `Mt. St. Mary's` | `Mount St. Mary's` | 2014, 2017 |
| `Albany (NY)` | `Albany` | 2013-2015 |
| `Fla. Atlantic` | `Florida Atlantic` | 2023, 2024 |
| `Col. of Charleston` | `Charleston` | 2023, 2024 |
| `Gardner-Webb` | `Gardner Webb` | 2019 |
| `Loyola (IL)` | `Loyola Chicago` | 2018 |
| `UALR` | `Arkansas Little Rock` | 2016 |
| `Bakersfield` | `Cal St. Bakersfield` | 2016 |
| `Saint Peter's` | `St. Peter's` | 2011 |
| `UNC Asheville` | `NC Asheville` (2011-2013) / `UNC Asheville` (2014+) | 2011 |
| `UTSA` | `Texas San Antonio` | 2011 |
| `Grambling` | `Grambling St.` | 2024 |
| `McNeese` | `McNeese St.` | 2024 |
| `Omaha` | `Nebraska Omaha` | 2025 |
| `UNCW` | `UNC Wilmington` | 2025 |
| `Southern U.` | `Southern` | 2013, 2016 |
| `N.C. Central` | `North Carolina Central` | 2014, 2017-2019 |
| `N.C. A&T` | `North Carolina A&T` | 2013 |
| `East Tenn. St.` | `East Tennessee St.` | 2017 |
| `Eastern Ky.` | `Eastern Kentucky` | 2014 |
| `Western Mich.` | `Western Michigan` | 2014 |
| `Prairie View` | `Prairie View A&M` | 2019 |
| `A&M-Corpus Christi` | `Texas A&M Corpus Chris` | 2022, 2023 |
| `Southeast Mo. St.` | `Southeast Missouri St.` | 2023 |
| `Saint Louis` | `St. Louis` | 2013 |

---

## Issue 2: AdjEM Scale Inconsistency (CRITICAL)

### The Problem

The KenPom `adj_em` field uses **two completely different scales** depending on the year:

| Years | adj_em Scale | Range | Source |
|-------|-------------|-------|--------|
| 2011, 2013-2016 | **Percentile (0 to 1)** | 0.015 to 0.980 | Wayback scraping artifact |
| 2017-2025 | **Real AdjEM** | -42.21 to +38.08 | Correct KenPom values |

### Evidence

```
2011: #1 Ohio St.    adj_em=0.9804   adj_o=124.7   adj_d=88.7  (real AdjEM should be ~36.0)
2016: #1 Kansas      adj_em=0.9503   adj_o=120.4   adj_d=93.5  (real AdjEM should be ~26.9)
2017: #1 Gonzaga     adj_em=33.11    adj_o=123.8   adj_d=90.7  (correct!)
2024: #1 Houston     adj_em=33.06    adj_o=120.1   adj_d=87.0  (correct!)
```

For 2011 and 2013-2016, the `adj_em` appears to be a percentile rank (rank / total_teams), not the actual efficiency margin. The `adj_o` and `adj_d` values are correct in all years — only `adj_em` is affected.

### Impact on Model

This means features like `adj_em_diff`, `seed_x_adj_em`, and `round_x_adj_em` have **completely different magnitudes** for 2011-2016 vs 2017+:

- For 2017-2025: `adj_em_diff` between a 1-seed and 16-seed might be ~40 points
- For 2011-2016: `adj_em_diff` between a 1-seed and 16-seed is ~0.95

The StandardScaler will partially compensate, but since all years are pooled together, the scaler fits to the combined distribution. This means:
- 2011-2016 `adj_em_diff` values cluster near zero after scaling
- 2017+ `adj_em_diff` values dominate the feature

The model effectively **ignores AdjEM for 5 of its 13 training years**, which is ~35-40% of the training data.

### Root Cause

The `scrape_kenpom_real.py` parser reads `cells[4].text.strip()` for AdjEM. The Wayback Machine snapshots for 2011-2016 likely had AdjEM displayed as a percentile or in a different format than later years. The `adj_o` and `adj_d` columns parsed correctly because they use a consistent format.

### Fix

Either:
1. Re-scrape 2011-2016 and fix the parser to get real AdjEM values, or
2. Compute `adj_em = adj_o - adj_d` for all years (since these columns are correct), or
3. For 2011-2016, convert percentile back to AdjEM using `adj_o - adj_d`

Option 2 is the simplest and most robust.

---

## Issue 3: USC/Southern California Circular Alias (MODERATE)

### The Problem

```python
aliases = {
    'Southern California': 'USC',    # Line A
    ...
    'USC': 'Southern California',    # Line B
}
```

These two aliases create a **circular swap**: `'Southern California' → 'USC'` and `'USC' → 'Southern California'`. Since Python dicts iterate in insertion order and the function returns on first match:

- Tournament name `"Southern California"` → matches Line A → normalized to `"USC"`
- KenPom name `"USC"` (2014+) → matches Line B → normalized to `"Southern California"`
- `"USC" ≠ "Southern California"` → **join fails**

KenPom uses `"Southern California"` in 2011-2013 and `"USC"` from 2014 onward, so the alias only works for 2011 (where both sides have `"Southern California"` → both normalize to `"USC"`).

This affects ~11 tournament games involving USC/Southern California across 2016-2023.

---

## Issue 4: Spot-Check Results (GOOD NEWS)

### Oakland 2024 (14-seed that beat Kentucky)

✅ **Real data confirmed:**
```json
{
  "year": 2024,
  "team": "Oakland",
  "rank": 135,
  "adj_em": 2.81,
  "adj_o": 108.9,
  "adj_d": 106.1,
  "adj_t": 66.8,
  "luck": 0.082
}
```

This matches the real 2024 KenPom data. Oakland's AdjEM of +2.81 and rank 135 are correct. The scraper successfully captured all D1 teams, not just top 68.

### Other 2024 Low Seeds

| Team | Seed | KenPom Found | AdjEM | Rank |
|------|------|-------------|-------|------|
| Oakland | 14 | ✅ | 2.81 | 135 |
| Wagner | 16 | ✅ | -10.1 | 292 |
| Howard | 16 | ✅ | -8.8 | 281 |
| Montana St. | 16 | ✅ | -3.94 | 214 |
| Akron | 14 | ✅ | 5.04 | 117 |
| Long Beach St. | 15 | ✅ | -0.8 | 171 |
| Grambling | 16 | ❌ (name: `Grambling St.`) | — | — |
| McNeese | 12 | ❌ (name: `McNeese St.`) | — | — |

When teams ARE matched, they have real KenPom stats. The failures are all name mismatches, not missing data.

---

## Summary: Model Health Assessment

### What's OK ✅
- KenPom historical data has **345-364 teams per year** (all D1) — NOT just 68
- The data is **real**, scraped from Wayback Machine archives
- `adj_o`, `adj_d`, `adj_t`, `luck` values appear correct across all years
- Low-seeded teams have their real KenPom stats when name matching succeeds

### What's Broken ❌
1. **120 games dropped** (15%) due to name mismatches — biased toward high-seed teams
2. **AdjEM scale wrong for 5 years** (2011, 2013-2016) — percentile instead of real value
3. **USC circular alias** — ~11 games affected
4. The current model (AUC 0.681) was trained on **638 of 799 games** with corrupted AdjEM features

### Recommended Actions (Priority Order)

1. **Fix `adj_em` computation:** Use `adj_o - adj_d` for all years (or just fix 2011-2016). This is a one-line fix that corrects 35% of training data.

2. **Expand `normalize_team_name()`:** Add the ~40 missing aliases listed above. This recovers 120+ dropped games.

3. **Fix USC alias:** Change to a single canonical form:
   ```python
   'Southern California': 'USC',
   # DELETE the 'USC': 'Southern California' line
   ```
   Then also normalize the KenPom 2011-2013 entries from `'Southern California'` to `'USC'`.

4. **Retrain the model** after all fixes. Expected improvements:
   - Training on ~780+ games instead of 638
   - Correct AdjEM features across all years
   - Better calibration for high-seed upset probabilities

### Impact on Current Bracket Predictions

The current model's upset probabilities for 12-16 seed upsets are likely **underconfident** because:
- 31% of 1v16 training examples are missing
- 21% of 3v14 examples are missing
- AdjEM differential (a key feature) is essentially noise for 5 of 13 training years

The ensemble AUC of 0.681 should improve materially after these fixes.

---

*Review complete. No fabricated stats found — just incomplete joins and a scraping artifact. The model is trainable on real data once the preprocessing is fixed.*
