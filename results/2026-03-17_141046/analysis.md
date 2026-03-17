# March Madness Bracket Optimizer -- Analysis Report

## Executive Summary

**Champion:** Purdue
**Final Four:** Illinois, Duke, Iowa St., Purdue
**Elite Eight:** Duke, Michigan St., Arizona, Purdue, Vanderbilt, Illinois, Michigan, Iowa St.

| Metric | Value |
|--------|-------|
| P(1st place) | 17.7% |
| P(Top 3) | 24.0% |
| Expected finish | 13.5 |
| Expected score | 706 pts |
| Brackets evaluated | 75 |
| Strategy | optimal |

## Cross-Bracket Analysis

Aggregate view across all 75 evaluated brackets.

### Champion Distribution

| Team | Seed | Count | % of Brackets |
|------|------|-------|---------------|
| Duke | 1 | 9/75 | 12% |
| Purdue | 2 | 6/75 | 8% |
| Illinois | 3 | 6/75 | 8% |
| Michigan | 1 | 6/75 | 8% |
| UConn | 2 | 6/75 | 8% |
| Houston | 2 | 6/75 | 8% |
| Florida | 1 | 6/75 | 8% |
| Iowa St. | 2 | 6/75 | 8% |
| Virginia | 3 | 6/75 | 8% |
| Arizona | 1 | 6/75 | 8% |
| Arkansas | 4 | 6/75 | 8% |
| Alabama | 4 | 6/75 | 8% |

### Final Four Frequency

| Team | Seed | Appearances | % |
|------|------|-------------|---|
| Purdue | 2 | 60/75 | 80% |
| Iowa St. | 2 | 33/75 | 44% |
| Duke | 1 | 29/75 | 39% |
| UConn | 2 | 26/75 | 35% |
| Illinois | 3 | 24/75 | 32% |
| Florida | 1 | 18/75 | 24% |
| Houston | 2 | 15/75 | 20% |
| Michigan | 1 | 14/75 | 19% |
| Alabama | 4 | 11/75 | 15% |
| Texas Tech | 5 | 11/75 | 15% |
| Louisville | 6 | 10/75 | 13% |
| UCLA | 7 | 10/75 | 13% |

### Consensus Upsets

Upsets the model picks in >50% of brackets -- these are real.

| Team | Round | Frequency | % |
|------|-------|-----------|---|
| Purdue (2) | E8 | 60/75 | 80% |
| Illinois (3) | S16 | 50/75 | 67% |
| NC State (11) | R32 | 72/75 | 96% |
| Wisconsin (5) | R32 | 66/75 | 88% |
| Texas Tech (5) | R32 | 61/75 | 81% |
| Vanderbilt (5) | R32 | 47/75 | 63% |
| Utah St. (9) | R64 | 74/75 | 99% |
| Iowa (9) | R64 | 74/75 | 99% |
| NC State (11) | R64 | 73/75 | 97% |
| Santa Clara (10) | R64 | 73/75 | 97% |
| Missouri (10) | R64 | 72/75 | 96% |
| VCU (11) | R64 | 72/75 | 96% |
| Texas A&M (10) | R64 | 72/75 | 96% |
| SMU (11) | R64 | 72/75 | 96% |
| Saint Louis (9) | R64 | 48/75 | 64% |
| South Florida (11) | R64 | 38/75 | 51% |

## All Brackets

| # | Label | Champion | P(1st) | P(Top 3) | E[Score] | E[Finish] | Upsets |
|---|-------|----------|--------|----------|----------|-----------|--------|
| 1 | optimal **[OPTIMAL]** | Purdue | 17.7% | 24.0% | 706 | 13.5 | 21 |
| 2 | contrarian_Duke_medium | Duke | 16.8% | 26.9% | 752 | 11.7 | 20 |
| 3 | safe_alternate **[SAFE_ALTERNATE]** | Illinois | 16.5% | 24.6% | 705 | 13.3 | 19 |
| 4 | aggressive_alternate **[AGGRESSIVE_ALTERNATE]** | Illinois | 15.9% | 22.6% | 668 | 14.8 | 20 |
| 5 | chaos_Purdue_high | Purdue | 15.8% | 21.3% | 640 | 15.9 | 23 |
| 6 | chaos_Illinois_high_v2 | Illinois | 15.6% | 21.8% | 648 | 15.3 | 24 |
| 7 | chaos_Duke_high | Duke | 14.7% | 23.3% | 722 | 13.3 | 22 |
| 8 | chaos_Illinois_high | Illinois | 14.7% | 20.5% | 635 | 16.0 | 24 |
| 9 | chalk_Purdue_low_v2 | Purdue | 14.4% | 23.1% | 678 | 14.1 | 16 |
| 10 | contrarian_Purdue_medium_v2 | Purdue | 14.4% | 20.8% | 655 | 15.2 | 19 |
| 11 | chalk_Illinois_low | Illinois | 14.2% | 21.6% | 724 | 12.7 | 19 |
| 12 | chaos_Purdue_high_v2 | Purdue | 14.1% | 19.3% | 617 | 16.6 | 25 |
| 13 | chalk_Michigan_low_v2 | Michigan | 14.0% | 26.7% | 733 | 11.8 | 16 |
| 14 | chaos_Michigan_high | Michigan | 14.0% | 23.8% | 702 | 13.5 | 22 |
| 15 | chalk_Purdue_low | Purdue | 14.0% | 20.9% | 699 | 13.4 | 18 |
| 16 | contrarian_Illinois_medium | Illinois | 13.9% | 21.1% | 719 | 12.9 | 21 |
| 17 | contrarian_Michigan_medium_v2 | Michigan | 13.8% | 25.4% | 716 | 12.7 | 19 |
| 18 | contrarian_UConn_medium | UConn | 13.7% | 21.7% | 652 | 14.7 | 20 |
| 19 | chalk_Houston_low_v2 | Houston | 13.4% | 24.2% | 694 | 13.2 | 17 |
| 20 | chaos_Michigan_high_v2 | Michigan | 13.3% | 23.4% | 700 | 13.5 | 23 |
| 21 | contrarian_Houston_medium_v2 | Houston | 12.9% | 22.1% | 657 | 14.8 | 18 |
| 22 | chalk_Florida_low_v2 | Florida | 12.7% | 22.3% | 685 | 13.3 | 16 |
| 23 | chaos_Iowa St._high | Iowa St. | 12.6% | 18.9% | 624 | 15.9 | 22 |
| 24 | chalk_Iowa St._low_v2 | Iowa St. | 12.6% | 21.5% | 655 | 14.5 | 16 |
| 25 | chaos_Iowa St._high_v2 | Iowa St. | 12.3% | 19.3% | 622 | 15.9 | 23 |
| 26 | chalk_Virginia_low_v2 | Virginia | 12.3% | 20.1% | 652 | 14.8 | 19 |
| 27 | contrarian_Michigan_medium | Michigan | 12.2% | 24.7% | 766 | 10.6 | 19 |
| 28 | chaos_UConn_high | UConn | 12.2% | 19.2% | 629 | 15.8 | 22 |
| 29 | contrarian_Iowa St._medium_v2 | Iowa St. | 12.1% | 19.4% | 638 | 15.4 | 19 |
| 30 | contrarian_Arizona_medium | Arizona | 12.0% | 19.9% | 708 | 13.5 | 20 |
| 31 | contrarian_Virginia_medium_v2 | Virginia | 12.0% | 18.9% | 635 | 15.6 | 21 |
| 32 | contrarian_Arkansas_medium | Arkansas | 12.0% | 17.0% | 648 | 15.4 | 21 |
| 33 | contrarian_Florida_medium_v2 | Florida | 11.9% | 21.1% | 650 | 14.7 | 18 |
| 34 | chaos_Virginia_high | Virginia | 11.9% | 18.4% | 621 | 16.1 | 24 |
| 35 | chaos_Duke_high_v2 | Duke | 11.8% | 21.4% | 724 | 12.8 | 22 |
| 36 | chaos_Houston_high_v2 | Houston | 11.7% | 21.0% | 637 | 15.4 | 21 |
| 37 | contrarian_Iowa St._medium | Iowa St. | 11.6% | 20.3% | 699 | 13.0 | 20 |
| 38 | chaos_Virginia_high_v2 | Virginia | 11.6% | 18.1% | 619 | 16.2 | 25 |
| 39 | chaos_Florida_high_v2 | Florida | 11.5% | 19.8% | 628 | 15.7 | 21 |
| 40 | chalk_Alabama_low_v2 | Alabama | 11.4% | 18.8% | 644 | 15.1 | 18 |
| 41 | chaos_Houston_high | Houston | 11.2% | 19.3% | 624 | 16.1 | 22 |
| 42 | contrarian_Virginia_medium | Virginia | 11.0% | 18.4% | 696 | 13.4 | 21 |
| 43 | chaos_UConn_high_v2 | UConn | 10.9% | 17.9% | 624 | 15.8 | 22 |
| 44 | chaos_Alabama_high | Alabama | 10.9% | 17.3% | 613 | 16.4 | 24 |
| 45 | chaos_Florida_high | Florida | 10.7% | 18.3% | 617 | 16.3 | 22 |
| 46 | chaos_Alabama_high_v2 | Alabama | 10.7% | 16.6% | 598 | 16.9 | 25 |
| 47 | contrarian_Alabama_medium_v2 | Alabama | 10.6% | 17.1% | 615 | 16.3 | 21 |
| 48 | chaos_Arizona_high | Arizona | 10.1% | 16.4% | 644 | 16.0 | 23 |
| 49 | chalk_UConn_low | UConn | 10.1% | 19.1% | 645 | 14.8 | 17 |
| 50 | chalk_Houston_low | Houston | 10.0% | 20.0% | 713 | 12.5 | 17 |
| 51 | contrarian_Alabama_medium | Alabama | 10.0% | 17.1% | 680 | 13.9 | 21 |
| 52 | chalk_Duke_low | Duke | 9.7% | 24.0% | 745 | 11.4 | 16 |
| 53 | contrarian_Houston_medium | Houston | 9.6% | 19.4% | 708 | 12.7 | 19 |
| 54 | chaos_Arkansas_high | Arkansas | 9.6% | 14.1% | 569 | 18.0 | 24 |
| 55 | chalk_UConn_low_v2 | UConn | 9.2% | 18.3% | 695 | 13.0 | 17 |
| 56 | contrarian_Arkansas_medium_v2 | Arkansas | 9.1% | 14.8% | 601 | 17.0 | 22 |
| 57 | contrarian_UConn_medium_v2 | UConn | 9.1% | 14.8% | 607 | 16.8 | 20 |
| 58 | chaos_Arkansas_high_v2 | Arkansas | 9.0% | 12.1% | 557 | 18.6 | 25 |
| 59 | chalk_Florida_low | Florida | 8.9% | 19.8% | 704 | 12.6 | 16 |
| 60 | contrarian_Duke_medium_v2 | Duke | 8.8% | 16.4% | 694 | 14.4 | 19 |
| 61 | chalk_Iowa St._low | Iowa St. | 8.7% | 17.8% | 699 | 12.9 | 18 |
| 62 | contrarian_Arizona_medium_v2 | Arizona | 8.4% | 16.9% | 667 | 15.0 | 19 |
| 63 | contrarian_Florida_medium | Florida | 8.2% | 18.8% | 699 | 12.8 | 18 |
| 64 | chalk_Arkansas_low_v2 | Arkansas | 8.2% | 15.0% | 627 | 16.0 | 17 |
| 65 | chaos_Arizona_high_v2 | Arizona | 8.1% | 12.4% | 617 | 17.0 | 24 |
| 66 | chalk_Virginia_low | Virginia | 8.1% | 16.3% | 696 | 13.2 | 19 |
| 67 | chalk_Duke_low_v2 | Duke | 7.7% | 22.3% | 784 | 9.8 | 16 |
| 68 | chalk_Arizona_low_v2 | Arizona | 7.5% | 18.7% | 689 | 13.8 | 16 |
| 69 | chalk_Michigan_low | Michigan | 6.9% | 21.3% | 764 | 10.3 | 15 |
| 70 | chalk_Arkansas_low | Arkansas | 6.8% | 12.6% | 639 | 15.6 | 16 |
| 71 | chalk_Alabama_low | Alabama | 6.7% | 14.0% | 678 | 13.9 | 17 |
| 72 | chalk_Arizona_low | Arizona | 5.6% | 14.5% | 699 | 13.6 | 15 |
| 73 | BERNS_CHALK | Duke | 5.4% | 20.6% | 806 | 7.7 | 6 |
| 74 | KP_CHALK | Duke | 3.9% | 16.4% | 797 | 8.4 | 5 |
| 75 | CHALK | Duke | 3.1% | 12.6% | 765 | 10.4 | 0 |

## Model vs Public Ownership

Top teams by model title probability vs public championship ownership.

| Team | Seed | Model Title % | Public Title % | Leverage |
|------|------|---------------|----------------|----------|
| Duke | 1 | 12.0% | 29.3% | 0.02 |
| Purdue | 2 | 8.0% | 3.2% | 0.04 |
| Illinois | 3 | 8.0% | 1.2% | 0.05 |
| Michigan | 1 | 8.0% | 14.3% | 0.02 |
| UConn | 2 | 8.0% | 3.5% | 0.02 |
| Houston | 2 | 8.0% | 5.5% | 0.02 |
| Florida | 1 | 8.0% | 6.4% | 0.01 |
| Iowa St. | 2 | 8.0% | 1.9% | 0.02 |
| Virginia | 3 | 8.0% | 0.8% | 0.02 |
| Arizona | 1 | 8.0% | 21.0% | 0.02 |
| Arkansas | 4 | 8.0% | 1.2% | 0.02 |
| Alabama | 4 | 8.0% | 0.5% | 0.02 |

## Key Differentiators (Optimal Bracket)

High-leverage picks that separate the optimal bracket from the field:

1. **Illinois** to F4 -- Leverage: 0.4905, Seed: 3, Public: 3.3%, In 21% of our brackets
2. **Purdue** to F4 -- Leverage: 0.3563, Seed: 2, Public: 7.4%, In 45% of our brackets
3. **NC State** to R32 -- Leverage: 0.3159, Seed: 11, Public: 3.2%, In 96% of our brackets
4. **Illinois** to E8 -- Leverage: 0.2898, Seed: 3, Public: 10.1%, In 32% of our brackets
5. **SMU** to R64 -- Leverage: 0.2613, Seed: 11, Public: 11.8%, In 96% of our brackets
6. **Vanderbilt** to S16 -- Leverage: 0.2372, Seed: 5, Public: 10.7%, In 41% of our brackets
7. **Purdue** to E8 -- Leverage: 0.2064, Seed: 2, Public: 15.8%, In 80% of our brackets
8. **NC State** to R64 -- Leverage: 0.2035, Seed: 11, Public: 16.3%, In 97% of our brackets
9. **Iowa St.** to E8 -- Leverage: 0.1882, Seed: 2, Public: 17.8%, In 44% of our brackets
10. **Illinois** to S16 -- Leverage: 0.1614, Seed: 3, Public: 21.4%, In 67% of our brackets
11. **VCU** to R64 -- Leverage: 0.1272, Seed: 11, Public: 28.6%, In 96% of our brackets
12. **Santa Clara** to R64 -- Leverage: 0.1216, Seed: 10, Public: 30.1%, In 97% of our brackets

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
