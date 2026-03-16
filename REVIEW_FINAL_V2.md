# Review: Bracket Optimizer V2 (Post-Column Fix)
**Date:** 2026-03-16 17:06 UTC

## Check Results

| # | Check | Result |
|---|-------|--------|
| 1 | Duke AdjD/AdjT sanity | ✅ AdjD=89.1, AdjT=65.3 — correct. **Luck=0.0** (expected ~0.049) ❌ |
| 2 | AdjD range (80-120) | ✅ Range: 89.0–117.2 |
| 3 | AdjT range (60-75) | ✅ Range: 62.3–73.1 |
| 4 | Luck range (±0.1) | ❌ **ALL ZEROS.** Still defaulting to 0.0 for every team. Fix didn't take effect. |
| 5 | AdjEM ≈ AdjO - AdjD | ✅ All 5 sampled teams match (max diff 0.04) |
| 6 | P(1st) = 23.8% | ✅ Confirmed in summary.json (was 12.2% in old run) |
| 7 | Output timestamp | ✅ 2026-03-16 17:06:14 UTC |
| 8 | Bracket coherence | ✅ Purdue (champ) in FF, all FF in E8, full 6-round path |
| 9 | No 15/16 seed upsets | ✅ Highest upset seed is 12 (Northern Iowa) |

## Summary

**AdjD and AdjT fixes worked perfectly.** Values are now real efficiency metrics (not ranks). This is why P(1st) jumped from 12.2% → 23.8% — the model can now differentiate teams properly.

**Luck is still broken.** Every team has `luck: 0.0`. The cell[11] fix either didn't apply before this run, or cell[11] doesn't contain luck on the scraped page. The model ran without luck data. Impact is likely minor (luck is a small factor), but it wasn't fixed as intended.

## VERDICT: FAIL

Reason: Check #4 fails — luck field is all zeros across all 68 teams. The primary fixes (AdjD, AdjT) are good, but the stated luck fix did not produce real values. Needs investigation of the scraper's cell[11] mapping before a clean pass.

**Note:** The bracket output is otherwise solid and usable. If luck is deemed non-critical, this could be promoted to PASS-WITH-CAVEAT, but per the stated checks it's a fail.
