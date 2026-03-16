# New Features Plan: Upset Prediction Model v2

**Author:** Data science plan  
**Date:** 2025-03-15  
**Current AUC:** 0.733 (ensemble) vs 0.686 (seed-only baseline)  
**Target:** 0.76+ AUC with 12 new features (21 total)

---

## Table of Contents
1. [Feature Summary](#1-feature-summary)
2. [Scraping Plan](#2-scraping-plan)
3. [Data Storage](#3-data-storage)
4. [Feature Engineering](#4-feature-engineering)
5. [Training Plan](#5-training-plan)
6. [Evaluation Plan](#6-evaluation-plan)
7. [Implementation Order](#7-implementation-order)

---

## 1. Feature Summary

| # | Feature | Source | New Scraping? | Expected Lift |
|---|---------|--------|--------------|---------------|
| 1 | `luck_diff` | KenPom | No (extend existing scraper) | Medium-High |
| 2 | `favorite_luck` | KenPom | No | Medium |
| 3 | `tempo_mismatch` | KenPom (existing data) | No | Low-Medium |
| 4 | `slow_dog_vs_fast_fav` | KenPom (existing data) | No | Low-Medium |
| 5 | `efg_diff` | Barttorvik | Yes | High |
| 6 | `to_diff` | Barttorvik | Yes | Medium-High |
| 7 | `or_diff` | Barttorvik | Yes | Medium |
| 8 | `ft_rate_diff` | Barttorvik | Yes | Medium |
| 9 | `top25_winpct_diff` | LRMC | Yes | High |
| 10 | `dog_top25_winpct` | LRMC | Yes | High |
| 11 | `luck_x_seed_diff` | Interaction | No | Medium |
| 12 | `efg_x_round` | Interaction | No | Low-Medium |

**Total: 12 new features → 21 features total (9 existing + 12 new)**

---

## 2. Scraping Plan

### 2A. KenPom Luck (Extend Existing Scraper)

**Source:** `scrape_kenpom_real.py` already scrapes the KenPom Wayback snapshots.

**What to change:** The existing scraper reads cells `[4]`, `[5]`, `[7]`, `[9]` from the `ratings-table` and skips cell `[11]`. Add cell `[11]` to capture the Luck column.

**Verified HTML structure (consistent across 2015, 2019, 2024):**

The KenPom `ratings-table` has 21 `<td>` cells per data row in `<tbody>`:

```
[0]  = Rank (int)
[1]  = Team name (may include seed number appended, e.g., "Kentucky 1")
[2]  = Conference (e.g., "SEC")
[3]  = W-L record (e.g., "34-0")
[4]  = AdjEM (e.g., "+33.06" or ".9787" for older years)
[5]  = AdjO (e.g., "120.1")
[6]  = AdjO Rank (int, skip)
[7]  = AdjD (e.g., "87.0")
[8]  = AdjD Rank (int, skip)
[9]  = AdjT (e.g., "63.3")
[10] = AdjT Rank (int, skip)
[11] = Luck (e.g., "+.035", "+.055", "-.012")
[12] = Luck Rank (int, skip)
[13] = SOS AdjEM (skip)
[14] = SOS AdjEM Rank (skip)
[15] = SOS OppO (skip)
[16] = SOS OppO Rank (skip)
[17] = SOS OppD (skip)
[18] = SOS OppD Rank (skip)
[19] = NCSOS AdjEM (skip)
[20] = NCSOS AdjEM Rank (skip)
```

**Parsing logic for Luck (cell [11]):**
```
raw = cells[11].text.strip()       # e.g., "+.035", "-.012", "+.055"
luck = float(raw)                   # Direct float parse works (includes sign)
```

**Format notes:**
- Luck values are always signed: `+.035`, `-.012`
- Typical range: `-0.10` to `+0.10`
- Meaning: positive = won more close games than expected, negative = lost more
- The value is consistent across all verified years (2015, 2019, 2024)

**Missing year handling:** Same as existing scraper — iterate `DATE_ATTEMPTS` list for each year. If a year snapshot is truly missing (no snapshot in March), set `luck = 0.0` (neutral assumption). The existing years in the dataset (2011, 2013-2019, 2021-2025) all have KenPom snapshots confirmed.

**URL pattern (same as existing):**
```
https://web.archive.org/web/{YYYY}0315/https://kenpom.com/
```

**Modification to existing scraper (`scrape_kenpom_real.py`):**
In `parse_kenpom_table()`, after extracting `adj_t` from `cells[9]`, add:
```python
luck = float(cells[11].text.strip())
```
And include `'luck': luck` in the team dict.

---

### 2B. Barttorvik Four Factors (New Scraper)

**Source:** Wayback Machine snapshots of Barttorvik's team rankings page.

**URL pattern:**
```
https://web.archive.org/web/{YYYY}0315/https://barttorvik.com/trank.php?year={YYYY}
```

**Confirmed availability:** 2011, 2013, 2014, 2019, 2024 verified. Likely available for all years we need.

**Date fallback attempts (same as KenPom):**
```python
DATE_ATTEMPTS = ['0315', '0314', '0316', '0313', '0317', '0310', '0320', '0301']
```

**HTML structure:**

The page has 2 `<table>` elements. We want `tables[1]` (index 1). The table has:
- A `<thead>` with 2+ header rows. The last header row has column names.
- A `<tbody>` with data rows.

**CRITICAL PARSING NOTE — Barttorvik cells contain embedded ranks:**

Each data cell contains the value AND a rank in a `<span>` after a `<br/>`:
```html
<td class="7 mobileout" style="background-color:#A5D9B4">56.9<br/><span style="font-size:8px">7</span></td>
```

**Correct parsing approach:**
```python
def parse_barttorvik_value(cell):
    """Extract numeric value from a Barttorvik cell, ignoring the rank."""
    br = cell.find('br')
    if br and br.previous_sibling:
        return float(str(br.previous_sibling).strip())
    # Fallback: try the full text (for cells without ranks)
    return float(cell.text.strip())
```

If you use `.text.strip()` directly, you get `"56.97"` which concatenates `"56.9"` + `"7"` (the rank). **This is a data corruption bug waiting to happen.** Always parse before `<br/>`.

**Column layout (verified 2019 = 22 cells, 2024 = 24 cells):**

2024 layout (24 cells):
```
[0]  = Rank
[1]  = Team (includes seed + tournament result, e.g., "Connecticut   1 seed, CHAMPS")
[2]  = Conference
[3]  = Games played
[4]  = Record (W-L)
[5]  = AdjOE (adjusted offensive efficiency)
[6]  = AdjDE (adjusted defensive efficiency)
[7]  = Barthag (win probability metric)
[8]  = EFG%  ← WANT (effective field goal %, offense)
[9]  = EFGD% ← WANT (effective field goal %, defense)
[10] = TOR   ← WANT (turnover rate, offense — lower is better)
[11] = TORD  ← WANT (turnover rate forced on defense — higher is better)
[12] = ORB   ← WANT (offensive rebound %)
[13] = DRB   (defensive rebound % — skip, redundant with ORB)
[14] = FTR   ← WANT (free throw rate, offense)
[15] = FTRD  (free throw rate allowed on defense — skip for now)
[16] = 2P%
[17] = 2P%D
[18] = 3P%
[19] = 3P%D
[20] = 3PR
[21] = 3PRD
[22] = Adj T.
[23] = WAB
```

2019 layout (22 cells — no 3PR/3PRD columns):
```
[0]-[7]  = Same as 2024
[8]  = EFG%
[9]  = EFGD%
[10] = TOR
[11] = TORD
[12] = ORB
[13] = DRB
[14] = FTR
[15] = FTRD
[16] = 2P%
[17] = 2P%D
[18] = 3P%
[19] = 3P%D
[20] = Adj T.
[21] = WAB
```

**Handling the layout difference:**
The four factors we need (`EFG%`, `EFGD%`, `TOR`, `TORD`, `ORB`, `FTR`) are at the SAME indices `[8]-[14]` in both layouts. So no conditional logic needed — always read `[8]`, `[9]`, `[10]`, `[11]`, `[12]`, `[14]`.

**Team name parsing:**
Barttorvik embeds seed + tournament result in the team name cell:
- `"Connecticut   1 seed, CHAMPS"`
- `"Gonzaga 1 seed, ❌"`
- `"Alabama"`

Parsing: Strip everything after the first digit sequence that matches seed patterns, or use the `id` attribute on the `<td>` tag:
```html
<td class="teamname" id="Gonzaga">
```
**Use `cell.get('id')` as the canonical team name** — it's clean and consistent. Falls back to parsing `.text` if no `id` attribute.

**Values to extract per team:**
```python
{
    'year': YYYY,
    'team': cell_1.get('id', parse_team_name(cell_1.text)),
    'efg': parse_barttorvik_value(cells[8]),    # Offensive EFG%
    'efg_d': parse_barttorvik_value(cells[9]),  # Defensive EFG% (opponent EFG%)
    'to_rate': parse_barttorvik_value(cells[10]),  # Turnover rate (offense)
    'to_rate_d': parse_barttorvik_value(cells[11]),  # Turnover rate forced (defense)
    'or_pct': parse_barttorvik_value(cells[12]),  # Offensive rebound %
    'ft_rate': parse_barttorvik_value(cells[14]),  # Free throw rate (offense)
}
```

**Rate limiting:** 2-second delay between requests. Barttorvik snapshots are ~100-200KB each.

---

### 2C. LRMC Win% vs Top 25 (New Scraper)

**Source:** Wayback Machine snapshots + live site for current year.

**URL patterns:**
```
# Historical (Wayback):
https://web.archive.org/web/{YYYY}0315/https://www2.isye.gatech.edu/~jsokol/lrmc/

# Current year (live):
https://www2.isye.gatech.edu/~jsokol/lrmc/
```

**Confirmed availability:** 2015, 2019, 2024 via Wayback. Live site has 2025/2026 data.

**HTML structure:**

The page has 2 `<table>` elements. We want `tables[1]` (index 1).

Header structure (2 header rows + 1 empty row before data):
- Row 0: Group headers — includes `"vs.1-25"`, `"vs.26-50"`, etc.
- Row 1: Sub-headers — `"LRMC Rank"`, `"Team"`, `"Conference"`, etc.
- Row 2: Empty spacer row (0 cells)
- Rows 3+: Data rows

**Data row layout (31 cells — lots of empty spacers):**
```
[0]  = empty spacer
[1]  = LRMC Rank
[2]  = Team name (e.g., "Arizona", "Gonzaga")
[3]  = Conference (e.g., "Pacific-12", "West Coast")
[4]  = empty spacer
[5]  = Overall W-L Record, format: "22-6(21-5-2)" where parens = (regW-regL-OT)
[6]  = Avg Opp Rank
[7]  = empty spacer
[8]  = Home Avg Opp Rank
[9]  = Road Avg Opp Rank
[10] = Neutral Avg Opp Rank
[11] = empty spacer
[12] = Conference W-L
[13] = Conference Avg Opp Rank
[14] = Non-Conference W-L
[15] = Non-Conference Avg Opp Rank
[16] = vs.1-25 W-L Record ← THIS IS WHAT WE WANT
[17] = vs.1-25 Avg Opp Rank
[18] = empty spacer
[19] = vs.1-50 W-L
[20] = vs.1-50 Avg Opp Rank
[21] = vs.26-50 W-L (wait — inconsistent with header; see note)
... remaining columns are vs.51-100, vs.101-200, vs.201+ breakdowns
[30] = empty spacer
```

**Note on column order:** The header row says `"vs.1-25"`, `"vs.26-50"`, `"vs.1-50"`, `"vs.51-100"`, `"vs.101-200"`, `"vs.201+"`. But the actual mapping may differ slightly. **The reliable way to identify the vs.1-25 column:** it's always at index `[16]` in data rows. Verified for both 2019 and 2024 snapshots.

**Parsing the vs.1-25 W-L record (cell [16]):**

Format: `"W-L(regW-regL-OT)"` or `"---"` (if no games vs top 25)

Examples:
- `"4-2(4-2-0)"` → 4 wins, 2 losses
- `"2-2(2-1-1)"` → 2 wins, 2 losses
- `"---"` → no data, treat as 0 games

```python
def parse_top25_record(cell_text):
    """Parse vs.1-25 W-L record. Returns (wins, losses) or (0, 0) if missing."""
    text = cell_text.strip()
    if text == '---' or not text:
        return (0, 0)
    # Take the part before '(' → "4-2"
    wl = text.split('(')[0].strip()
    parts = wl.split('-')
    return (int(parts[0]), int(parts[1]))
```

**Team name from cell [2]:** Clean text, no embedded ranks or extras. Just `.text.strip()`.

**Values to extract per team:**
```python
{
    'year': YYYY,
    'team': cells[2].text.strip(),
    'lrmc_rank': int(cells[1].text.strip()),
    'top25_wins': wins,
    'top25_losses': losses,
    'top25_games': wins + losses,
}
```

**Missing year handling:**
- If a Wayback snapshot isn't available for a year, try adjacent dates (same `DATE_ATTEMPTS` list).
- If still missing: **set `top25_winpct = None`** and handle as missing data in feature engineering (see Section 4).
- Expected: ~3-5 years may be missing from Wayback. This is acceptable — the model degrades gracefully.

---

## 3. Data Storage

### 3A. File Layout

All new data goes in the existing `data/` directory:

```
upset_model/data/
├── kenpom_historical.json          # MODIFIED — add 'luck' field
├── barttorvik_historical.json      # NEW — Barttorvik four factors
├── lrmc_historical.json            # NEW — LRMC vs-top-25 records
├── ncaa_tournament_real.json       # UNCHANGED
└── README.md                       # UPDATE with new sources
```

### 3B. JSON Formats

**KenPom (modified `kenpom_historical.json`):**
```json
{
    "year": 2024,
    "team": "Houston",
    "rank": 1,
    "conference": "B12",
    "record": "29-3",
    "adj_em": 33.06,
    "adj_o": 120.1,
    "adj_d": 87.0,
    "adj_t": 63.3,
    "luck": 0.035
}
```

**Barttorvik (`barttorvik_historical.json`):**
```json
{
    "year": 2024,
    "team": "Connecticut",
    "efg": 56.9,
    "efg_d": 44.4,
    "to_rate": 14.5,
    "to_rate_d": 16.0,
    "or_pct": 36.7,
    "ft_rate": 31.9
}
```

**LRMC (`lrmc_historical.json`):**
```json
{
    "year": 2024,
    "team": "Arizona",
    "lrmc_rank": 1,
    "top25_wins": 2,
    "top25_losses": 2,
    "top25_games": 4
}
```

### 3C. Joining with Tournament Games

The join key is `(year, team_name)`. The existing `find_team_stats()` function in `train_ensemble.py` already handles fuzzy matching + aliases via `TEAM_ALIASES` and `normalize_team_name()`.

**New join functions needed:**
1. `load_barttorvik_data(path)` → dict mapping `(year, team_name) → stats`
2. `load_lrmc_data(path)` → dict mapping `(year, team_name) → stats`

These follow the exact same pattern as `load_kenpom_data()`. The same `TEAM_ALIASES` dict and `normalize_team_name()` are used for matching.

**New aliases to add** (Barttorvik and LRMC use slightly different team names):
```python
# Barttorvik uses the td id= attribute — usually clean, but check:
"Connecticut": "UConn",          # Barttorvik uses "Connecticut", NCAA uses "UConn"
"N.C. State": "NC State",       # Barttorvik may use different abbreviations
# LRMC uses full conference-style names
"Pacific-12": "Pac-12",         # Conference name, not team — ignore
```

**Important:** Build a team-name-matching validation step that logs unmatched teams. Run once after first scrape to identify alias gaps.

### 3D. Default Values for Missing Data

When a team has no data for a source:
- **KenPom Luck:** `luck = 0.0` (neutral — no luck signal)
- **Barttorvik:** `efg = 50.0`, `efg_d = 50.0`, `to_rate = 17.0`, `to_rate_d = 17.0`, `or_pct = 29.0`, `ft_rate = 33.0` (D-I averages, shown in Barttorvik header)
- **LRMC:** `top25_wins = 0`, `top25_losses = 0`, `top25_games = 0` → treated as insufficient sample

---

## 4. Feature Engineering

### 4A. Complete Feature List (21 features)

**Existing features (1-9) — UNCHANGED:**

| # | Name | Definition |
|---|------|------------|
| 1 | `seed_diff` | dog.seed - fav.seed |
| 2 | `round_num` | Tournament round (1-6) |
| 3 | `adj_em_diff` | dog.adj_em - fav.adj_em |
| 4 | `adj_o_diff` | dog.adj_o - fav.adj_o |
| 5 | `adj_d_diff` | dog.adj_d - fav.adj_d |
| 6 | `adj_t_diff` | dog.adj_t - fav.adj_t |
| 7 | `seed_x_adj_em` | seed_diff × adj_em_diff |
| 8 | `round_x_seed` | round_num × seed_diff |
| 9 | `round_x_adj_em` | round_num × adj_em_diff |

**New features (10-21):**

| # | Name | Definition | Rationale |
|---|------|------------|-----------|
| 10 | `luck_diff` | fav.luck - dog.luck | High = favorite is a paper tiger. Positive means favorite's wins were luckier than underdog's. Upset signal. |
| 11 | `favorite_luck` | fav.luck (standalone) | High-luck favorite is vulnerable regardless of underdog's luck. |
| 12 | `tempo_mismatch` | \|fav.adj_t - dog.adj_t\| | How different their pace preferences are. Large mismatch creates unpredictability. |
| 13 | `slow_dog_vs_fast_fav` | 1 if dog.adj_t < 65 AND fav.adj_t > 69, else 0 | Slow defensive underdogs compress variance. Binary indicator for the extreme case. |
| 14 | `efg_diff` | fav.efg - dog.efg | Shooting quality gap. Smaller = underdog can hang offensively. |
| 15 | `to_diff` | fav.to_rate - dog.to_rate | Turnover tendency gap. Positive = favorite turns it over MORE → upset risk. |
| 16 | `or_diff` | fav.or_pct - dog.or_pct | Offensive rebound differential. Negative = underdog gets more second chances. |
| 17 | `ft_rate_diff` | fav.ft_rate - dog.ft_rate | Late-game execution ability. Higher FT rate = more trips to the line. |
| 18 | `top25_winpct_diff` | fav.top25_winpct - dog.top25_winpct | How much better the favorite is vs elite teams. Small gap = dangerous underdog. |
| 19 | `dog_top25_winpct` | dog.top25_winpct (standalone) | A 12-seed that's 3-1 vs top 25 is genuinely dangerous. |
| 20 | `luck_x_seed_diff` | luck_diff × seed_diff | Interaction: lucky favorites in big seed gaps are the most paper-tiger-ish. |
| 21 | `efg_x_round` | efg_diff × round_num | Later rounds reward shooting quality — this interaction captures that. |

### 4B. Feature Computation Details

**Luck features (10-11):**
```
luck_diff = fav_stats.get('luck', 0.0) - dog_stats.get('luck', 0.0)
favorite_luck = fav_stats.get('luck', 0.0)
```

**Tempo features (12-13):**
```
tempo_mismatch = abs(fav_stats.get('adj_t', 67.0) - dog_stats.get('adj_t', 67.0))
slow_dog_vs_fast_fav = 1.0 if (dog_stats.get('adj_t', 67.0) < 65.0 and fav_stats.get('adj_t', 67.0) > 69.0) else 0.0
```

**Four Factors features (14-17):**
```
efg_diff = fav_bt.get('efg', 50.0) - dog_bt.get('efg', 50.0)
to_diff = fav_bt.get('to_rate', 17.0) - dog_bt.get('to_rate', 17.0)
or_diff = fav_bt.get('or_pct', 29.0) - dog_bt.get('or_pct', 29.0)
ft_rate_diff = fav_bt.get('ft_rate', 33.0) - dog_bt.get('ft_rate', 33.0)
```

**LRMC features (18-19):**
```python
def compute_top25_winpct(stats):
    """Matt's rule: if fewer than 4 games vs top 25, assume 0.0 (small sample = bad)."""
    games = stats.get('top25_games', 0)
    if games < 4:
        return 0.0
    wins = stats.get('top25_wins', 0)
    return wins / games

top25_winpct_diff = compute_top25_winpct(fav_lrmc) - compute_top25_winpct(dog_lrmc)
dog_top25_winpct = compute_top25_winpct(dog_lrmc)
```

**Interaction features (20-21):**
```
luck_x_seed_diff = luck_diff * seed_diff
efg_x_round = efg_diff * float(round_num)
```

### 4C. Modifications to `features.py`

The `extract_features()` function signature changes from:
```python
def extract_features(team_a: dict, team_b: dict, round_num: int) -> List[float]:
```
to:
```python
def extract_features(team_a: dict, team_b: dict, round_num: int,
                     team_a_bt: dict = None, team_b_bt: dict = None,
                     team_a_lrmc: dict = None, team_b_lrmc: dict = None) -> List[float]:
```

Where `team_a_bt` / `team_b_bt` are Barttorvik stats dicts, and `team_a_lrmc` / `team_b_lrmc` are LRMC stats dicts. All optional with `None` defaulting to D-I averages / no data.

The `FEATURE_NAMES` list extends to 21 entries.

**Backward compatibility:** When called with only the original 3 args (as in `predict.py` and `predict_from_teams()`), the new features get default/neutral values. The model still works, just without the extra signal. This is important for the public API.

---

## 5. Training Plan

### 5A. Data Pipeline Update

Modify `build_training_data()` in `train_ensemble.py`:

1. Load KenPom data (with new `luck` field) — existing loader, just has new field
2. Load Barttorvik data — new `load_barttorvik_data()` function
3. Load LRMC data — new `load_lrmc_data()` function
4. For each game:
   - Find KenPom stats (existing — now includes `luck`)
   - Find Barttorvik stats (new — by `(year, team_name)`)
   - Find LRMC stats (new — by `(year, team_name)`)
   - Call updated `extract_features()` with all 5 args
5. Return feature matrix with 21 columns

### 5B. Stepwise Feature Addition Strategy

Do NOT add all 12 features at once. Use stepwise inclusion to eliminate noise:

**Step 1: Luck features only (features 10-11)**
- Train on 11 features (9 existing + 2 luck)
- Evaluate via LOOCV (see Section 6)
- These require NO new scraping, just extending the existing scraper
- Expected: AUC improvement of +0.005-0.010

**Step 2: Add Tempo features (features 12-13)**
- Train on 13 features (11 + 2 tempo)
- These require NO scraping at all — derived from existing AdjT
- Expected: AUC improvement of +0.002-0.005

**Step 3: Add Barttorvik Four Factors (features 14-17)**
- Train on 17 features (13 + 4 factors)
- Requires Barttorvik scraping completion
- Expected: AUC improvement of +0.008-0.015

**Step 4: Add LRMC features (features 18-19)**
- Train on 19 features (17 + 2 LRMC)
- Requires LRMC scraping completion
- Expected: AUC improvement of +0.005-0.012

**Step 5: Add Interaction features (features 20-21)**
- Train on 21 features (19 + 2 interactions)
- Expected: AUC improvement of +0.002-0.005

**After each step:** Run full evaluation. If AUC decreases or stays flat, the newly added features are noise — drop them. Only keep features that show positive lift in LOOCV.

### 5C. Hyperparameter Adjustments

With more features, adjust RF hyperparameters:
- **`max_features`**: Currently defaults to `sqrt(9) ≈ 3`. With 21 features, `sqrt(21) ≈ 5`. This is automatic.
- **`n_trees`**: Increase from 300 to 500. More features = more trees needed for stability.
- **`max_depth`**: Keep at 8. May reduce to 6 if overfitting is observed.
- **`min_samples_split`**: Keep at 10 or increase to 15 with more features.
- **LR L2 penalty**: May increase from 0.01 to 0.05 to handle more correlated features.

---

## 6. Evaluation Plan

### 6A. Leave-One-Year-Out Cross-Validation (LOYO-CV)

This is the primary evaluation method. For each year Y in the dataset:
1. Train on all years EXCEPT Y
2. Predict on year Y
3. Collect predictions

After all folds, compute metrics on the full set of held-out predictions.

**Years in dataset:** 2011, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025 (13 folds)

**Note:** 2020 is missing (COVID). 2012 is missing from KenPom data.

### 6B. Metrics to Compare

For each model variant (old 9-feature vs new 21-feature), compute:

| Metric | What it measures | Target |
|--------|-----------------|--------|
| **AUC** | Discrimination ability | ≥ 0.76 |
| **Brier Score** | Calibration + discrimination | Lower is better |
| **Log Loss** | Probability quality | Lower is better |
| **Calibration by round** | Per-round predicted vs actual upset rate | Within ±3% |
| **Calibration by seed matchup** | e.g., 5v12 predicted vs actual | Within ±5% |

### 6C. Comparison Table

After training, produce a table like:

```
Model                  | AUC   | Brier | LogLoss | Notes
-----------------------|-------|-------|---------|------
Seed-only baseline     | 0.686 | ?.??? | ?.???   | 
9-feature ensemble     | 0.733 | ?.??? | ?.???   | Current model
11-feature (+luck)     | ?.??? | ?.??? | ?.???   |
13-feature (+tempo)    | ?.??? | ?.??? | ?.???   |
17-feature (+4factors) | ?.??? | ?.??? | ?.???   |
19-feature (+LRMC)     | ?.??? | ?.??? | ?.???   |
21-feature (full)      | ?.??? | ?.??? | ?.???   |
```

### 6D. Overfitting Check

With 799 games and 21 features, overfitting is a real risk.

- **In-sample AUC vs LOYO-CV AUC gap:** Should be < 0.05. If gap > 0.05, model is overfit.
- **Feature importance:** After training, rank features by RF importance. If any new feature has near-zero importance, consider dropping it.
- **Regularization:** If overfitting, increase LR L2 penalty and reduce RF max_depth.

---

## 7. Implementation Order

### Priority ordering based on effort vs. expected lift:

**Phase 1: No-scraping features (do first — highest ROI)**

| Priority | Task | Effort | Expected Lift |
|----------|------|--------|---------------|
| 1a | Add Luck column to KenPom scraper | 15 min | Medium-High |
| 1b | Re-scrape KenPom to get Luck for all years | 5 min (run existing scraper) | — |
| 1c | Add Tempo features (pure feature engineering) | 10 min | Low-Medium |
| 1d | Train + evaluate 13-feature model | 5 min | Validate lift |

**Phase 2: Barttorvik scraper (highest expected lift from new data)**

| Priority | Task | Effort | Expected Lift |
|----------|------|--------|---------------|
| 2a | Write Barttorvik scraper | 45 min | — |
| 2b | Run scraper for all years | 10 min | — |
| 2c | Build team name matching + validate join coverage | 20 min | — |
| 2d | Add 4 four-factor features to `features.py` | 15 min | High |
| 2e | Train + evaluate 17-feature model | 5 min | Validate lift |

**Phase 3: LRMC scraper (high lift but most uncertainty)**

| Priority | Task | Effort | Expected Lift |
|----------|------|--------|---------------|
| 3a | Write LRMC scraper (Wayback + live) | 45 min | — |
| 3b | Run scraper — expect some missing years | 10 min | — |
| 3c | Handle missing years gracefully | 15 min | — |
| 3d | Add 2 LRMC features | 10 min | High |
| 3e | Train + evaluate 19-feature model | 5 min | Validate lift |

**Phase 4: Interactions + finalize**

| Priority | Task | Effort | Expected Lift |
|----------|------|--------|---------------|
| 4a | Add interaction features (20-21) | 5 min | Low-Medium |
| 4b | Final evaluation — full 21-feature model | 10 min | — |
| 4c | Run feature importance, drop underperformers | 15 min | — |
| 4d | Update `predict.py` API to accept new stats | 20 min | — |
| 4e | Update README and model docs | 10 min | — |

**Total estimated effort: ~4-5 hours**

### Why this order?

1. **Phase 1 is free lunch** — no new scraping, features 10-13 use data we already have or can trivially add. Ship a quick win.
2. **Barttorvik before LRMC** — Four Factors have the most theoretical basis for predicting upsets (Dean Oliver's work), and Barttorvik has better Wayback coverage. Four features × all years = lots of signal.
3. **LRMC last** — highest uncertainty (Wayback gaps), but the "battle-tested vs elite teams" signal is uniquely valuable. Worth the effort even if we only get 8-10 years of data.
4. **Interactions last** — they're cheap but depend on the base features being solid first.

---

## Appendix A: Team Name Matching Strategy

The biggest integration risk is team name mismatches across sources. Each source uses slightly different naming:

| Team | NCAA | KenPom | Barttorvik | LRMC |
|------|------|--------|------------|------|
| UConn | UConn | Connecticut | Connecticut | Connecticut |
| LSU | LSU | Louisiana St. | LSU | Louisiana St. |
| USC | USC | USC | USC | Southern Cal |
| Saint Mary's | Saint Mary's (CA) | St. Mary's CA | Saint Mary's | Saint Mary's |

**Strategy:**
1. Each scraper normalizes team names to a canonical form on save
2. Expand `TEAM_ALIASES` in `train_ensemble.py` with Barttorvik and LRMC variants
3. After first scrape, run a validation pass that cross-references all tournament teams against each data source and logs unmatched teams
4. Fix aliases iteratively until 100% match rate for tournament teams

## Appendix B: Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| Wayback Machine snapshots missing for some years | Reduced training data for those features | Graceful defaults; model still uses other features |
| Barttorvik HTML structure changed between years | Parse errors for some years | Version-detect: check cell count (22 vs 24) and adjust indices |
| LRMC site goes offline | Can't get current year data | Cache aggressively; live site is only needed for current year |
| Overfitting with 21 features on 799 games | Worse LOYO-CV than 9-feature model | Stepwise addition; only keep features that improve LOYO-CV |
| Team name matching failures | Missing features for some matchups | Validate join coverage; expand aliases; fuzzy match fallback |
| KenPom AdjEM scale change (2011-2015 vs 2019+) | Luck column format might also differ | Verified: Luck column format is consistent (`+.xxx`) across all years |
