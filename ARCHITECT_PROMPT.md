# ARCHITECT PROMPT: Redesign the Bracket Construction Algorithm

**From:** Dickie V, Statistical Consultant  
**To:** Software Architect  
**Re:** Complete redesign of the bracket optimizer's core algorithm  
**Priority:** This is the whole ballgame, baby.

---

## Preamble: Why You're Reading This

A bracket optimization system exists. It has a solid statistical model (`sharp.py`), good historical constants, and a reasonable ownership/leverage framework. The problem is the brain — `optimizer.py` — which takes all of these good inputs and produces brackets that lose to a coin flip. I gave it a D+. The optimizer needs to be redesigned from first principles.

Before you write a single line of code, I need you to deeply understand the **theory** of what we're trying to do. This isn't a refactoring exercise. The current algorithm has fundamental conceptual errors in how it thinks about pool optimization. I'm going to walk you through the mathematics and game theory of what "winning a bracket pool" actually means, then give you the design constraints for a correct algorithm.

**Critical ground rule:** The algorithm must be GENERIC. No team names, no year-specific logic, no hardcoded picks. If a particular team is the right champion pick, the algorithm must discover that from the data — team probabilities, ownership distributions, pool size, and scoring system. The system should work for any year, any tournament, any pool size, any scoring system. Think of it as a function: `f(probabilities, ownership, pool_size, scoring) → optimal_bracket`.

---

## Part I: The Theory of Pool Optimization

### 1.1 The Objective Function Is NOT Expected Score

This is the most important thing to understand. The current system conflates two very different objectives:

- **Maximize Expected Score:** Pick the most likely winner of every game. This produces a chalk bracket. It maximizes the average number of points you'll score across all possible tournament outcomes.
- **Maximize P(Finish 1st):** Construct a bracket that has the highest probability of scoring more points than every other bracket in the pool. This is what we actually want.

These are radically different objectives, and they diverge more as pool size increases. Here's why:

Imagine a 100-person pool. If you submit the maximum-expected-score bracket (pure chalk), maybe 20 other people submitted something very similar. When the chalk scenario plays out, you're competing with those 20 for first place — your P(1st | chalk scenario) ≈ 1/20 = 5%. When the non-chalk scenario plays out, you lose badly because you have no upset picks. Your overall P(1st) ends up around 3% — worse than the 1% you'd get by random chance, because you're concentrated in a scenario where you have tons of competition.

The fundamental insight: **P(1st) is maximized not by being right the most, but by being right when others are wrong.** The value of a correct pick is proportional to (a) the points it earns and (b) the inverse of how many opponents also have that pick. A correct pick that everyone has is worth almost nothing for winning the pool. A correct pick that nobody has is enormously valuable.

This is game theory, not statistics. You're playing against the field, not against the tournament.

### 1.2 The Formal Framework

Let me lay this out mathematically so you can implement it correctly.

Let:
- `B` = our bracket (a complete set of 63 picks)
- `O₁, O₂, ..., Oₙ` = the n opponent brackets in the pool (n = pool_size - 1)
- `T` = the actual tournament outcome (one of the possible bracket completions)
- `S(B, T)` = the score of bracket B given tournament outcome T
- `P(T)` = the probability of tournament outcome T

Then our objective is:

```
Maximize P(1st) = Σ_T P(T) × P(S(B, T) > S(Oᵢ, T) for all i)
```

This is intractable to compute exactly (the space of T is enormous), which is why we use Monte Carlo simulation. But the structure of this formula reveals everything:

1. **We need P(T)** — the probability of each tournament outcome. This comes from the matchup matrix. The current system has this (mostly) right.

2. **We need the distribution of opponent brackets** — what picks will the other people in the pool make? This comes from ownership data. The current system has a reasonable framework for this but the implementation has bugs.

3. **We need to find B that maximizes the sum** — this is the hard part. The current system uses a heuristic construction (champion → chalk → upset overlay) that doesn't actually optimize this objective.

### 1.3 The Champion Selection Problem

The champion pick is worth 320 points in ESPN standard scoring — 16.7% of the maximum possible score. Getting the champion right (when others don't) or wrong (when others are right) is the single biggest swing factor in pool outcomes.

**The current formula is: `champion_score = title_prob × leverage` where `leverage = title_prob / title_ownership`.**

This simplifies to: `champion_score = title_prob² / title_ownership`.

This is wrong. Here's why:

What we actually want is: for each candidate champion C, what is P(we finish 1st | we pick C as champion)?

```
P(1st | pick C) = P(C wins) × P(1st | C wins, we picked C) + P(C doesn't win) × P(1st | C doesn't win, we picked C)
```

The second term, `P(1st | C doesn't win, we picked C)`, is small but nonzero — you can still win the pool without the champion if you nail everything else. But the first term dominates.

`P(1st | C wins, we picked C)` depends critically on **how many opponents also picked C**. If k opponents picked C, then you're competing with them for first in the "C wins" scenario, and your probability of winning depends on whether your non-champion picks are better than theirs.

In a pool of size N, if the champion has ownership fraction `o`, the expected number of opponents who also picked that champion is `(N-1) × o`. Your probability of beating all of them is roughly `1 / ((N-1) × o + 1)` (simplified — assumes your other picks are average among champion-pickers).

So the real champion value is approximately:

```
V(C) ≈ P(C wins) / ((N-1) × ownership(C) + 1)
```

Compare the current formula `title_prob² / ownership` against this correct formula `title_prob / ((N-1) × ownership + 1)`:

**Example: Pool size N=25, two candidate champions:**
- Team A: P(win) = 28%, ownership = 30%
- Team B: P(win) = 10%, ownership = 5%

Current formula:
- A: 0.28² / 0.30 = 0.261
- B: 0.10² / 0.05 = 0.200
- **Picks A** ✓

Correct formula:
- A: 0.28 / (24 × 0.30 + 1) = 0.28 / 8.2 = 0.034
- B: 0.10 / (24 × 0.05 + 1) = 0.10 / 2.2 = 0.045
- **Picks B** — because in a 25-person pool, having 7 opponents with the same champion kills your edge even though A is more likely to win.

Wait — which is actually right? It depends on pool size:
- In a 10-person pool: A: 0.28 / (9×0.30+1) = 0.072, B: 0.10 / (9×0.05+1) = 0.069 → **A wins** (small pool, pick the best team)
- In a 25-person pool: A: 0.034, B: 0.045 → **B wins** (medium pool, differentiation matters)
- In a 100-person pool: A: 0.28 / 31 = 0.009, B: 0.10 / 6 = 0.017 → **B wins big** (large pool, must differentiate)

**The formula must be pool-size-sensitive.** The current formula has no pool size parameter. This is a fundamental flaw.

But here's the deeper issue: even the improved formula above is a simplification because it treats "having the same champion" as making you equal to your opponents. In reality, even among brackets with the same champion, there's huge variance in the rest of the bracket. The Monte Carlo simulation handles this correctly by actually scoring full brackets against each other. The champion selection heuristic is just the starting point — it tells you which champion to evaluate, and then Monte Carlo tells you if it's actually good.

**My recommendation:** Use the pool-size-adjusted formula `V(C) ≈ P(C wins) / ((N-1) × ownership(C) + 1)` as the heuristic for champion selection during bracket construction. But also enforce these constraints:

1. **Minimum probability threshold:** Don't pick a champion with P(winning tournament) < some floor. A team with 1% title probability and 0.1% ownership has high leverage but almost never delivers. The floor should scale with pool size — a bigger pool tolerates lower-probability champions because you need more differentiation.

   Suggested thresholds:
   - Pool ≤ 10: champion must have P(title) ≥ 15%
   - Pool 11-25: P(title) ≥ 8%
   - Pool 26-50: P(title) ≥ 5%
   - Pool 51-100: P(title) ≥ 3%
   - Pool 100+: P(title) ≥ 2%

2. **Path quality:** The champion must have a plausible path. A team that has to beat three teams with higher AdjEM to reach the Final Four is a bad champion pick even if their leverage is great, because conditional on them winning the title, the rest of the bracket probably went chaotic in ways your bracket didn't predict. Compute `path_difficulty = product of P(champion beats each opponent on their path)`. Discount the champion value by path difficulty.

3. **No seed-range filtering.** The current system has `STRATEGY_CHAMPION_SEEDS = {"conservative": [1, 2], "aggressive": [2, 3, 4, 5, 6]}`. This is terrible. The aggressive strategy EXCLUDES 1-seeds, which means it can never pick the most likely champion, even when the most likely champion also has the best leverage. Delete this entirely. Let the formula decide. If a 1-seed has both high probability AND good leverage (because the pool is small or the public is distracted by a different 1-seed), the algorithm should pick them. If a 4-seed has better value, pick them. The math should decide, not hardcoded seed ranges.

### 1.4 The Upset Selection Problem

The current system selects upsets by ranking all possible upsets by a composite score and then picking the top N. This is wrong in several ways.

**Problem 1: Upsets are not independent decisions.**

Picking upset A changes the value of picking upset B, in two ways:

(a) **Path interaction:** If you pick a 12-seed to beat a 5-seed, the 4-seed in that quarter of the bracket now faces the 12-seed in R2 instead of the 5-seed. That makes the 4-seed much more likely to reach the Sweet 16 — which means picking the 4-seed in the Sweet 16 is now chalk, not a value play. Conversely, if you pick BOTH the 12-over-5 and the 13-over-4 in the same quarter, you've created a 12-vs-13 R2 game where your 12-seed is the favorite.

(b) **Frequency interaction:** Each additional upset you pick lowers the probability that your overall bracket is correct. Each wrong upset costs you the points for that game PLUS all future games that team would have played in. The cost of a wrong upset is not just 10 points (R1) — it's 10 + 20 + possibly 40 + 80 + ... depending on how far you had the favorite advancing. A wrong upset on a team you had in the Sweet 16 costs you 70 points.

The implication is that upsets should be selected jointly, considering the whole bracket, not independently from a ranked list. The current system's approach of "rank by composite score, take the top N" ignores these interactions entirely.

**Problem 2: Leverage is not the right primary metric for upset selection.**

The current composite score is `0.40 × upset_prob + 0.30 × leverage + 0.20 × ups + 0.10 × advancement_prob`. Let me break down what's wrong:

- **Leverage** (model_prob / public_ownership) measures how undervalued a pick is. A 14-seed that nobody picks has astronomical leverage. But leverage alone doesn't tell you if the pick is GOOD for winning the pool. A pick can be highly leveraged and still terrible because the probability is so low that you'll almost never collect the value.

- The right metric is **Expected Marginal Value (EMV)**: how much does adding this upset to my bracket increase my P(1st)?

```
EMV(upset) = P(1st | bracket_with_upset) - P(1st | bracket_without_upset)
```

This is expensive to compute exactly (requires Monte Carlo for each candidate upset), but you can approximate it:

```
EMV(upset) ≈ P(upset correct) × (points_gained × scarcity_factor) - P(upset wrong) × (points_lost × commonality_factor)
```

Where:
- `points_gained` = points for getting this game right (10 for R1, but also downstream if you advance the upset)
- `scarcity_factor` = 1 / (expected opponents with this pick + 1). Measures how differentiating this pick is.
- `points_lost` = points you would have earned if you'd picked the favorite and the favorite won (10 for R1, plus downstream points for the favorite's advancement)
- `commonality_factor` = fraction of opponents who picked the favorite. If everyone has the favorite, losing this pick doesn't hurt your relative standing much.

**A correct upset pick has positive EMV: the value when right × P(right) exceeds the cost when wrong × P(wrong), all adjusted for pool positioning.**

**Problem 3: The upset "budget" approach is backwards.**

The current system says "balanced strategy gets 7-9 upsets." This is backwards reasoning — it's saying "I want to look contrarian" rather than "I want to maximize P(1st)." The right number of upsets is whatever number maximizes P(1st), and that depends entirely on the specific matchups, the ownership data, and the pool size.

In a year where every 5-seed is vastly better than every 12-seed (big AdjEM gaps), picking any 12-over-5 upsets might be negative EMV. In a year where three of the four 5-vs-12 matchups are nearly even (AdjEM gap < 5), you might want to pick three 12-over-5 upsets.

The distribution targets in `UPSET_TARGETS` are useful as a sanity check and calibration baseline, but they should not be hard constraints on the algorithm. They should be soft priors that the optimizer can override when the data says otherwise.

### 1.5 Bracket Coherence: The Correlation Problem

This is the most subtle and most important concept that the current system completely ignores.

A bracket is a correlated set of predictions. Tournament outcomes are correlated — if a 12-seed beats a 5-seed in R1, it tells you something about the state of the tournament:

- Maybe the 12-seed is better than expected (they should be picked to advance further)
- Maybe this region is chaotic (other upsets in this region are more likely)
- The 4-seed in the same quarter just got an easier R2 matchup

The current system ignores all of this. It picks upsets as an overlay on chalk, and never advances upset winners past R1 (despite the PLAN_AMENDMENT calling for it).

**A coherent bracket tells a consistent story about the tournament.** It doesn't pick a 12-seed to beat a 5-seed and then pick the 5-seed's likely R2 opponent to go to the Elite 8 (because now that opponent faces the 12-seed, not the 5-seed, which is easier). It doesn't pick three Cinderella upsets in one region and also pick the 1-seed from that region as champion (because those Cinderellas would have to beat the 1-seed).

**Implementation approach — Scenario-Based Construction:**

Instead of building one bracket by making isolated decisions, think of bracket construction as choosing a **tournament scenario** — a coherent story about how the tournament plays out.

A scenario has these elements:
1. **Which teams are "for real"** — which teams perform at or above their seed expectations?
2. **Which teams are vulnerable** — which favorites underperform?
3. **Where does chaos concentrate** — which region(s) produce upsets?
4. **How does it resolve** — given the chaos, who emerges?

The algorithm should:
1. Generate 5-10 distinct scenarios (not thousands — each one should be a plausible, coherent narrative)
2. For each scenario, construct the bracket that follows from that narrative
3. Evaluate each scenario-bracket via Monte Carlo
4. Return the top performers

Example scenarios:
- **Scenario A (Chalk):** "The best teams win. Top overall seed dominates. 1-seeds hold serve. The few upsets are the standard 12-over-5 and 10-over-7 near-coin-flips."
- **Scenario B (One Cinderella):** "The tournament is mostly chalk, but one mid-major has a magical run to the Elite 8. Which mid-major? The one with the highest UPS and best path."
- **Scenario C (Chaos Region):** "One region goes haywire. The 1-seed in that region falls to a hot 4 or 5-seed. That region produces an unlikely Final Four team."
- **Scenario D (Contrarian Champion):** "The overall best team stumbles (maybe in the Elite 8 against a tough 2-seed). The champion comes from a different region — the 2-seed or 3-seed with the easiest path."

Each scenario naturally produces a coherent bracket with correlated picks. Scenario C, for example, would have extra upsets in the chaos region and fewer in others. It would have a non-1-seed from the chaos region in the Final Four, and other regions would be relatively chalky. This is much better than "pick 10 random upsets from a ranked list."

### 1.6 Expected Value vs. Variance: The Kelly Criterion Analogy

In gambling, the Kelly Criterion tells you how much to bet on a positive-EV proposition. It balances expected return against variance — even when you have an edge, overbetting destroys you.

Bracket pools have an analogous problem. Each contrarian pick adds variance to your bracket's score. A highly contrarian bracket (many upsets, longshot champion) has:
- **Higher ceiling:** If everything hits, you score far above the field
- **Lower floor:** If things go chalk, you finish last
- **Higher variance** in P(1st) across tournament outcomes

The optimal level of contrarianism depends on:
- **Pool size:** Larger pools require more variance (you need to separate from more opponents)
- **Number of entries:** If you submit 3 brackets, you can allocate risk — one conservative, one moderate, one aggressive. If you submit 1, you need to find the optimal risk level.
- **Scoring system:** Systems that heavily weight late rounds (like ESPN's exponential scoring) make champion selection even more important and reduce the value of early-round upsets.

The algorithm should have a **risk budget** that it allocates across decisions. The risk budget determines how much total probability you're "spending" on contrarian picks. A conservative bracket spends less risk; an aggressive bracket spends more. But the key insight is that the risk should be allocated OPTIMALLY — concentrated on the picks with the best risk-reward ratio, not spread evenly.

This means you might make 95% chalk picks and put ALL your risk budget on one huge contrarian play (e.g., a 3-seed as champion). Or you might spread the risk across many small contrarian picks (multiple R1 upsets). The algorithm should determine which allocation maximizes P(1st).

### 1.7 What a Sharp Actually Does

Let me tell you what separates a professional gambler's bracket from a casual fan's bracket. It's not about "picking more upsets." It's about three things:

**1. Conditional Probability Thinking**

A sharp doesn't ask "will Duke win the tournament?" They ask "conditional on Duke winning the tournament, what does the rest of the bracket look like, and can I differentiate within that scenario?"

If Duke wins, roughly 30% of the pool also has Duke. The sharp's edge comes from the OTHER 62 picks — getting the right upsets, right Cinderellas, right Final Four composition. The sharp picks upsets that are CONSISTENT with a world where Duke wins — maybe chaos in the opposite region (which doesn't affect Duke), maybe a specific 12-seed run that Duke never has to face.

**2. Game Theory Against the Field**

A sharp thinks about what OTHER people will pick, not just what's likely to happen. If ESPN runs a story about a 12-seed being "the upset special," that 12-seed's ownership skyrockets and its value as a contrarian pick drops. The sharp avoids the trendy upset and finds the UNFASHIONABLE one — the 12-seed that CBS barely mentioned but has elite defensive metrics.

This is why actual ESPN pick data (or a good proxy for it) is gold. Without it, you're estimating what the field will do based on historical seed-based patterns. With it, you know which specific teams are over-owned and under-owned THIS year.

**3. Information Edge Exploitation**

A sharp identifies where their model disagrees with the market (the public). A team that's AdjEM #12 but seeded as a 5 is under-seeded — the committee gave them a weaker seed than they deserve. The public picks based on seed. The sharp picks based on actual quality. This creates a systematic edge: under-seeded teams are under-owned relative to their quality, and over-seeded teams are over-owned.

The algorithm should explicitly compute "seed-adjusted quality" — how much better or worse is each team compared to the typical team at their seed? Teams with positive seed-adjusted quality are systematic value picks. Teams with negative seed-adjusted quality are systematic fades.

---

## Part II: Design Specification for the New Algorithm

### 2.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    BRACKET OPTIMIZER v2                         │
│                                                                 │
│  Input: teams[], matchup_matrix, ownership_profiles,            │
│         pool_size, scoring_system, num_entries                  │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  Champion     │  │  Scenario    │  │  Bracket             │  │
│  │  Evaluator    │─▶│  Generator   │─▶│  Constructor         │  │
│  │              │  │              │  │  (scenario → bracket) │  │
│  └──────────────┘  └──────────────┘  └──────────┬───────────┘  │
│                                                  │              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────▼───────────┐  │
│  │  Monte Carlo │  │  Perturbation│  │  Coherence           │  │
│  │  Evaluator   │◀─│  Engine      │◀─│  Validator           │  │
│  │              │  │              │  │                      │  │
│  └──────┬───────┘  └──────────────┘  └──────────────────────┘  │
│         │                                                       │
│         ▼                                                       │
│  Output: ranked list of brackets with P(1st) estimates          │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Component 1: Champion Evaluator

**Purpose:** Identify 3-5 viable champion candidates, each with an estimated pool-value score.

**Algorithm:**

```
function evaluate_champions(teams, matchup_matrix, ownership, pool_size, scoring):
    
    # Step 1: Estimate title probability for all teams
    # Use quick Monte Carlo (1000-2000 sims, no opponents needed)
    # Just simulate tournaments, count who wins
    title_probs = quick_monte_carlo_title_probs(matchup_matrix, bracket, sims=2000)
    
    # Step 2: Compute path difficulty for each contender
    # For each team, identify their most likely path to the title
    # path_difficulty = product of P(beat each opponent on path)
    # Use the actual bracket structure, not generic matchups
    for team in teams:
        team.path = compute_most_likely_path(team, matchup_matrix, bracket)
        team.path_difficulty = product(P(team beats opp) for opp in team.path)
    
    # Step 3: Compute pool-adjusted champion value
    for team in teams:
        if title_probs[team] < minimum_title_prob_threshold(pool_size):
            continue  # Skip teams with negligible title probability
        
        expected_opponents_with_same_champ = (pool_size - 1) * ownership[team].title_ownership
        
        # Pool-conditional value: P(I win | I pick this champion)
        # Rough approximation — Monte Carlo will refine this
        pool_value = title_probs[team] / (expected_opponents_with_same_champ + 1)
        
        # Penalty for difficult path (team may technically be able to win,
        # but if their path is brutal, the rest of our bracket suffers
        # because we have to pick chalk upsets elsewhere to make room)
        adjusted_value = pool_value * sqrt(team.path_difficulty)
        
        candidates.append((team, adjusted_value, title_probs[team]))
    
    # Step 4: Return top 3-5 candidates, sorted by adjusted_value
    return sorted(candidates, key=lambda x: x[1], reverse=True)[:5]
```

**Key differences from current system:**
- Pool size is a first-class parameter in the formula
- Path difficulty is considered (a strong team in a brutal region is worth less than a strong team with a cakewalk)
- NO seed-range filtering — any seed is eligible if the math works
- The output is a short list of candidates, not a single pick — scenarios will try different champions

### 2.3 Component 2: Scenario Generator

**Purpose:** Create 5-8 coherent tournament scenarios, each producing a different bracket.

**Algorithm:**

```
function generate_scenarios(champion_candidates, teams, matchup_matrix, ownership, bracket, pool_size):
    
    scenarios = []
    
    # Scenario type 1: "Chalk Plus" (1-2 scenarios)
    # The most likely tournament outcome with smart value adds
    # Champion: highest-probability candidate
    # FF: 3-4 of the top-4 overall seeds
    # Upsets: Only positive-EMV upsets (see 2.5)
    # Chaos level: LOW
    
    # Scenario type 2: "Smart Contrarian" (2-3 scenarios)  
    # A plausible upset-heavy tournament
    # Champion: 2nd or 3rd most likely candidate (must be different from chalk)
    # FF: 2 chalk + 1-2 non-chalk (leverage-driven picks)
    # Upsets: Concentrated in 1-2 regions ("chaos regions")
    # Cinderella: 1 team advanced to Sweet 16
    # Chaos level: MEDIUM
    
    # Scenario type 3: "Chaos Theory" (1-2 scenarios)
    # An unusual but not impossible tournament outcome
    # Champion: high-leverage candidate (lower probability, much lower ownership)
    # FF: 1-2 chalk + 2-3 contrarian
    # Upsets: 10+ R1, at least 1 Cinderella to Elite 8
    # Chaos level: HIGH
    
    # For each scenario, define:
    #   - champion (who wins it all)
    #   - final_four (one per region)
    #   - chaos_regions (which regions have above-average upset activity)
    #   - cinderella (if any: which low seed has a deep run, and how deep)
    
    # Critical: scenarios must be DIVERSE
    # Enforce: no two scenarios share both the same champion AND same FF
    # Enforce: at least one scenario has a non-top-overall-seed as champion
    # Enforce: at least one scenario has a seed 4+ team in the Final Four
    
    return scenarios
```

**How to choose Final Four for each scenario:**

For each region not occupied by the champion, select the regional champion. The selection should be based on:

```
regional_value(team, region, scenario_chaos_level) = 
    P(team wins region) × leverage_of_winning_region / cost_of_making_it_happen
```

Where:
- `P(team wins region)` = probability this team beats everyone in their regional path. Compute from the bracket structure and matchup matrix. This must account for who they ACTUALLY play (based on the bracket tree), not generic probabilities.
- `leverage_of_winning_region` = P(team wins region) / ownership(team, round=5). How undervalued is this team as a regional champion?
- `cost_of_making_it_happen` = if the team is a 4-seed, getting them to the Final Four means they beat a 5, 1, and either a 2 or 3 on their side of the bracket. Each of those picks has a cost (you're picking against the favorite in the later rounds). The cost is the sum of `(points_at_risk × P(you're wrong))` for each non-chalk pick on their path.

For chalk scenarios, prefer 1-2 seeds as regional champions.
For contrarian scenarios, require at least one 3-5 seed as a regional champion — but ONLY in a region where that's actually plausible (they have a reasonable path).
For chaos scenarios, allow 4-7 seeds as regional champions.

### 2.4 Component 3: Bracket Constructor (Scenario → Complete Bracket)

**Purpose:** Given a scenario (champion, FF, chaos regions, cinderella), fill in all 63 picks coherently.

**This is where the current system fails most spectacularly.** The current approach fills chalk first, then overlays upsets. This produces incoherent brackets (upsets that conflict with the FF picks, favorites advancing past upset winners, etc.).

**The correct construction order:**

```
function construct_bracket(scenario, teams, matchup_matrix, ownership, bracket_structure):
    
    picks = {}  # slot_id → winner
    
    # ──── PHASE 1: SKELETON (champion path + FF paths) ────
    
    # Set champion
    picks[championship_slot] = scenario.champion
    
    # For each Final Four team, build their COMPLETE path from R1 to FF
    for ff_team in scenario.final_four:
        path = trace_path_to_final_four(ff_team, bracket_structure)
        for slot in path:
            picks[slot.slot_id] = determine_winner_on_path(ff_team, slot, matchup_matrix)
            # The FF team wins every game on their path
            # Their OPPONENTS on the path are determined by what the bracket
            # structure says they'd face (given other picks in their region)
    
    # The FF semifinal matchups and championship are determined by the
    # bracket structure (which regions play each other in the semis)
    fill_final_four_and_championship(scenario.final_four, scenario.champion, picks)
    
    # ──── PHASE 2: UPSET SELECTION (within the skeleton constraints) ────
    
    # For each R1 game NOT on any FF team's path, evaluate upset EMV
    open_r1_games = [slot for slot in r1_slots if slot.slot_id not in picks]
    
    upset_candidates = compute_upset_emv(open_r1_games, matchup_matrix, ownership, pool_size)
    
    # Select upsets using the scenario's chaos profile
    if scenario.chaos_level == "LOW":
        # Pick only upsets with positive EMV, no more than 2 per region
        selected_upsets = select_positive_emv_upsets(upset_candidates, max_per_region=2)
    elif scenario.chaos_level == "MEDIUM":
        # Pick positive-EMV upsets, concentrate extra upsets in chaos regions
        selected_upsets = select_upsets_with_concentration(
            upset_candidates, scenario.chaos_regions, max_per_region=3)
    else:  # HIGH
        # Pick all positive-EMV upsets, and some marginal ones in chaos regions
        selected_upsets = select_aggressive_upsets(
            upset_candidates, scenario.chaos_regions, max_per_region=4)
    
    for upset in selected_upsets:
        picks[upset.slot_id] = upset.underdog
    
    # ──── PHASE 3: UPSET ADVANCEMENT ────
    
    # For each upset winner, evaluate whether to advance them
    # Key question: does advancing this upset increase or decrease P(1st)?
    for upset in selected_upsets:
        r2_slot = find_r2_slot(upset.slot_id, bracket_structure)
        if r2_slot.slot_id in picks:
            continue  # Already determined by FF path
        
        # Who does the upset winner face in R2?
        r2_opponent = determine_r2_opponent(upset, picks, bracket_structure)
        
        if r2_opponent is None:
            continue
        
        # Should we advance the upset winner?
        advance_emv = compute_advancement_emv(
            upset.underdog, r2_opponent, matchup_matrix, ownership, pool_size)
        
        if advance_emv > 0:
            picks[r2_slot.slot_id] = upset.underdog
            # Consider advancing further (S16, E8) for Cinderella scenarios
            if scenario.cinderella == upset.underdog:
                advance_cinderella(upset.underdog, picks, matchup_matrix, 
                                   bracket_structure, scenario.cinderella_depth)
    
    # ──── PHASE 4: FILL REMAINING GAMES ────
    
    # For all remaining open slots, pick the team with higher P(winning)
    # from the matchup matrix, CONDITIONED on who actually plays
    # (which depends on our picks in earlier rounds)
    for round_num in [1, 2, 3, 4]:  # R1 through E8
        for slot in slots_in_round(round_num):
            if slot.slot_id in picks:
                continue
            team_a, team_b = determine_teams_in_game(slot, picks, bracket_structure)
            if team_a and team_b:
                prob_a = matchup_matrix[team_a][team_b]
                picks[slot.slot_id] = team_a if prob_a >= 0.5 else team_b
    
    # ──── PHASE 5: VALIDATE COHERENCE ────
    
    validate_bracket_coherence(picks, bracket_structure)
    # - Every team that appears in round N must appear as the winner in round N-1
    # - The champion must have a complete unbroken path from R1 to Championship
    # - No team appears in two different games in the same round
    # - Each game has exactly two participants
    # - The champion of the championship game matches scenario.champion
    
    return CompleteBracket(picks, scenario.champion, scenario.final_four, ...)
```

**Critical detail: the Cinderella advancement logic.**

When the scenario calls for a Cinderella run, don't just blindly advance a 12-seed. Consider:

1. **Who do they face?** If the 12-seed beat the 5-seed, they face the 4/13 winner in R2. If we ALSO picked the 13-over-4 upset, the 12-seed faces a 13-seed — they're now the favorite! This creates enormous differentiation value: a 12-seed in the Sweet 16 is a pick only ~3-5% of brackets have. The EMV is massive.

2. **How far is credible?** A 12-seed in the Sweet 16 has happened dozens of times. A 12-seed in the Elite 8 has happened several times. A 12-seed in the Final Four has happened (Oregon State 2021, closest they've come is Missouri 2002... it's rare). Don't advance them further than the scenario's chaos level justifies.

3. **What does this do to the rest of the region?** A 12-seed in the Sweet 16 means the 1-seed or 2-seed on the other side of the region has an easier Elite 8 game. This makes that higher seed MORE likely to reach the FF — which should be captured in the FF selection.

### 2.5 Component 4: Expected Marginal Value (EMV) for Individual Picks

**Purpose:** For any individual pick decision (upset or chalk), compute how much it helps or hurts P(1st).

This is the key analytical function that replaces the current "leverage ranking."

```
function compute_upset_emv(upset_candidate, matchup_matrix, ownership, pool_size, scoring):
    
    underdog = upset_candidate.underdog
    favorite = upset_candidate.favorite
    
    # P(upset happens)
    p_upset = matchup_matrix[underdog][favorite]
    p_chalk = 1 - p_upset
    
    # Points analysis
    r1_points = scoring[0]  # Points for getting R1 right
    
    # If upset is correct: we get r1_points AND we differentiate
    # What fraction of opponents have the favorite? (Almost everyone)
    fav_ownership_r1 = ownership[favorite].round_ownership.get(2, 
                        SEED_OWNERSHIP_CURVES[favorite.seed][2])
    opponents_with_favorite = (pool_size - 1) * fav_ownership_r1
    
    # If upset correct, we gain r1_points AND opponents_with_favorite lose r1_points
    # Net relative gain = r1_points × (1 + opponents_with_favorite / pool_size)
    # This isn't exact but captures the intuition
    
    # If upset is wrong: we lose r1_points AND potentially cascade losses
    # How far did we have the favorite going?
    # If we only had the favorite winning R1 (chalk replaced by upset in R1 only), 
    # the cascade cost is just R1 points.
    # But if the favorite was on an FF path, the cascade is much worse.
    
    # Downstream cascade: how many additional points are at risk?
    # This depends on how far the favorite would have advanced in our bracket
    # For R1-only (favorite not on FF path): cascade = 0
    # For favorites on FF path: DON'T pick this upset (the skeleton handles it)
    
    # Simple EMV (no cascade, R1-only upsets):
    gain_if_right = r1_points  # We score, others don't
    loss_if_wrong = r1_points  # We miss, others score
    
    # Differentiation multiplier: how much does this help RELATIVE to field?
    # If 90% of opponents have the favorite: being right is very differentiating
    # If 55% have the favorite: less differentiating
    differentiation = fav_ownership_r1  # Higher ownership = more value in being contrarian
    
    emv = p_upset * gain_if_right * differentiation - p_chalk * loss_if_wrong * (1 - differentiation)
    
    # Adjustment for downstream advancement
    # If we plan to advance the underdog (Cinderella), add R2+ value
    if upset_candidate.advance_to_r2:
        r2_points = scoring[1]
        p_advance = matchup_matrix[underdog][likely_r2_opponent]
        dog_r2_ownership = ownership[underdog].round_ownership.get(3,
                            SEED_OWNERSHIP_CURVES[underdog.seed][3])
        r2_differentiation = 1 - dog_r2_ownership  # Almost nobody has this
        
        emv += p_upset * p_advance * r2_points * r2_differentiation
    
    return emv
```

**Important nuance:** This EMV calculation is an approximation used during bracket construction. The Monte Carlo simulation later gives the definitive evaluation. But the approximation should be good enough to guide construction in the right direction — specifically, it should distinguish between "this upset is genuinely valuable for winning the pool" and "this upset has high leverage but negative expected value."

### 2.6 Component 5: Monte Carlo Evaluator

The current Monte Carlo simulation is structurally correct but has implementation bugs. Keep the structure, fix these issues:

**Fix 1: Round-aware matchup probabilities.**

The current `build_matchup_matrix()` calls `compute_matchup_probability()` without a round number, so all matchups use R1 blending weights. Tournament simulation should use round-appropriate weights.

Two options:
- (a) Build separate matrices for each round (memory-intensive, 6 matrices)
- (b) Don't use the pre-computed matrix for simulation; call `compute_matchup_probability(team_a, team_b, round_num)` on-the-fly during simulation

Option (b) is cleaner but slower. Since matchup computation is cheap (a few math operations), this should be fine for 10K sims. If performance is an issue, cache the results.

**Fix 2: Opponent bracket generation must be realistic.**

The current `generate_public_bracket()` has bugs that make opponents too random. The opponents should behave like real pool participants:

- ~50-60% of opponents should pick a 1-seed as champion
- ~20-25% should pick a 2-seed
- ~10-15% should pick a 3-4 seed
- ~5% should pick a 5+ seed
- Each opponent should have 5-10 R1 upsets (not 0 and not 15)
- Opponent brackets should be CONSISTENT (no team advancing without winning prior games)
- When real ESPN pick data is available, use it to calibrate opponent behavior

The ownership profiles should be the basis for opponent generation: for each game, the opponent picks the winner based on the public ownership distribution. But the current implementation's fallback defaults (0.5 for missing ownership) must be replaced with `SEED_OWNERSHIP_CURVES` values.

**Fix 3: Simulation count.**

10,000 simulations minimum for final evaluation. 2,000 is not enough to reliably distinguish between brackets with P(1st) differences of 1-2 percentage points. The standard error at P=0.05 with N=10000 is 0.22%, which gives meaningful resolution.

For the quick champion evaluation (in the Champion Evaluator), 2,000 sims is fine because you're estimating title probability, not pool placement.

**Fix 4: Correct scoring.**

Verify that the scoring function correctly handles:
- Round 0 (play-in) games: these are not scored in most pools. Confirm whether the pool scores them.
- The championship game: this is round 6 in the slot numbering. Make sure the championship slot gets `scoring[5]` (320 points), not some off-by-one value.

### 2.7 Component 6: Perturbation Engine

After Monte Carlo evaluation of all scenario-based brackets, take the top 2-3 and generate perturbations:

```
function perturb_bracket(bracket, perturbation_type):
    match perturbation_type:
        case "swap_champion":
            # Replace champion with 2nd-best candidate
            # Rebuild championship path
            # Keep everything else the same
            
        case "swap_ff_team":
            # Replace one FF team with 2nd-best regional candidate
            # Rebuild that region's path
            
        case "add_upset":
            # Find the highest positive-EMV upset not currently in the bracket
            # Add it, ripple through later rounds
            
        case "remove_upset":
            # Find the most marginal upset (lowest EMV) currently in bracket
            # Remove it, replace with chalk, ripple
            
        case "advance_cinderella":
            # Take an existing R1 upset winner
            # Advance them one additional round
            # Ripple through later rounds
            
        case "swap_cinderella":
            # Replace the current Cinderella with a different one
    
    validate_coherence(new_bracket)
    return new_bracket
```

Generate 5-10 perturbations of each top bracket. Re-evaluate via Monte Carlo. This explores the local neighborhood of good solutions.

### 2.8 Component 7: Output Selection

The final output should be 3 brackets that represent genuinely different strategies:

```
function select_output_brackets(all_evaluated_brackets):
    
    # Sort all brackets by P(1st)
    ranked = sort_by_p_first(all_evaluated_brackets)
    
    # Bracket 1 ("Optimal"): Highest P(1st)
    optimal = ranked[0]
    
    # Bracket 2 ("Safe Alternate"): Highest P(top 3) among brackets
    # that differ from optimal in at least 10 picks
    safe = max(
        [b for b in ranked if count_different_picks(b, optimal) >= 10],
        key=lambda b: b.p_top_three
    )
    
    # Bracket 3 ("Aggressive Alternate"): Highest P(1st) among brackets
    # that have a DIFFERENT champion from both optimal and safe
    aggressive = max(
        [b for b in ranked if b.champion != optimal.champion 
                         and b.champion != safe.champion
                         and count_different_picks(b, optimal) >= 15],
        key=lambda b: b.p_first_place
    )
    
    # If we can't find brackets meeting the differentiation requirements,
    # relax constraints but ALWAYS ensure different champions for at least 2 of 3
    
    return [optimal, safe, aggressive]
```

**Minimum differentiation requirements between output brackets:**
- At least 2 of 3 brackets must have different champions
- The three brackets must have at least 3 different Final Four teams total
- The optimal and aggressive brackets must differ in at least 15 picks
- Each bracket must have a different number of R1 upsets (±2 minimum difference)

---

## Part III: What to Keep, What to Gut, What to Build

### 3.1 Keep (These Are Good)

| Component | Why It's Good |
|-----------|---------------|
| `sharp.py` — AdjEM logistic model with κ=13.0 | Well-calibrated for tournament games |
| `sharp.py` — UPS (Upset Propensity Score) | Good idea, good feature selection, correct implementation |
| `sharp.py` — Round-dependent seed prior blending | Correct approach to Bayesian updating |
| `sharp.py` — Experience, tempo, momentum modifiers | Directionally correct, individually well-implemented |
| `constants.py` — Historical upset rates | Accurate data, well-structured |
| `constants.py` — Seed ownership curves | Reasonable fallback when ESPN data unavailable |
| Monte Carlo framework | Correct approach to P(1st) estimation |
| Scoring function | Simple and correct |

### 3.2 Fix (Bugs and Miscalibrations)

| Issue | Fix |
|-------|-----|
| `build_matchup_matrix()` ignores `round_num` | Pass round_num through, or compute on-the-fly during simulation |
| `generate_public_bracket()` defaults to 0.5 ownership | Use `SEED_OWNERSHIP_CURVES[seed][round]` as fallback |
| Opponent brackets lack consistency enforcement | Implement top-down opponent bracket generation (champion first) |
| Simulation count too low (2000) | Use 10,000 minimum for final evaluation |
| `STRATEGY_CHAMPION_SEEDS` restricts by seed | Delete entirely — let the math decide |

### 3.3 Rewrite (Fundamentally Wrong Approach)

| Component | Problem | Replacement |
|-----------|---------|-------------|
| Champion selection formula `title_prob² / ownership` | Not pool-size-aware, not path-aware | `V(C) = title_prob × path_quality / ((N-1) × ownership + 1)` |
| Bracket construction (chalk → upset overlay) | Produces incoherent brackets | Scenario-based top-down construction |
| Upset selection by leverage ranking | Ignores EMV, treats picks as independent | EMV-based selection with correlation awareness |
| Strategy differentiation by seed constraints | Arbitrary, not meaningful | Scenario-based differentiation (chalk vs. contrarian vs. chaos) |
| No upset advancement | Missing entirely (upset winners never advance past R1) | EMV-based advancement decisions |
| Three "strategies" that produce near-identical brackets | 97%+ overlap, wasted entries | Enforce minimum differentiation, different scenarios |

### 3.4 Build (Currently Missing)

| Component | Purpose |
|-----------|---------|
| Scenario generator | Creates 5-8 coherent tournament narratives |
| EMV calculator | Evaluates individual picks for pool value, not just probability |
| Path analyzer | Computes path difficulty for champion/FF candidates |
| Perturbation engine | Explores neighborhood of good solutions |
| Coherence validator | Ensures bracket tells a consistent story |
| Output diversification | Enforces minimum differentiation between output brackets |
| Seed-adjusted quality metric | Identifies systematically under/over-seeded teams |
| Conditional correlation logic | Connects upset picks to downstream implications |

---

## Part IV: Testing and Validation

### 4.1 How to Know If the Redesign Worked

The system should pass these validation tests:

**Test 1: Champion Selection Sanity**
- In a year with one dominant team (AdjEM 5+ points above the field), the system should pick that team as champion in the conservative bracket for pool sizes ≤ 25, regardless of seed.
- In a year with 3-4 roughly equal contenders, the system should pick different champions for the conservative and aggressive brackets.

**Test 2: P(1st) Above Baseline**
- For a 25-person pool, the optimal bracket should have P(1st) > 4.5% (above the 4% random baseline). Ideally 7-10%.
- The safe alternate should have P(top 3) > 14% (above the 12% random baseline).
- The aggressive bracket should have P(1st) > 3.5% with a higher ceiling (P(1st | favorable scenario) > 15%).

**Test 3: Upset Distribution Matches Historical Norms**
- The balanced bracket should have 7-9 R1 upsets.
- The upset distribution by seed type should roughly match historical averages (±50%).
- At least one bracket should have an upset winner advanced to R2 or beyond.

**Test 4: Bracket Coherence**
- Every bracket passes consistency validation (no team advances without winning prior games).
- The champion has a complete, unbroken path from R1 to the championship.
- No logical contradictions (e.g., picking a 12-seed to beat a 5-seed in R1, then picking the 5-seed in R2).

**Test 5: Bracket Differentiation**
- The three output brackets differ in at least 10 picks each.
- At least 2 of 3 have different champions.
- The aggressive bracket has meaningfully more variance than the conservative bracket.

**Test 6: Pool Size Sensitivity**
- Running the optimizer with pool_size=10 should produce more conservative brackets (higher-probability champions, fewer upsets) than pool_size=100.
- The champion pick should change between pool sizes (a team that's right for a 10-person pool may be wrong for a 100-person pool).

**Test 7: Scoring System Sensitivity**
- With flat scoring (10 points per round, not escalating), the system should be more contrarian in early rounds (because late-round picks are less important).
- With hyper-escalating scoring (e.g., R1=1, Championship=1000), the system should be almost entirely focused on champion selection with minimal early-round risk.

### 4.2 Calibration Checks

Run 10,000 tournament simulations and verify:
- 5-vs-12 upset rate: 1.3-1.5 per tournament (historical: 1.40)
- Total R1 upsets: 7.5-8.5 (historical: ~8.1)
- 1-seeds reaching FF: 2.0-2.5 per tournament (historical: ~2.2)
- 1-seed champions: 55-65% of tournaments (historical: ~60%)
- Correct R1 picks in a chalk bracket: 23-25 of 32 (historical average)

If simulated rates deviate from historical by >15%, the probability model needs recalibration (adjust κ, blending weights, or modifier strengths).

---

## Part V: Implementation Priorities

If you're building this iteratively, here's the order:

**Phase 1 (Critical — do this first):**
1. Fix champion selection formula to be pool-size-aware
2. Delete `STRATEGY_CHAMPION_SEEDS` seed-range filtering
3. Implement top-down bracket construction (champion → FF → paths → fill)
4. Fix opponent generation defaults (0.5 → SEED_OWNERSHIP_CURVES)
5. Increase sim count to 10,000

**Phase 2 (High Impact):**
6. Implement EMV-based upset selection (replacing leverage ranking)
7. Add upset advancement logic
8. Add path difficulty to champion/FF evaluation
9. Implement coherence validation
10. Enforce output bracket differentiation

**Phase 3 (Full System):**
11. Implement scenario generator
12. Implement perturbation engine
13. Add conditional correlation logic
14. Implement seed-adjusted quality metric
15. End-to-end testing with validation suite

---

## Final Note

The difference between a D+ system and an A system isn't about code quality — it's about whether the algorithm understands what it's optimizing. The current system optimizes for "a bracket with high-leverage picks." The correct system optimizes for "a bracket with the highest probability of beating every other bracket in the pool."

Those sound similar. They are worlds apart.

Every design decision should be traced back to: **"Does this increase P(finishing 1st in the pool)?"** If you can't explain how a feature connects to that objective, it shouldn't be in the system.

The math is on our side. A well-designed optimizer can push P(1st) to 8-10% in a 25-person pool — double to triple random chance. That's a real, exploitable edge. Build the system that captures it.

Now go get it done, baby.

—Dickie V 🏀
