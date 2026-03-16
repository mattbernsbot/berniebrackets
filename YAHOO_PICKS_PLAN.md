# Yahoo Pick Distribution — Data Assessment & Integration Plan

**Date:** 2026-03-16  
**Source:** https://tournament.fantasysports.yahoo.com/mens-basketball-bracket/pickdistribution  
**Status:** ✅ Confirmed — this is the missing piece for R2-R6 ownership data

---

## 1. Data Assessment

### What Yahoo Has

| Attribute | Value |
|-----------|-------|
| **Rounds covered** | **All 6 (R1 through Championship)** |
| **Teams per round** | 65 (all tournament teams including play-in) |
| **Data format** | JSON embedded in server-rendered HTML (`root.App.main = {...}`) |
| **Data path** | `.pickDistribution.distributionByRound[].distributionByTeam[]` |
| **Team identifier** | `editorialTeamKey` (e.g., `ncaab.t.173` → Duke) |
| **Team name mapping** | Also embedded in same JSON blob (displayName field) |
| **Precision** | 4 decimal places (e.g., 98.2117%) |
| **Requires auth?** | No — fully public, no login needed |
| **Requires Playwright?** | **No** — data is server-side rendered in HTML, `urllib` works |
| **Sample size** | Not explicitly stated in page; Yahoo Bracket Mayhem is a major contest with $25K prize |

### Data Is REAL, Not Estimated

**Critical finding:** The R2/R1 ratios vary wildly per team, proving this is actual crowd data:

| Team | R1 | R2 | R2/R1 Ratio | Interpretation |
|------|-----|-----|-------------|----------------|
| Duke | 98.2% | 93.6% | 0.953 | Clear #1 seed favorite |
| Kansas | 94.2% | 43.8% | **0.465** | Public expects R2 upset! |
| Alabama | 87.9% | 54.9% | **0.625** | Perceived tough draw |
| Connecticut | 96.1% | 77.4% | 0.805 | Slight skepticism |
| St. John's | 87.6% | 51.6% | **0.589** | Public doubts them |
| Michigan | 94.2% | 89.6% | 0.951 | Strong public confidence |

**Compare to ESPN:** ESPN R2/R1 is a flat **0.850 for every team** (hard-coded decay multiplier). Yahoo's ratios range from 0.04 to 0.95. This is game-changing — matchup-aware public sentiment, exactly what our contrarian model needs.

### Later Round Examples (R5/R6 — Final Four & Championship)

| Team | R5 (FF) | R6 (Champ) | Notes |
|------|---------|------------|-------|
| Duke | 49.5% | 30.2% | Near-majority champion pick |
| Arizona | 38.9% | 19.4% | Strong title contender |
| Michigan | 28.5% | 14.5% | Good leverage opportunity? |
| Florida | 13.7% | 6.5% | Under-owned for their talent? |
| Kansas | 2.5% | 1.6% | Ultra-contrarian if they survive R2 |

### Data Structure

```json
{
  "pickDistribution": {
    "distributionByRound": [
      {
        "roundId": "1",
        "distributionByTeam": [
          {
            "editorialTeamKey": "ncaab.t.173",
            "percentage": 98.2117,
            "rank": 1
          },
          ...
        ]
      },
      // ... rounds 2-6
    ]
  }
}
```

Team key → name mapping is also embedded in the page:
```
ncaab.t.173 → Duke
ncaab.t.17  → Arizona
ncaab.t.210 → Florida
ncaab.t.357 → Michigan
ncaab.t.287 → Kansas
... (65 total)
```

---

## 2. Comparison: Yahoo vs ESPN

| Feature | ESPN (current) | Yahoo (new) |
|---------|---------------|-------------|
| **R1 data** | ✅ Real (1.1M+ brackets) | ✅ Real |
| **R2 data** | ❌ Fake (R1 × 0.85) | ✅ **Real** |
| **R3 data** | ❌ Fake (R1 × 0.65) | ✅ **Real** |
| **R4 data** | ❌ Fake (R1 × 0.45) | ✅ **Real** |
| **R5 data** | ❌ Fake (R1 × 0.30) | ✅ **Real** |
| **R6 data** | ❌ Fake (R1 × 0.15) | ✅ **Real** |
| **Scraping** | Playwright + API intercept | Simple urllib GET |
| **Rate limit risk** | Low (API) | Very low (single page) |
| **Reliability** | Fragile (API changes yearly) | Robust (SSR HTML) |
| **Sample size** | 1.1M+ (stated) | Unknown (large contest) |
| **Team ID format** | ESPN abbrevs (DUKE, ILL) | Yahoo keys (ncaab.t.173) |

### Verdict

Yahoo solves our **#1 data gap**: real per-team, per-round public ownership. The flat decay multiplier is one of the reviewer's top complaints — this eliminates it entirely.

---

## 3. Scraping Approach

### No Playwright Needed

The data is embedded in the initial HTML response as `root.App.main = {...}`. A simple `urllib.request` GET with a standard User-Agent header returns the full 1.7MB page with all data inline.

### Proposed Scraper: `scrape_yahoo_picks()`

```python
def scrape_yahoo_picks(
    year: int = 2026,
    data_dir: str = "data",
    cache_hours: float = 4.0,
) -> dict[str, dict[int, float]] | None:
    """Scrape Yahoo Fantasy pick distribution for all 6 rounds.
    
    Returns:
        Dict mapping team_name → {round_num: pick_pct (0.0-1.0)}.
    """
    cache_file = Path(data_dir) / "yahoo_picks_cache.json"
    
    # Check cache
    if cache_file.exists():
        cached = load_json(str(cache_file))
        age = (time.time() - cached.get("timestamp", 0)) / 3600
        if age < cache_hours:
            return cached["picks"]
    
    # Fetch page
    url = "https://tournament.fantasysports.yahoo.com/mens-basketball-bracket/pickdistribution"
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
    })
    html = urllib.request.urlopen(req, timeout=30).read().decode()
    
    # Extract root.App.main JSON blob
    match = re.search(r'root\.App\.main\s*=\s*(\{.*?\});\s*\n', html, re.DOTALL)
    if not match:
        logger.error("Could not find root.App.main in Yahoo page")
        return None
    
    data_str = match.group(1).replace('\\u002F', '/')
    
    # Extract pickDistribution object (brace-matching to avoid parsing 1MB+ JSON)
    pd_start = data_str.find('"pickDistribution"')
    if pd_start < 0:
        logger.error("pickDistribution key not found in Yahoo data")
        return None
    
    brace_start = data_str.find('{', pd_start)
    depth = 0
    for i in range(brace_start, len(data_str)):
        if data_str[i] == '{': depth += 1
        elif data_str[i] == '}':
            depth -= 1
            if depth == 0:
                pd_json = data_str[brace_start:i+1]
                break
    
    pd = json.loads(pd_json)
    
    # Extract team key → displayName mapping
    team_map = {}
    for m in re.finditer(
        r'"editorialTeamKey"\s*:\s*"(ncaab\.t\.\d+)"[^}]{0,200}"displayName"\s*:\s*"([^"]+)"',
        data_str
    ):
        team_map[m.group(1)] = m.group(2)
    
    # Build picks dict
    picks = {}
    for rnd in pd['distributionByRound']:
        round_id = int(rnd['roundId'])
        for entry in rnd['distributionByTeam']:
            key = entry['editorialTeamKey']
            pct = entry['percentage'] / 100.0  # Convert to 0.0-1.0
            name = team_map.get(key, key)
            if name not in picks:
                picks[name] = {}
            picks[name][round_id] = pct
    
    # Cache
    save_json(str(cache_file), {
        "timestamp": time.time(),
        "source": "yahoo",
        "url": url,
        "teams_count": len(picks),
        "picks": picks
    })
    
    return picks
```

### Name Normalization

Yahoo uses slightly different team names than ESPN/KenPom. Need a mapping:

| Yahoo Name | ESPN/KenPom Name | Notes |
|-----------|------------------|-------|
| N. Carolina | North Carolina | Abbreviation style |
| Connecticut | UConn | Both used in code |
| Iowa St. | Iowa State | Period vs full |
| Michigan St. | Michigan State | Period vs full |
| N. Dak. St. | North Dakota State | Abbreviation |
| St. John's | St. John's | Match ✓ |
| St. Mary's | St. Mary's | Match ✓ |
| Miami (FL) | Miami FL | Parentheses |
| PV/LEH, TX/NCST, etc. | Play-in teams | Combine with winner |

A `YAHOO_NAME_MAP` constant will normalize these to canonical names already used in `real_bracket_*.json`.

---

## 4. Integration Strategy

### Recommended: Yahoo as Primary Source for R2-R6, Blend for R1

```
R1: Average ESPN + Yahoo (both are real; two sources > one)
R2-R6: Yahoo only (ESPN is synthetic/fake for these rounds)
```

**Rationale:**
- For R1, ESPN has a massive sample (1.1M+) and Yahoo adds signal. Averaging reduces noise.
- For R2-R6, ESPN data is *literally fabricated* (flat decay). Yahoo is the only real source.
- If Yahoo is unavailable (site down, off-season), fall back to ESPN + decay as before.

### Alternative: Yahoo as Sole Source

Simpler but loses ESPN's large R1 sample. Only recommended if Yahoo proves more accurate than ESPN in backtesting.

### Code Changes Required

#### `src/scout.py` — New Function

1. Add `scrape_yahoo_picks()` function (as shown above)
2. Add `YAHOO_NAME_MAP` constant for team name normalization
3. Add `build_yahoo_name_mapping()` that maps Yahoo display names → canonical names using the real bracket file + alias table

#### `src/scout.py` — Modify Main Pipeline

In the main data gathering function, call Yahoo scraper alongside ESPN:

```python
# Existing ESPN scraping
espn_picks = scrape_espn_picks_playwright(year, data_dir)

# NEW: Yahoo scraping
yahoo_picks = scrape_yahoo_picks(year, data_dir)

# Merge sources
merged_picks = merge_pick_sources(espn_picks, yahoo_picks)
```

#### `src/scout.py` — New `merge_pick_sources()` Function

```python
def merge_pick_sources(
    espn_picks: dict | None,
    yahoo_picks: dict | None,
) -> dict[str, dict[int, float]]:
    """Merge ESPN and Yahoo pick data.
    
    Strategy:
    - R1: Average both sources (weighted by confidence/sample size)
    - R2-R6: Use Yahoo if available (real data), else ESPN decay
    - Log which source is used for each round
    """
    if not yahoo_picks and not espn_picks:
        return {}
    if not yahoo_picks:
        return espn_picks  # Fallback to ESPN + decay
    if not espn_picks:
        return yahoo_picks  # Yahoo-only mode
    
    merged = {}
    all_teams = set(list(espn_picks.keys()) + list(yahoo_picks.keys()))
    
    for team in all_teams:
        espn = espn_picks.get(team, {})
        yahoo = yahoo_picks.get(team, {})
        team_picks = {}
        
        for rnd in range(1, 7):
            e_val = espn.get(rnd)
            y_val = yahoo.get(rnd)
            
            if rnd == 1 and e_val is not None and y_val is not None:
                # R1: average both real sources (ESPN weighted higher due to larger sample)
                team_picks[rnd] = 0.6 * e_val + 0.4 * y_val
            elif y_val is not None:
                # R2-R6: Yahoo is real, ESPN is fake — use Yahoo
                team_picks[rnd] = y_val
            elif e_val is not None:
                team_picks[rnd] = e_val
        
        if team_picks:
            merged[team] = team_picks
    
    return merged
```

#### `src/contrarian.py` — Minimal Changes

The `build_ownership_profiles()` function already accepts `espn_picks` as a generic dict. Rename the parameter:

```python
def build_ownership_profiles(
    teams: list[Team],
    public_picks: dict[str, dict[int, float]] | None = None  # was: espn_picks
) -> list[OwnershipProfile]:
```

The internal logic doesn't need to change — it already uses the dict values directly.

#### `src/constants.py` — New Constants

```python
YAHOO_PICKS_URL = "https://tournament.fantasysports.yahoo.com/mens-basketball-bracket/pickdistribution"

# Yahoo display name → canonical name mapping
YAHOO_NAME_MAP: dict[str, str] = {
    "N. Carolina": "North Carolina",
    "Connecticut": "UConn",
    "Iowa St.": "Iowa State",
    "Michigan St.": "Michigan State",
    "N. Dak. St.": "North Dakota State",
    "Miami (FL)": "Miami FL",
    "Miami (OH)": "Miami OH",
    "Kennesaw St.": "Kennesaw State",
    "Tennessee St.": "Tennessee State",
    "Utah St.": "Utah State",
    "California Baptist": "Cal Baptist",
    # Play-in teams (resolve after play-in games)
    "PV/LEH": None,   # Prairie View A&M vs Lehigh
    "TX/NCST": None,   # Texas vs NC State  
    "UMBC/HOW": None,  # UMBC vs Howard
    "MOH/SMU": None,   # Miami OH vs SMU
}
```

### `src/config.py` — New Config Option

```python
PICK_SOURCE: str = "merged"  # "espn", "yahoo", "merged"
ESPN_WEIGHT: float = 0.6     # Weight for ESPN in R1 averaging
YAHOO_WEIGHT: float = 0.4   # Weight for Yahoo in R1 averaging
```

---

## 5. Impact Assessment

### What This Fixes

1. **R2-R6 ownership is no longer synthetic** — Reviewer's top complaint, eliminated
2. **Matchup-aware contrarian scoring** — Kansas at 43.8% R2 ownership (Yahoo) vs 80.1% (ESPN decay) is a *completely different* leverage signal
3. **Title pick accuracy** — Duke at 30.2% championship (Yahoo) vs 14.7% (ESPN decay: 0.98 × 0.15) — the real number is 2× higher, meaning Duke title picks offer less contrarian value than we thought
4. **Better upset identification** — Teams with steep ownership drops (Kansas R1→R2: -50 pts) reveal where the public expects upsets, which is *exactly* what contrarian strategy needs

### Risk

- **Yahoo availability** — Could go down or change format year-to-year. Mitigated by fallback to ESPN + decay.
- **Sample size unknown** — Yahoo doesn't publish bracket count. Likely hundreds of thousands (Bracket Mayhem is Yahoo's premier product). But if smaller than ESPN, R1 averaging should weight ESPN more.
- **Name mapping drift** — Yahoo team names may change. The mapping dict handles this; update annually.

### Expected Grade Impact

This directly addresses the reviewer's criticism about "estimated, not real" R2-R6 data. Combined with the ESPN R1 data we already have, this gives us **real public ownership for all 6 rounds from two major platforms**. Should move the ownership/leverage score from C+ to A-.

---

## 6. Implementation Priority

| Step | Effort | Description |
|------|--------|-------------|
| 1 | 30 min | Add `scrape_yahoo_picks()` to `src/scout.py` |
| 2 | 15 min | Add `YAHOO_NAME_MAP` to `src/constants.py` |
| 3 | 20 min | Add `merge_pick_sources()` to `src/scout.py` |
| 4 | 10 min | Wire into main pipeline, rename `espn_picks` → `public_picks` |
| 5 | 15 min | Update `src/contrarian.py` parameter name |
| 6 | 30 min | Add tests: mock Yahoo HTML, verify parsing, verify merge logic |
| 7 | 10 min | Cache Yahoo data alongside ESPN in `data/` |

**Total: ~2 hours** for a complete integration that solves the biggest data quality gap.

---

## 7. Quick Validation Script

Save this to verify the data works end-to-end:

```bash
python3 -c "
import urllib.request, json, re

url = 'https://tournament.fantasysports.yahoo.com/mens-basketball-bracket/pickdistribution'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
html = urllib.request.urlopen(req, timeout=30).read().decode()

data_str = re.search(r'root\.App\.main\s*=\s*(\{.*?\});\s*\n', html, re.DOTALL).group(1)

pd_start = data_str.find('\"pickDistribution\"')
brace_start = data_str.find('{', pd_start)
depth = 0
for i in range(brace_start, len(data_str)):
    if data_str[i] == '{': depth += 1
    elif data_str[i] == '}':
        depth -= 1
        if depth == 0:
            pd = json.loads(data_str[brace_start:i+1])
            break

for rnd in pd['distributionByRound']:
    teams = len(rnd['distributionByTeam'])
    top = rnd['distributionByTeam'][0]
    print(f\"Round {rnd['roundId']}: {teams} teams, top={top['editorialTeamKey']} at {top['percentage']:.1f}%\")
print('✅ Yahoo pick distribution: ALL 6 ROUNDS confirmed')
"
```
