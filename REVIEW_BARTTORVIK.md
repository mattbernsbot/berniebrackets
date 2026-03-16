# Barttorvik Data Review — Independent Verification

**Reviewer:** Senior Code Reviewer (data inspection subagent)  
**Date:** 2026-03-16  
**Reviewed:** BARTTORVIK_INVESTIGATION.md + raw data + Wayback Machine HTML

---

## VERDICT

| Question | Answer |
|----------|--------|
| Is the data truly unrecoverable? | **NO — THE DATA IS FULLY RECOVERABLE** |
| Should we keep Barttorvik dropped? | **NO — Fix the scraper and re-add features** |
| Alternative to get four-factors data? | Not needed — Barttorvik data exists in Wayback |

---

## 🚨 Critical Finding: The Coder's Investigation Was Wrong

The Coder concluded that old Barttorvik years (2011-2018) only contain "percentile ranks" and the real four-factors data is unrecoverable. **This is incorrect.** The data IS present in the Wayback HTML — the scraper was reading the wrong column.

### Root Cause: Column Index Mismatch

Barttorvik changed its HTML table layout between 2018 and 2019:

| Layout | Years | Cells per row | eFG% at cell | Barthag at cell |
|--------|-------|---------------|--------------|-----------------|
| **Old** | 2011-2018 | **31** (value + rank in separate `<td>`) | **Cell 11** | Cell 8 |
| **New** | 2019+ | **24** (value + rank combined via `<br/>`) | **Cell 8** | Cell 7 |

The scraper (`scrape_barttorvik.py`) was hardcoded to read `cells[8]` for eFG% — correct for the new layout, **wrong for the old layout** where cell 8 is the Barthag rating (0.9750), which the Coder misidentified as a "percentile rank."

### Proof: Raw HTML Cell Content for Gonzaga 2017

```
Cell  4 (AdjO):     120.2
Cell  5 (AdjO rank): 14
Cell  6 (AdjD):      84.0
Cell  7 (AdjD rank): 1
Cell  8 (Barthag):   .9750    ← Scraper reads THIS as "eFG%"
Cell  9 (Record):    37-2
Cell 10 (Conf Rec):  17-1
Cell 11 (eFG%):      56.6    ← REAL eFG% is HERE
Cell 12 (eFG rank):  8
Cell 13 (eFG% D):    41.1
Cell 14 (eFG% D rank): 1
Cell 15 (TO%):       16.2    ← REAL TO%
Cell 17 (TO% D):     17.1
Cell 19 (OR%):       30.0    ← REAL OR%
Cell 23 (FTR):       39.0    ← REAL FTR
```

### Verified: ALL 7 "Broken" Years Have Real Data

I independently fetched every problematic year from Wayback and extracted the first team's four-factors:

| Year | Team | eFG% | TO% | OR% | FTR | Valid? |
|------|------|------|-----|-----|-----|--------|
| 2011 | Ohio St. | 56.3 | 15.8 | 35.7 | 37.1 | ✅ |
| 2013 | Louisville | 50.6 | 18.3 | 38.2 | 40.0 | ✅ |
| 2014 | Louisville | 53.5 | 15.3 | 37.1 | 41.2 | ✅ |
| 2015 | Kentucky | 51.5 | 16.3 | 39.5 | 43.9 | ✅ |
| 2016 | Villanova | 56.1 | 16.3 | 28.2 | 34.1 | ✅ |
| 2017 | Gonzaga | 56.6 | 16.2 | 30.0 | 39.0 | ✅ |
| 2018 | Villanova | 59.5 | 15.0 | 29.6 | 29.4 | ✅ |

All values fall in the expected basketball ranges (eFG%: 40-60, TO%: 12-25, OR%: 15-42, FTR: 20-50).

---

## How the Coder Went Wrong

1. **Saw `.9750` in cell 8 and assumed "percentile rank"** — it's actually the Barthag rating (a win probability metric that naturally lives in 0-1 range)
2. **Did not compare cell indices between old and new layouts** — the old layout has 31 cells per row (separate value/rank cells), the new has 24 (combined)
3. **The `or_pct` field** in old years currently contains ordinal ranks (1-351), which are from the rank cells being read instead of the value cells
4. **`to_rate` is all zeros for old years** — because in the old layout, the cell at the scraper's expected index contains non-numeric data

### Why the Percentile-Rank Theory Seemed Plausible

The Barthag values (.9750, .9642, .9587...) are in the 0-1 range, which superficially looks like percentile ranks. The `or_pct` values (1-351) also looked like ranks. But Barthag is a legitimate Barttorvik metric (win probability), and the "ordinal ranks" were literally rank cells being read by accident.

---

## Current Data Quality vs. Corrected

**Current (broken scraper):**
```
2017 efg: range=[0.0278, 0.9750] ← These are Barthag values, NOT eFG%
2017 to_rate: NO DATA             ← Parser failed on non-numeric cell
2017 or_pct: range=[1.0, 351.0]  ← These are ordinal RANKS
```

**Corrected scraper would produce:**
```
2017 efg: ~[45.0, 59.0]  ← Real eFG% (from cell 11)
2017 to_rate: ~[13.0, 25.0]  ← Real TO% (from cell 15)
2017 or_pct: ~[22.0, 38.0]  ← Real OR% (from cell 19)
2017 ft_rate: ~[21.0, 48.0] ← Real FTR (from cell 23)
```

---

## Check 3: Do We Need Four-Factors If We Have KenPom?

KenPom provides: `adj_em`, `adj_o`, `adj_d`, `adj_t`, `luck`

**You CANNOT derive four-factors from KenPom:**
- AdjO = overall offensive efficiency (points per 100 possessions)  
- eFG% = shooting accuracy only (excludes turnovers, rebounding, FT drawing)
- A team can have high AdjO via elite shooting (high eFG%) or via great offensive rebounding (high OR%) — AdjO conflates these

**Four-factors add INDEPENDENT information:**
- eFG% tells you HOW a team scores (shooting)
- TO% tells you ball security
- OR% tells you second-chance generation
- FTR tells you foul-drawing ability

These are classic "style of play" features that explain WHY matchups go sideways. A team with a terrible eFG% opponent but great defense might be vulnerable against a team that rebounds well rather than shoots well. KenPom's aggregate efficiency numbers miss this.

**Recommendation:** Four-factors features are worth adding if the data is clean. They provide matchup-style information that aggregate efficiency metrics cannot capture.

---

## Recommended Fix

### Scraper Fix (scrape_barttorvik.py)

The fix is a column-mapping table for old vs new layout:

```python
# Old layout (2011-2018): 31 cells, separate value/rank columns
OLD_LAYOUT = {
    'efg': 11,      # eFG% offense
    'efg_d': 13,    # eFG% defense
    'to_rate': 15,  # TO% offense
    'to_rate_d': 17,# TO% defense
    'or_pct': 19,   # OR% offense
    'ft_rate': 23,  # FTR offense
}

# New layout (2019+): 24 cells, value<br/>rank combined
NEW_LAYOUT = {
    'efg': 8,
    'efg_d': 9,
    'to_rate': 10,
    'to_rate_d': 11,
    'or_pct': 12,
    'ft_rate': 14,
}
```

Detection: if `len(cells) > 28`, use OLD_LAYOUT; else use NEW_LAYOUT.

### After Re-Scraping

1. Re-run scraper with layout-aware column mapping
2. Verify all years produce values in expected ranges
3. Re-add `efg_diff`, `to_diff`, `or_diff`, `ft_rate_diff` features
4. Retrain model and compare AUC with and without four-factors
5. If four-factors improve AUC → keep; otherwise → drop on merit (not broken data)

---

## Summary

The Coder's investigation made an understandable but critical error: they mistook a scraper bug (wrong column index) for a data availability problem. The Barttorvik four-factors data for ALL years 2011-2018 exists in the Wayback Machine HTML. **7 additional years of training data are recoverable with a simple scraper fix.**

This isn't a "maybe" — I fetched and verified every single year from Wayback. The data is there. The fix is straightforward.
