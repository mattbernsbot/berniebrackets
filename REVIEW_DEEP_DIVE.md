# Deep Dive Review: Upset Prediction Model

**Date:** 2026-03-16  
**Reviewer:** Automated code review (subagent)

---

## 1. KenPom 68-Team Bug: Present in Training?

### Verdict: **NO** — Not present. Training data is complete.

### Evidence

**`kenpom_historical.json` team counts per year:**

| Year | Teams |
|------|-------|
| 2011 | 345   |
| 2013 | 347   |
| 2014 | 351   |
| 2015 | 351   |
| 2016 | 351   |
| 2017 | 351   |
| 2018 | 351   |
| 2019 | 353   |
| 2021 | 357   |
| 2022 | 358   |
| 2023 | 363   |
| 2024 | 362   |
| 2025 | 364   |
| **Total** | **4,604** |

All years have 345-364 teams — the full D1 population. No year is truncated to 68.

**Match rate by seed line (games joined to KenPom):**

| Seed | Matched | Total | Rate |
|------|---------|-------|------|
| 1    | 190     | 190   | 100% |
| 2    | 146     | 146   | 100% |
| 3    | 135     | 136   | 99.3% |
| 4    | 127     | 127   | 100% |
| 5    | 101     | 101   | 100% |
| ...  | ...     | ...   | 100% |
| 12   | 76      | 76    | 100% |
| 13   | 63      | 63    | 100% |
| 14   | 55      | 55    | **100%** |
| 15   | 61      | 61    | **100%** |
| 16   | 102     | 102   | **100%** |
| **Total** | **1,596** | **1,598** | **99.9%** |

The only 2 misses are the D2 teams from the 2013 Grand Canyon/Seattle Pacific game (correctly filtered by the D2 removal fix).

**Training pipeline (`train_sklearn.py`) does NOT filter KenPom data:**
- Loads full JSON: `json.load(open('kenpom_historical.json'))`
- Applies AdjEM scale fix for years {2011, 2013-2016} (where `adj_em` was stored as percentile)
- Joins on `year + team_norm` key
- No ranking filter, no top-N cutoff, no subsetting

### Conclusion

The 68-team bug was specific to the **prediction/live** pipeline, not the training pipeline. Training uses all D1 teams and matches 100% of 14/15/16-seeds — exactly what we want for upset modeling.

---

## 2. Barttorvik: Real Data at Wrong Scale, or Actually Garbage?

### Verdict: **Actually garbage for 2011-2018 — scraping artifact, not a scale issue.**

### Evidence

The data falls into three distinct categories:

**Category A: Percentile ranks + ordinal ranks (2011-2018) — GARBAGE**

| Year | eFG Range | ft_rate Range | or_pct Range | to_rate |
|------|-----------|---------------|--------------|---------|
| 2011 | 0.025 – 0.977 | 1 – 345 (integers) | 1 – 345 (integers) | ALL ZEROS |
| 2014 | 0.043 – 0.972 | 1 – 351 (integers) | 1 – 351 (integers) | ALL ZEROS |
| 2018 | 0.038 – 0.973 | 1 – 351 (integers) | 1 – 351 (integers) | ALL ZEROS |

- **eFG**: Spread of ~0.95 across the 0-1 range. Real eFG% for NCAA teams ranges 0.43-0.58 (fraction) or 43-58 (percentage) — a spread of only ~0.15. The 0.95 spread is definitive: **these are percentile ranks** (team at the Nth percentile), NOT real shooting percentages.
- **ft_rate, or_pct**: Integer values from 1 to N (where N ≈ number of teams). These are **ordinal ranks** (1st, 2nd, 3rd...), not real rates.
- **to_rate**: All zeros — completely missing.

The previous reviewer's "false alarm" hypothesis (that 0.48-0.56 might be real fractions) is **wrong**. The actual range is 0.025-0.977, not 0.48-0.56. That range is only possible if these are percentile ranks.

**Category B: Real data (2019, 2022, 2024) — GOOD**

| Year | eFG Range | ft_rate Range | or_pct Range | to_rate Range |
|------|-----------|---------------|--------------|---------------|
| 2019 | 40.0 – 59.0 | 21.9 – 48.6 | 15.9 – 38.7 | 13.5 – 25.1 |
| 2022 | 41.3 – 59.2 | (similar) | (similar) | (similar) |
| 2024 | 41.0 – 59.8 | (similar) | (similar) | (similar) |

These are real percentages in the expected ranges.

**Category C: Missing years — NO DATA**

| Year | Status |
|------|--------|
| 2021 | Not in file |
| 2023 | Not in file |
| 2025 | All fields = 0.0 |

### Root Cause: Scraper Bug

The scraper (`scrape_barttorvik.py`) uses Wayback Machine snapshots. It parses cells with `parse_barttorvik_value()`, which tries to extract the value before `<br/>` tags. For **2011-2018 snapshots**, the Barttorvik page layout was different:

- The page rendered **rank** in the main cell text and **value** in a nested span (or vice versa)
- The parser extracted the **rank** instead of the **real value**
- For eFG, ranks were normalized to 0-1 (percentile), producing the 0.025-0.977 range
- For ft_rate/or_pct, raw ordinal ranks (1-351) were captured instead of real rates
- For to_rate, the parser failed entirely and returned zeros

For 2019+ snapshots, the page layout matched what the parser expected, so values were correctly extracted.

### Summary Scorecard

| Years | Count | Data Quality | Usable? |
|-------|-------|-------------|---------|
| 2011, 2013-2018 | 7 years | Ranks, not values | ❌ |
| 2019, 2022, 2024 | 3 years | Real percentages | ✅ |
| 2021, 2023 | 2 years | Missing entirely | ❌ |
| 2025 | 1 year | All zeros | ❌ |
| **Total usable** | **3 of 13** | | **23%** |

### Recommendation: **Keep Barttorvik features DROPPED.**

**Reasons:**
1. Only 3/13 training years have real data — too few to learn stable feature weights
2. Including garbage ranks as if they were real statistics would actively poison the model
3. Fixing requires re-scraping from Wayback Machine with a parser that handles old page layouts, with no guarantee usable snapshots exist
4. The model already achieves good performance with 16 KenPom + LRMC features
5. Adding 4 features with 77% missing data creates a sparse feature problem

**If someone wants to restore Barttorvik in the future:**
1. Download raw Wayback Machine HTML for 2011-2018 and inspect the actual cell structure
2. Rewrite `parse_barttorvik_value()` to handle the old layout (extract from rank spans, not main text)
3. Verify that Wayback Machine actually archived the value data (it may have only captured the ranked view)
4. Re-scrape 2021, 2023, and 2025
5. Validate all years against known team stats before re-enabling features

This is non-trivial effort for marginal gain. The four factors (eFG, TO%, ORB%, FTR) are correlated with KenPom's AdjO/AdjD, so much of their signal is already captured.

---

## Summary

| Investigation | Finding | Action Needed |
|---------------|---------|---------------|
| KenPom 68-team bug | **NOT present** in training. All 345-364 D1 teams per year. 100% match rate for seeds 12-16. | None — training pipeline is correct |
| Barttorvik data quality | **Genuinely garbage** for 7/13 years (scraper extracted ranks, not values). Only 3 years usable. | Keep dropped. Fix scraper only if Barttorvik features become high priority. |
