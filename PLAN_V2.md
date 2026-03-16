# PLAN V2: Bracket Optimizer — Complete Redesign

**Status:** Active Implementation Plan  
**Replaces:** PLAN.md, PLAN_AMENDMENT.md  
**Date:** 2026-03-15  
**Author:** Architecture Team, incorporating Dickie V's ARCHITECT_PROMPT  
**Objective:** Rewrite `optimizer.py` from scratch, fix `contrarian.py`, extend `models.py`; produce brackets with P(1st) > 4.5% in a 25-person pool (above 4% random baseline)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [What to Keep vs Rewrite](#2-what-to-keep-vs-rewrite)
3. [New Data Models](#3-new-data-models)
4. [Architecture Overview & Data Flow](#4-architecture-overview--data-flow)
5. [Component 1: Champion Evaluator](#5-component-1-champion-evaluator)
6. [Component 2: Scenario Generator](#6-component-2-scenario-generator)
7. [Component 3: Bracket Constructor](#7-component-3-bracket-constructor)
8. [Component 4: EMV Calculator](#8-component-4-emv-calculator)
9. [Component 5: Monte Carlo Evaluator](#9-component-5-monte-carlo-evaluator)
10. [Component 6: Perturbation Engine](#10-component-6-perturbation-engine)
11. [Component 7: Output Selection](#11-component-7-output-selection)
12. [Changes to contrarian.py](#12-changes-to-contrarianpy)
13. [Changes to constants.py](#13-changes-to-constantspy)
14. [Mathematical Formulas Reference](#14-mathematical-formulas-reference)
15. [Testing Strategy](#15-testing-strategy)
16. [Implementation Order](#16-implementation-order)
17. [Performance Budget](#17-performance-budget)

---

## 1. Executive Summary

The current `optimizer.py` earned a D+ because it optimizes for "high-leverage picks" instead of "highest probability of finishing 1st in the pool." This plan replaces it with a 7-component pipeline that:

1. **Evaluates champion candidates** using pool-size-adjusted value formulas instead of `title_prob² / ownership`
2. **Generates coherent tournament scenarios** (chalk, contrarian, chaos) instead of three near-identical strategy-threshold brackets
3. **Constructs brackets top-down** (champion → FF paths → upsets → fill) instead of bottom-up with upset overlay
4. **Uses Expected Marginal Value (EMV)** for upset selection instead of leverage ranking
5. **Evaluates via Monte Carlo** with 10,000 sims, round-aware matchup probabilities, and realistic opponent generation
6. **Perturbs top brackets** to explore the local neighborhood of good solutions
7. **Selects 3 diverse output brackets** with enforced minimum differentiation

The pipeline reads from `sharp.py` (matchup probabilities) and `contrarian.py` (ownership data) — both of which are kept with minor fixes. Everything in `optimizer.py` is rewritten.

### Key Invariant

Every design decision traces back to one question: **"Does this increase P(finishing 1st in the pool)?"** If a feature can't be connected to that objective, it doesn't belong in the system.

---

## 2. What to Keep vs Rewrite

### 2.1 KEEP — Do Not Modify

| Module | Why It's Good |
|--------|---------------|
| `src/sharp.py` | κ=13.0 logistic model, UPS, round-dependent blending, all modifiers — well-calibrated and correctly implemented |
| `src/constants.py` | Historical upset rates, seed ownership curves, UPS weights — accurate data, well-structured (one deletion needed, see §13) |
| `src/models.py` | Existing dataclasses — stable API, all tests pass (additions needed, see §3) |
| `src/scout.py` | Data acquisition — not part of the optimizer pipeline |
| `src/utils.py` | Shared helpers — stable |

### 2.2 FIX — Targeted Bug Fixes

| Module | Issue | Fix |
|--------|-------|-----|
| `src/contrarian.py` | `update_leverage_with_model()` uses crude `seed_factor ** N` heuristic instead of actual simulation probabilities | Replace with quick Monte Carlo probability estimation (see §12) |
| `src/contrarian.py` | Leverage formula doesn't incorporate pool size | Add pool-size-aware leverage: `V = prob / ((N-1) × ownership + 1)` (see §12) |
| `src/constants.py` | `STRATEGY_CHAMPION_SEEDS` excludes 1-seeds from aggressive strategy | DELETE entirely (see §13) |

### 2.3 REWRITE — Complete Replacement

| Module | Problem | Replacement |
|--------|---------|-------------|
| `src/optimizer.py` | Every function except `simulate_tournament()`, `score_bracket()`, and `evaluate_bracket_in_pool()` | 7-component pipeline described in §5-§11 |

### 2.4 ADD — New Code

| Module | What's New |
|--------|-----------|
| `src/models.py` | 5 new dataclasses (§3) |
| `src/optimizer.py` | ~15 new functions organized into 7 logical components |

---

## 3. New Data Models

Add these dataclasses to `src/models.py`. All must include `to_dict()` and `@classmethod from_dict()` following the existing pattern.

### 3.1 ChampionCandidate

```
@dataclass
class ChampionCandidate:
    """A team evaluated as a potential tournament champion.
    
    Attributes:
        team_name: Team name string (key into team/ownership maps).
        seed: Tournament seed (1-16).
        region: Tournament region.
        title_prob: Probability of winning the tournament (from quick Monte Carlo).
        title_ownership: Fraction of public brackets picking this team as champion.
        path_difficulty: Product of P(champion beats each opponent on most likely path).
                        Range [0, 1]. 1.0 = easiest possible path. Lower = harder.
        pool_value: Pool-size-adjusted champion value = title_prob / ((N-1) * ownership + 1).
        adjusted_value: pool_value * sqrt(path_difficulty). Final ranking score.
    """
    team_name: str
    seed: int
    region: str
    title_prob: float
    title_ownership: float
    path_difficulty: float
    pool_value: float
    adjusted_value: float
```

### 3.2 Scenario

```
@dataclass
class Scenario:
    """A coherent tournament narrative that drives bracket construction.
    
    Attributes:
        scenario_id: Unique identifier (e.g., "chalk_0", "contrarian_1", "chaos_2").
        scenario_type: One of "chalk", "contrarian", "chaos".
        champion: Team name picked to win it all.
        champion_seed: Seed of champion (for logging/validation).
        final_four: Dict mapping region name → team name for each FF slot.
        chaos_regions: List of region names where above-average upset activity is expected.
                      Empty for chalk scenarios. 1-2 regions for contrarian. 2+ for chaos.
        cinderella: Team name of a low seed with a deep run (None if no Cinderella).
        cinderella_target_round: How far the Cinderella should advance (3=S16, 4=E8). 
                                None if no Cinderella.
        chaos_level: "LOW", "MEDIUM", or "HIGH". Controls upset budget.
    """
    scenario_id: str
    scenario_type: str
    champion: str
    champion_seed: int
    final_four: dict[str, str]
    chaos_regions: list[str]
    cinderella: str | None
    cinderella_target_round: int | None
    chaos_level: str
```

### 3.3 PathInfo

```
@dataclass
class PathInfo:
    """The most likely path a team takes through the bracket to a target round.
    
    Attributes:
        team_name: Team following this path.
        target_round: The round this path reaches (5=FF, 6=championship).
        opponents: List of (slot_id, opponent_name, win_prob) tuples representing
                  each game the team must win, ordered R1 → target_round.
        path_probability: Product of all win_prob values. P(team wins every game on this path).
        path_slots: List of slot_ids that this path occupies (these picks are locked).
    """
    team_name: str
    target_round: int
    opponents: list[tuple[int, str, float]]
    path_probability: float
    path_slots: list[int]
```

### 3.4 UpsetCandidate

```
@dataclass
class UpsetCandidate:
    """A potential upset pick evaluated for Expected Marginal Value.
    
    Attributes:
        slot_id: The game slot where the upset occurs.
        round_num: Tournament round (1-4).
        favorite: Team name of the higher-seeded team.
        underdog: Team name of the lower-seeded team.
        fav_seed: Favorite's seed number.
        dog_seed: Underdog's seed number.
        upset_prob: P(underdog wins this game).
        fav_ownership: Fraction of public brackets picking the favorite to advance past this round.
        dog_ownership: Fraction of public brackets picking the underdog to advance past this round.
        emv: Expected Marginal Value. Positive = picking this upset increases P(1st).
        ups: Upset Propensity Score (from sharp.py).
        advancement_prob: P(underdog wins R2 | underdog wins R1). From UPSET_ADVANCEMENT_RATE.
        region: The region this game is in.
        on_ff_path: True if either team in this game is on a Final Four path (skip if True).
    """
    slot_id: int
    round_num: int
    favorite: str
    underdog: str
    fav_seed: int
    dog_seed: int
    upset_prob: float
    fav_ownership: float
    dog_ownership: float
    emv: float
    ups: float
    advancement_prob: float
    region: str
    on_ff_path: bool
```

### 3.5 EvaluatedBracket

```
@dataclass
class EvaluatedBracket:
    """A complete bracket with Monte Carlo evaluation results attached.
    
    Wraps CompleteBracket with richer evaluation metadata for comparison and selection.
    
    Attributes:
        bracket: The underlying CompleteBracket.
        scenario_id: Which scenario produced this bracket (for traceability).
        p_first: P(finishing 1st in pool).
        p_top_three: P(finishing top 3 in pool).
        expected_finish: Mean finish position.
        expected_score: Mean bracket score.
        champion_correct_rate: Fraction of sims where our champion won.
        p_first_given_champion_correct: P(1st | our champion wins). Key diagnostic metric.
        num_r1_upsets: Count of R1 upset picks.
        num_distinct_picks: Number of picks that differ from pure chalk.
    """
    bracket: CompleteBracket
    scenario_id: str
    p_first: float
    p_top_three: float
    expected_finish: float
    expected_score: float
    champion_correct_rate: float
    p_first_given_champion_correct: float
    num_r1_upsets: int
    num_distinct_picks: int
```

---

## 4. Architecture Overview & Data Flow

### 4.1 Pipeline Diagram

```
INPUTS:
  teams[]  ←─── scout.py (scraped data)
  matchup_matrix  ←─── sharp.py (win probabilities, round-aware)
  ownership_profiles  ←─── contrarian.py (public pick %, leverage)
  pool_size, scoring  ←─── config

                    ┌────────────────────────────┐
                    │  1. CHAMPION EVALUATOR      │
                    │  evaluate_champions()       │
                    │                             │
                    │  IN:  teams, matchup_matrix, │
                    │       ownership, pool_size   │
                    │  OUT: List[ChampionCandidate]│
                    │       (3-5 candidates)       │
                    └─────────────┬──────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │  2. SCENARIO GENERATOR       │
                    │  generate_scenarios()        │
                    │                              │
                    │  IN:  champion_candidates,   │
                    │       teams, matchup_matrix,  │
                    │       ownership, bracket,     │
                    │       pool_size               │
                    │  OUT: List[Scenario]          │
                    │       (5-8 scenarios)         │
                    └─────────────┬──────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │  3. BRACKET CONSTRUCTOR       │
                    │  construct_bracket()          │
                    │      (called per scenario)   │
                    │                              │
                    │  IN:  scenario, teams,        │
                    │       matchup_matrix,         │
                    │       ownership, bracket,     │
                    │       pool_size, scoring      │
                    │  OUT: CompleteBracket         │
                    │                              │
                    │  INTERNALLY CALLS:            │
                    │  4. EMV CALCULATOR            │
                    │     compute_emv()             │
                    └─────────────┬──────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │  5. MONTE CARLO EVALUATOR    │
                    │  evaluate_bracket()           │
                    │      (called per bracket)    │
                    │                              │
                    │  IN:  bracket, matchup_matrix,│
                    │       ownership, bracket_struct│
                    │       pool_size, scoring,     │
                    │       sim_count               │
                    │  OUT: EvaluatedBracket        │
                    └─────────────┬──────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │  6. PERTURBATION ENGINE       │
                    │  perturb_and_evaluate()       │
                    │                              │
                    │  IN:  top 2-3 EvaluatedBrackets│
                    │       + all pipeline inputs   │
                    │  OUT: additional               │
                    │       EvaluatedBrackets        │
                    │       (5-10 per input bracket) │
                    └─────────────┬──────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │  7. OUTPUT SELECTION          │
                    │  select_output_brackets()     │
                    │                              │
                    │  IN:  all EvaluatedBrackets   │
                    │  OUT: [optimal, safe,          │
                    │        aggressive]             │
                    │       (3 CompleteBrackets)    │
                    └──────────────────────────────┘
```

### 4.2 Top-Level Orchestrator

The single entry point that replaces the current `optimize_bracket()`:

```python
def optimize_bracket(
    teams: list[Team],
    matchup_matrix: dict[str, dict[str, float]],
    ownership_profiles: list[OwnershipProfile],
    bracket: BracketStructure,
    config: Config
) -> list[CompleteBracket]:
    """Full optimization pipeline. Replaces the existing optimize_bracket().
    
    Orchestration:
      1. Evaluate champion candidates (quick MC, ~2000 sims)
      2. Generate 5-8 scenarios from candidates
      3. Construct a bracket for each scenario
      4. Evaluate each bracket via Monte Carlo (10,000 sims each)
      5. Take top 2-3, generate perturbations, evaluate those
      6. Select 3 diverse output brackets
    
    Args:
        teams: All 68 tournament teams with stats and seedings.
        matchup_matrix: Pre-computed P(A beats B) from sharp.py.
                       NOTE: This is the round-1 matrix. For later rounds,
                       the evaluator calls compute_matchup_probability() on-the-fly.
        ownership_profiles: Public ownership and leverage from contrarian.py.
        bracket: Tournament bracket structure from scout.py.
        config: Configuration (pool_size, scoring, sim_count, random_seed).
    
    Returns:
        List of 3 CompleteBrackets: [optimal, safe_alternate, aggressive_alternate].
        Each has p_first_place, p_top_three, expected_finish, expected_score populated.
    
    Side Effects:
        Logs progress at INFO level throughout.
        Saves data/sim_results.json and data/optimal_brackets.json.
    """
```

The implementation calls components 1-7 in sequence. Total runtime target: < 10 minutes with 10,000 sims per bracket evaluation.

---

## 5. Component 1: Champion Evaluator

### 5.1 Purpose

Identify 3-5 viable champion candidates with pool-size-adjusted value scores. This replaces the current system's `STRATEGY_CHAMPION_SEEDS` filtering and `title_prob * leverage` scoring.

### 5.2 The Champion Value Formula

The correct formula for champion value in a pool of size N:

```
V(C) = title_prob(C) / ((N - 1) × ownership(C) + 1)
```

**Where:**
- `title_prob(C)` = probability that team C wins the tournament (estimated via quick Monte Carlo)
- `ownership(C)` = fraction of public brackets picking C as champion (from ownership profiles)
- `N` = pool_size

**Path-adjusted value:**

```
V_adj(C) = V(C) × sqrt(path_difficulty(C))
```

**Where:**
- `path_difficulty(C)` = product of P(C beats opponent_i) for each opponent on C's most likely path from R1 to championship. Range [0, 1].
- `sqrt()` dampens the penalty — a difficult path matters but shouldn't dominate

**Minimum probability thresholds** (a team must clear this to be considered as champion):

| Pool Size | Min title_prob |
|-----------|---------------|
| ≤ 10      | 15%           |
| 11-25     | 8%            |
| 26-50     | 5%            |
| 51-100    | 3%            |
| 100+      | 2%            |

### 5.3 Function Signatures

```python
def evaluate_champions(
    teams: list[Team],
    matchup_matrix: dict[str, dict[str, float]],
    ownership_profiles: list[OwnershipProfile],
    bracket: BracketStructure,
    pool_size: int,
    sim_count: int = 2000,
    base_seed: int = 42
) -> list[ChampionCandidate]:
    """Identify 3-5 viable champion candidates ranked by pool-adjusted value.
    
    Algorithm:
      1. Run quick Monte Carlo (sim_count sims) to estimate title_prob for all teams.
         Uses simulate_tournament() from the existing codebase.
      2. Filter: only teams where title_prob >= min_threshold(pool_size).
      3. For each surviving team, compute path_difficulty via compute_champion_path().
      4. Compute pool_value = title_prob / ((pool_size - 1) * ownership + 1).
      5. Compute adjusted_value = pool_value * sqrt(path_difficulty).
      6. Return top 5 by adjusted_value, sorted descending.
    
    Args:
        teams: All 68 tournament teams.
        matchup_matrix: P(A beats B) for all pairs.
        ownership_profiles: Public ownership data.
        bracket: Tournament bracket structure.
        pool_size: Number of entrants in the pool.
        sim_count: Number of quick sims for title probability estimation. 
                  2000 is sufficient — we're estimating title_prob, not P(1st).
        base_seed: Random seed for reproducibility.
    
    Returns:
        List of 3-5 ChampionCandidate objects, sorted by adjusted_value descending.
        Always returns at least 2 candidates (relaxes thresholds if needed).
    
    Raises:
        DataError: If no teams survive filtering even with relaxed thresholds.
    """
```

```python
def compute_champion_path(
    team: Team,
    bracket: BracketStructure,
    matchup_matrix: dict[str, dict[str, float]],
    teams: list[Team]
) -> PathInfo:
    """Compute the most likely path for a team from R1 to the championship.
    
    Walks the bracket tree from the team's R1 slot to the championship slot.
    At each round, determines the most likely opponent (the team most likely
    to emerge from the other half of the sub-bracket at that level).
    
    Algorithm:
      For each round on the path (R1 through Championship):
        1. Identify the sub-bracket of teams the champion could face.
        2. The most likely opponent = the team in that sub-bracket with the
           highest probability of reaching that round (estimated as the highest
           seed, or more precisely, the team with the best AdjEM in that sub-bracket).
        3. Record (slot_id, opponent_name, P(champion beats opponent)).
      
      path_probability = product of all individual win probabilities.
    
    Args:
        team: The champion candidate.
        bracket: Tournament bracket structure (for tree navigation).
        matchup_matrix: P(A beats B) for all pairs.
        teams: All teams (for looking up most-likely opponents by AdjEM).
    
    Returns:
        PathInfo with the team's most likely 5-game path (R1, R2, S16, E8, FF)
        plus the championship game (6 games total).
        path_slots contains the 6 slot_ids that this path occupies.
    
    Note:
        For the FF and Championship games, the path uses whichever region's 
        top team emerges (by AdjEM). This is an approximation — Monte Carlo 
        will evaluate the actual dynamics later.
    """
```

```python
def get_min_title_prob_threshold(pool_size: int) -> float:
    """Return the minimum title probability for a champion candidate.
    
    Larger pools tolerate lower-probability champions because differentiation
    is more valuable. Smaller pools want higher-probability champions because
    there's less competition.
    
    Args:
        pool_size: Number of entrants in the pool.
    
    Returns:
        Minimum title probability threshold (float, 0-1).
        Pool ≤ 10: 0.15
        Pool 11-25: 0.08
        Pool 26-50: 0.05
        Pool 51-100: 0.03
        Pool 100+: 0.02
    """
```

```python
def estimate_title_probabilities(
    matchup_matrix: dict[str, dict[str, float]],
    bracket: BracketStructure,
    sim_count: int = 2000,
    base_seed: int = 42
) -> dict[str, float]:
    """Run quick Monte Carlo to estimate title probability for every team.
    
    Simulates sim_count tournaments using simulate_tournament() and counts
    how often each team wins the championship.
    
    Args:
        matchup_matrix: P(A beats B) for all pairs.
        bracket: Tournament bracket structure.
        sim_count: Number of simulations. 2000 is sufficient for title estimation.
        base_seed: Random seed.
    
    Returns:
        Dict mapping team_name → title_probability (float, 0-1).
        Teams that never won in sims get probability 0.0.
    """
```

---

## 6. Component 2: Scenario Generator

### 6.1 Purpose

Create 5-8 coherent tournament scenarios. Each scenario is a "story" about how the tournament plays out, producing a fundamentally different bracket. This replaces the current system's three near-identical strategy-threshold brackets.

### 6.2 Scenario Types

**Type A: "Chalk Plus" (generate 1-2)**
- Champion: highest-probability candidate (usually a 1-seed)
- Final Four: 3-4 of the top-4 overall seeds
- Chaos regions: none
- Cinderella: none
- Chaos level: LOW
- Purpose: Maximizes P(top 3). The "safe" bracket.

**Type B: "Smart Contrarian" (generate 2-3)**
- Champion: 2nd or 3rd candidate by adjusted_value (different from chalk champion)
- Final Four: 2 chalk + 1-2 non-chalk (selected by regional value)
- Chaos regions: 1-2 regions (opposite the champion)
- Cinderella: possibly one, to Sweet 16
- Chaos level: MEDIUM
- Purpose: Maximizes P(1st) with a balanced risk profile.

**Type C: "Chaos Theory" (generate 1-2)**
- Champion: high-leverage candidate (lower probability, much lower ownership)
- Final Four: 1-2 chalk + 2-3 contrarian (seed 3-5)
- Chaos regions: 2+ regions
- Cinderella: one, to Sweet 16 or Elite 8
- Chaos level: HIGH
- Purpose: Boom-or-bust. Wins big in upset-heavy tournaments.

### 6.3 Diversity Constraints

The scenario set MUST satisfy ALL of these:
1. No two scenarios share the same champion AND the same Final Four composition
2. At least two different champions across all scenarios
3. At least one scenario has a non-1-seed as champion (if any candidate qualifies)
4. At least one scenario has a seed 3+ team in the Final Four
5. At least one scenario has 0 chaos regions; at least one has 1+ chaos regions

### 6.4 Function Signatures

```python
def generate_scenarios(
    champion_candidates: list[ChampionCandidate],
    teams: list[Team],
    matchup_matrix: dict[str, dict[str, float]],
    ownership_profiles: list[OwnershipProfile],
    bracket: BracketStructure,
    pool_size: int
) -> list[Scenario]:
    """Generate 5-8 coherent tournament scenarios for bracket construction.
    
    Algorithm:
      1. Generate 1-2 chalk scenarios using the top champion candidate.
         Vary FF composition slightly between them (swap one regional pick).
      2. Generate 2-3 contrarian scenarios using the 2nd and 3rd champion candidates.
         For each, select chaos regions (regions opposite the champion).
         For each, select FF teams with high regional leverage.
      3. Generate 1-2 chaos scenarios using lower-ranked but viable candidates.
         These have aggressive FF picks and Cinderella selections.
      4. Validate diversity constraints. If violated, adjust (swap champions,
         vary FF picks) until all constraints are met.
    
    Args:
        champion_candidates: Output of evaluate_champions() (3-5 candidates).
        teams: All 68 tournament teams.
        matchup_matrix: P(A beats B) for all pairs.
        ownership_profiles: Public ownership data.
        bracket: Tournament bracket structure.
        pool_size: Pool size (affects FF selection aggressiveness).
    
    Returns:
        List of 5-8 Scenario objects, each representing a unique tournament narrative.
    
    Raises:
        DataError: If fewer than 2 champion candidates provided.
    """
```

```python
def select_regional_champion(
    region: str,
    teams: list[Team],
    matchup_matrix: dict[str, dict[str, float]],
    ownership_profiles: list[OwnershipProfile],
    bracket: BracketStructure,
    chaos_level: str,
    pool_size: int,
    exclude_teams: list[str] | None = None
) -> tuple[str, float]:
    """Select the best team to win a region, given a chaos level.
    
    For each candidate in the region, compute:
      regional_value = P(team wins region) × leverage_factor
    
    Where:
      P(team wins region) = estimated probability of winning all 4 games in the region.
        Approximated as: product of P(team beats likely opponent) for 4 rounds.
      leverage_factor = P(team wins region) / ownership(team, round=5).
        How undervalued this team is as a regional champion.
    
    Candidate filtering by chaos_level:
      LOW:    seeds 1-2 only
      MEDIUM: seeds 1-4
      HIGH:   seeds 1-7
    
    Args:
        region: Region name ("East", "West", "South", "Midwest").
        teams: All tournament teams.
        matchup_matrix: P(A beats B) for all pairs.
        ownership_profiles: Public ownership data.
        bracket: Tournament bracket structure.
        chaos_level: "LOW", "MEDIUM", or "HIGH".
        pool_size: For leverage calculation.
        exclude_teams: Teams to exclude (e.g., already selected for other roles).
    
    Returns:
        Tuple of (team_name, regional_value_score).
    """
```

```python
def select_cinderella(
    teams: list[Team],
    matchup_matrix: dict[str, dict[str, float]],
    ownership_profiles: list[OwnershipProfile],
    bracket: BracketStructure,
    chaos_regions: list[str],
    pool_size: int
) -> tuple[str | None, int | None]:
    """Select a Cinderella team for a deep tournament run.
    
    A Cinderella is a seed 10-15 team with:
      - High Upset Propensity Score (UPS > 0.60)
      - Located in a chaos region
      - Reasonable path to advancement (AdjEM gap < 10 vs R1 opponent)
    
    Target depth:
      Seeds 10-12: can target Sweet 16 (round 3)
      Seeds 13-14: target Round of 32 (round 2) only
      Seeds 15-16: never select as Cinderella
    
    Args:
        teams: All tournament teams.
        matchup_matrix: Win probabilities.
        ownership_profiles: For differentiation value calculation.
        bracket: Bracket structure.
        chaos_regions: Regions where chaos is expected (Cinderella should be here).
        pool_size: For value calculation.
    
    Returns:
        Tuple of (team_name, target_round) or (None, None) if no viable Cinderella.
    """
```

---

## 7. Component 3: Bracket Constructor

### 7.1 Purpose

Given a scenario, produce a complete 63-pick bracket. This is where the current system fails most — it builds bottom-up with upset overlays that produce incoherent brackets. The new system builds top-down in 5 phases.

### 7.2 Construction Phases

```
Phase 1: SKELETON
  Set championship winner (scenario.champion).
  Set FF winners (scenario.final_four).
  Build champion's complete path from R1 → Championship (6 games).
  Build each FF team's complete path from R1 → FF (4 games per team).
  These paths lock ~20 picks.

Phase 2: UPSET SELECTION
  For each R1 game NOT on any FF path, compute EMV (Component 4).
  Select upsets based on chaos_level:
    LOW:    only positive-EMV upsets, max 2 per region
    MEDIUM: positive-EMV upsets + extra in chaos regions, max 3 per region
    HIGH:   all positive-EMV upsets + marginal ones in chaos regions, max 4 per region
  Apply Cinderella advancement if scenario specifies one.

Phase 3: UPSET ADVANCEMENT
  For each R1 upset winner, evaluate whether to advance them to R2.
  If they face another upset winner in R2 (e.g., 12 vs 13), advance the 12.
  If they face a higher seed and their advancement_emv > 0, advance them.
  If the scenario's Cinderella, advance to the target round.

Phase 4: FILL REMAINING
  For all unfilled slots (R1 through E8), pick the team with higher P(winning)
  from the matchup matrix, CONDITIONED on who actually plays (based on our picks).
  Use compute_matchup_probability(team_a, team_b, round_num) for round-aware probs.

Phase 5: VALIDATE COHERENCE
  Every team in round N must appear as the winner in round N-1.
  The champion has an unbroken path R1 → Championship.
  No team appears in two games in the same round.
  No logical contradictions.
```

### 7.3 Function Signatures

```python
def construct_bracket(
    scenario: Scenario,
    teams: list[Team],
    matchup_matrix: dict[str, dict[str, float]],
    ownership_profiles: list[OwnershipProfile],
    bracket: BracketStructure,
    pool_size: int,
    scoring: list[int]
) -> CompleteBracket:
    """Construct a complete 63-pick bracket from a scenario, top-down.
    
    This is the core bracket construction function. It replaces the current
    construct_candidate_bracket() entirely.
    
    Algorithm:
      Phase 1: Build skeleton (champion path + FF paths)
      Phase 2: Select upsets via EMV (for games not on any path)
      Phase 3: Advance upset winners where EMV is positive
      Phase 4: Fill remaining games with chalk (highest probability)
      Phase 5: Validate coherence
    
    Args:
        scenario: The tournament scenario to realize as a bracket.
        teams: All 68 tournament teams.
        matchup_matrix: P(A beats B) for all pairs (round-1 pre-computed;
                       later rounds use compute_matchup_probability on-the-fly).
        ownership_profiles: Public ownership data.
        bracket: Tournament bracket structure.
        pool_size: Number of pool entrants (for EMV calculation).
        scoring: Points per round [R1=10, R2=20, S16=40, E8=80, F4=160, Champ=320].
    
    Returns:
        CompleteBracket with all picks filled, champion, final_four, elite_eight populated.
        The label field is set to the scenario's scenario_id.
        p_first_place, p_top_three, expected_score, expected_finish are 0.0 
        (populated later by Monte Carlo).
    
    Raises:
        BracketConsistencyError: If coherence validation fails (should never happen
        if construction logic is correct — this is a safety net).
    """
```

```python
def build_team_path(
    team_name: str,
    target_round: int,
    bracket: BracketStructure,
    matchup_matrix: dict[str, dict[str, float]],
    teams: list[Team],
    existing_picks: dict[int, str]
) -> PathInfo:
    """Build a team's complete path from R1 to target_round.
    
    Starting from the team's R1 slot, traces the bracket tree forward, determining:
    - Which slot the team plays in each round
    - Who their most likely opponent is (from the other feeder slot)
    - The win probability for each game
    
    The most likely opponent at each round is determined by:
    1. If existing_picks already specifies who won the feeder slot, use that team.
    2. Otherwise, use the team with the highest AdjEM in the sub-bracket feeding 
       that slot (i.e., the most likely team to emerge from that sub-bracket).
    
    This function locks picks: it writes the team as the winner of each game 
    on their path into existing_picks.
    
    Args:
        team_name: The team to build a path for.
        target_round: How far to build (4=E8/regional final, 5=FF, 6=championship).
        bracket: Tournament bracket structure.
        matchup_matrix: Win probabilities.
        teams: All teams (for AdjEM lookup when determining likely opponents).
        existing_picks: Dict of slot_id → winner. Modified in-place to add path picks.
    
    Returns:
        PathInfo for this team's path.
    
    Side Effects:
        Modifies existing_picks in-place, adding entries for each game on the path.
    """
```

```python
def find_team_r1_slot(
    team_name: str,
    bracket: BracketStructure
) -> BracketSlot | None:
    """Find the R1 slot where a team starts their tournament.
    
    Args:
        team_name: Team to find.
        bracket: Tournament bracket structure.
    
    Returns:
        The BracketSlot for the team's R1 game, or None if not found.
    """
```

```python
def find_most_likely_opponent_in_sub_bracket(
    slot_id: int,
    bracket: BracketStructure,
    teams: list[Team],
    existing_picks: dict[int, str],
    matchup_matrix: dict[str, dict[str, float]]
) -> str | None:
    """Determine the most likely team to emerge from a sub-bracket at a given slot.
    
    Used during path construction to determine who a team will face.
    
    If existing_picks already has a winner for the feeder slot, returns that.
    Otherwise, identifies all teams that could reach this slot and returns
    the one with the highest AdjEM (most likely to win through).
    
    Args:
        slot_id: The slot we need an opponent for (the "other" feeder).
        bracket: Tournament bracket structure.
        teams: All teams.
        existing_picks: Current state of bracket picks.
        matchup_matrix: Win probabilities.
    
    Returns:
        Team name of the most likely opponent, or None if sub-bracket is empty.
    """
```

```python
def validate_bracket_coherence(
    picks: dict[int, str],
    bracket: BracketStructure
) -> None:
    """Validate that a bracket has no logical contradictions.
    
    Checks:
      1. Every team in round N was the winner of a round N-1 game that feeds
         into the round N game.
      2. The championship winner has a complete unbroken path from R1.
      3. No team appears in two different games in the same round.
      4. All 63 main-bracket slots (R1-R6) have picks.
    
    Args:
        picks: Dict of slot_id → winner for all games.
        bracket: Tournament bracket structure.
    
    Raises:
        BracketConsistencyError: With a descriptive message identifying the inconsistency.
    """
```

---

## 8. Component 4: EMV Calculator

### 8.1 Purpose

For any individual pick decision, compute the Expected Marginal Value — how much picking the upset (vs chalk) is expected to change P(1st). This replaces the current composite score (`0.40 × upset_prob + 0.30 × leverage + ...`).

### 8.2 The EMV Formula

For a single R1 upset candidate:

```
EMV(upset) = P(upset) × gain_if_right - P(chalk) × cost_if_wrong
```

**Where:**

```
gain_if_right = R1_points × differentiation_factor
differentiation_factor = fav_ownership_R2   
  (fraction of opponents who picked the favorite to advance — those people all lose points)

cost_if_wrong = R1_points × (1 - fav_ownership_R2)
  (fraction of opponents who ALSO missed this game — those people are in the same boat)

P(upset) = matchup_matrix[underdog][favorite]
P(chalk) = 1 - P(upset)
```

**For upsets with advancement potential (e.g., advancing a 12-seed to S16):**

```
EMV_with_advancement = EMV_base + 
    P(upset) × P(advance_R2) × R2_points × R2_differentiation +
    P(upset) × P(advance_R2) × P(advance_S16) × S16_points × S16_differentiation
```

Where `R2_differentiation ≈ 1 - dog_ownership_R3` (almost nobody picks the underdog that far).

**EMV is positive when:** the probability-weighted gain from differentiating outweighs the probability-weighted cost of being wrong. This naturally limits upsets — a 14-over-3 with 15% probability has very high differentiation but very low hit rate, so the EMV is often negative unless the differentiation is extreme.

### 8.3 Function Signatures

```python
def compute_upset_emv(
    slot_id: int,
    favorite: str,
    underdog: str,
    matchup_matrix: dict[str, dict[str, float]],
    ownership_profiles: list[OwnershipProfile],
    bracket: BracketStructure,
    teams: list[Team],
    pool_size: int,
    scoring: list[int],
    existing_picks: dict[int, str]
) -> UpsetCandidate:
    """Compute the Expected Marginal Value of picking an upset in a specific game.
    
    This is the core analytical function that replaces the current leverage-based
    ranking. It answers: "Does picking this upset increase or decrease my P(1st)?"
    
    Algorithm:
      1. Get P(upset) from matchup_matrix.
      2. Get favorite's R2 ownership (fav_ownership).
         Use SEED_OWNERSHIP_CURVES as fallback, never 0.5.
      3. Compute gain_if_right = scoring[0] × fav_ownership.
      4. Compute cost_if_wrong = scoring[0] × (1 - fav_ownership).
      5. EMV_base = P(upset) × gain_if_right - P(chalk) × cost_if_wrong.
      6. If underdog has advancement potential (UPSET_ADVANCEMENT_RATE > 0.25
         AND round 2 opponent is weak), add advancement EMV.
      7. Check if this game is on any FF path (on_ff_path flag).
    
    Args:
        slot_id: The game slot to evaluate.
        favorite: Higher-seeded team name.
        underdog: Lower-seeded team name.
        matchup_matrix: P(A beats B) for all pairs.
        ownership_profiles: Public ownership data.
        bracket: Tournament bracket structure.
        teams: All teams (for seed/AdjEM lookups).
        pool_size: Number of pool entrants.
        scoring: Points per round.
        existing_picks: Current bracket picks (for determining R2 opponent).
    
    Returns:
        UpsetCandidate with all fields populated, including EMV.
        EMV > 0 means this upset is worth picking.
        EMV < 0 means chalk is better here.
    """
```

```python
def evaluate_all_r1_upsets(
    teams: list[Team],
    matchup_matrix: dict[str, dict[str, float]],
    ownership_profiles: list[OwnershipProfile],
    bracket: BracketStructure,
    pool_size: int,
    scoring: list[int],
    existing_picks: dict[int, str],
    locked_slots: set[int]
) -> list[UpsetCandidate]:
    """Evaluate EMV for all possible R1 upsets not on any FF path.
    
    Iterates over all R1 slots. For each, computes UpsetCandidate via
    compute_upset_emv(). Skips slots in locked_slots (already determined by
    FF paths) and skips games where the underdog has < 15% win probability.
    
    Args:
        teams: All tournament teams.
        matchup_matrix: Win probabilities.
        ownership_profiles: Public ownership data.
        bracket: Tournament bracket structure.
        pool_size: Pool size.
        scoring: Points per round.
        existing_picks: Current bracket state (from Phase 1 skeleton).
        locked_slots: Set of slot_ids that are locked by FF paths (don't touch).
    
    Returns:
        List of UpsetCandidate, sorted by EMV descending.
        Only includes candidates where on_ff_path is False.
    """
```

```python
def select_upsets(
    candidates: list[UpsetCandidate],
    chaos_level: str,
    chaos_regions: list[str],
    champion_region: str
) -> list[UpsetCandidate]:
    """Select which upsets to include based on chaos level and EMV.
    
    Selection rules:
      LOW chaos:
        - Only upsets with EMV > 0.
        - Max 2 upsets per region.
        - Prefer NOT to put upsets in champion's region.
        - Target: ~5-7 total R1 upsets.
      
      MEDIUM chaos:
        - All upsets with EMV > 0.
        - In chaos_regions: also include upsets with EMV > -0.5 (marginal upsets).
        - Max 3 upsets per region.
        - Champion's region: max 1 upset.
        - Target: ~7-9 total R1 upsets.
      
      HIGH chaos:
        - All upsets with EMV > 0.
        - In chaos_regions: include upsets with EMV > -1.0 (even risky ones).
        - Max 4 upsets per region.
        - Target: ~9-12 total R1 upsets.
    
    Region balancing: each region should have at least 1 upset and at most
    max_per_region upsets. The champion's region gets reduced quota.
    
    Args:
        candidates: Output of evaluate_all_r1_upsets(), sorted by EMV desc.
        chaos_level: "LOW", "MEDIUM", or "HIGH".
        chaos_regions: Regions with expected chaos (more lenient EMV thresholds here).
        champion_region: Champion's region (protect with fewer upsets).
    
    Returns:
        Subset of candidates selected for inclusion, sorted by slot_id.
    """
```

```python
def compute_advancement_emv(
    underdog_name: str,
    r2_opponent_name: str,
    matchup_matrix: dict[str, dict[str, float]],
    ownership_profiles: list[OwnershipProfile],
    teams: list[Team],
    pool_size: int,
    scoring: list[int]
) -> float:
    """Compute the EMV of advancing an R1 upset winner to R2 (and beyond).
    
    If the underdog beat their R1 opponent, should we pick them to also 
    win in R2? This depends on:
      - P(underdog beats R2 opponent)
      - How differentiating is a R2 pick for this underdog? (Almost nobody has it)
      - What do we lose if wrong? (We lose R2 points, but most opponents also 
        don't have the underdog here, so the relative cost is small)
    
    Formula:
      EMV_adv = P(win_R2) × R2_points × (1 - dog_R3_ownership)
              - P(lose_R2) × R2_points × dog_R3_ownership
    
    Where dog_R3_ownership is the fraction of opponents who pick this underdog 
    to reach R3 (typically < 5%).
    
    Args:
        underdog_name: The upset winner considering advancement.
        r2_opponent_name: Who they face in R2.
        matchup_matrix: Win probabilities.
        ownership_profiles: Public ownership.
        teams: All teams.
        pool_size: Pool size.
        scoring: Points per round.
    
    Returns:
        EMV as a float. Positive = advance, negative = don't advance.
    """
```

---

## 9. Component 5: Monte Carlo Evaluator

### 9.1 Purpose

Given a completed bracket, estimate P(1st), P(top 3), and expected finish by simulating 10,000 tournaments and scoring our bracket against simulated opponent brackets.

### 9.2 What to Keep from Current Code

The following functions are structurally correct and should be KEPT with minimal modification:

- `simulate_tournament()` — Keep as-is. Correctly simulates one tournament.
- `score_bracket()` — Keep as-is. Correctly scores a bracket.
- `evaluate_bracket_in_pool()` — Keep as-is. Correctly computes rank.

### 9.3 What to Fix

**Fix 1: Round-aware matchup probabilities in simulation.**

The current `simulate_tournament()` uses `matchup_matrix[team_a][team_b]` which is a single pre-computed matrix (round-agnostic). The matchup matrix from `build_matchup_matrix()` computes all matchups using `compute_matchup_probability(team_a, team_b)` without passing `round_num`, so everything gets round-1 blending weights.

**Solution:** Do NOT change `simulate_tournament()`. Instead, change `build_matchup_matrix()` to NOT apply seed prior blending (which is the round-dependent part). Apply seed prior blending only during bracket construction when we know the round. For simulation, the base AdjEM probability (with experience, tempo, momentum, and UPS modifiers) is sufficient and round-agnostic.

Actually, the simplest fix: pass a `round_num` parameter to the simulation and call `compute_matchup_probability()` on-the-fly instead of using the pre-computed matrix. This is slightly slower but correct.

**Implementation choice: Use on-the-fly computation during simulation.**

```python
def simulate_tournament_v2(
    teams: list[Team],
    bracket: BracketStructure,
    rng: random.Random
) -> dict[int, str]:
    """Simulate one complete tournament using round-aware matchup probabilities.
    
    Identical to simulate_tournament() except it calls 
    compute_matchup_probability(team_a_obj, team_b_obj, round_num) 
    for each game instead of looking up a pre-computed matrix.
    
    This ensures round-dependent seed prior blending is correctly applied:
    R1 matchups use w=0.60 (heavier historical weight), while E8+ uses w=0.80.
    
    Args:
        teams: All 68 tournament teams (need Team objects for on-the-fly computation).
        bracket: Tournament bracket structure.
        rng: Seeded Random instance for reproducibility.
    
    Returns:
        Dict mapping slot_id → winning team name for all games.
    
    Performance:
        compute_matchup_probability is ~10 math ops. 63 games × 10,000 sims = 
        630,000 calls. At ~1μs each, this is ~0.6 seconds. Acceptable.
    """
```

**Fix 2: Realistic opponent bracket generation.**

The current `generate_public_bracket()` has been partially fixed but still produces unrealistic opponent brackets. Key issues:

1. It doesn't enforce champion consistency (champion must win every game on their path).
2. It uses R1 ownership to pick R1 winners, but doesn't cascade correctly.

Replace with a new function:

```python
def generate_opponent_bracket(
    ownership_profiles: list[OwnershipProfile],
    bracket: BracketStructure,
    teams: list[Team],
    rng: random.Random
) -> dict[int, str]:
    """Generate one simulated opponent bracket using public ownership distributions.
    
    Produces a realistic public bracket by building top-down (like a real person):
    
    Algorithm:
      1. Pick champion: weighted by title_ownership.
         ~50-60% chance of a 1-seed, ~20-25% a 2-seed, etc.
      2. Build champion's path: champion wins all games on their path.
      3. Pick remaining FF teams: for each non-champion region, pick the 
         regional champion weighted by round 5 ownership (FF ownership).
      4. Build FF teams' paths similarly.
      5. For remaining games: pick winners weighted by the appropriate round's
         ownership probability. Higher-seeded team's ownership is used as
         the probability of picking them.
      6. Enforce consistency: a team picked in round N must be picked in round N-1.
    
    Fallback values: when ownership data is missing, use 
    SEED_OWNERSHIP_CURVES[seed][round]. NEVER use 0.5 as default.
    
    Args:
        ownership_profiles: Public pick distributions.
        bracket: Bracket structure.
        teams: All teams (for seed lookups).
        rng: Random instance.
    
    Returns:
        Dict of slot_id → picked winner for all 63 main-bracket games.
    """
```

**Fix 3: Simulation count.**

Use 10,000 simulations for final evaluation (config.sim_count). At P=0.05 with N=10000, the standard error is √(0.05 × 0.95 / 10000) ≈ 0.22%, giving meaningful resolution to distinguish brackets.

### 9.4 Evaluation Function

```python
def evaluate_bracket(
    our_bracket: CompleteBracket,
    teams: list[Team],
    ownership_profiles: list[OwnershipProfile],
    bracket: BracketStructure,
    pool_size: int,
    scoring: list[int],
    sim_count: int = 10000,
    base_seed: int = 42
) -> EvaluatedBracket:
    """Run Monte Carlo simulation to evaluate a bracket's pool performance.
    
    For each of sim_count simulations:
      1. Simulate the actual tournament outcome using simulate_tournament_v2().
      2. Generate (pool_size - 1) opponent brackets using generate_opponent_bracket().
      3. Score our bracket and all opponents against the actual results.
      4. Determine our rank (1 = we won the pool).
    
    Aggregate across all sims to compute P(1st), P(top 3), expected finish, etc.
    Also compute conditional metrics:
      - champion_correct_rate: fraction of sims where our champion won
      - p_first_given_champion_correct: P(1st | our champion wins)
    
    Args:
        our_bracket: The bracket to evaluate.
        teams: All 68 tournament teams (for simulate_tournament_v2).
        ownership_profiles: For generating opponent brackets.
        bracket: Tournament bracket structure.
        pool_size: Number of pool entrants.
        scoring: Points per round.
        sim_count: Number of simulations (10,000 for final eval, can lower for debug).
        base_seed: Random seed for reproducibility.
    
    Returns:
        EvaluatedBracket wrapping the CompleteBracket with all metrics populated.
    
    Performance:
        Each sim: 1 tournament sim + (pool_size-1) opponent brackets + scoring.
        At pool_size=25 and sim_count=10000: ~250K opponent brackets generated.
        Target: < 120 seconds per bracket evaluation.
    """
```

---

## 10. Component 6: Perturbation Engine

### 10.1 Purpose

After evaluating all scenario-based brackets, take the top 2-3 performers and generate local perturbations — small modifications that might improve P(1st). This is a hill-climbing step that explores the neighborhood of good solutions.

### 10.2 Perturbation Types

| Type | What Changes | How Many Per Bracket |
|------|-------------|---------------------|
| `swap_champion` | Replace champion with 2nd-best candidate. Rebuild championship path. Keep everything else. | 1 |
| `swap_ff_team` | Replace one FF team with the 2nd-best regional candidate. Rebuild that region's path. | Up to 3 (one per non-champion region) |
| `add_upset` | Find the highest positive-EMV upset NOT in the bracket. Add it. Ripple through later rounds. | 1-2 |
| `remove_upset` | Find the lowest-EMV upset IN the bracket. Remove it (replace with chalk). Ripple. | 1-2 |
| `advance_cinderella` | Take an existing R1 upset winner and advance them one additional round. | 1 |

### 10.3 Function Signatures

```python
def generate_perturbations(
    base_bracket: CompleteBracket,
    champion_candidates: list[ChampionCandidate],
    teams: list[Team],
    matchup_matrix: dict[str, dict[str, float]],
    ownership_profiles: list[OwnershipProfile],
    bracket: BracketStructure,
    pool_size: int,
    scoring: list[int]
) -> list[CompleteBracket]:
    """Generate 5-10 perturbations of a top-performing bracket.
    
    For each perturbation type:
      1. Deep-copy the bracket's picks dict.
      2. Apply the perturbation (swap champion, swap FF, add/remove upset, etc.).
      3. Ripple changes through later rounds (re-determine downstream matchups).
      4. Validate coherence.
      5. If valid, add to output list.
    
    Args:
        base_bracket: The bracket to perturb (a top performer from scenario evaluation).
        champion_candidates: Alternative champions to try.
        teams: All tournament teams.
        matchup_matrix: Win probabilities.
        ownership_profiles: Public ownership.
        bracket: Tournament bracket structure.
        pool_size: Pool size.
        scoring: Points per round.
    
    Returns:
        List of 5-10 perturbed CompleteBrackets. Each has label = f"perturbed_{type}_{n}".
        Each is guaranteed to pass coherence validation.
    """
```

```python
def apply_perturbation(
    picks: dict[int, str],
    perturbation_type: str,
    bracket: BracketStructure,
    teams: list[Team],
    matchup_matrix: dict[str, dict[str, float]],
    **kwargs
) -> dict[int, str]:
    """Apply a single perturbation to a bracket's picks dict.
    
    This function modifies a copy of the picks dict according to the
    perturbation type. After modification, it ripples changes through 
    later rounds to maintain consistency.
    
    Perturbation types:
      "swap_champion": kwargs must include new_champion (str).
        - Change championship slot winner to new_champion.
        - Rebuild new champion's path from R1 to Championship.
        - Rebuild old champion's region with new regional champion.
      
      "swap_ff_team": kwargs must include region (str) and new_team (str).
        - Change the regional final winner to new_team.
        - Rebuild new_team's path from R1 to regional final.
        - Re-determine FF semifinal outcomes.
      
      "add_upset": kwargs must include upset (UpsetCandidate).
        - Set picks[upset.slot_id] = upset.underdog.
        - Ripple: re-determine R2+ matchups involving this slot.
      
      "remove_upset": kwargs must include slot_id (int) and chalk_winner (str).
        - Set picks[slot_id] = chalk_winner.
        - Ripple: re-determine R2+ matchups.
      
      "advance_cinderella": kwargs must include team_name (str) and target_round (int).
        - Advance team one additional round beyond their current deepest appearance.
        - Ripple downstream.
    
    Args:
        picks: Dict of slot_id → winner. This is a COPY — will be modified.
        perturbation_type: One of the 5 types above.
        bracket: Tournament bracket structure.
        teams: All teams.
        matchup_matrix: Win probabilities.
        **kwargs: Type-specific parameters.
    
    Returns:
        Modified picks dict.
    
    Raises:
        BracketConsistencyError: If the perturbation produces an invalid bracket.
    """
```

```python
def ripple_picks(
    picks: dict[int, str],
    changed_slot_id: int,
    bracket: BracketStructure,
    matchup_matrix: dict[str, dict[str, float]],
    teams: list[Team],
    locked_slots: set[int] | None = None
) -> None:
    """After changing a pick, ripple the change through all downstream rounds.
    
    When picks[slot_id] changes, all games that feed from this slot's winner
    may need to be recalculated. This function walks forward through the 
    bracket tree and re-determines winners for all affected downstream games.
    
    For each affected downstream game:
      - Determine the two teams that would play (based on current picks).
      - If both teams are determined, pick the one with higher matchup probability.
      - Unless a locked_slot is reached (don't change those).
    
    Args:
        picks: Dict of slot_id → winner. Modified in-place.
        changed_slot_id: The slot that was just changed.
        bracket: Tournament bracket structure.
        matchup_matrix: Win probabilities.
        teams: All teams.
        locked_slots: Slot IDs that must not be changed (e.g., championship 
                     slot for champion perturbations).
    """
```

---

## 11. Component 7: Output Selection

### 11.1 Purpose

From all evaluated brackets (scenario-based + perturbations), select 3 diverse output brackets. The current system just sorts by P(1st) and takes three — which produces near-identical brackets. The new system enforces meaningful differentiation.

### 11.2 Differentiation Requirements

| Dimension | Minimum Requirement |
|-----------|-------------------|
| Champions | At least 2 of 3 brackets must have different champions |
| Final Four | At least 3 different FF teams across the 3 brackets combined |
| R1 upsets | At least 3 picks different between any two brackets |
| Total pick differences | ≥ 10 different picks between optimal and safe; ≥ 15 between optimal and aggressive |

### 11.3 Function Signatures

```python
def select_output_brackets(
    evaluated_brackets: list[EvaluatedBracket]
) -> list[CompleteBracket]:
    """Select 3 diverse brackets from the pool of evaluated candidates.
    
    Selection algorithm:
      1. Sort all brackets by p_first descending.
      2. Bracket 1 ("optimal"): The bracket with the highest P(1st).
         Label it "optimal".
      3. Bracket 2 ("safe_alternate"): Among brackets that differ from 
         optimal in at least 10 picks, the one with the highest P(top 3).
         Label it "safe_alternate".
      4. Bracket 3 ("aggressive_alternate"): Among brackets that:
         - Have a DIFFERENT champion from both optimal and safe (if possible)
         - Differ from optimal in at least 15 picks
         The one with the highest P(1st). Label it "aggressive_alternate".
      5. If we can't find brackets meeting the strict differentiation 
         requirements, relax thresholds by 50% (10→5 picks, 15→8 picks)
         and retry. Always ensure at least 2 of 3 have different champions.
    
    Args:
        evaluated_brackets: All brackets that have been evaluated via Monte Carlo.
                           Must have at least 3 entries.
    
    Returns:
        List of 3 CompleteBrackets: [optimal, safe_alternate, aggressive_alternate].
        Each has its label field set and all Monte Carlo metrics populated.
    
    Raises:
        DataError: If fewer than 3 brackets provided.
    """
```

```python
def count_different_picks(
    bracket_a: CompleteBracket,
    bracket_b: CompleteBracket
) -> int:
    """Count how many picks differ between two brackets.
    
    Compares slot_id → winner for every pick in both brackets.
    
    Args:
        bracket_a: First bracket.
        bracket_b: Second bracket.
    
    Returns:
        Number of slots where the two brackets pick different winners.
    """
```

---

## 12. Changes to contrarian.py

### 12.1 Fix: update_leverage_with_model()

The current implementation uses a crude `seed_factor ** N` heuristic to estimate advancement probabilities. This produces nonsensical leverage values (e.g., 15.18x for a 12-seed to R32).

**Replace the heuristic with quick Monte Carlo estimation:**

```python
def update_leverage_with_model(
    ownership_profiles: list[OwnershipProfile],
    teams: list[Team],
    matchup_matrix: dict[str, dict[str, float]],
    bracket_structure: BracketStructure,
    pool_size: int,
    title_probs: dict[str, float] | None = None
) -> list[OwnershipProfile]:
    """Update ownership profiles with model-based advancement probabilities and pool-size-aware leverage.
    
    Changes from current implementation:
      1. Uses title_probs (from quick Monte Carlo in Champion Evaluator) instead of 
         seed_factor ** 5 for title probability.
      2. For round-by-round advancement, uses a simplified path analysis: 
         P(reach round R) ≈ P(win each game on the most likely path from R1 to R).
      3. Leverage is pool-size-aware: 
         leverage = prob / ((pool_size - 1) * ownership + 1)
         instead of simple prob / ownership.
      4. Fallback for missing ownership: SEED_OWNERSHIP_CURVES[seed][round], NEVER 0.5.
    
    Args:
        ownership_profiles: Initial profiles to update.
        teams: All 68 tournament teams.
        matchup_matrix: P(A beats B) for all pairs.
        bracket_structure: Tournament bracket structure.
        pool_size: Number of pool entrants (new parameter).
        title_probs: Pre-computed title probabilities from quick Monte Carlo.
                    If None, uses seed-based approximation.
    
    Returns:
        Updated ownership profiles with corrected leverage scores.
    
    Side Effects:
        Modifies profiles in-place and returns them.
    """
```

### 12.2 Fix: Pool-Size-Aware Leverage

Add a new function and modify `calculate_leverage()`:

```python
def calculate_pool_leverage(
    model_prob: float,
    public_ownership: float,
    pool_size: int
) -> float:
    """Calculate pool-size-aware leverage for a pick.
    
    Formula: prob / ((pool_size - 1) * ownership + 1)
    
    This accounts for the EXPECTED NUMBER of opponents with the same pick.
    In a 25-person pool with 30% ownership, ~7 opponents have the pick.
    In a 10-person pool with 30% ownership, ~3 opponents have it.
    The same pick has very different value in each case.
    
    Args:
        model_prob: Our model's probability for this outcome.
        public_ownership: Fraction of public brackets making this pick.
        pool_size: Number of pool entrants.
    
    Returns:
        Pool-adjusted leverage score (float, ≥ 0).
    """
    ownership = max(0.005, public_ownership)
    expected_opponents_with_pick = (pool_size - 1) * ownership
    return model_prob / (expected_opponents_with_pick + 1)
```

---

## 13. Changes to constants.py

### 13.1 DELETE: STRATEGY_CHAMPION_SEEDS

Remove entirely:

```python
# DELETE THIS:
STRATEGY_CHAMPION_SEEDS: dict[str, list[int]] = {
    "conservative": [1, 2],
    "balanced": [1, 2, 3, 4],
    "aggressive": [2, 3, 4, 5, 6],
}
```

**Reason:** This is the single worst design decision in the system. The aggressive strategy EXCLUDES 1-seeds, meaning it can never pick the most likely champion even when the most likely champion also has the best leverage. The Champion Evaluator (§5) replaces this with a mathematical formula that considers any seed — the math decides, not hardcoded ranges.

### 13.2 ADD: Champion Probability Thresholds

```python
# Minimum title probability to be considered as champion candidate
# Scales with pool size: larger pools tolerate lower-probability champions
CHAMPION_MIN_TITLE_PROB: dict[str, float] = {
    "tiny":   0.15,  # Pool ≤ 10
    "small":  0.08,  # Pool 11-25
    "medium": 0.05,  # Pool 26-50
    "large":  0.03,  # Pool 51-100
    "huge":   0.02,  # Pool 100+
}
```

### 13.3 KEEP: Everything Else

All other constants (`HISTORICAL_SEED_WIN_RATES`, `SEED_OWNERSHIP_CURVES`, `BRAND_NAME_BOOST`, `UPSET_TARGETS`, `UPS_WEIGHTS`, etc.) are correct and well-calibrated. Keep them as-is.

The `UPSET_TARGETS` dict is kept as a soft reference for calibration checks in testing (§15), but the optimizer no longer uses it as a hard constraint. The EMV-based upset selection naturally produces historically plausible upset counts.

---

## 14. Mathematical Formulas Reference

This section collects all formulas in one place for the Coder's reference.

### 14.1 Champion Value

```
V(C) = title_prob(C) / ((N - 1) × ownership(C) + 1)

V_adj(C) = V(C) × √(path_difficulty(C))

path_difficulty(C) = ∏(i=1 to 6) P(C beats opponent_i)
```

**Example: Pool size N=25**
- Team A: title_prob=0.28, ownership=0.30
  - V(A) = 0.28 / (24 × 0.30 + 1) = 0.28 / 8.2 = 0.0341
- Team B: title_prob=0.10, ownership=0.05
  - V(B) = 0.10 / (24 × 0.05 + 1) = 0.10 / 2.2 = 0.0455
  - Team B has higher value despite lower win probability (differentiation wins)

### 14.2 Expected Marginal Value (EMV) for R1 Upsets

```
EMV = P(upset) × gain_if_right − P(chalk) × cost_if_wrong

gain_if_right = R1_points × fav_ownership
  (fav_ownership = fraction of opponents who picked the favorite)

cost_if_wrong = R1_points × (1 − fav_ownership)
  (opponents who also got this wrong — same boat as us)
```

**With advancement:**

```
EMV_total = EMV_base
          + P(upset) × P(win_R2) × R2_points × (1 − dog_R3_ownership)
          − P(upset) × P(lose_R2) × R2_points × dog_R3_ownership
```

**Example: 12-seed upset**
- P(upset) = 0.35, fav_ownership = 0.88
- R1_points = 10
- gain_if_right = 10 × 0.88 = 8.8 (88% of opponents lose 10 points)
- cost_if_wrong = 10 × 0.12 = 1.2 (only 12% of opponents also missed this)
- EMV = 0.35 × 8.8 − 0.65 × 1.2 = 3.08 − 0.78 = +2.30 → **PICK THE UPSET**

**Example: 14-seed upset**
- P(upset) = 0.15, fav_ownership = 0.96
- gain_if_right = 10 × 0.96 = 9.6
- cost_if_wrong = 10 × 0.04 = 0.4
- EMV = 0.15 × 9.6 − 0.85 × 0.4 = 1.44 − 0.34 = +1.10 → **Marginal positive**

**Example: 15-seed upset**
- P(upset) = 0.06, fav_ownership = 0.99
- gain_if_right = 10 × 0.99 = 9.9
- cost_if_wrong = 10 × 0.01 = 0.1
- EMV = 0.06 × 9.9 − 0.94 × 0.1 = 0.594 − 0.094 = +0.50 → **Barely positive**

Note: These EMV values are in "relative points" — they approximate the expected point differential vs the field. Higher EMV = more valuable upset pick for pool positioning.

### 14.3 Pool-Size-Adjusted Leverage

```
leverage(pick, N) = model_prob / ((N - 1) × ownership + 1)
```

### 14.4 Path Difficulty

```
path_difficulty(team) = ∏(round=R1 to target_round) P(team beats most_likely_opponent_at_round)
```

Where `most_likely_opponent_at_round` is the team with the highest AdjEM in the sub-bracket feeding the opponent's side of the game.

### 14.5 Regional Value (for FF team selection)

```
regional_value(team, region) = P(team wins region) / ((N-1) × regional_ownership + 1)
```

Where:
- `P(team wins region)` ≈ product of P(team beats each opponent on their 4-game regional path)
- `regional_ownership` = ownership for this team reaching the FF (round 5 ownership)

---

## 15. Testing Strategy

### 15.1 The 7 Validation Tests (from ARCHITECT_PROMPT)

These are the acceptance criteria. The system MUST pass all 7.

**Test 1: Champion Selection Sanity**
```
Setup: Create a tournament with one dominant team (AdjEM 5+ above field).
       Pool size = 25.

Assert: 
  - The dominant team appears as champion candidate #1 from evaluate_champions().
  - At least one of the 3 output brackets has this team as champion.
  - If the dominant team has < 35% ownership, it should be champion in 
    at least 2 of 3 output brackets.

Setup 2: Create a tournament with 3 roughly equal contenders (AdjEM within 2 of each other).
Assert:
  - evaluate_champions() returns at least 3 candidates.
  - The optimal and aggressive output brackets have different champions.
```

**Test 2: P(1st) Above Baseline**
```
Setup: Use real or realistic team data. Pool size = 25. 10,000 sims.

Assert:
  - Optimal bracket: P(1st) > 4.5% (above 4% random baseline).
  - Ideally P(1st) in range 6-10%.
  - Safe alternate: P(top 3) > 14% (above 12% random baseline).
  - Aggressive bracket: P(1st) > 3.5%.
  
Note: This test takes ~10 minutes to run. Mark as @slow.
```

**Test 3: Upset Distribution Matches Historical Norms**
```
Setup: Any realistic tournament data.

Assert:
  - The optimal bracket has 6-10 R1 upsets.
  - At least one bracket has a 12-over-5 upset.
  - At least one bracket advances an upset winner past R1.
  - No bracket has more than 4 upsets in a single region.
  - Total R1 upsets across the 3 brackets span a range of at least 3 
    (e.g., one has 6, one has 8, one has 10).
```

**Test 4: Bracket Coherence**
```
Setup: Generate all 3 output brackets.

Assert (for EACH bracket):
  - Every team in round N is the winner of a round N-1 game that feeds into it.
  - The champion has an unbroken path from R1 to Championship 
    (trace backward — champion must be winner of championship game,
    championship game winner must be winner of their FF game, etc.).
  - No team appears in two games in the same round.
  - All 63 main-bracket slots have picks.
  - The championship game's two participants both won their FF games.
  
  Also assert for simulated opponent brackets (spot-check 100 random ones):
  - Same coherence rules apply.
```

**Test 5: Bracket Differentiation**
```
Setup: Generate all 3 output brackets.

Assert:
  - count_different_picks(optimal, safe) >= 10.
  - count_different_picks(optimal, aggressive) >= 15.
  - At least 2 of 3 brackets have different champions.
  - At least 3 different FF teams across the 3 brackets combined.
```

**Test 6: Pool Size Sensitivity**
```
Setup: Same team data. Run optimizer with pool_size=10 and pool_size=100.

Assert:
  - pool_size=10 optimal bracket has FEWER R1 upsets than pool_size=100.
  - pool_size=10 champion has HIGHER title_prob than pool_size=100 champion.
  - OR pool_size=10 and pool_size=100 pick different champions.
  - (At least one of the above must hold — the system must be pool-sensitive.)
```

**Test 7: Scoring System Sensitivity**
```
Setup: Same team data, pool_size=25.
       Run with ESPN scoring [10,20,40,80,160,320].
       Run with flat scoring [10,10,10,10,10,10].

Assert:
  - With flat scoring: the optimal bracket has MORE R1 upsets 
    (early rounds are proportionally worth more).
  - With ESPN scoring: champion selection is the dominant factor 
    (championship is 320/1920 = 16.7% of max score).
  - The champion picks differ between the two scoring systems, 
    OR the upset count differs by at least 2.
```

### 15.2 Unit Tests for New Functions

**Test file: `tests/test_optimizer_v2.py`**

```
test_evaluate_champions_basic():
  - Create 4 teams with known AdjEM, seed, ownership.
  - Call evaluate_champions().
  - Assert the team with best V_adj is ranked #1.
  - Assert all candidates have title_prob > min_threshold.

test_evaluate_champions_pool_size_effect():
  - Same teams, different pool sizes (10, 25, 100).
  - Assert rankings change with pool size.
  - At pool_size=10, the highest title_prob team should rank highest.
  - At pool_size=100, a lower-owned team may rank higher.

test_champion_path_difficulty():
  - Create a bracket with known matchup probabilities.
  - Compute path for a specific team.
  - Assert path_difficulty = product of individual game probs.
  - Assert path_slots contains the correct slot IDs.

test_compute_upset_emv_positive():
  - Setup: 12-seed with 35% win prob, favorite has 88% ownership.
  - Assert EMV > 0 (this upset is worth picking).

test_compute_upset_emv_negative():
  - Setup: 15-seed with 6% win prob, favorite has 99% ownership.
  - Assert EMV is small or barely positive (marginal).

test_compute_upset_emv_no_differentiation():
  - Setup: 8-seed with 48% win prob, favorite has 52% ownership.
  - Assert EMV is near zero (no differentiation value — everyone knows this is close).

test_select_upsets_low_chaos():
  - Provide 10 candidates with various EMVs.
  - Assert only positive-EMV candidates are selected.
  - Assert max 2 per region.
  - Assert total count is 5-7.

test_select_upsets_high_chaos():
  - Same candidates.
  - Assert some negative-EMV candidates in chaos regions are included.
  - Assert total count is 9-12.

test_construct_bracket_coherence():
  - Construct a bracket from any scenario.
  - Assert validate_bracket_coherence() passes.
  - Trace champion backward — unbroken path.

test_construct_bracket_champion_in_championship():
  - Construct a bracket.
  - Assert the championship game winner IS the scenario's champion.
  - Assert the championship game's two participants won their FF games.

test_generate_scenarios_diversity():
  - Generate scenarios from 4 champion candidates.
  - Assert 5-8 scenarios returned.
  - Assert at least 2 different champions.
  - Assert at least one scenario has chaos_level != "LOW".

test_generate_opponent_bracket_consistency():
  - Generate 100 opponent brackets.
  - For each, verify bracket coherence (every advancing team won their prior game).

test_generate_opponent_bracket_champion_distribution():
  - Generate 1000 opponent brackets.
  - Assert 50-70% picked a 1-seed as champion.
  - Assert < 5% picked a seed 5+ as champion.

test_perturbation_swap_champion():
  - Create a bracket with champion A.
  - Apply swap_champion perturbation to champion B.
  - Assert new bracket has champion B.
  - Assert coherence is maintained.
  - Assert champion B has unbroken path.

test_perturbation_add_upset():
  - Create a chalk bracket.
  - Add one upset via perturbation.
  - Assert the upset is present.
  - Assert later-round picks are rippled correctly.

test_select_output_brackets_differentiation():
  - Create 10 evaluated brackets with various metrics.
  - Assert 3 returned brackets satisfy all differentiation requirements.
  - Assert bracket 1 has highest P(1st).

test_count_different_picks():
  - Two brackets differing in 12 picks.
  - Assert count_different_picks returns 12.

test_simulate_tournament_v2_round_aware():
  - Create two teams with specific AdjEM.
  - Run simulate_tournament_v2 1000 times.
  - Assert win rate is consistent with round-dependent blending.
```

### 15.3 Calibration Tests

```
test_simulation_calibration():
  - Simulate 10,000 tournaments with realistic team data.
  - Count upset rates by seed matchup.
  - Assert 5-vs-12 upset rate: 1.2-1.6 per tournament (historical: 1.40).
  - Assert total R1 upsets: 7.0-9.0 (historical: ~8.1).
  - Assert 1-seeds reaching FF: 1.8-2.6 per tournament (historical: ~2.2).
  - Assert 1-seed champions: 50-70% of tournaments (historical: ~60%).
  - If any rate deviates > 15% from historical, flag for kappa/modifier recalibration.
```

### 15.4 Existing Tests

All existing tests in `tests/test_sharp.py`, `tests/test_models.py`, and any others MUST continue to pass. The sharp.py and models.py modules are NOT being modified (only extended with new dataclasses in models.py, which is additive).

---

## 16. Implementation Order

Build in this order. Each phase is independently testable and deployable.

### Phase 1: Foundation (CRITICAL — Do First)

**Goal:** Fix the worst bugs and establish the new data model.

1. **Add new dataclasses to `models.py`** (§3)
   - ChampionCandidate, Scenario, PathInfo, UpsetCandidate, EvaluatedBracket
   - Include to_dict()/from_dict() for each
   - Test: round-trip serialization for each new class

2. **Delete STRATEGY_CHAMPION_SEEDS from `constants.py`** (§13.1)
   - Add CHAMPION_MIN_TITLE_PROB dict (§13.2)
   - Remove all imports/references to STRATEGY_CHAMPION_SEEDS in optimizer.py

3. **Fix contrarian.py** (§12)
   - Add `calculate_pool_leverage()` function
   - Fix `update_leverage_with_model()` to use title_probs and path analysis
   - Fix all fallback values: SEED_OWNERSHIP_CURVES[seed][round], NEVER 0.5
   - Test: verify leverage values are sensible (no 15x leverage for 12-seeds)

4. **Implement `estimate_title_probabilities()`** (§5.3)
   - Quick Monte Carlo (2000 sims), count who wins
   - Test: dominant team wins > 20% of sims; 16-seed wins < 1%

**Tests to pass after Phase 1:** All existing tests + new model serialization tests + title probability sanity check.

### Phase 2: Champion Evaluator + EMV Calculator (HIGH IMPACT)

**Goal:** Replace the broken champion selection and upset valuation logic.

5. **Implement `get_min_title_prob_threshold()`** (§5.3)
   - Simple lookup by pool_size bracket

6. **Implement `compute_champion_path()`** (§5.3)
   - Trace bracket tree from team's R1 slot to championship
   - Determine most likely opponent at each round
   - Compute path_difficulty as product of win probs
   - Test: path has exactly 6 opponents; path_difficulty is in [0, 1]

7. **Implement `evaluate_champions()`** (§5.3)
   - Combine title_probs + path_difficulty + pool-size formula
   - Return top 5 ChampionCandidates sorted by adjusted_value
   - Test: Test 1 (Champion Selection Sanity)

8. **Implement `compute_upset_emv()`** (§8.3)
   - The EMV formula from §14.2
   - Test: verify positive EMV for classic 12/5 upsets, near-zero for 8/9 games

9. **Implement `evaluate_all_r1_upsets()` and `select_upsets()`** (§8.3)
   - Filter, rank by EMV, select based on chaos level and region
   - Test: upset count is historically plausible (6-12 range)

**Tests to pass after Phase 2:** Champion selection tests + EMV tests + calibration spot-checks.

### Phase 3: Scenario Generator + Bracket Constructor (FULL SYSTEM)

**Goal:** The core algorithm — coherent bracket construction from scenarios.

10. **Implement `select_regional_champion()`** (§6.4)
    - Regional value formula, chaos-level-dependent seed filtering
    - Test: returns reasonable FF picks for each chaos level

11. **Implement `select_cinderella()`** (§6.4)
    - Identify best Cinderella candidate in chaos regions
    - Test: returns a 10-12 seed in a chaos region (or None for chalk scenarios)

12. **Implement `generate_scenarios()`** (§6.4)
    - Generate 5-8 scenarios across chalk/contrarian/chaos types
    - Enforce diversity constraints
    - Test: Test 5 (diversity), at least 2 different champions

13. **Implement helper functions for bracket construction** (§7.3)
    - `find_team_r1_slot()`
    - `find_most_likely_opponent_in_sub_bracket()`
    - `build_team_path()`
    - `validate_bracket_coherence()`
    - Test: each helper individually

14. **Implement `construct_bracket()`** (§7.3)
    - The 5-phase construction algorithm
    - Test: Test 4 (Bracket Coherence), Test 3 (Upset Distribution)

**Tests to pass after Phase 3:** Tests 1, 3, 4, 5.

### Phase 4: Monte Carlo + Perturbation + Output Selection

**Goal:** Complete the evaluation and output pipeline.

15. **Implement `simulate_tournament_v2()`** (§9.3)
    - Round-aware matchup probability computation
    - Test: calibration test (upset rates match historical)

16. **Implement `generate_opponent_bracket()`** (§9.3)
    - Top-down opponent generation with ownership-weighted picks
    - Test: champion distribution matches public (50-60% 1-seeds)

17. **Implement `evaluate_bracket()`** (§9.4)
    - 10,000-sim Monte Carlo evaluation
    - Compute P(1st), P(top 3), conditional metrics
    - Test: Test 2 (P(1st) Above Baseline) — this is the key acceptance test

18. **Implement perturbation engine** (§10.3)
    - `generate_perturbations()`, `apply_perturbation()`, `ripple_picks()`
    - Test: perturbations maintain coherence, at least some improve P(1st)

19. **Implement `select_output_brackets()`** (§11.3)
    - Differentiation-enforced selection
    - Test: Test 5 (Bracket Differentiation)

20. **Wire up `optimize_bracket()` orchestrator** (§4.2)
    - Connect all 7 components
    - Test: end-to-end integration test, Tests 6 and 7

**Tests to pass after Phase 4:** ALL 7 validation tests.

### Phase 5: Polish

21. **Performance optimization** — profile and optimize hot paths if needed
22. **Update analyst.py** — add conditional P(1st | champion wins) to reports
23. **End-to-end testing with real tournament data** — if available

---

## 17. Performance Budget

### 17.1 Time Targets

| Operation | Target | Notes |
|-----------|--------|-------|
| Champion evaluation (2000 sims) | < 10 seconds | Quick MC, no opponents |
| Scenario generation | < 1 second | Pure computation, no simulation |
| Bracket construction (per scenario) | < 1 second | Tree traversal + EMV computation |
| Monte Carlo evaluation (10,000 sims, pool=25) | < 120 seconds per bracket | Main bottleneck |
| Perturbation generation | < 5 seconds | Tree manipulation, no simulation |
| Total pipeline | < 10 minutes | 6-8 brackets × 120s each + perturbations |

### 17.2 Memory Budget

- Matchup matrix: 68 × 68 × 8 bytes ≈ 37 KB (negligible)
- 10,000 SimResult objects: each ~500 bytes → 5 MB (manageable)
- Do NOT store all 10,000 SimResults in memory. Only aggregate statistics. Stream the sim loop.

### 17.3 Optimization Opportunities (If Needed)

- Cache `compute_matchup_probability()` results per (team_a, team_b, round) triple
- Pre-compute round-specific matchup matrices (6 matrices × 37 KB = 222 KB)
- Reduce sim_count to 5,000 for perturbation evaluation (half the time, minimal accuracy loss)
- Use the pre-computed round-1 matrix for simulate_tournament() and only call on-the-fly for rounds 2+ (saves ~80% of on-the-fly calls)

---

## Appendix A: File Changes Summary

| File | Action | Scope |
|------|--------|-------|
| `src/models.py` | ADD | 5 new dataclasses (§3) — additive, no existing code modified |
| `src/constants.py` | DELETE + ADD | Delete STRATEGY_CHAMPION_SEEDS; add CHAMPION_MIN_TITLE_PROB |
| `src/contrarian.py` | FIX | Add calculate_pool_leverage(); fix update_leverage_with_model() |
| `src/optimizer.py` | REWRITE | Keep simulate_tournament, score_bracket, evaluate_bracket_in_pool. Replace everything else with 7 components (~15 new functions) |
| `src/analyst.py` | MINOR | Add p_first_given_champion_correct to analysis report (optional, Phase 5) |
| `tests/test_optimizer_v2.py` | NEW | All unit tests for the new optimizer |
| `tests/test_validation.py` | NEW | The 7 acceptance tests from §15.1 |

## Appendix B: What the Coder Should NOT Do

1. **Do NOT hardcode team names.** The system must work for any tournament, any year.
2. **Do NOT hardcode seed ranges for champion selection.** That's the whole point of the redesign.
3. **Do NOT use 0.5 as a default for missing ownership data.** Always use `SEED_OWNERSHIP_CURVES[seed][round]`.
4. **Do NOT build brackets bottom-up.** Always champion → FF paths → upsets → fill.
5. **Do NOT treat upsets as independent decisions.** EMV accounts for pool positioning.
6. **Do NOT generate near-identical output brackets.** Enforce differentiation requirements.
7. **Do NOT reduce sim_count below 10,000 for final evaluation.** 2,000 is not enough.
8. **Do NOT modify sharp.py or constants.py** beyond the specific changes listed in §13.

---

*This plan is complete. The Coder should be able to implement every function from the signatures, formulas, and algorithms described above. When in doubt, refer to the ARCHITECT_PROMPT.md for the game-theoretic rationale behind each design decision.*
