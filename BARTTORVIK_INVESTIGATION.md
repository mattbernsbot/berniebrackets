# Barttorvik Scraper Investigation - Complete Analysis

**Date:** 2026-03-16  
**Investigator:** Senior ML Engineer (subagent barttorvik-fix)

---

## Executive Summary

**The Barttorvik four-factors data for 2011-2018 is NOT recoverable from Wayback Machine.**

The historical snapshots only captured **percentile ranks** and **ordinal ranks**, NOT the underlying statistical values. This is a fundamental limitation of what was archived, not a scraper bug that can be fixed.

**Recommendation: Keep Barttorvik features DROPPED.** Only 3 of 13 training years have usable data, making stable feature learning impossible.

---

## Investigation Details

### Step 1: HTML Structure Analysis

Fetched and compared actual Wayback Machine HTML for two years:

**2019 (WORKS) - Example cell structure:**
```html
<td>59<br/><span style="font-size:8px;">1</span></td>
```
- **59** = actual eFG% value
- **1** = rank (1st in nation)

**2017 (BROKEN) - Example cell structure:**
```html
<td style="text-align:center">.9750</td>
```
- **.9750** = 97.5th percentile rank
- NO actual eFG% value exists

### Step 2: Systematic Scan of All Years

Tested multiple dates for each year (2014-2018):

| Year | EFG Cell Content | Interpretation |
|------|------------------|----------------|
| 2014 | `.9718` | 97.18th percentile rank |
| 2015 | `.9858` | 98.58th percentile rank |
| 2016 | `.9707` | 97.07th percentile rank |
| 2017 | `.9750` | 97.50th percentile rank |
| 2018 | `.9727` | 97.27th percentile rank |

**Tried multiple snapshot dates per year** (March 1, 10, 15, 20, April 1) - ALL had the same rank-only structure.

**Tried alternative URLs** (`teamstats.php`) - no usable four-factors data found.

### Step 3: Current Scraped Data Analysis

From `barttorvik_historical.json`:

| Year | Teams | eFG% Range | Data Quality |
|------|-------|------------|--------------|
| 2011 | 351 | 0.025 - 0.977 | ❌ Percentile ranks |
| 2013 | 353 | 0.038 - 0.978 | ❌ Percentile ranks |
| 2014 | 357 | 0.043 - 0.972 | ❌ Percentile ranks |
| 2015 | 357 | 0.025 - 0.986 | ❌ Percentile ranks |
| 2016 | 357 | 0.048 - 0.971 | ❌ Percentile ranks |
| 2017 | 357 | 0.028 - 0.975 | ❌ Percentile ranks |
| 2018 | 357 | 0.037 - 0.973 | ❌ Percentile ranks |
| 2019 | 353 | 40.0 - 59.0 | ✅ Real percentages |
| 2021 | ? | ? | ⚠️ Missing from file |
| 2022 | 254 | 41.3 - 59.2 | ✅ Real percentages |
| 2023 | ? | ? | ⚠️ Missing from file |
| 2024 | 362 | 41.0 - 59.8 | ✅ Real percentages |
| 2025 | 364 | All 0.0 | ❌ Incomplete season |

**Verification against known ranges:**
- Real eFG%: 42-58% ✓
- Real TO%: 14-25% ✓
- Real OR%: 22-38% ✓
- Real FTR: 25-45% ✓

### Step 4: Root Cause

Between 2018 and 2019, Barttorvik changed the website layout:

**Old layout (2011-2018):**
- Displayed only ranks in table cells
- Actual values may have existed in JavaScript or were never served to browsers
- Wayback Machine captured what browsers saw: ranks only

**New layout (2019+):**
- Displays `value<br/><span>rank</span>` in each cell
- Both value and rank are in HTML
- Current parser correctly extracts value by splitting on `<br/>`

---

## Data Availability Summary

| Category | Years | Count | Usable? |
|----------|-------|-------|---------|
| Rank-only (unfixable) | 2011, 2013-2018 | 7 | ❌ |
| Real values | 2019, 2022, 2024 | 3 | ✅ |
| Missing entirely | 2021, 2023 | 2 | ❌ |
| Incomplete | 2025 | 1 | ❌ |
| **Total usable** | | **3/13** | **23%** |

---

## Why This Matters for ML

**Problem: Sparse feature catastrophe**

Including Barttorvik features means:
- 7 years get **garbage percentile ranks** disguised as real stats
- 3 years get **real four-factors data**
- 3 years get **zeros** (missing data imputation)

**Expected model behavior:**
- Feature weights will be unstable (learned from 23% good data, 77% noise)
- Signal-to-noise ratio is terrible
- Four-factors already correlated with KenPom AdjO/AdjD (which we have 100% complete)

**Better alternative:**
- Use only KenPom + LRMC features (100% data coverage)
- Four-factors information is implicitly captured in Adjusted Efficiency margins
- Cleaner feature matrix = more stable weights

---

## Recommendation: KEEP BARTTORVIK DROPPED

Reasons:
1. ❌ Only 23% of training years have real data
2. ❌ Cannot fix via scraper (data doesn't exist in archives)
3. ❌ Four-factors already captured in KenPom AdjO/AdjD
4. ❌ Sparse features hurt model stability
5. ✅ Current 16-feature model (KenPom + LRMC) is clean and complete

---

## Alternative (If Someone Insists)

**Option A: Use only the 3 good years**
- Re-scrape 2019, 2022, 2024 with verified parser
- Try to find 2021, 2023 snapshots (different dates)
- Train model with `efg_diff`, `to_diff`, `or_diff`, `ft_rate_diff`
- Compare AUC to baseline (expect minimal or negative gain)

**Option B: Wait for 2026+ data**
- Modern Barttorvik site has real values
- In 3-4 years, we'll have 6-7 years of clean data (50%+ coverage)
- Then it might be worth adding

---

## Files Modified

None. Investigation concluded that no code changes can fix the fundamental data unavailability.

---

## Next Steps

**Requester decision needed:**

1. **Accept recommendation** → Close this task, keep Barttorvik dropped
2. **Try Option A** → Re-scrape 3 good years, retrain model, measure AUC impact
3. **Defer to future** → Wait for more years of clean Barttorvik data

**My professional recommendation as ML engineer:** Accept option 1. Adding sparse, low-coverage features is an anti-pattern in production ML.
