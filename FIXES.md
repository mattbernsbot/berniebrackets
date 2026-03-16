# Bug Fixes - March Madness Bracket Optimizer

## Summary
Fixed all 5 critical bugs identified in the code review. The system now generates complete 63-pick brackets with actual leverage scores, proper ASCII visualization, comprehensive analysis reports, and robust test coverage.

---

## Bug #1: construct_candidate_bracket() Only Built R1 Picks (32/63) ✅ FIXED

### Problem
The function only created BracketPick objects for Round 1 (32 games) and never generated picks for rounds 2-6. It set champion/final_four/elite_eight as fields but didn't create the corresponding BracketPick objects.

### Solution
Completely rewrote `construct_candidate_bracket()` to use the same `feeds_into` traversal pattern that `generate_public_bracket()` already demonstrated:

1. **Round 1**: Process all 32 first-round games with strategic upset selection based on leverage
2. **Rounds 2-6**: Walk the bracket tree using `feeds_into` relationships:
   - For each slot in round N, find the two teams that advanced from round N-1
   - Calculate win probabilities and leverage for both teams
   - Pick winner based on probability + leverage strategy
   - Create BracketPick object for every game

3. **Extract metadata**: After all picks are created, extract champion (R6 winner), Final Four (R4 winners), and Elite Eight (R3 winners) from the picks

### Validation
- Added test `test_construct_candidate_bracket_completeness()` that verifies:
  - Exactly 63 picks are created
  - All 6 rounds are covered
  - Correct distribution: 32+16+8+4+2+1 picks
  - Champion and Final Four/Elite Eight are properly set

---

## Bug #2: Leverage Scores Hardcoded to 1.0 ✅ FIXED

### Problem
`build_ownership_profiles()` set `leverage_by_round = {r: 1.0 for r in ...}` and `title_leverage = 1.0` with a comment saying "will be updated later" - but this never happened. The contrarian strategy was completely non-functional.

### Solution
1. **Created `update_leverage_with_model()` function** in `contrarian.py`:
   - Estimates each team's probability of reaching each round based on seed and KenPom rank
   - Calculates actual leverage = model_probability / public_ownership
   - Updates all OwnershipProfile objects with real leverage scores

2. **Updated `cmd_analyze()` in main.py**:
   - Calls `update_leverage_with_model()` after building the matchup matrix
   - Saves updated ownership profiles with leverage scores

3. **Used leverage in bracket construction**:
   - Modified `construct_candidate_bracket()` to calculate leverage for each pick
   - Uses `calculate_leverage(prob, ownership)` for every game
   - Stores actual leverage score in each BracketPick

### Validation
- Added test `test_leverage_scores_not_all_one()` that verifies:
  - Leverage scores are NOT all 1.0
  - There is variation in leverage across picks
  - Actual leverage calculation is working

---

## Bug #3: ASCII Bracket Was a Flat List ✅ FIXED

### Problem
`generate_ascii_bracket()` just listed team names in a flat list by round. No matchup pairings, no bracket structure, no visual indication of who plays who or who advances.

### Solution
Completely rewrote `generate_ascii_bracket()` to show actual bracket structure:

1. **Round 1**: Shows initial matchups with both teams, seeds, and winner indicator (✓)
2. **Later Rounds**: Shows which teams are playing (the two that advanced from previous round)
3. **Visual markers**: 
   - ✓ indicates which team won
   - Seeds shown as (1), (2), etc.
   - [UPSET] marker for upset picks
   - Confidence tiers shown for each pick
4. **Summary section**: Champion, Final Four, Elite Eight, expected score, and P(1st)

### Example Output Format
```
─────────────────── ROUND OF 64 ──────────────────
  Duke                      (1) ✓
  Norfolk St               (16)
    → Winner: Duke 🔒 Lock

─────────────────── ROUND OF 32 ──────────────────
  Duke                           ✓
      vs
  Marquette                     
    → Winner: Duke 👍 Lean
```

---

## Bug #4: Analysis Report Sections Empty ✅ FIXED

### Problem
The analysis report had empty "Key Differentiators" and incomplete "Round-by-Round Breakdown" sections because:
- No picks beyond R1 to analyze
- Leverage scores were all 1.0, so no high-leverage picks to highlight

### Solution
With fixes #1 and #2 in place, the report now auto-populates:

1. **Key Differentiators**: 
   - Finds all picks with leverage > 1.5
   - Sorts by leverage descending
   - Shows top 8 differentiating picks with seed, ownership %, and leverage score

2. **Round-by-Round Breakdown**:
   - Shows upset count per round
   - Lists each upset with seed and confidence tier
   - Organized by round (R64, R32, S16, E8, F4, Championship)

3. **Risk Assessment**:
   - Populated with actual champion and Final Four requirements
   - Counts and lists "gamble" picks (low win probability)

---

## Bug #5: Tests Didn't Validate Production Output ✅ FIXED

### Problem
Tests validated hand-built mock data but never called `construct_candidate_bracket()` to verify:
- Actual pick count
- Round distribution
- Bracket consistency
- Leverage calculation

### Solution
Added 3 comprehensive integration tests:

1. **`test_construct_candidate_bracket_completeness()`**:
   - Creates realistic 68-team bracket
   - Calls actual `construct_candidate_bracket()` function
   - Asserts exactly 63 picks
   - Verifies all 6 rounds present
   - Checks correct distribution (32, 16, 8, 4, 2, 1)
   - Validates champion and Final Four/Elite Eight are set

2. **`test_bracket_consistency()`**:
   - Verifies champion won their semifinal
   - Checks each R2 winner won an R1 game
   - Ensures advancement path consistency

3. **`test_leverage_scores_not_all_one()`**:
   - Creates bracket with varied ownership profiles
   - Verifies leverage scores are calculated (not hardcoded to 1.0)
   - Checks for variation in leverage across picks

### Test Results
All 44 tests now pass, including 9 optimizer tests (3 new + 6 existing).

---

## Additional Improvements

### Code Quality
- Added `assign_confidence_tier()` helper function to `optimizer.py` (was only in `analyst.py`)
- Used consistent leverage calculation pattern throughout
- Better error handling for missing matchup data

### Documentation
- Updated function docstrings to reflect actual behavior
- Added inline comments explaining champion-down construction strategy
- Clarified round numbering and slot relationships

---

## Files Modified

1. **src/optimizer.py** (~200 lines changed)
   - Rewrote `construct_candidate_bracket()` to build all 63 picks
   - Added `assign_confidence_tier()` function
   - Added leverage calculation to each pick

2. **src/contrarian.py** (~50 lines added)
   - Added `update_leverage_with_model()` function
   - Integrated leverage calculation with matchup matrix

3. **main.py** (~10 lines changed)
   - Added call to `update_leverage_with_model()` in `cmd_analyze()`
   - Updated ownership profile save after leverage update

4. **src/analyst.py** (~100 lines changed)
   - Completely rewrote `generate_ascii_bracket()` for proper visualization
   - Analysis report now auto-populates all sections

5. **tests/test_optimizer.py** (~200 lines added)
   - Added 3 comprehensive integration tests
   - Validates production code paths

---

## Verification

Run the full test suite:
```bash
python3 -m pytest tests/ -v
```

Result: **44/44 tests passing** ✅

The system now:
- ✅ Generates complete 63-pick brackets covering all rounds
- ✅ Calculates actual leverage scores based on model probabilities
- ✅ Produces proper ASCII bracket visualization with matchups
- ✅ Fills all analysis report sections with real data
- ✅ Has comprehensive test coverage validating production output

All critical bugs from the review are resolved. The bracket optimizer is now functional and ready for production use.
