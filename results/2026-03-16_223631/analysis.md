# March Madness Bracket Optimizer -- Analysis Report

## Executive Summary

**Champion:** Purdue
**Final Four:** Iowa St., Duke, Illinois, Purdue
**Elite Eight:** Duke, Michigan St., Arizona, Purdue, Vanderbilt, Illinois, Michigan, Iowa St.

| Metric | Value |
|--------|-------|
| P(1st place) | 18.0% |
| P(Top 3) | 24.0% |
| Expected finish | 13.4 |
| Expected score | 706 pts |
| Brackets evaluated | 24 |
| Strategy | optimal |

## Cross-Bracket Analysis

Aggregate view across all 24 evaluated brackets.

### Champion Distribution

| Team | Seed | Count | % of Brackets |
|------|------|-------|---------------|
| Duke | 1 | 5/24 | 21% |
| Illinois | 3 | 5/24 | 21% |
| Purdue | 2 | 3/24 | 12% |
| Michigan | 1 | 3/24 | 12% |
| Arizona | 1 | 2/24 | 8% |
| Vanderbilt | 5 | 2/24 | 8% |
| Houston | 2 | 2/24 | 8% |
| Santa Clara | 10 | 2/24 | 8% |

### Final Four Frequency

| Team | Seed | Appearances | % |
|------|------|-------------|---|
| Purdue | 2 | 22/24 | 92% |
| Duke | 1 | 15/24 | 62% |
| Illinois | 3 | 15/24 | 62% |
| Iowa St. | 2 | 9/24 | 38% |
| Louisville | 6 | 7/24 | 29% |
| Texas Tech | 5 | 6/24 | 25% |
| Michigan | 1 | 5/24 | 21% |
| Houston | 2 | 5/24 | 21% |
| UConn | 2 | 2/24 | 8% |
| Alabama | 4 | 2/24 | 8% |
| Arizona | 1 | 2/24 | 8% |
| Vanderbilt | 5 | 2/24 | 8% |

### Consensus Upsets

Upsets the model picks in >50% of brackets -- these are real.

| Team | Round | Frequency | % |
|------|-------|-----------|---|
| Purdue (2) | E8 | 22/24 | 92% |
| Illinois (3) | S16 | 17/24 | 71% |
| Michigan St. (3) | S16 | 15/24 | 62% |
| Vanderbilt (5) | S16 | 13/24 | 54% |
| Wisconsin (5) | R32 | 24/24 | 100% |
| NC State (11) | R32 | 24/24 | 100% |
| Texas Tech (5) | R32 | 22/24 | 92% |
| Vanderbilt (5) | R32 | 17/24 | 71% |
| Utah St. (9) | R64 | 24/24 | 100% |
| NC State (11) | R64 | 24/24 | 100% |
| Missouri (10) | R64 | 24/24 | 100% |
| Iowa (9) | R64 | 24/24 | 100% |
| VCU (11) | R64 | 24/24 | 100% |
| SMU (11) | R64 | 24/24 | 100% |
| Santa Clara (10) | R64 | 24/24 | 100% |
| Texas A&M (10) | R64 | 18/24 | 75% |
| Saint Louis (9) | R64 | 18/24 | 75% |
| South Florida (11) | R64 | 17/24 | 71% |

## All Brackets

| # | Label | Champion | P(1st) | P(Top 3) | E[Score] | E[Finish] | Upsets |
|---|-------|----------|--------|----------|----------|-----------|--------|
| 1 | optimal **[OPTIMAL]** | Purdue | 18.0% | 24.0% | 706 | 13.4 | 21 |
| 2 | contrarian_Duke_medium | Duke | 16.9% | 26.9% | 752 | 11.7 | 20 |
| 3 | safe_alternate **[SAFE_ALTERNATE]** | Illinois | 16.8% | 24.3% | 703 | 13.3 | 19 |
| 4 | aggressive_alternate **[AGGRESSIVE_ALTERNATE]** | Illinois | 16.0% | 22.7% | 668 | 14.7 | 20 |
| 5 | chaos_Purdue_high | Purdue | 15.8% | 21.4% | 640 | 15.8 | 23 |
| 6 | chaos_Duke_high | Duke | 15.0% | 23.5% | 722 | 13.2 | 22 |
| 7 | chaos_Illinois_high | Illinois | 14.6% | 20.6% | 635 | 15.9 | 24 |
| 8 | chalk_Illinois_low | Illinois | 14.1% | 21.5% | 722 | 12.8 | 19 |
| 9 | chalk_Purdue_low | Purdue | 14.0% | 21.7% | 703 | 13.3 | 17 |
| 10 | contrarian_Illinois_medium | Illinois | 14.0% | 21.2% | 719 | 12.9 | 21 |
| 11 | chaos_Michigan_high | Michigan | 13.9% | 24.2% | 702 | 13.4 | 22 |
| 12 | contrarian_Michigan_medium | Michigan | 12.8% | 25.0% | 766 | 10.6 | 19 |
| 13 | contrarian_Arizona_medium | Arizona | 12.3% | 20.4% | 708 | 13.4 | 20 |
| 14 | chaos_Vanderbilt_high | Vanderbilt | 12.2% | 18.3% | 610 | 16.4 | 26 |
| 15 | chaos_Houston_high | Houston | 11.3% | 19.2% | 624 | 16.0 | 22 |
| 16 | contrarian_Vanderbilt_medium | Vanderbilt | 10.8% | 18.2% | 698 | 13.3 | 22 |
| 17 | chaos_Santa Clara_high | Santa Clara | 10.7% | 16.9% | 603 | 16.5 | 27 |
| 18 | chalk_Duke_low | Duke | 10.4% | 24.0% | 749 | 11.4 | 16 |
| 19 | chaos_Arizona_high | Arizona | 10.3% | 16.7% | 644 | 15.8 | 23 |
| 20 | ff_variant_Duke_med | Duke | 10.3% | 18.4% | 704 | 13.8 | 19 |
| 21 | contrarian_Houston_medium | Houston | 9.7% | 19.8% | 708 | 12.6 | 19 |
| 22 | contrarian_Santa Clara_medium | Santa Clara | 9.4% | 16.7% | 672 | 14.3 | 24 |
| 23 | chalk_Michigan_low | Michigan | 7.8% | 21.0% | 766 | 10.3 | 16 |
| 24 | ff_variant_Duke | Duke | 7.2% | 20.7% | 779 | 10.0 | 15 |

## Model vs Public Ownership

Top teams by model title probability vs public championship ownership.

| Team | Seed | Model Title % | Public Title % | Leverage |
|------|------|---------------|----------------|----------|
| Duke | 1 | 20.8% | 30.2% | 0.02 |
| Illinois | 3 | 20.8% | 1.1% | 0.05 |
| Purdue | 2 | 12.5% | 3.2% | 0.04 |
| Michigan | 1 | 12.5% | 14.5% | 0.02 |
| Arizona | 1 | 8.3% | 19.4% | 0.02 |
| Vanderbilt | 5 | 8.3% | 0.3% | 0.03 |
| Houston | 2 | 8.3% | 5.2% | 0.02 |
| Santa Clara | 10 | 8.3% | 0.0% | 0.02 |
| Florida | 1 | 0.0% | 6.5% | 0.01 |
| UConn | 2 | 0.0% | 3.6% | 0.02 |
| Gonzaga | 3 | 0.0% | 1.9% | 0.01 |
| Iowa St. | 2 | 0.0% | 1.8% | 0.02 |

## Key Differentiators (Optimal Bracket)

High-leverage picks that separate the optimal bracket from the field:

1. **Illinois** to F4 -- Leverage: 0.5080, Seed: 3, Public: 3.0%, In 46% of our brackets
2. **Purdue** to F4 -- Leverage: 0.3543, Seed: 2, Public: 7.5%, In 42% of our brackets
3. **NC State** to R32 -- Leverage: 0.3384, Seed: 11, Public: 2.7%, In 100% of our brackets
4. **Illinois** to E8 -- Leverage: 0.3092, Seed: 3, Public: 9.2%, In 62% of our brackets
5. **SMU** to R64 -- Leverage: 0.2615, Seed: 11, Public: 11.8%, In 100% of our brackets
6. **Vanderbilt** to S16 -- Leverage: 0.2386, Seed: 5, Public: 10.6%, In 54% of our brackets
7. **NC State** to R64 -- Leverage: 0.2143, Seed: 11, Public: 15.3%, In 100% of our brackets
8. **Purdue** to E8 -- Leverage: 0.2061, Seed: 2, Public: 15.8%, In 92% of our brackets
9. **Iowa St.** to E8 -- Leverage: 0.2005, Seed: 2, Public: 16.4%, In 38% of our brackets
10. **Illinois** to S16 -- Leverage: 0.1679, Seed: 3, Public: 20.4%, In 71% of our brackets
11. **VCU** to R64 -- Leverage: 0.1360, Seed: 11, Public: 26.5%, In 100% of our brackets
12. **Santa Clara** to R64 -- Leverage: 0.1262, Seed: 10, Public: 28.8%, In 100% of our brackets

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
