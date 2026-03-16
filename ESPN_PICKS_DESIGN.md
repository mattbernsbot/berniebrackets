# ESPN Pick Data Extraction — Design Document

## Overview

Replace the seed-based ownership estimation in the bracket optimizer with real ESPN "People's Bracket" pick percentages scraped via Playwright. The scraper integrates into the existing Scout pipeline (`src/scout.py`) so that running `python3 main.py full` automatically collects live pick data alongside KenPom stats and bracket structure.

## 1. Data Source

ESPN's Tournament Challenge bracket game exposes a Gambit API:

```
GET gambit-api.fantasy.espn.com/apis/v1/challenges/tournament-challenge-bracket-{year}/
```

This returns the full challenge metadata including a `propositions` array. Each proposition represents a round's matchup structure, and each team appears as a `possibleOutcome` with `choiceCounters[].percentage` — the fraction of all submitted brackets that pick this team to advance through a given round.

### What We Capture

From the **full challenge endpoint** (already cached as `espn_challenge_2026.json`):

| Field | Path | Example |
|-------|------|---------|
| Team short name | `possibleOutcomes[].name` | `"Ohio State"` |
| Team abbreviation | `possibleOutcomes[].abbrev` | `"OSU"` |
| Full description | `possibleOutcomes[].description` | `"Ohio State Buckeyes"` |
| Seed | `possibleOutcomes[].mappings[type=SEED].value` | `"8"` |
| Region ID | `possibleOutcomes[].regionId` | `1` |
| Region seed | `possibleOutcomes[].regionSeed` | `8` |
| Pick % (per round) | `possibleOutcomes[].choiceCounters[].percentage` | `0.0038` |
| Pick count | `possibleOutcomes[].choiceCounters[].count` | `4255` |
| Scoring period | `proposition.scoringPeriodId` | `1` (R64) |

**Critical insight:** The API returns two different views of the data:

1. **Round-specific propositions** (32 for R1): `scoringPeriodId=1`, each with 2 outcomes (the matchup). These give R1 pick %. From `espn_challenge_2026.json`, `propositions[].scoringPeriodId=1`.

2. **Championship proposition** (`displayOrder=0`, `name="Round 6, Matchup 1"`): Contains ALL 64 teams with their **title pick %**. This single proposition has 64 `possibleOutcomes`, each with the percentage of brackets picking that team to win it all.

Both views come from the same API response. The R1 propositions give us granular head-to-head pick rates; the championship proposition gives us deep-round ownership in a single read.

### Scoring Periods Map to Rounds

| `scoringPeriodId` | Round | Label |
|----|-------|-------|
| 1 | R64 | Round of 64 |
| 2 | R32 | Round of 32 |
| 3 | S16 | Sweet 16 |
| 4 | E8 | Elite 8 |
| 5 | FF | Final Four |
| 6 | NC | National Championship |

Pre-tournament, only `scoringPeriodId=1` and the championship proposition (displayOrder=0) have meaningful data. Later-round propositions will populate as the tournament progresses.

---

## 2. Integration Point: `src/scout.py`

### New Function: `scrape_espn_picks_playwright()`

Lives inside `src/scout.py`. Called during `collect_all()` after KenPom and bracket collection.

```
collect_all(config)
├── scrape_kenpom()           # existing
├── scrape_espn_bracket()     # existing (or load_real_bracket fallback)
├── merge_team_data()         # existing
├── scrape_espn_picks_playwright()  # NEW
│   ├── Check cache freshness
│   ├── If stale: launch Playwright, intercept API response
│   ├── Save timestamped snapshot
│   ├── Save canonical data/espn_picks.json
│   └── Return parsed pick data
└── save all data files
```

### Function Signature

```python
def scrape_espn_picks_playwright(
    year: int,
    data_dir: str,
    cache_max_age_hours: float = 2.0,
    force_refresh: bool = False
) -> dict[str, dict[int, float]] | None:
    """Scrape ESPN pick percentages via Playwright API interception.
    
    Returns:
        Dict mapping team_name → {round_num: pick_pct} where pick_pct is 0.0–1.0.
        Returns None if ESPN data is unavailable (pre-Selection Sunday).
    """
```

### Cache-First Strategy

Every pipeline run doesn't need a fresh Playwright scrape. Pick percentages shift slowly (over hours, not minutes). The function:

1. **Check for `data/espn_picks.json`** — if it exists and `metadata.scraped_at` is within `cache_max_age_hours`, return the cached data immediately. No browser launch.
2. **If stale or missing** — launch Playwright, intercept the API, parse, save, and return.
3. **`--force-refresh` CLI flag** — bypasses cache check (add to `collect` and `full` subparsers).

This avoids Playwright overhead on repeated runs (analysis tweaks, debugging) while ensuring fresh data when it matters.

### Playwright Interception Strategy

```
1. Launch headless Chromium
2. Register response handler on page
3. Navigate to: fantasy.espn.com/tournament-challenge-bracket/{year}/en/whopickedwhom
4. In response handler, match URL containing the challenge API path
5. Capture the JSON response body
6. Wait up to 15 seconds for the response; timeout = data not available
7. Close browser
```

**URL pattern to intercept:**
```
*gambit-api.fantasy.espn.com/apis/v1/challenges/tournament-challenge-bracket-{year}*
```

The existing `scripts/scrape_espn_picks.py` proves this works. The page makes the API call on load; we just capture it.

### What Changes in `collect_all()`

The existing `scrape_espn_picks()` function (HTTP-based, returns None) gets replaced by `scrape_espn_picks_playwright()`. The return value feeds directly into `build_ownership_profiles()` via the `espn_picks` parameter that already exists in `contrarian.py`.

```python
def collect_all(config) -> tuple[list[Team], BracketStructure, dict | None]:
    # ... existing KenPom + bracket collection ...
    
    # NEW: Scrape ESPN picks via Playwright
    espn_picks = scrape_espn_picks_playwright(
        year=config.year,           # new config field
        data_dir=config.data_dir,
        cache_max_age_hours=2.0,
        force_refresh=getattr(config, 'force_espn_refresh', False)
    )
    
    # Save picks if we got them
    if espn_picks:
        save_json(espn_picks, f"{config.data_dir}/public_picks.json")
    
    return merged_teams, bracket, espn_picks
```

**Signature change:** `collect_all` returns a 3-tuple now, adding `espn_picks`. Update `cmd_collect()` and `cmd_full()` in `main.py` to unpack it.

### Downstream: `cmd_analyze()` Loads Pick Data

Currently `analyze_ownership()` tries to load `data/public_picks.json` and falls back to seed-based estimates. With the new flow:

- `collect` stage writes `data/public_picks.json` from real ESPN data.
- `analyze` stage's `analyze_ownership()` loads it — **no code change needed in contrarian.py** for basic loading.

The only change: the data format written by the new scraper must match what `build_ownership_profiles()` expects as its `espn_picks` parameter: `dict[str, dict[int, float]]` — team name → round → pick percentage.

---

## 3. Data Format

### Timestamped Snapshots

Every successful scrape saves a timestamped snapshot for tracking drift:

```
data/espn_picks_snapshots/
├── espn_picks_2026-03-16T004100Z.json
├── espn_picks_2026-03-17T120000Z.json
└── espn_picks_2026-03-18T180000Z.json
```

Snapshot format (preserves full fidelity from the API):

```json
{
  "metadata": {
    "year": 2026,
    "scraped_at": "2026-03-16T00:41:00Z",
    "total_brackets": 1153679,
    "source_url": "https://fantasy.espn.com/tournament-challenge-bracket/2026/en/whopickedwhom",
    "scoring_periods_available": [1, 6]
  },
  "teams": {
    "Duke": {
      "abbrev": "DUKE",
      "espn_name": "Duke",
      "description": "Duke Blue Devils",
      "seed": 1,
      "region_id": 1,
      "region_seed": 1,
      "picks_by_round": {
        "1": {"pct": 0.9800, "count": 1130735},
        "6": {"pct": 0.2716, "count": 302538}
      }
    }
  }
}
```

### Canonical `data/espn_picks.json`

The file the pipeline actually reads. Always the latest scrape, overwritten in-place:

```json
{
  "metadata": {
    "year": 2026,
    "scraped_at": "2026-03-16T00:41:00Z",
    "total_brackets": 1153679
  },
  "picks": {
    "Duke": {
      "1": 0.9800,
      "6": 0.2716
    },
    "Illinois": {
      "1": 0.9228,
      "6": 0.0105
    }
  }
}
```

### `data/public_picks.json` (Pipeline Interface)

This is what `contrarian.py`'s `build_ownership_profiles()` reads. Format matches the existing `espn_picks` parameter type: `dict[str, dict[int, float]]`:

```json
{
  "Duke": {"1": 0.98, "2": 0.65, "3": 0.45, "4": 0.35, "5": 0.30, "6": 0.27},
  "Illinois": {"1": 0.92, "2": 0.60, "3": 0.30, "4": 0.15, "5": 0.05, "6": 0.01}
}
```

**Note on int keys:** JSON serializes dict keys as strings. The existing `OwnershipProfile.from_dict()` already handles `int(k)` conversion. The scraper should write string keys; the loader converts.

---

## 4. Name Matching

This is the hardest part. Three naming systems must reconcile:

| System | Example | Source |
|--------|---------|--------|
| **Real bracket** (`real_bracket_2026.json`) | `"St. John's"`, `"Miami (FL)"`, `"Iowa St."` | ncaa.com scrape |
| **ESPN API** | `"St John's"` (name), `"SJU"` (abbrev), `"St. John's Red Storm"` (description) | gambit API |
| **KenPom** | `"St. John's"`, `"Miami FL"` | kenpom.com scrape |

The optimizer's canonical team names come from `load_real_bracket.py` → `data/teams.json`. These are what `OwnershipProfile.team` uses. ESPN names must map **to these**.

### Mapping Strategy: ESPN Abbreviation → Canonical Name

Build the mapping at scrape time, not lookup time. The ESPN API gives us three identification fields per team:

- `abbrev` (e.g., `"SJU"`)
- `name` (e.g., `"St John's"`)
- `description` (e.g., `"St. John's Red Storm"`)
- `regionId` + `regionSeed` (unique identifier: region 1, seed 5)

The mapping function:

```python
def build_espn_to_canonical_map(
    espn_outcomes: list[dict],
    canonical_teams: list[Team]
) -> dict[str, str]:
    """Map ESPN team identifiers to canonical team names from our bracket.
    
    Strategy (in priority order):
    1. Exact match on (region, seed) — most reliable, zero ambiguity
    2. Fuzzy name match on ESPN description → canonical name
    3. Abbreviation lookup table (hardcoded fallback)
    
    Returns: dict mapping ESPN abbrev → canonical team name
    """
```

**Why (region, seed) is the primary key:** Both our bracket and ESPN's API encode `regionId` + `regionSeed` per team. A 3-seed in region 2 is the same team in both systems. This completely sidesteps name normalization for all non-play-in teams. This is deterministic and requires no fuzzy matching.

Region ID mapping (must verify per year, but historically stable):
```
regionId 1 → "East" (or whatever ESPN calls it)
regionId 2 → "South"
regionId 3 → "West"
regionId 4 → "Midwest"
```

**Verify at scrape time** by cross-referencing a few known teams (e.g., the 1-seeds). If ESPN's region naming changes, log a warning and fall through to name matching.

**Play-in teams** (e.g., `"M-OH/SMU"`, `"PV/LEH"`, `"UMBC/HOW"`, `"TEX/NCSU"`) are the tricky case. Before play-in games are decided, ESPN shows combined abbreviations. These need special handling:

1. If the play-in game hasn't been played: the pick % applies to the play-in winner slot, not a specific team. Store it under a synthetic key like `"play_in_MIDWEST_11"` and distribute equally to both play-in teams, or use the combined pick % as-is for the slot.
2. After play-in games: ESPN updates to the actual winner. Standard mapping applies.

### Fallback: Hardcoded Abbreviation Table

For edge cases where region+seed matching fails, maintain a static table in `constants.py`:

```python
ESPN_ABBREV_TO_NAME: dict[str, str] = {
    "DUKE": "Duke",
    "CONN": "UConn",
    "SJU": "St. John's",
    "SMC": "Saint Mary's",
    "TA&M": "Texas A&M",
    "ISU": "Iowa St.",
    "MSU": "Michigan St.",
    "WRST": "Wright St.",
    "NDSU": "North Dakota St.",
    "KENN": "Kennesaw St.",
    "TNST": "Tennessee St.",
    # ... all 64+ teams
}
```

This table must be regenerated each year (or at least verified). The scraper should **auto-generate** it on first successful scrape and write it to `data/espn_name_map_2026.json` for manual review.

### Verification

After building the map, assert:
- Every canonical team in `data/teams.json` (non-play-in) has exactly one ESPN match.
- No two canonical teams map to the same ESPN entry.
- All 64 ESPN outcomes (from the championship proposition) are accounted for.

Log unmatched teams as errors, not warnings — this is a data integrity issue.

---

## 5. Multi-Round Handling

### Pre-Tournament (Current State)

Two data sources from the API:

1. **R1 propositions** (`scoringPeriodId=1`): 32 matchups, each with 2 outcomes. Gives R1 pick % for all 64 teams. Example: Illinois 92.28% vs Penn 7.72%.

2. **Championship proposition** (`displayOrder=0`): All 64 teams with title pick %. Example: Duke 27.16%, Arizona 18.40%, Florida 7.43%.

**For rounds 2–5, we don't have direct ESPN data pre-tournament.** We need to interpolate.

### Interpolation Strategy for R2–R5

Given:
- `p_r1` = R1 win probability (from ESPN picks, e.g., 0.92 for Illinois)
- `p_title` = Title probability (from championship proposition, e.g., 0.0105 for Illinois)
- `seed` = Team's seed

Estimate intermediate rounds using geometric interpolation between R1 and title:

```
p_round(r) = p_r1 * (p_title / p_r1) ^ ((r - 1) / 5)
```

This creates a smooth decay curve from R1 pick % to title pick %, which is what the public ownership profile actually looks like. Example for Illinois (seed 3, R1=0.92, title=0.0105):

| Round | Geometric Interp | Seed-Based Fallback |
|-------|-------------------|---------------------|
| R1 | 0.920 | 0.850 |
| R2 | 0.539 | 0.630 |
| S16 | 0.316 | 0.390 |
| E8 | 0.185 | 0.190 |
| FF | 0.108 | 0.070 |
| Title | 0.0105 | 0.040 |

The interpolation is imperfect but far better than seed-based curves because it uses two real data points that bracket the curve. The R1 data captures team-specific sentiment (Iowa 56.7% despite being a 9-seed; Akron 21.1% despite being a 12-seed), and the title data captures deep-run expectations.

**Alternative considered:** Use seed-based curves for R2–R5 but anchor them to R1 actual data. Rejected because the title pick % is also available and is highly team-specific — Duke 27% vs Arizona 18% vs Michigan 14% despite all being 1-seeds.

### During Tournament (Progressive Updates)

As rounds complete, ESPN populates new `scoringPeriodId` propositions:

1. After R1 finishes: `scoringPeriodId=2` appears with R2 matchup pick percentages.
2. After R2: `scoringPeriodId=3` (Sweet 16), etc.

The scraper should:
- Check which `scoringPeriodId` values have data.
- For rounds with real data, use it directly.
- For future rounds, continue interpolating from the latest known round + title data.
- Store `metadata.scoring_periods_available` to track what's real vs interpolated.

In `public_picks.json`, tag interpolated values:

```json
{
  "Duke": {
    "1": 0.98,
    "2": 0.65,
    "3": {"value": 0.45, "interpolated": true},
    "4": {"value": 0.35, "interpolated": true},
    "5": {"value": 0.30, "interpolated": true},
    "6": 0.27
  }
}
```

Or simpler: just use flat floats everywhere and note in metadata which rounds are real. The optimizer doesn't need to distinguish — it just needs the best estimate.

**Recommended:** Flat floats. Simpler consumer code. Metadata tracks provenance.

---

## 6. Integration with `build_ownership_profiles()`

### Current Flow (Seed-Based)

```python
# contrarian.py
def build_ownership_profiles(teams, espn_picks=None):
    if espn_picks and team.name in espn_picks:
        round_ownership = espn_picks[team.name]   # use real data
    else:
        round_ownership = {r: estimate_seed_ownership(seed, r) for r in range(1,7)}  # fallback
```

This already works. The `espn_picks` parameter expects `dict[str, dict[int, float]]`. The scraper must produce exactly this.

### What Changes

1. **`collect_all()` return value** adds `espn_picks` (3-tuple).
2. **`cmd_collect()` and `cmd_full()`** pass `espn_picks` through to `analyze_ownership()` or save to `data/public_picks.json` for `cmd_analyze()` to load.
3. **`analyze_ownership()`** already loads `public_picks.json` — no change needed there.
4. **`build_ownership_profiles()`** — minor change: currently checks `team.name in espn_picks`. The name must match exactly. The name mapping (§4) ensures this.

### The EMV Connection

The whole point: with real pick % instead of seed estimates, `UpsetCandidate.fav_ownership` and `dog_ownership` are real numbers. This means:

```python
# Before: fav_ownership estimated from SEED_OWNERSHIP_CURVES → generic, same for all 4-seeds
# After:  fav_ownership from ESPN → specific: Alabama 92.4%, Arkansas 92.5%, Kansas 93.9%, Nebraska 86.9%

# Nebraska at 86.9% vs Kansas at 93.9% — picking against Nebraska is less contrarian
# than picking against Kansas, even though both are 4-seeds.
```

EMV calculation (`emv = upset_prob * scoring_value / fav_ownership`) becomes team-specific rather than seed-generic.

---

## 7. Error Handling

### Playwright Failures

| Failure Mode | Detection | Recovery |
|-------------|-----------|----------|
| Chromium won't launch | `playwright.sync_api.Error` on `launch()` | Log error, return None → seed-based fallback |
| Page timeout (ESPN down) | `TimeoutError` on `goto()` | Retry once after 5s, then return None |
| API response not intercepted | `captured` dict empty after 15s wait | Return None → seed-based fallback |
| API response schema change | Key lookup fails during parsing | Log specific missing keys, return None |
| Partial data (e.g., only 30 of 32 R1 matchups) | Count outcomes < expected | Log warning, use what we have, fill gaps with seed-based |

**Principle:** Never crash the pipeline because ESPN changed something. Always fall back gracefully to seed-based estimates (which are decent approximations). The optimizer works either way — real data just makes it better.

### Data Validation

After parsing, validate:

```python
def validate_espn_picks(picks: dict, expected_team_count: int = 64) -> list[str]:
    """Return list of warning messages. Empty = all good."""
    warnings = []
    
    teams_found = len(picks)
    if teams_found < expected_team_count * 0.9:
        warnings.append(f"Only found {teams_found} teams, expected ~{expected_team_count}")
    
    for team, rounds in picks.items():
        r1_pct = rounds.get(1, 0)
        if r1_pct <= 0 or r1_pct >= 1.0:
            warnings.append(f"{team}: R1 pick % = {r1_pct} (suspicious)")
    
    # Check that matchup pairs sum to ~1.0
    # (requires matchup pairing info from propositions)
    
    return warnings
```

### ESPN API Versioning

The API URL contains the year: `tournament-challenge-bracket-{year}`. If ESPN changes the URL pattern or response schema:

1. The scraper logs the actual URL that was intercepted (or that failed).
2. Snapshot files preserve the raw API response for forensic analysis.
3. A `data/espn_api_schema_version.txt` could track the last known working schema, but this is probably overkill — just fix it when it breaks.

---

## 8. Config & CLI Changes

### New Config Fields

In `src/models.py` `Config` dataclass:

```python
year: int = 2026                          # tournament year
espn_cache_max_age_hours: float = 2.0     # how old is too old for cached pick data
force_espn_refresh: bool = False          # bypass cache
```

### New CLI Flags

In `main.py`, for `collect` and `full` subparsers:

```python
subparser.add_argument('--year', type=int, default=2026, help='Tournament year')
subparser.add_argument('--force-espn-refresh', action='store_true',
                       help='Force fresh ESPN pick scrape (ignore cache)')
subparser.add_argument('--no-espn', action='store_true',
                       help='Skip ESPN pick scraping entirely (use seed-based)')
```

`--no-espn` is useful for offline development and testing.

---

## 9. Testing

### Verify Completeness

```python
def test_all_bracket_teams_have_picks():
    """Every team in real_bracket_2026.json must appear in espn_picks."""
    bracket_teams = load_bracket_team_names()  # 64 non-play-in teams
    pick_teams = set(load_espn_picks().keys())
    
    missing = bracket_teams - pick_teams
    assert not missing, f"Teams missing from ESPN picks: {missing}"
```

### Verify Reasonableness

```python
def test_pick_percentages_are_sane():
    """Basic sanity: 1-seeds should have high R1 %, 16-seeds low."""
    picks = load_espn_picks()
    
    for team in get_one_seeds():
        assert picks[team][1] > 0.90, f"1-seed {team} has suspiciously low R1 pick %"
    
    for team in get_sixteen_seeds():
        assert picks[team][1] < 0.15, f"16-seed {team} has suspiciously high R1 pick %"
```

### Verify Matchup Pairs Sum to 1.0

```python
def test_matchup_pairs_sum_to_one():
    """R1 matchup opponents' pick percentages should sum to ~1.0."""
    for matchup in get_r1_matchups():
        team_a_pct = picks[matchup.team_a][1]
        team_b_pct = picks[matchup.team_b][1]
        assert abs(team_a_pct + team_b_pct - 1.0) < 0.01
```

### Verify Name Mapping

```python
def test_name_mapping_is_bijective():
    """Every ESPN team maps to exactly one canonical team, and vice versa."""
    espn_to_canonical = build_espn_to_canonical_map(...)
    
    assert len(set(espn_to_canonical.values())) == len(espn_to_canonical), "Duplicate mappings"
    assert len(espn_to_canonical) >= 64, f"Only {len(espn_to_canonical)} mappings"
```

### Integration Test: Full Pipeline

```bash
# Run collect only, verify ESPN picks were loaded
python3 main.py collect --verbose 2>&1 | grep -i "espn picks"
# Should see: "Scraped ESPN picks for 64 teams" or "Loaded cached ESPN picks"

# Check the output
python3 -c "
import json
with open('data/public_picks.json') as f:
    data = json.load(f)
print(f'Teams: {len(data)}')
print(f'Duke R1: {data.get(\"Duke\", {}).get(\"1\", \"MISSING\")}')
"
```

---

## 10. Cron / Scheduled Scraping

### Pattern: OpenClaw Heartbeat + Cron Hybrid

For the pre-tournament window (Selection Sunday through Thursday deadline):

1. **Cron job** (via OpenClaw): Scrape every 6 hours from Monday through Wednesday.
   ```
   # scrape at 06:00, 12:00, 18:00, 00:00 UTC (Mon–Wed of tournament week)
   openclaw cron add --schedule "0 */6 * * 1-3" --command "cd /path/to/bracket-optimizer && python3 -c 'from src.scout import scrape_espn_picks_playwright; scrape_espn_picks_playwright(2026, \"data\", force_refresh=True)'"
   ```

2. **On-demand** via pipeline: `python3 main.py full --force-espn-refresh` at any time.

3. **Heartbeat check**: During heartbeats, compare latest snapshot timestamp to now. If >8 hours old and it's tournament week, trigger a refresh.

### Snapshot Diff for Monitoring

A utility (not in the main pipeline, but useful for analysis):

```bash
python3 -m scripts.compare_espn_snapshots \
    data/espn_picks_snapshots/espn_picks_2026-03-16*.json \
    data/espn_picks_snapshots/espn_picks_2026-03-18*.json
```

Output: teams whose pick % shifted >2 percentage points, sorted by magnitude. Useful for spotting late-breaking injury news or bracket-busting public shifts.

---

## 11. File Layout Summary

```
bracket-optimizer/
├── src/
│   ├── scout.py                    # MODIFIED: add scrape_espn_picks_playwright()
│   ├── contrarian.py               # UNCHANGED (already accepts espn_picks param)
│   ├── models.py                   # MODIFIED: add year, cache fields to Config
│   └── constants.py                # MODIFIED: add ESPN_ABBREV_TO_NAME fallback table
├── main.py                         # MODIFIED: new CLI flags, pass espn_picks through
├── data/
│   ├── espn_picks.json             # Canonical latest picks (scraper output)
│   ├── public_picks.json           # Pipeline-format picks (what contrarian.py reads)
│   ├── espn_picks_snapshots/       # Timestamped history
│   │   └── espn_picks_2026-03-16T004100Z.json
│   ├── espn_name_map_2026.json     # Auto-generated abbrev→name mapping
│   ├── espn_challenge_2026.json    # Raw API response (already exists)
│   └── espn_propositions_2026.json # Raw propositions (already exists)
├── scripts/
│   └── scrape_espn_picks.py        # KEEP as standalone utility (already works)
└── ESPN_PICKS_DESIGN.md            # This document
```

---

## 12. Implementation Priority

### Phase 1 — Minimum Viable (do this now)

1. Add `scrape_espn_picks_playwright()` to `src/scout.py` with Playwright interception.
2. Implement `(regionId, regionSeed)` → canonical name mapping using existing `real_bracket_2026.json`.
3. Parse R1 pick % and title pick % from the API response.
4. Interpolate R2–R5 using geometric interpolation.
5. Write `data/public_picks.json` in the format `contrarian.py` already expects.
6. Add cache check (skip Playwright if data <2 hours old).
7. Wire into `collect_all()` and `main.py`.

**Result:** `python3 main.py full` uses real ESPN data. EMV calculations are team-specific.

### Phase 2 — Polish (do this week)

8. Timestamped snapshots in `data/espn_picks_snapshots/`.
9. Auto-generate `espn_name_map_2026.json` with manual review step.
10. Validation suite (completeness, sanity, pair-sum checks).
11. `--force-espn-refresh` and `--no-espn` CLI flags.
12. Cron job for periodic scraping.

### Phase 3 — Tournament Time (do as rounds progress)

13. Detect newly available `scoringPeriodId` data and replace interpolated values.
14. Snapshot diff tool for tracking public sentiment shifts.
15. Year parameterization (verify API URL pattern for 2027).

---

## 13. Key Design Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| Integrate into `scout.py`, not a standalone script | Pipeline should be one command. Standalone script already exists for ad-hoc use. |
| Cache with 2-hour TTL | Pick %s shift slowly. Avoids 10-second Playwright launch on every debug run. |
| `(regionId, regionSeed)` as primary matching key | Deterministic, no fuzzy matching needed. Names are messy across systems. |
| Geometric interpolation for R2–R5 | Two real data points (R1 + title) bracket the curve. Better than pure seed-based. |
| Fall back to seed-based on any error | The optimizer works either way. Real data improves it; missing data shouldn't break it. |
| Keep `scripts/scrape_espn_picks.py` | Useful for quick manual checks without running the full pipeline. Already works. |
| Flat floats in `public_picks.json` | Simplest consumer code. Provenance tracked in metadata, not per-value. |
