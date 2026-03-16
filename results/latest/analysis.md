# March Madness Bracket Optimizer -- Analysis Report

## Executive Summary

**Champion:** Purdue
**Final Four:** Duke, Iowa St., Illinois, Purdue
**Elite Eight:** Duke, Michigan St., Arizona, Purdue, Vanderbilt, Illinois, Michigan, Iowa St.

| Metric | Value |
|--------|-------|
| P(1st place) | 18.9% |
| P(Top 3) | 25.5% |
| Expected finish | 10.8 |
| Expected score | 706 pts |
| Brackets evaluated | 72 |
| Strategy | optimal |

## Cross-Bracket Analysis

Aggregate view across all 72 evaluated brackets.

### Champion Distribution

| Team | Seed | Count | % of Brackets |
|------|------|-------|---------------|
| Purdue | 2 | 6/72 | 8% |
| Duke | 1 | 6/72 | 8% |
| Illinois | 3 | 6/72 | 8% |
| Michigan | 1 | 6/72 | 8% |
| Houston | 2 | 6/72 | 8% |
| UConn | 2 | 6/72 | 8% |
| Florida | 1 | 6/72 | 8% |
| Arizona | 1 | 6/72 | 8% |
| Iowa St. | 2 | 6/72 | 8% |
| Virginia | 3 | 6/72 | 8% |
| Arkansas | 4 | 6/72 | 8% |
| Alabama | 4 | 6/72 | 8% |

### Final Four Frequency

| Team | Seed | Appearances | % |
|------|------|-------------|---|
| Purdue | 2 | 60/72 | 83% |
| Iowa St. | 2 | 30/72 | 42% |
| Illinois | 3 | 30/72 | 42% |
| Duke | 1 | 26/72 | 36% |
| UConn | 2 | 26/72 | 36% |
| Houston | 2 | 18/72 | 25% |
| Michigan | 1 | 14/72 | 19% |
| Alabama | 4 | 14/72 | 19% |
| Florida | 1 | 12/72 | 17% |
| UCLA | 7 | 10/72 | 14% |
| Louisville | 6 | 10/72 | 14% |
| Texas Tech | 5 | 8/72 | 11% |

### Consensus Upsets

Upsets the model picks in >50% of brackets -- these are real.

| Team | Round | Frequency | % |
|------|-------|-----------|---|
| Purdue (2) | E8 | 60/72 | 83% |
| Illinois (3) | S16 | 52/72 | 72% |
| Virginia (3) | S16 | 36/72 | 50% |
| NC State (11) | R32 | 72/72 | 100% |
| Wisconsin (5) | R32 | 66/72 | 92% |
| Texas Tech (5) | R32 | 58/72 | 81% |
| Vanderbilt (5) | R32 | 44/72 | 61% |
| Utah St. (9) | R64 | 72/72 | 100% |
| NC State (11) | R64 | 72/72 | 100% |
| Missouri (10) | R64 | 72/72 | 100% |
| Iowa (9) | R64 | 72/72 | 100% |
| VCU (11) | R64 | 72/72 | 100% |
| SMU (11) | R64 | 72/72 | 100% |
| Santa Clara (10) | R64 | 72/72 | 100% |
| South Florida (11) | R64 | 62/72 | 86% |
| Texas A&M (10) | R64 | 48/72 | 67% |
| Saint Louis (9) | R64 | 48/72 | 67% |

## All Brackets

| # | Label | Champion | P(1st) | P(Top 3) | E[Score] | E[Finish] | Upsets |
|---|-------|----------|--------|----------|----------|-----------|--------|
| 1 | optimal **[OPTIMAL]** | Purdue | 18.9% | 25.5% | 706 | 10.8 | 21 |
| 2 | contrarian_Duke_medium | Duke | 18.4% | 29.1% | 752 | 9.4 | 20 |
| 3 | safe_alternate **[SAFE_ALTERNATE]** | Illinois | 17.9% | 25.6% | 703 | 10.7 | 19 |
| 4 | contrarian_Purdue_medium_v2 | Purdue | 17.8% | 24.4% | 673 | 11.8 | 19 |
| 5 | chaos_Purdue_high_v2 | Purdue | 17.3% | 23.8% | 653 | 12.2 | 23 |
| 6 | aggressive_alternate **[AGGRESSIVE_ALTERNATE]** | Illinois | 16.6% | 23.9% | 668 | 11.8 | 20 |
| 7 | chaos_Illinois_high_v2 | Illinois | 16.5% | 23.7% | 648 | 12.3 | 24 |
| 8 | chaos_Purdue_high | Purdue | 16.4% | 22.4% | 640 | 12.7 | 23 |
| 9 | chaos_Duke_high | Duke | 16.3% | 25.4% | 722 | 10.6 | 22 |
| 10 | chalk_Michigan_low_v2 | Michigan | 15.8% | 29.3% | 729 | 9.5 | 16 |
| 11 | chalk_Illinois_low | Illinois | 15.2% | 23.4% | 722 | 10.3 | 19 |
| 12 | contrarian_Michigan_medium_v2 | Michigan | 15.2% | 27.4% | 716 | 10.2 | 19 |
| 13 | chaos_Michigan_high | Michigan | 15.2% | 26.3% | 702 | 10.8 | 22 |
| 14 | chaos_Illinois_high | Illinois | 15.1% | 21.6% | 635 | 12.8 | 24 |
| 15 | chalk_Purdue_low | Purdue | 15.1% | 23.6% | 703 | 10.8 | 17 |
| 16 | chalk_Houston_low_v2 | Houston | 15.1% | 25.4% | 692 | 10.6 | 17 |
| 17 | contrarian_Illinois_medium | Illinois | 15.1% | 23.1% | 719 | 10.4 | 21 |
| 18 | contrarian_UConn_medium | UConn | 15.0% | 23.3% | 652 | 11.8 | 20 |
| 19 | chaos_Michigan_high_v2 | Michigan | 15.0% | 25.7% | 700 | 10.9 | 23 |
| 20 | chalk_Purdue_low_v2 | Purdue | 14.7% | 23.1% | 720 | 10.2 | 17 |
| 21 | contrarian_Michigan_medium | Michigan | 14.4% | 27.9% | 766 | 8.6 | 19 |
| 22 | contrarian_Houston_medium_v2 | Houston | 14.3% | 23.4% | 657 | 11.9 | 18 |
| 23 | chalk_Florida_low_v2 | Florida | 14.0% | 24.2% | 683 | 10.8 | 16 |
| 24 | contrarian_Arizona_medium_v2 | Arizona | 13.6% | 22.0% | 677 | 11.6 | 19 |
| 25 | chaos_Iowa St._high | Iowa St. | 13.5% | 20.7% | 624 | 12.7 | 22 |
| 26 | chalk_Virginia_low_v2 | Virginia | 13.5% | 21.6% | 648 | 11.9 | 19 |
| 27 | contrarian_Arizona_medium | Arizona | 13.3% | 22.7% | 708 | 10.8 | 20 |
| 28 | chaos_UConn_high | UConn | 13.3% | 20.6% | 629 | 12.7 | 22 |
| 29 | chaos_Iowa St._high_v2 | Iowa St. | 13.3% | 20.7% | 622 | 12.8 | 23 |
| 30 | contrarian_Florida_medium_v2 | Florida | 13.3% | 22.7% | 650 | 11.8 | 18 |
| 31 | chaos_Houston_high_v2 | Houston | 13.2% | 22.4% | 637 | 12.3 | 21 |
| 32 | chalk_Iowa St._low_v2 | Iowa St. | 13.2% | 22.6% | 652 | 11.8 | 17 |
| 33 | contrarian_Arkansas_medium | Arkansas | 13.0% | 18.3% | 648 | 12.3 | 21 |
| 34 | contrarian_Virginia_medium_v2 | Virginia | 12.9% | 20.2% | 635 | 12.5 | 21 |
| 35 | contrarian_Iowa St._medium | Iowa St. | 12.9% | 22.1% | 699 | 10.5 | 20 |
| 36 | chaos_Virginia_high | Virginia | 12.8% | 19.6% | 621 | 12.9 | 24 |
| 37 | contrarian_Iowa St._medium_v2 | Iowa St. | 12.8% | 21.1% | 638 | 12.3 | 19 |
| 38 | chaos_Virginia_high_v2 | Virginia | 12.8% | 19.4% | 619 | 13.0 | 25 |
| 39 | chaos_Florida_high_v2 | Florida | 12.7% | 21.2% | 628 | 12.6 | 21 |
| 40 | chaos_Duke_high_v2 | Duke | 12.7% | 24.2% | 724 | 10.3 | 22 |
| 41 | chaos_Alabama_high_v2 | Alabama | 12.7% | 18.7% | 608 | 13.2 | 25 |
| 42 | chaos_Arizona_high_v2 | Arizona | 12.5% | 20.7% | 665 | 12.0 | 23 |
| 43 | contrarian_Alabama_medium_v2 | Alabama | 12.4% | 19.0% | 625 | 12.8 | 21 |
| 44 | chaos_Houston_high | Houston | 12.4% | 20.2% | 624 | 12.9 | 22 |
| 45 | chalk_Duke_low | Duke | 12.4% | 27.7% | 749 | 9.2 | 16 |
| 46 | contrarian_Virginia_medium | Virginia | 12.2% | 20.4% | 696 | 10.8 | 21 |
| 47 | chalk_Alabama_low_v2 | Alabama | 12.2% | 20.5% | 643 | 12.1 | 18 |
| 48 | contrarian_Arkansas_medium_v2 | Arkansas | 11.9% | 17.6% | 612 | 13.1 | 21 |
| 49 | chaos_Alabama_high | Alabama | 11.8% | 18.7% | 613 | 13.2 | 24 |
| 50 | chaos_Florida_high | Florida | 11.7% | 19.7% | 617 | 13.0 | 22 |
| 51 | chaos_UConn_high_v2 | UConn | 11.7% | 19.6% | 624 | 12.7 | 22 |
| 52 | chalk_Houston_low | Houston | 11.6% | 22.7% | 711 | 10.1 | 17 |
| 53 | chaos_Arkansas_high_v2 | Arkansas | 11.6% | 16.9% | 602 | 13.5 | 23 |
| 54 | contrarian_Duke_medium_v2 | Duke | 11.4% | 20.4% | 704 | 11.1 | 19 |
| 55 | chalk_UConn_low | UConn | 11.4% | 21.3% | 649 | 11.8 | 16 |
| 56 | contrarian_Alabama_medium | Alabama | 11.3% | 19.2% | 680 | 11.2 | 21 |
| 57 | contrarian_UConn_medium_v2 | UConn | 11.2% | 16.9% | 617 | 13.0 | 20 |
| 58 | contrarian_Houston_medium | Houston | 11.2% | 22.2% | 708 | 10.2 | 19 |
| 59 | chaos_Arkansas_high | Arkansas | 11.1% | 15.9% | 579 | 14.1 | 24 |
| 60 | chaos_Arizona_high | Arizona | 11.0% | 18.1% | 644 | 12.8 | 23 |
| 61 | chalk_UConn_low_v2 | UConn | 10.0% | 20.1% | 691 | 10.4 | 17 |
| 62 | chalk_Florida_low | Florida | 9.8% | 21.9% | 701 | 10.2 | 16 |
| 63 | contrarian_Florida_medium | Florida | 9.7% | 21.5% | 699 | 10.3 | 18 |
| 64 | chalk_Michigan_low | Michigan | 9.6% | 24.9% | 766 | 8.4 | 16 |
| 65 | chalk_Iowa St._low | Iowa St. | 9.5% | 19.6% | 698 | 10.4 | 17 |
| 66 | chalk_Virginia_low | Virginia | 9.4% | 17.8% | 695 | 10.8 | 19 |
| 67 | chalk_Duke_low_v2 | Duke | 8.9% | 24.6% | 779 | 8.1 | 15 |
| 68 | chalk_Arkansas_low | Arkansas | 8.4% | 15.6% | 644 | 12.4 | 17 |
| 69 | chalk_Alabama_low | Alabama | 8.0% | 16.0% | 680 | 11.2 | 18 |
| 70 | chalk_Arkansas_low_v2 | Arkansas | 7.8% | 14.3% | 662 | 11.9 | 17 |
| 71 | chalk_Arizona_low | Arizona | 7.3% | 19.5% | 704 | 10.7 | 16 |
| 72 | chalk_Arizona_low_v2 | Arizona | 7.2% | 18.4% | 721 | 10.1 | 16 |

## Model vs Public Ownership

Top teams by model title probability vs public championship ownership.

| Team | Seed | Model Title % | Public Title % | Leverage |
|------|------|---------------|----------------|----------|
| Purdue | 2 | 8.3% | 3.2% | 0.05 |
| Duke | 1 | 8.3% | 30.2% | 0.03 |
| Illinois | 3 | 8.3% | 1.1% | 0.05 |
| Michigan | 1 | 8.3% | 14.5% | 0.03 |
| Houston | 2 | 8.3% | 5.2% | 0.02 |
| UConn | 2 | 8.3% | 3.6% | 0.02 |
| Florida | 1 | 8.3% | 6.5% | 0.02 |
| Arizona | 1 | 8.3% | 19.4% | 0.02 |
| Iowa St. | 2 | 8.3% | 1.8% | 0.02 |
| Virginia | 3 | 8.3% | 0.8% | 0.02 |
| Arkansas | 4 | 8.3% | 1.2% | 0.02 |
| Alabama | 4 | 8.3% | 0.6% | 0.02 |

## Key Differentiators (Optimal Bracket)

High-leverage picks that separate the optimal bracket from the field:

1. **Illinois** to F4 -- Leverage: 0.5570, Seed: 3, Public: 3.0%, In 31% of our brackets
2. **Purdue** to F4 -- Leverage: 0.4091, Seed: 2, Public: 7.5%, In 47% of our brackets
3. **NC State** to R32 -- Leverage: 0.3687, Seed: 11, Public: 2.7%, In 100% of our brackets
4. **Illinois** to E8 -- Leverage: 0.3609, Seed: 3, Public: 9.2%, In 42% of our brackets
5. **SMU** to R64 -- Leverage: 0.3090, Seed: 11, Public: 11.8%, In 100% of our brackets
6. **Vanderbilt** to S16 -- Leverage: 0.2805, Seed: 5, Public: 10.6%, In 42% of our brackets
7. **NC State** to R64 -- Leverage: 0.2562, Seed: 11, Public: 15.3%, In 100% of our brackets
8. **Purdue** to E8 -- Leverage: 0.2468, Seed: 2, Public: 15.8%, In 83% of our brackets
9. **Iowa St.** to E8 -- Leverage: 0.2405, Seed: 2, Public: 16.4%, In 42% of our brackets
10. **Illinois** to S16 -- Leverage: 0.2031, Seed: 3, Public: 20.4%, In 72% of our brackets
11. **VCU** to R64 -- Leverage: 0.1658, Seed: 11, Public: 26.5%, In 100% of our brackets
12. **Santa Clara** to R64 -- Leverage: 0.1543, Seed: 10, Public: 28.8%, In 100% of our brackets

## Round-by-Round Breakdown (Optimal)

### Round of 64

**Upsets:** 10
- South Florida (11-seed) -- 🎲 Gamble
- Utah St. (9-seed) -- 🔒 Lock
- NC State (11-seed) -- 👍 Lean
- Missouri (10-seed) -- 🎲 Gamble
- Iowa (9-seed) -- 👍 Lean
- VCU (11-seed) -- 🎲 Gamble
- Texas A&M (10-seed) -- 🎲 Gamble
- Saint Louis (9-seed) -- 🎲 Gamble
- SMU (11-seed) -- 🎲 Gamble
- Santa Clara (10-seed) -- 🔒 Lock

### Round of 32

**Upsets:** 4
- Wisconsin (5-seed) -- 🎲 Gamble
- NC State (11-seed) -- 🎲 Gamble
- Vanderbilt (5-seed) -- 👍 Lean
- Texas Tech (5-seed) -- 🎲 Gamble

### Sweet 16

**Upsets:** 3
- Illinois (3-seed) -- 🎲 Gamble
- Michigan St. (3-seed) -- 🎲 Gamble
- Vanderbilt (5-seed) -- 🎲 Gamble

### Elite 8

**Upsets:** 2
- Purdue (2-seed) -- 🎲 Gamble
- Iowa St. (2-seed) -- 🎲 Gamble

### Final Four

**Upsets:** 2
- Purdue (2-seed) -- 🎲 Gamble
- Illinois (3-seed) -- 👍 Lean

### Championship

No upsets.

## Risk Assessment

**Champion dependency:** Purdue path accounts for 630 potential points (89% of expected score)

**Gamble picks by round:**
- Round of 64: 6/32
- Round of 32: 5/16
- Sweet 16: 3/8
- Elite 8: 2/4
- Final Four: 1/2

**Chalk overlap:** 42/63 picks match chalk (67%)
