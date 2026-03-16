# Bug Fix Summary - March 2026

## Bugs Fixed

### ✅ Bug #1: is_upset always False for R2+ picks (CRITICAL)
**File:** `src/optimizer.py`, line ~830  
**Problem:** R2-R6 bracket slots have `seed_a=0, seed_b=0`, so upset detection using slot seeds always returned False  
**Fix:** For R2+ rounds, look up actual team seeds from `team_map` instead of using slot seeds
```python
# Now correctly detects upsets like:
# - 3-seed Michigan St. over 1-seed Duke in Elite 8
# - 5-seed Arkansas over 2-seed Michigan in Sweet 16
```
**Verification:**
- Before: 10 R1 upsets, 0 R2+ upsets
- After: 10 R1 upsets, **9 R2+ upsets** (4 in R2, 3 in R3, 2 in R4)

---

### ✅ Bug #2: Region mismatch between team.region and bracket slots (HIGH)
**File:** `src/scout.py`, line ~263  
**Problem:** `merge_team_data()` assigned regions using `idx % 4` (round-robin), but `generate_bracket_from_kenpom()` uses S-curve reversal  
**Fix:** Removed region assignment from `merge_team_data()` — let bracket generator be the single source of truth
```python
# Old (WRONG): team.region = region_names[idx % 4]
# New (CORRECT): region comes from generate_bracket_from_kenpom() S-curve
```
**Verification:**
- Before: 32/68 teams had mismatched regions
- After: **64/64 teams match their bracket slot regions** (all R1 games)

---

### ✅ Bug #3: Leverage scores tiny, Key Differentiators always empty (HIGH)
**File:** `src/analyst.py`, line ~45  
**Problem:** Pool-aware leverage formula produces 0.04-0.22, but report filtered for `leverage > 1.5`  
**Fix:** Changed threshold from `1.5` to `0.02` to match actual scale
```python
# Old: high_leverage_picks = [p for p in bracket.picks if p.leverage_score > 1.5]
# New: high_leverage_picks = [p for p in bracket.picks if p.leverage_score > 0.02]
```
**Verification:**
- Before: Key Differentiators section was **empty** (0 picks shown)
- After: Shows **12 high-leverage picks** with leverage 0.11-0.22

---

## Test Results

```bash
$ python3 -m pytest tests/test_optimizer.py -q
.........                                                                [100%]
9 passed in 0.25s
```

## Full Pipeline Run

```bash
$ python3 main.py full --sims 200
# Successfully completed with:
# - 3 diverse brackets generated
# - Later-round upsets visible in output
# - Key Differentiators section populated
# - All regions aligned correctly
```

## Output Verification

**Later-round upsets now visible in bracket.txt:**
```
─ SWEET 16 ─
  Michigan St. ✓ vs Purdue
    → Winner: Michigan St. 🎲 Gamble [UPSET]
  
  Arkansas ✓ vs Michigan
    → Winner: Arkansas 🎲 Gamble [UPSET]

─ ELITE 8 ─
  Michigan St. ✓ vs Duke
    → Winner: Michigan St. 🎲 Gamble [UPSET]
```

**Key Differentiators section now populated:**
```
1. Virginia Tech to R64 (Leverage: 0.2185, Seed: 14, Ownership: 14.9%)
2. Illinois to F4 (Leverage: 0.1861, Seed: 2, Ownership: 18.0%)
3. Michigan St. to E8 (Leverage: 0.1781, Seed: 3, Ownership: 19.0%)
... (12 total)
```

---

## Files Modified

1. `src/optimizer.py` - Fixed is_upset detection for R2+ rounds
2. `src/scout.py` - Removed incorrect region assignment  
3. `src/analyst.py` - Adjusted leverage threshold to match pool-aware scale

**No changes to:** `sharp.py`, `constants.py`, `upset_model/` (as required)
