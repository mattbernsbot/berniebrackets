# PLAN AMENDMENT: Upset Prediction & Strategy Differentiation

**Status:** Proposed  
**Date:** 2026-03-15  
**Problem:** The optimizer produces near-chalk brackets across all three strategies with zero meaningful upsets (no 12/5, 14/3, or Cinderella runs). The aggressive bracket underperforms chalk. Root causes are identified below with specific fixes.

---

## Table of Contents

1. [Diagnosis: Why the Current System Fails](#1-diagnosis)
2. [Historical Upset Distribution (Real Data)](#2-historical-upset-distribution)
3. [Upset Prediction Model](#3-upset-prediction-model)
4. [Bracket Construction Strategy Overhaul](#4-bracket-construction-strategy)
5. [Variance and Strategy Differentiation](#5-variance-and-differentiation)
6. [Implementation Changes](#6-implementation-changes)

---

## 1. Diagnosis: Why the Current System Fails <a name="1-diagnosis"></a>

There are **five compounding failures** that produce chalk:

### 1.1 The AdjEM Model Systematically Underestimates Underdogs

The core win probability formula `P = 1/(1+10^(-ΔEM/11.5))` is well-calibrated for regular-season games but **overestimates favorites in the tournament context.** Here's why:

- **Tournament games are structurally different.** Teams have a week to prepare for one opponent (vs. 2-3 days in regular season). Preparation disproportionately helps underdogs because their coaches can game-plan against specific strengths.
- **AdjEM adjusts for strength of schedule, but SOS adjustments have higher uncertainty for mid-majors.** A 12-seed from the Missouri Valley with AdjEM +12 may be underestimated because their SOS adjustment is less reliable than a 5-seed from the Big 12.
- **The possession-variance adjustment in the current code helps favorites further** by reducing variance for high-tempo games, compounding the chalk bias.

**Concrete example:** For a 5-seed (AdjEM +16) vs 12-seed (AdjEM +10), ΔEM = 6:
- Current model gives: P(5 wins) ≈ 0.76
- After seed prior (w=0.75): P(5 wins) ≈ 0.73  
- **Historical reality: P(5 wins) = 0.649** — the model overstates the favorite by 8+ percentage points

### 1.2 Seed Prior Blending Is Too Weak

The current `w = 0.75` (75% model, 25% historical) is insufficient. The model already agrees with the historical direction (higher seeds win more), so blending barely moves the number. For first-round games where we have 150+ data points per seed matchup, historical rates should carry **more** weight.

### 1.3 Bracket Construction Is Bottom-Up, Not Top-Down

The PLAN specifies champion-first bracket construction. The actual code in `construct_candidate_bracket()` builds **bottom-up** (Round 1 → Round 6), meaning the champion is whoever survives a gauntlet of probability-threshold decisions. This makes the champion a by-product rather than a strategic choice, and it means later-round picks can't inform first-round strategy.

### 1.4 The Upset Budget Is a Count, Not a Distribution

The current system says "max N upsets in R1" but treats all upsets equally. An 8-over-9 upset is a 50/50 coin flip that provides zero pool differentiation. A 12-over-5 upset is a meaningful pick. A 14-over-3 or 15-over-2 is a bold Cinderella bet. The system needs to reason about **what kind** of upsets, not just how many.

### 1.5 Leverage Calculation Has a Default-Value Bug

When ownership data is missing (common), `round_ownership.get(2, 0.5)` defaults to **0.5**, which makes leverage artificially low. A 12-seed with actual ownership of 12.5% gets calculated as if 50% of brackets pick them. This kills almost all upset leverage signals.

---

## 2. Historical Upset Distribution (Real Data) <a name="2-historical-upset-distribution"></a>

### 2.1 First-Round Upset Rates by Seed Matchup (1985-2024, 156 tournaments worth of games per matchup)

| Matchup | Higher Seed Win % | Upset Rate | Avg Upsets per Tournament (4 games) | Notes |
|---------|-------------------|------------|-------------------------------------|-------|
| 1 vs 16 | 99.3% | 0.7% | 0.03 | Only 2 ever: UMBC (2018), FDU (2023) |
| 2 vs 15 | 93.8% | 6.2% | 0.25 | ~1 every 4 years; Oral Roberts (2021), Saint Peter's (2022) |
| 3 vs 14 | 85.1% | 14.9% | 0.60 | Roughly 1 every other year |
| 4 vs 13 | 79.3% | 20.7% | 0.83 | ~1 per year on average |
| 5 vs 12 | 64.9% | 35.1% | 1.40 | **Most reliable upset spot.** At least 1 happens ~72% of years. Two happen ~35% of years. |
| 6 vs 11 | 62.5% | 37.5% | 1.50 | Historically slightly more upset-prone than 5/12 thanks to First Four 11-seeds being hot |
| 7 vs 10 | 60.7% | 39.3% | 1.57 | Very competitive matchup |
| 8 vs 9 | 51.9% | 48.1% | 1.92 | Near coin-flip, almost exactly 2 per year |

### 2.2 Total Upsets Per Tournament (Lower Seed Wins)

Based on tournaments from 1985-2024:

| Round | Avg Upsets per Tournament | Typical Range | Notes |
|-------|--------------------------|---------------|-------|
| Round of 64 | ~8.1 | 5-12 | A "normal" year has 7-9 first-round upsets |
| Round of 32 | ~3.5 | 2-6 | This is where Cinderellas get tested |
| Sweet 16 | ~1.8 | 0-4 | Higher seeds re-assert, but 1-2 surprises normal |
| Elite Eight | ~1.0 | 0-2 | Typically 1 underdog region champ |
| Final Four | ~0.5 | 0-1 | Lower seed wins semifinal ~once every 2 years |
| Championship | ~0.4 | 0-1 | Lower seed wins title ~40% of the time |

**Total upsets per tournament: ~15.3** (range: 10-22)

### 2.3 Distribution of First-Round Upsets by Type (per tournament)

A typical tournament's ~8 first-round upsets break down as:
- **~2 trivial upsets** (8/9 matchups): These are coin flips, not real differentiation
- **~3 competitive upsets** (7/10, 6/11): Happen frequently, moderate differentiation  
- **~2 classic upsets** (5/12, 4/13): The bread-and-butter upset picks
- **~1 shocker** (3/14 or rarer): Big upset that shakes a region
- **~0.25 stunner** (2/15 or 1/16): Once every 4 years

### 2.4 Probability of At Least One Upset by Matchup Type (per tournament)

These are critical for bracket construction — they tell us "should we pick at least one of these?"

| Matchup Type | P(≥1 upset across 4 games) | P(≥2 upsets) | Implication |
|---|---|---|---|
| 5 vs 12 | **72%** | 35% | You should almost always pick at least one 12-over-5 |
| 6 vs 11 | **77%** | 39% | Almost always pick at least one 11-over-6 |
| 7 vs 10 | **79%** | 42% | Almost always pick at least one 10-over-7 |
| 4 vs 13 | **60%** | 22% | More often than not, pick one 13-over-4 |
| 3 vs 14 | **47%** | 10% | Worth a pick in aggressive brackets |
| 2 vs 15 | **22%** | 2% | Very aggressive / large pool only |

### 2.5 Upset Advancement: How Far Do Upsets Go?

This is critical for bracket construction — if you pick a 12-seed upset, do you advance them?

| Seed | Avg R1 Wins (of 4 per tourney) | Of those, % that win R2 | % that reach S16 | % that reach E8 |
|------|-------------------------------|------------------------|-----------------|-----------------|
| 12 | 1.40 | ~35% (0.49 per tourney) | ~14% (0.20) | ~4% (0.06) |
| 11 | 1.50 | ~38% (0.57) | ~16% (0.24) | ~6% (0.09) |
| 10 | 1.57 | ~33% (0.52) | ~12% (0.19) | ~4% (0.06) |
| 13 | 0.83 | ~20% (0.17) | ~4% (0.03) | ~1% (0.01) |
| 14 | 0.60 | ~18% (0.11) | ~3% (0.02) | <1% |
| 15 | 0.25 | ~24% (0.06) | ~4% (0.01) | ~2% (0.005) |

**Key insight:** When a 12-seed wins R1, they have a ~35% chance of also winning R2 (often against a 4-seed). This is much higher than people expect because the matchup is favorable — 4-seeds are often flawed teams, and 12-seeds who just beat a 5-seed are genuinely good. **A 12-seed Sweet 16 pick (~14% of R1 upset winners) is a high-leverage pool differentiator.**

### 2.6 Factors That Correlate With Upsets

From academic research and sports analytics literature, ranked by predictive importance:

1. **AdjEM Gap < 6 points** (most important): When the efficiency gap is small, the higher seed's advantage is mostly seed-based, not quality-based. These games are close to 50/50 regardless of seed.

2. **Tempo Mismatch (slow underdog vs. fast favorite)**: Slow-tempo underdogs that play elite defense can compress the game into fewer possessions, increasing variance. This is the classic "any given night" mechanism. The current model has this backwards — it should be the underdog's advantage, not just a generic modifier.

3. **Experience & Coaching**: Programs with coaches who have multiple tournament wins tend to outperform seed expectations. Bob Huggins, Tom Izzo, Bill Self, Mark Few — their teams as underdogs win more than AdjEM predicts. The current system tracks this but the modifier is too small (+0.02 per appearance, max +0.05 is negligible).

4. **Mid-Major Regular Season Dominance**: A 12-seed that went 28-4 in their conference (even if the conference is weak) is battle-tested and confident. Teams with high win totals relative to their seed tend to upset more.

5. **Hot Streak / Momentum**: Teams that won their conference tournament (especially by winning 3+ games in 3+ days) are physically and mentally conditioned for March. The "auto-bid" modifier needs to apply to mid-majors too, not just power conferences.

6. **Geographic Proximity**: Teams playing in pods close to home have a crowd advantage that AdjEM doesn't capture. A 12-seed playing in their home state vs. a 5-seed 2,000 miles away has a real edge.

7. **Free Throw Shooting**: In close tournament games, free throws matter disproportionately. Teams that shoot >75% from the line tend to hold leads in tight games. Bad free throw shooting teams tend to collapse under pressure.

8. **Guard Play / Backcourt Experience**: Tournament games tighten in the last 5 minutes. Teams with experienced, composed guards who can handle pressure (ball security, free throws, shot creation) outperform. Junior/senior-heavy backcourts consistently outperform freshmen-heavy teams in March.

---

## 3. Upset Prediction Model <a name="3-upset-prediction-model"></a>

### 3.1 Two-Layer Probability Model

Replace the current single-model approach with a **two-layer system:**

**Layer 1: Base Win Probability (recalibrated)**
- Same AdjEM logistic model, but with **tournament-specific κ = 13.0** (instead of 11.5). The higher κ compresses probabilities toward 50%, reflecting the higher variance of single-elimination tournament play vs. regular season.
- Rationale: Tournament games have ~15% more upsets than regular-season games between the same teams, due to preparation time, pressure, neutral-site effects, and elimination stakes.

**Layer 2: Upset Propensity Score (new)**
- A per-team "upset danger score" for underdogs and "upset vulnerability score" for favorites.
- This is NOT a replacement for the win probability — it's a **modifier** that adjusts the base probability based on team-specific upset indicators.

### 3.2 Upset Propensity Score: Features & Weights

For each first-round matchup, compute an **Upset Propensity Score (UPS)** on a scale of 0.0 to 1.0:

```
UPS = w1*tempo_mismatch + w2*experience_edge + w3*momentum + 
      w4*efficiency_gap_small + w5*underdog_quality + w6*free_throw_edge
```

**Feature definitions:**

| Feature | Calculation | Weight | Rationale |
|---------|-------------|--------|-----------|
| `tempo_mismatch` | 1.0 if underdog tempo < 64 AND underdog AdjD < 94 AND favorite tempo > 69; else scaled 0-1 | 0.20 | Slow defensive underdogs compress variance |
| `experience_edge` | Underdog's tournament_appearances / 3.0, capped at 1.0 | 0.15 | Been-there-before matters for underdogs |
| `momentum` | 1.0 if underdog won conf tourney (auto_bid); 0.5 if won 5+ of last 7 | 0.15 | Hot teams stay hot in March |
| `efficiency_gap_small` | max(0, 1.0 - abs(ΔEM)/12.0) | 0.25 | Small AdjEM gaps mean the matchup is closer than the seed suggests |
| `underdog_quality` | max(0, (underdog_adj_em - SEED_DEFAULT_ADJEM[underdog_seed]) / 10.0), capped at 1.0 | 0.15 | Underdogs who are better than their seed expect |
| `free_throw_edge` | 1.0 if underdog FT% > 76% AND favorite FT% < 70%; scaled 0-1 otherwise | 0.10 | Late-game execution under pressure |

**How UPS modifies the probability:**

```python
def apply_upset_propensity(base_prob_favorite: float, ups: float, seed_fav: int, seed_dog: int) -> float:
    """Adjust win probability using Upset Propensity Score."""
    # Maximum adjustment depends on the seed gap
    # Closer seeds (5v12) can swing more than distant seeds (1v16)
    max_adjustment = {
        (1,16): 0.02, (2,15): 0.04, (3,14): 0.06, (4,13): 0.07,
        (5,12): 0.10, (6,11): 0.10, (7,10): 0.10, (8,9): 0.08
    }
    max_adj = max_adjustment.get((seed_fav, seed_dog), 0.05)
    
    # UPS of 0.5 = no change; >0.5 = upset more likely; <0.5 = favorite safer
    adjustment = (ups - 0.5) * 2.0 * max_adj
    
    return clamp(base_prob_favorite + adjustment, 0.01, 0.99)
```

This means a 12-seed with a high UPS (e.g., 0.85 — slow defensive team, hot streak, small AdjEM gap) could see the 5-seed's win probability drop from 0.71 to 0.64, which aligns with historical rates and makes the upset a legitimate pick.

### 3.3 Recalibrated Seed Prior Blending

Change the blending weight from a fixed `w = 0.75` to a **round-dependent and sample-dependent weight:**

| Round | Blending Weight (model) | Rationale |
|-------|------------------------|-----------|
| R1 (64) | 0.60 | We have 156+ games per seed matchup; historical data is very reliable |
| R2 (32) | 0.65 | ~78 games per matchup type; still highly reliable |
| S16 | 0.70 | Fewer samples but matchups vary more |
| E8+ | 0.80 | Limited samples, model should dominate |

For R1 specifically, the formula becomes:
```
final_prob = 0.60 * model_prob_with_ups + 0.40 * historical_prob
```

This is a significant shift. For the 5v12 example:
- Model prob with UPS (typical): P(5 wins) ≈ 0.70
- Historical: 0.649
- Blended: 0.60 * 0.70 + 0.40 * 0.649 = 0.420 + 0.260 = 0.680

P(12 wins) = 0.320 — much more realistic and actionable.

### 3.4 Team-Level Upset Identification

Beyond the statistical model, implement a **team-tagging system** that flags specific upset candidates:

**Tier 1 — Strong Upset Candidates (pick in balanced + aggressive):**
- 12-seed with AdjEM within 6 points of the 5-seed AND (auto_bid OR experienced coach)
- 11-seed with AdjEM within 4 points of the 6-seed AND slow defensive style
- 10-seed with AdjEM within 3 points of the 7-seed (nearly even matchups)
- Any mid-major with 28+ wins and a top-40 KenPom ranking seeded 10+ (under-seeded killers)

**Tier 2 — Moderate Upset Candidates (pick in aggressive, consider in balanced):**
- 13-seed with AdjEM within 8 points of the 4-seed AND elite defense (AdjD < 96)
- 14-seed with AdjEM within 5 points of the 3-seed (rare, but Cleveland State/Mercer/Abilene Christian type)
- 11-seed from a power conference (at-large or First Four) — these are effectively "under-seeded" teams
- Any team with a top-25 defense and tempo < 64

**Tier 3 — Longshot Upset Candidates (aggressive only, for large pools):**
- 15-seed with a legitimate offensive weapon (top-50 AdjO) — Oral Roberts type
- 14-seed that won its conference tournament by beating a tournament-caliber team
- Any team from a conference that had another team upset a higher seed in the same tournament (conference quality signaling)

---

## 4. Bracket Construction Strategy Overhaul <a name="4-bracket-construction-strategy"></a>

### 4.1 Top-Down Construction (Fix the Build Order)

The current code builds bottom-up (R1 → R6). The PLAN specifies top-down (champion → R1). **Implement the plan as written.** The build order matters because:

1. Champion selection determines one entire region's structure
2. Final Four selection determines all four regional outcomes
3. Upset picks in early rounds should be **informed by** later-round picks (if you pick a 12-seed to reach the Sweet 16, you must also pick them to win R1 and R2 — these aren't independent decisions)

**Revised construction order:**
1. Select champion (highest leverage × probability product)
2. Select Final Four (3 additional teams)
3. Build each FF team's path backward to R1 (identify which teams they beat)
4. Fill remaining games in each region, working outward from the regional path
5. Apply upset distribution targets (see 4.2)
6. Validate consistency

### 4.2 Upset Distribution Targets by Strategy

Instead of a simple "max N upsets" count, use **distribution targets** that reflect historical reality:

**Conservative Strategy Target (aim for ~6 first-round upsets):**
- 8/9 upsets: Pick 2 (of 4) — just pick the better team by AdjEM
- 7/10 upsets: Pick 1 (of 4) — the single best 10-seed
- 6/11 upsets: Pick 1 (of 4) — the single best 11-seed
- 5/12 upsets: Pick 1 (of 4) — the single best 12-seed
- 4/13 upsets: Pick 1 (of 4) — only if strong candidate exists
- 3/14 or higher: Pick 0

**Balanced Strategy Target (aim for ~8 first-round upsets):**
- 8/9 upsets: Pick 2 (of 4) — the two better teams
- 7/10 upsets: Pick 1-2 (of 4) — best candidates
- 6/11 upsets: Pick 1-2 (of 4) — best candidates
- 5/12 upsets: Pick 1-2 (of 4) — at least 1 is mandatory given 72% historical frequency
- 4/13 upsets: Pick 1 (of 4) — the best candidate
- 3/14 upsets: Pick 0-1 — only with a strong Tier 2 candidate

**Aggressive Strategy Target (aim for ~10 first-round upsets):**
- 8/9 upsets: Pick 2-3 (of 4) — follow the model
- 7/10 upsets: Pick 2 (of 4)
- 6/11 upsets: Pick 2 (of 4) 
- 5/12 upsets: Pick 2 (of 4) — two is a real contrarian move
- 4/13 upsets: Pick 1-2 (of 4)
- 3/14 upsets: Pick 1 (of 4) — the single best Cinderella candidate
- 2/15 upsets: Pick 0-1 — only with exceptional circumstances (pool size > 50)

### 4.3 Upset Advancement Rules

A critical missing concept: **when you pick an upset winner, how far do you advance them?**

**Rule: Advance upset picks based on their Upset Propensity Score and the bracket path:**

| Scenario | Advancement Rule | Example |
|----------|-----------------|---------|
| 12-seed beats 5-seed, faces 4-seed in R2 | Advance if UPS > 0.65 AND AdjEM gap < 8 vs 4-seed | Strong 12-seed can reach Sweet 16 |
| 12-seed beats 5-seed, faces 13-seed in R2 | Always advance (12-seed is the favorite) | If you also picked 13-over-4 in the other half |
| 11-seed beats 6-seed, faces 3-seed in R2 | Advance only if UPS > 0.75 AND model gives >35% | Rare but memorable (Loyola-Chicago 2018) |
| 10-seed beats 7-seed, faces 2-seed in R2 | Rarely advance (2-seeds are very strong) | Only in aggressive, with exceptional 10-seed |
| 13+ seed wins R1 | Almost never advance | The pool value is in the R1 pick alone |

**Key principle:** In a 25-person pool, picking a 12-seed to the Sweet 16 is enormously differentiating. If only ~3-5% of public brackets have that pick and it hits, you get 40 points (S16) + 20 points (R32) + 10 points (R1) = 70 bonus points vs. the field. That's worth more than 7 correct first-round chalk picks combined.

### 4.4 Region-Aware Upset Distribution

Upsets should NOT cluster in one region. Rules:

1. **Each region should have 1-3 first-round upsets** (not 5 in one and 0 in another)
2. **The champion's region should have the fewest upsets** (protect the champion's path unless the upset is far from their bracket quadrant)
3. **The "chaos region" (if any) should be opposite the champion** — this maximizes the chance that the champion's path is clear while we farm upset points in a different region
4. **Never pick more than one Cinderella run (S16+) per region** — they cannibalize each other's advancement probability

### 4.5 Late-Round Upset Picks

The current system ignores late-round upsets entirely. Historical data shows:

- **~1.8 Sweet 16 games are won by the lower seed** per tournament
- **~1 Elite Eight game is won by the lower seed** per tournament
- A single correct Elite Eight upset is worth 80 points — equal to 8 correct R1 picks

**Late-round upset rules:**
- In the balanced bracket, pick at least 1 lower seed to reach the Final Four (a 3/4/5-seed winning their region instead of the 1 or 2-seed)
- In the aggressive bracket, pick 1-2 non-1-seeds as regional champions
- The champion should be a 1-4 seed in conservative/balanced, and a 2-6 seed in aggressive
- Never pick a 1-seed to win it all in the aggressive bracket — by definition, the aggressive bracket's value comes from correctly predicting an unusual champion

---

## 5. Variance and Strategy Differentiation <a name="5-variance-and-differentiation"></a>

### 5.1 The Three Brackets Must Be Fundamentally Different

The current system's three strategies share 97%+ of their picks. This is useless. The three brackets should represent three **different theories of the tournament:**

**Conservative = "The Best Chalk-Plus"**
- Champion: The most likely champion (usually a top-2 overall seed with the easiest path)
- Final Four: 3 of the 4 top seeds (e.g., three 1-seeds + one 2-seed)
- Upsets: Only the most obvious ones (high-UPS 12-seeds, 10/7 near-toss-ups)
- Target: ~6 R1 upsets, 0-1 regional upsets (non-1-seed winning a region)
- Goal: Maximize P(top 3) — finish near the top even if you don't win
- Expected P(1st): 5-7% in a 25-person pool (slightly above 4% random chance)

**Balanced = "The Smart Contrarian"**
- Champion: A leveraged pick — a team the model likes more than the public (often a 2-3 seed, or a strong 1-seed the public is overlooking for a sexier 1-seed)
- Final Four: 2 chalk + 1-2 contrarian picks (a 3-4 seed with high leverage)
- Upsets: The statistically best candidates across all tiers
- Target: ~8 R1 upsets, 1-2 non-chalk regional outcomes
- Goal: Maximize P(1st) — the single bracket most likely to win
- Expected P(1st): 7-10% in a 25-person pool

**Aggressive = "The Chaos Theory"**
- Champion: A high-leverage pick the public is sleeping on (a 3-5 seed with elite metrics, or a 2-seed with an easy path that everyone passed over for a flashier 1-seed)
- Final Four: At most 2 top-2 seeds; at least 1 pick of 4+ seed
- Upsets: Heavy upset load including at least one "Cinderella to the Sweet 16" and one "mid-seed wins region"
- Target: ~10 R1 upsets, 2 non-chalk regional outcomes
- Goal: Maximize P(1st) in a scenario where chaos happens — this bracket wins BIG in upset-heavy years, and bombs in chalk years
- Expected P(1st): 4-8% (lower floor, higher ceiling than balanced)

### 5.2 Minimum Differentiation Requirements

Enforce these constraints between the three brackets:

| Dimension | Minimum Difference |
|-----------|-------------------|
| Champion | At least 2 of 3 brackets must have different champions |
| Final Four | At least 2 different FF teams between brackets (e.g., conservative has Duke, balanced has Houston) |
| R1 upsets | Aggressive must have ≥3 more R1 upsets than conservative |
| Cinderella picks (seed 11+) | Aggressive must advance at least one 11+ seed to S16; conservative must not |
| Regional champions | At least 1 region must have different winners across all 3 brackets |

### 5.3 Deterministic, Not Random

Each bracket should be **deterministically optimal for its risk profile.** No randomization. Given the same input data, the same three brackets should be produced. Randomization is for Monte Carlo evaluation, not bracket construction.

The current approach of using threshold parameters to produce "three flavors of the same bracket" must be replaced with three genuinely different construction algorithms (see §6).

### 5.4 Pool Size Adjustments

The risk curve should also affect upset TYPE, not just count:

| Pool Size | Champion Seed Range | Expected R1 Upsets | Cinderella Depth |
|-----------|--------------------|--------------------|------------------|
| ≤10 | 1-2 seeds only | 5-6 | None |
| 11-25 | 1-3 seeds | 7-9 | One S16 possible |
| 26-50 | 1-4 seeds | 8-10 | One S16 likely |
| 51-100 | 2-5 seeds (contrarian) | 9-12 | One E8 possible |
| 100+ | 3-6 seeds (very contrarian) | 10-13 | One FF possible |

---

## 6. Implementation Changes <a name="6-implementation-changes"></a>

### 6.1 Changes to `constants.py`

**Add the following new constants:**

```python
# Historical upset distribution targets per tournament (of 4 games each)
# Maps (favorite_seed, underdog_seed) -> expected_upsets_per_tournament
EXPECTED_UPSETS_PER_TOURNAMENT: dict[tuple[int, int], float] = {
    (1, 16): 0.03,
    (2, 15): 0.25,
    (3, 14): 0.60,
    (4, 13): 0.83,
    (5, 12): 1.40,
    (6, 11): 1.50,
    (7, 10): 1.57,
    (8, 9): 1.92,
}

# Probability of at least 1 upset in this matchup type (across 4 games)
P_AT_LEAST_ONE_UPSET: dict[tuple[int, int], float] = {
    (1, 16): 0.03,
    (2, 15): 0.22,
    (3, 14): 0.47,
    (4, 13): 0.60,
    (5, 12): 0.72,
    (6, 11): 0.77,
    (7, 10): 0.79,
    (8, 9): 0.93,
}

# Conditional advancement probability: given R1 upset, P(also wins R2)
UPSET_ADVANCEMENT_RATE: dict[int, float] = {
    9: 0.40,   # 9-seeds who beat 8-seeds often face 1-seed → lose
    10: 0.33,  # 10-seeds who beat 7-seeds face 2-seed → usually lose
    11: 0.38,  # 11-seeds who beat 6-seeds face 3-seed → sometimes advance
    12: 0.35,  # 12-seeds who beat 5-seeds face 4-seed → real chance
    13: 0.20,  # 13-seeds who beat 4-seeds face 5-seed or 12-seed → possible
    14: 0.18,  # 14-seeds who beat 3-seeds face 6/11-seed → slim
    15: 0.24,  # 15-seeds who beat 2-seeds face 7/10-seed → St. Peter's did it
    16: 0.00,  # 16-seeds who beat 1-seeds face 8/9-seed → UMBC lost immediately
}

# Strategy-specific upset distribution targets
# Maps strategy -> {(fav_seed, dog_seed): (min_upsets, max_upsets)}
UPSET_TARGETS: dict[str, dict[tuple[int, int], tuple[int, int]]] = {
    "conservative": {
        (8, 9): (1, 3), (7, 10): (0, 2), (6, 11): (0, 2),
        (5, 12): (1, 1), (4, 13): (0, 1), (3, 14): (0, 0),
        (2, 15): (0, 0), (1, 16): (0, 0),
    },
    "balanced": {
        (8, 9): (1, 3), (7, 10): (1, 2), (6, 11): (1, 2),
        (5, 12): (1, 2), (4, 13): (0, 1), (3, 14): (0, 1),
        (2, 15): (0, 0), (1, 16): (0, 0),
    },
    "aggressive": {
        (8, 9): (2, 3), (7, 10): (1, 3), (6, 11): (1, 3),
        (5, 12): (1, 3), (4, 13): (1, 2), (3, 14): (0, 1),
        (2, 15): (0, 1), (1, 16): (0, 0),
    },
}

# Upset Propensity Score feature weights
UPS_WEIGHTS = {
    "tempo_mismatch": 0.20,
    "experience_edge": 0.15,
    "momentum": 0.15,
    "efficiency_gap_small": 0.25,
    "underdog_quality": 0.15,
    "free_throw_edge": 0.10,
}

# Max probability adjustment from UPS by seed matchup
UPS_MAX_ADJUSTMENT: dict[tuple[int, int], float] = {
    (1, 16): 0.02, (2, 15): 0.04, (3, 14): 0.06, (4, 13): 0.07,
    (5, 12): 0.10, (6, 11): 0.10, (7, 10): 0.10, (8, 9): 0.08,
}

# Seed-based default AdjEM for tournament teams (CORRECTED - all positive for tourney teams)
SEED_DEFAULT_ADJEM: dict[int, float] = {
    1: 28.0, 2: 23.0, 3: 19.0, 4: 16.0,
    5: 14.0, 6: 12.0, 7: 10.0, 8: 8.0,
    9: 7.0, 10: 6.0, 11: 5.0, 12: 6.0,
    13: 3.0, 14: 2.0, 15: 0.0, 16: -2.0,
}

# Champion seed distribution (historical %)
CHAMPION_SEED_FREQUENCY: dict[int, float] = {
    1: 0.60, 2: 0.18, 3: 0.10, 4: 0.04, 5: 0.02,
    6: 0.03, 7: 0.02, 8: 0.01, 9: 0.00, 10: 0.00,
    11: 0.00, 12: 0.00, 13: 0.00, 14: 0.00, 15: 0.00, 16: 0.00,
}

# Strategy champion seed ranges
STRATEGY_CHAMPION_SEEDS: dict[str, list[int]] = {
    "conservative": [1, 2],
    "balanced": [1, 2, 3, 4],
    "aggressive": [2, 3, 4, 5, 6],
}
```

**Fix the existing `SEED_DEFAULT_ADJEM`:** The current values have 11-16 seeds as negative, which is unrealistic for tournament teams. A 16-seed tournament team typically has an AdjEM around -2 to +2, not -15. This matters when KenPom data is unavailable.

### 6.2 Changes to `sharp.py`

#### 6.2.1 New Function: `compute_upset_propensity_score()`

```
def compute_upset_propensity_score(favorite: Team, underdog: Team) -> float
    """Compute the Upset Propensity Score (UPS) for a matchup.
    
    Evaluates 6 features that predict upset likelihood beyond raw AdjEM:
    tempo_mismatch, experience, momentum, efficiency_gap, underdog_quality, free_throw_edge.
    
    Args:
        favorite: The higher-seeded (lower seed number) team.
        underdog: The lower-seeded (higher seed number) team.
    
    Returns:
        UPS value between 0.0 and 1.0. Higher = more upset-prone.
        0.5 = neutral, >0.7 = strong upset candidate, <0.3 = chalk is safe.
    """
```

#### 6.2.2 New Function: `apply_upset_propensity_modifier()`

```
def apply_upset_propensity_modifier(base_prob_favorite: float, ups: float, seed_fav: int, seed_dog: int) -> float
    """Adjust win probability using the Upset Propensity Score.
    
    Uses UPS_MAX_ADJUSTMENT to determine the maximum swing for this seed pairing.
    UPS > 0.5 shifts probability toward the underdog.
    UPS < 0.5 shifts probability toward the favorite.
    
    Args:
        base_prob_favorite: Base probability that the favorite wins.
        ups: Upset Propensity Score (0-1).
        seed_fav: Favorite's seed.
        seed_dog: Underdog's seed.
    
    Returns:
        Adjusted win probability for the favorite, clamped to [0.01, 0.99].
    """
```

#### 6.2.3 Modify `adj_em_to_win_prob()`

- Change κ from 11.5 to **13.0** for tournament games. This single change compresses all probabilities toward 50%, producing more realistic upset rates.
- Optionally, make κ a parameter so it can be tuned: `def adj_em_to_win_prob(..., kappa: float = 13.0)`
- **Remove or reduce the possession-variance adjustment.** It currently helps favorites, which is the wrong direction for tournament games where fewer possessions help underdogs.

#### 6.2.4 Modify `apply_seed_prior()`

- Change blending weight from fixed `w = 0.75` to round-dependent:
  - R1: `w = 0.60`
  - R2: `w = 0.65`
  - S16: `w = 0.70`
  - E8+: `w = 0.80`
- Pass `round_num` as a parameter.

#### 6.2.5 Modify `compute_matchup_probability()`

- Add `round_num` parameter
- Insert `apply_upset_propensity_modifier()` into the modifier pipeline (after experience, before seed prior)
- Pass `round_num` to `apply_seed_prior()`
- Increase the experience modifier from +0.02 to +0.03 per appearance, cap at +0.06 (currently nearly invisible)
- Apply the auto-bid momentum modifier to **all conferences**, not just power conferences. A mid-major that won 4 games in 4 days to get their auto-bid is peaking.

### 6.3 Changes to `optimizer.py`

This module needs the most extensive rework.

#### 6.3.1 New Function: `rank_upset_candidates()`

```
def rank_upset_candidates(teams: list[Team], matchup_matrix: dict, bracket: BracketStructure, ownership_profiles: list[OwnershipProfile]) -> list[dict]
    """Rank all potential first-round upsets by composite score.
    
    For each R1 game where the underdog has a reasonable chance (>15%), 
    compute a composite score combining:
    - Upset probability (from matchup_matrix, which now includes UPS)
    - Leverage (model prob / public ownership for advancing)
    - Pool value (points gained × probability × leverage)
    - Advancement potential (can this team win R2 too?)
    
    Returns:
        List of dicts sorted by composite_score descending:
        {slot_id, favorite, underdog, upset_prob, leverage, composite_score,
         ups, advancement_prob, tier (1/2/3)}
    """
```

#### 6.3.2 New Function: `select_upsets_by_distribution()`

```
def select_upsets_by_distribution(ranked_candidates: list[dict], strategy: str, bracket: BracketStructure) -> list[int]
    """Select which upsets to include based on distribution targets.
    
    Uses UPSET_TARGETS[strategy] to ensure the right MIX of upsets:
    - At least the minimum for each seed matchup type
    - At most the maximum
    - Distributed across regions (max 3 upsets per region)
    - Champion's region gets fewer upsets
    
    Selects the BEST candidates within each category (highest composite score),
    not random ones.
    
    Args:
        ranked_candidates: Output of rank_upset_candidates().
        strategy: "conservative", "balanced", or "aggressive".
        bracket: For region awareness.
    
    Returns:
        List of slot_ids where upsets should be picked.
    """
```

#### 6.3.3 Rewrite `construct_candidate_bracket()` — Top-Down Build

The function must be restructured to build top-down:

**Phase 1: Select Champion**
- Filter to `STRATEGY_CHAMPION_SEEDS[strategy]`
- For each candidate, compute: `champion_score = title_probability * title_leverage`
  - `title_probability`: From quick 1000-sim Monte Carlo (existing logic, but use recalibrated probabilities)
  - `title_leverage`: `title_probability / title_ownership`
- Additional filter: champion must have a "clearable path" (no opponent on their path is rated significantly higher than them)
- Select the champion with the highest `champion_score`
- **Key constraint for differentiation:** The aggressive bracket's champion must differ from the conservative bracket's champion. If the balanced bracket ends up with the same champion as conservative, force the 2nd-best candidate.

**Phase 2: Select Final Four**
- For each remaining region, select the regional champion using a similar `regional_score = advance_probability * leverage` metric
- Conservative: prefer 1-2 seeds
- Balanced: at least 1 FF team must be seed 3+
- Aggressive: at least 1 FF team must be seed 4+, and at least 2 FF teams must differ from the conservative bracket

**Phase 3: Build Paths**
- For each FF team, trace their path from the regional final back to R1
- At each step, determine who they play (from the other half of their sub-bracket)
- This inherently creates some later-round upset picks (e.g., if a 3-seed is your regional champion, they beat a 1-seed in the E8)

**Phase 4: Fill Remaining Games**
- Use `select_upsets_by_distribution()` for all first-round games NOT on a FF team's path
- For R2-R3 games not on a path, use straight probability (adjusted by UPS)
- Apply region-balancing constraints

**Phase 5: Validate and Score**
- Enforce bracket consistency (every advancing team won all prior games)
- Count upsets by type, verify within distribution targets
- If targets not met, adjust (e.g., if no 12/5 upset was selected, force the best candidate)

#### 6.3.4 Fix `generate_public_bracket()`

The current implementation has a bug: the `round_ownership.get(2, 0.5)` default of 0.5 means opponent brackets are too chalky when real ownership data is missing. Fix:

- Default should be `SEED_OWNERSHIP_CURVES[seed][round_num]` (from constants), not 0.5
- Opponent brackets should reflect historical upset rates, not pure chalk. About 8/32 R1 games (~25%) should be upsets in opponent brackets too, matching public behavior.

#### 6.3.5 Add Perturbation Search (Currently Missing from Code)

The PLAN describes a perturbation search in Phase 3 of optimization. **This is not implemented in the current code.** Add it:

```
def perturb_bracket(bracket: CompleteBracket, perturbation_type: str, ...) -> CompleteBracket
    """Create a variant of a bracket by modifying key picks.
    
    perturbation_type:
    - "champion_swap": Replace champion with next-best candidate
    - "ff_swap": Replace one FF team with next-best candidate
    - "upset_toggle": Add or remove the highest-leverage upset pick
    - "advancement_toggle": Change whether an upset winner advances in R2
    
    Returns:
        New bracket with the perturbation applied, bracket consistency maintained.
    """
```

After evaluating the 3 base strategies, generate 2-3 perturbations of the best-performing bracket and re-evaluate them. This can find brackets in the "neighborhood" of the best strategy that perform even better.

### 6.4 Changes to `contrarian.py`

#### 6.4.1 Fix Default Ownership Values

When ESPN pick data is unavailable, the fallback must use `SEED_OWNERSHIP_CURVES` correctly. Currently, code paths use `0.5` as a default, which breaks leverage calculations. Every access to `round_ownership` should fall back to the appropriate seed-based curve value, never to 0.5.

#### 6.4.2 Add Differentiation-Weighted Ownership

For pool optimization, what matters isn't just "how many people pick Duke to win" but "how many people in YOUR POOL pick Duke to win." In a 25-person pool, there's significant variance — some pools are more chalky than others.

Add a `pool_variance_adjustment` that accounts for this:
- In a 25-person pool, if 25% of all brackets pick Duke as champion, the expected number of Duke champions in a random pool is 6.25 — but with variance, some pools will have 3 and others will have 9.
- The leverage calculation should account for this variance: having the same champion as 3/25 opponents is very different from 9/25.
- For the Monte Carlo simulation, this is already handled by generating random opponent brackets. But for the initial bracket construction heuristic, we should use the **expected unique holders** metric, not raw ownership percentage.

### 6.5 New Data Requirements

#### 6.5.1 Team Features for UPS (Add to Team Model or Compute from Existing)

The UPS calculation needs these features, some of which aren't currently in the Team model:

| Feature | Source | In Current Model? | Action |
|---------|--------|-------------------|--------|
| AdjEM | KenPom | ✅ Yes | Use as-is |
| AdjD (defense) | KenPom | ✅ Yes | Use as-is |
| AdjT (tempo) | KenPom | ✅ Yes | Use as-is |
| Auto-bid | ESPN | ✅ Yes | Use as-is |
| Tournament appearances | Manual | ✅ Yes | Increase modifier weight |
| Free throw % | KenPom | ❌ No | Add to scraper — available on KenPom four factors page |
| Recent record (last 10) | ESPN | ❌ No | Optional — can approximate from W-L + conference tournament performance |

**Minimum viable addition:** Free throw percentage. It's available on KenPom's "Four Factors" data and is a strong upset predictor.

**Nice to have:** Guard experience (Jr/Sr backcourt), travel distance to pod, KenPom luck rating (high-luck teams tend to regress in March).

### 6.6 Summary of Priority Changes

**Critical (must-fix, highest impact on bracket quality):**
1. Change κ from 11.5 to 13.0 in `adj_em_to_win_prob()` — single highest-impact fix
2. Change seed prior weight to round-dependent (0.60 for R1 instead of 0.75)
3. Fix the default ownership fallback from 0.5 to `SEED_OWNERSHIP_CURVES[seed][round]`
4. Implement upset distribution targets (`UPSET_TARGETS`) instead of a simple count
5. Rewrite `construct_candidate_bracket()` to build top-down (champion-first)
6. Enforce minimum differentiation between the three strategy brackets

**Important (significant quality improvement):**
7. Add Upset Propensity Score (UPS) computation
8. Implement `rank_upset_candidates()` for intelligent upset selection
9. Add upset advancement logic (when to advance upsets past R1)
10. Fix `SEED_DEFAULT_ADJEM` for realistic tournament-team values

**Nice to have (further refinement):**
11. Add perturbation search (PLAN says it should exist, code doesn't have it)
12. Scrape free throw percentage for UPS calculation
13. Add geographic proximity as a modifier
14. Add pool-variance-adjusted ownership

### 6.7 Expected Impact

With these changes, the three brackets should produce:

| Metric | Conservative | Balanced | Aggressive |
|--------|-------------|----------|------------|
| R1 Upsets | 5-7 | 7-9 | 9-12 |
| Of which 12/5 | 1 | 1-2 | 2 |
| Of which 13+/4- | 0-1 | 1 | 1-2 |
| Cinderella S16 | 0 | 0-1 | 1 |
| Non-1-seed regional champ | 0-1 | 1 | 2 |
| Champion seed | 1 | 1-3 | 2-5 |
| Shared picks between strategies | — | ~75% overlap w/ conservative | ~60% overlap w/ conservative |
| P(1st) in 25-person pool | 5-7% | 7-10% | 5-8% |
| P(top 3) | 15-22% | 14-18% | 10-15% |

The key outcome: **three genuinely different brackets that each represent a coherent theory of the tournament**, not three copies of chalk with slightly different thresholds.

---

## Appendix: Calibration Check

To validate the recalibrated model produces realistic upset rates, after implementation, run the following check:

1. Simulate 10,000 tournaments with the recalibrated probabilities
2. Count upsets by seed matchup type
3. Compare to historical frequencies:
   - 5v12 upsets per tournament should average 1.3-1.5 (not 0.5 or 2.5)
   - Total R1 upsets should average 7.5-8.5
   - 1-seeds should reach the Final Four ~55% of the time per region (not 80% or 30%)
4. If simulated rates deviate from historical by >15%, adjust κ and UPS weights

This calibration check should be automated as a test in `test_sharp.py`.
