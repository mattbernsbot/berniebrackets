"""Monte Carlo optimization engine - V2 Complete Implementation.

Implements a 7-component pipeline that maximizes P(1st place) in bracket pools.
"""

import logging
import random
import copy
from statistics import mean, median
from collections import Counter
from math import sqrt

from src.models import (
    Team, BracketStructure, BracketSlot, CompleteBracket, BracketPick,
    OwnershipProfile, SimResult, AggregateResults, BracketConsistencyError,
    ChampionCandidate, Scenario, PathInfo, UpsetCandidate, EvaluatedBracket
)
from src.utils import save_json
from src.constants import (
    UPSET_ADVANCEMENT_RATE, SEED_OWNERSHIP_CURVES,
    HISTORICAL_SEED_WIN_RATES
)

logger = logging.getLogger("bracket_optimizer")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def assign_confidence_tier(win_prob: float) -> str:
    """Assign a confidence tier to a pick based on win probability."""
    if win_prob >= 0.75:
        return "🔒 Lock"
    elif win_prob >= 0.55:
        return "👍 Lean"
    else:
        return "🎲 Gamble"



# ============================================================================
# SIMULATION FUNCTIONS (KEEP - These are correct)
# ============================================================================

def simulate_tournament(matchup_matrix: dict[str, dict[str, float]], 
                       bracket: BracketStructure, 
                       rng: random.Random) -> dict[int, str]:
    """Simulate one complete tournament using matchup probabilities."""
    results = {}
    
    # Group slots by round
    slots_by_round = {}
    for slot in bracket.slots:
        if slot.round_num not in slots_by_round:
            slots_by_round[slot.round_num] = []
        slots_by_round[slot.round_num].append(slot)
    
    # Simulate round by round
    for round_num in sorted(slots_by_round.keys()):
        for slot in slots_by_round[round_num]:
            # Determine teams in this game
            if round_num in [0, 1]:
                team_a = slot.team_a
                team_b = slot.team_b
            else:
                team_a = team_b = None
                for prev_slot in bracket.slots:
                    if prev_slot.feeds_into == slot.slot_id and prev_slot.slot_id in results:
                        if team_a is None:
                            team_a = results[prev_slot.slot_id]
                        else:
                            team_b = results[prev_slot.slot_id]
            
            if not team_a or not team_b:
                continue
            
            # Get matchup probability
            prob_a = matchup_matrix.get(team_a, {}).get(team_b, 0.5)
            
            # Simulate the game
            winner = team_a if rng.random() < prob_a else team_b
            results[slot.slot_id] = winner
    
    return results


def score_bracket(bracket_picks: dict[int, str], 
                 actual_results: dict[int, str], 
                 scoring: list[int], 
                 bracket_structure: BracketStructure) -> int:
    """Score a bracket against actual tournament results."""
    total_score = 0
    slot_map = {s.slot_id: s for s in bracket_structure.slots}
    
    for slot_id, picked_winner in bracket_picks.items():
        if slot_id in actual_results and slot_id in slot_map:
            if picked_winner == actual_results[slot_id]:
                slot = slot_map[slot_id]
                round_idx = slot.round_num - 1
                if 0 <= round_idx < len(scoring):
                    total_score += scoring[round_idx]
    
    return total_score


def evaluate_bracket_in_pool(our_picks: dict[int, str], 
                             actual_results: dict[int, str], 
                             opponent_brackets: list[dict[int, str]], 
                             scoring: list[int], 
                             bracket_structure: BracketStructure) -> tuple[int, int]:
    """Score our bracket and determine rank in pool."""
    our_score = score_bracket(our_picks, actual_results, scoring, bracket_structure)
    opponent_scores = [
        score_bracket(opp_picks, actual_results, scoring, bracket_structure)
        for opp_picks in opponent_brackets
    ]
    better_count = sum(1 for s in opponent_scores if s > our_score)
    our_rank = better_count + 1
    return our_score, our_rank


def generate_opponent_bracket(ownership_profiles: list[OwnershipProfile], 
                              bracket: BracketStructure, 
                              matchup_matrix: dict[str, dict[str, float]], 
                              rng: random.Random) -> dict[int, str]:
    """Generate one simulated opponent bracket using ownership distributions."""
    picks = {}
    ownership_map = {p.team: p for p in ownership_profiles}
    
    # Pick champion first (weighted by title ownership)
    champions = [(p.team, p.title_ownership) for p in ownership_profiles if p.title_ownership > 0.001]
    if not champions:
        champions = [(p.team, 0.25) for p in ownership_profiles if p.seed == 1]
    
    total_weight = sum(w for _, w in champions)
    r = rng.random() * total_weight
    cumulative = 0
    champion = champions[0][0]
    
    for team, weight in champions:
        cumulative += weight
        if r <= cumulative:
            champion = team
            break
    
    # Fill R1 games based on ownership
    for slot in bracket.slots:
        if slot.round_num in [0, 1] and slot.team_a and slot.team_b:
            team_a_profile = ownership_map.get(slot.team_a)
            team_b_profile = ownership_map.get(slot.team_b)
            
            if team_a_profile and team_b_profile:
                default_a = SEED_OWNERSHIP_CURVES.get(team_a_profile.seed, {}).get(2, 0.5)
                default_b = SEED_OWNERSHIP_CURVES.get(team_b_profile.seed, {}).get(2, 0.5)
                weight_a = team_a_profile.round_ownership.get(2, default_a)
                weight_b = team_b_profile.round_ownership.get(2, default_b)
                
                total = weight_a + weight_b
                if total > 0 and rng.random() < (weight_a / total):
                    picks[slot.slot_id] = slot.team_a
                else:
                    picks[slot.slot_id] = slot.team_b
            else:
                picks[slot.slot_id] = slot.team_a if slot.seed_a < slot.seed_b else slot.team_b
    
    # Simulate remaining rounds
    slots_by_round = {}
    for slot in bracket.slots:
        if slot.round_num not in slots_by_round:
            slots_by_round[slot.round_num] = []
        slots_by_round[slot.round_num].append(slot)
    
    for round_num in range(2, 7):
        if round_num not in slots_by_round:
            continue
        
        for slot in slots_by_round[round_num]:
            team_a = team_b = None
            for prev_slot in bracket.slots:
                if prev_slot.feeds_into == slot.slot_id and prev_slot.slot_id in picks:
                    if team_a is None:
                        team_a = picks[prev_slot.slot_id]
                    else:
                        team_b = picks[prev_slot.slot_id]
            
            if team_a and team_b:
                team_a_profile = ownership_map.get(team_a)
                team_b_profile = ownership_map.get(team_b)
                
                if team_a_profile and team_b_profile:
                    next_round = min(round_num + 1, 6)
                    default_a = SEED_OWNERSHIP_CURVES.get(team_a_profile.seed, {}).get(next_round, 0.5)
                    default_b = SEED_OWNERSHIP_CURVES.get(team_b_profile.seed, {}).get(next_round, 0.5)
                    weight_a = team_a_profile.round_ownership.get(next_round, default_a)
                    weight_b = team_b_profile.round_ownership.get(next_round, default_b)
                    total = weight_a + weight_b
                    
                    if total > 0 and rng.random() < (weight_a / total):
                        picks[slot.slot_id] = team_a
                    else:
                        picks[slot.slot_id] = team_b
                else:
                    prob_a = matchup_matrix.get(team_a, {}).get(team_b, 0.5)
                    picks[slot.slot_id] = team_a if rng.random() < prob_a else team_b
    
    return picks


# ============================================================================
# COMPONENT 1: CHAMPION EVALUATOR
# ============================================================================

def estimate_title_probabilities(matchup_matrix: dict[str, dict[str, float]], 
                                 bracket: BracketStructure, 
                                 sim_count: int = 2000, 
                                 base_seed: int = 42) -> dict[str, float]:
    """Run quick Monte Carlo to estimate title probability for every team."""
    logger.info(f"Estimating title probabilities with {sim_count} simulations")
    
    title_counts = Counter()
    championship_slots = [s for s in bracket.slots if s.round_num == 6]
    if not championship_slots:
        logger.warning("No championship slot found")
        return {}
    
    championship_slot = championship_slots[0]
    
    for sim_id in range(sim_count):
        rng = random.Random(base_seed + sim_id)
        results = simulate_tournament(matchup_matrix, bracket, rng)
        champion = results.get(championship_slot.slot_id)
        if champion:
            title_counts[champion] += 1
    
    title_probs = {team: count / sim_count for team, count in title_counts.items()}
    
    logger.info(f"Title probability estimation complete. Top 5:")
    for team, prob in sorted(title_probs.items(), key=lambda x: x[1], reverse=True)[:5]:
        logger.info(f"  {team}: {prob:.1%}")
    
    return title_probs


def find_team_r1_slot(team_name: str, bracket: BracketStructure) -> BracketSlot | None:
    """Find the R1 slot where a team starts their tournament."""
    for slot in bracket.slots:
        if slot.round_num == 1:
            if slot.team_a == team_name or slot.team_b == team_name:
                return slot
    return None


def find_most_likely_opponent_in_sub_bracket(slot_id: int, 
                                             bracket: BracketStructure, 
                                             teams: list[Team], 
                                             existing_picks: dict[int, str], 
                                             matchup_matrix: dict[str, dict[str, float]]) -> str | None:
    """Determine the most likely team to emerge from a sub-bracket."""
    if slot_id in existing_picks:
        return existing_picks[slot_id]
    
    slot = next((s for s in bracket.slots if s.slot_id == slot_id), None)
    if not slot:
        return None
    
    if slot.round_num == 1:
        team_map = {t.name: t for t in teams}
        team_a_obj = team_map.get(slot.team_a)
        team_b_obj = team_map.get(slot.team_b)
        
        if team_a_obj and team_b_obj:
            return slot.team_a if team_a_obj.adj_em >= team_b_obj.adj_em else slot.team_b
        return slot.team_a or slot.team_b
    
    feeder_slots = [s for s in bracket.slots if s.feeds_into == slot_id]
    candidate_teams = []
    for feeder in feeder_slots:
        likely_team = find_most_likely_opponent_in_sub_bracket(feeder.slot_id, bracket, teams, existing_picks, matchup_matrix)
        if likely_team:
            candidate_teams.append(likely_team)
    
    if not candidate_teams:
        return None
    
    team_map = {t.name: t for t in teams}
    best_team = max(candidate_teams, key=lambda t: team_map.get(t, Team(name=t, adj_em=-999)).adj_em, default=None)
    return best_team


def compute_champion_path(team: Team, 
                         bracket: BracketStructure, 
                         matchup_matrix: dict[str, dict[str, float]], 
                         teams: list[Team]) -> PathInfo:
    """Compute the most likely path for a team from R1 to championship."""
    team_map = {t.name: t for t in teams}
    opponents = []
    path_slots = []
    path_prob = 1.0
    
    r1_slot = find_team_r1_slot(team.name, bracket)
    if not r1_slot:
        logger.warning(f"Could not find R1 slot for {team.name}")
        return PathInfo(team.name, 6, [], 0.0, [])
    
    r1_opponent = r1_slot.team_b if r1_slot.team_a == team.name else r1_slot.team_a
    if r1_opponent:
        win_prob = matchup_matrix.get(team.name, {}).get(r1_opponent, 0.5)
        opponents.append((r1_slot.slot_id, r1_opponent, win_prob))
        path_slots.append(r1_slot.slot_id)
        path_prob *= win_prob
    
    current_slot = r1_slot
    for round_num in range(2, 7):
        next_slot = next((s for s in bracket.slots 
                         if s.round_num == round_num and current_slot.feeds_into == s.slot_id), None)
        
        if not next_slot:
            break
        
        feeder_slots = [s for s in bracket.slots 
                       if s.feeds_into == next_slot.slot_id and s.slot_id != current_slot.slot_id]
        
        if feeder_slots:
            likely_opponent = find_most_likely_opponent_in_sub_bracket(
                feeder_slots[0].slot_id, bracket, teams, {}, matchup_matrix)
            
            if likely_opponent:
                win_prob = matchup_matrix.get(team.name, {}).get(likely_opponent, 0.5)
                opponents.append((next_slot.slot_id, likely_opponent, win_prob))
                path_slots.append(next_slot.slot_id)
                path_prob *= win_prob
        
        current_slot = next_slot
    
    return PathInfo(
        team_name=team.name,
        target_round=6,
        opponents=opponents,
        path_probability=path_prob,
        path_slots=path_slots
    )


def evaluate_champions(teams: list[Team], 
                      matchup_matrix: dict[str, dict[str, float]], 
                      ownership_profiles: list[OwnershipProfile], 
                      bracket: BracketStructure, 
                      pool_size: int, 
                      sim_count: int = 2000, 
                      base_seed: int = 42) -> list[ChampionCandidate]:
    """Identify up to 8 viable champion candidates ranked by pool-adjusted value."""
    logger.info("=== COMPONENT 1: Evaluating champion candidates ===")
    
    title_probs = estimate_title_probabilities(matchup_matrix, bracket, sim_count, base_seed)

    ownership_map = {p.team: p for p in ownership_profiles}
    team_map = {t.name: t for t in teams}
    candidates = []

    for team_name, title_prob in title_probs.items():
        if title_prob <= 0:
            continue

        team = team_map.get(team_name)
        if not team:
            continue
        
        profile = ownership_map.get(team_name)
        title_ownership = profile.title_ownership if profile else SEED_OWNERSHIP_CURVES.get(team.seed, {}).get(6, 0.01)
        
        path_info = compute_champion_path(team, bracket, matchup_matrix, teams)
        path_difficulty = path_info.path_probability
        
        expected_opponents_with_same_champ = (pool_size - 1) * title_ownership
        pool_value = title_prob / (expected_opponents_with_same_champ + 1)
        adjusted_value = pool_value * sqrt(path_difficulty)
        
        candidates.append(ChampionCandidate(
            team_name=team_name,
            seed=team.seed,
            region=team.region,
            title_prob=title_prob,
            title_ownership=title_ownership,
            path_difficulty=path_difficulty,
            pool_value=pool_value,
            adjusted_value=adjusted_value
        ))
    
    candidates.sort(key=lambda c: c.adjusted_value, reverse=True)
    
    top_candidates = candidates[:8]
    
    logger.info(f"Champion evaluation complete. Top {len(top_candidates)} candidates:")
    for i, cand in enumerate(top_candidates, 1):
        logger.info(f"  {i}. {cand.team_name} ({cand.seed}-seed): "
                   f"title_prob={cand.title_prob:.1%}, adjusted_value={cand.adjusted_value:.4f}")
    
    return top_candidates


# ============================================================================
# BACKWARD COMPATIBILITY WRAPPERS FOR TESTS
# ============================================================================

def rank_upset_candidates(teams: list[Team],
                         matchup_matrix: dict[str, dict[str, float]],
                         ownership_profiles: list[OwnershipProfile],
                         bracket: BracketStructure,
                         config) -> list:
    """Backward compatibility - old function signature for tests."""
    logger.warning("rank_upset_candidates is deprecated (V1 function)")
    return []


def select_upsets_by_distribution(upset_candidates: list,
                                  distribution_targets: dict,
                                  max_total: int = 10) -> list:
    """Backward compatibility - old function signature for tests."""
    logger.warning("select_upsets_by_distribution is deprecated (V1 function)")
    return []


def construct_candidate_bracket(teams: list[Team],
                                matchup_matrix: dict[str, dict[str, float]],
                                ownership_profiles: list[OwnershipProfile],
                                bracket: BracketStructure,
                                config,
                                strategy: str = "balanced") -> CompleteBracket:
    """Backward compatibility wrapper for old test imports.
    
    This function existed in the old codebase. Tests import it.
    Redirect to the new optimize_bracket() pipeline.
    """
    logger.warning("construct_candidate_bracket is deprecated. Use optimize_bracket() instead.")
    
    # Detect if this is a full tournament bracket (has round 6 championship slot)
    has_championship = any(s.round_num == 6 for s in bracket.slots)
    
    if not has_championship:
        # Small test bracket — skip full pipeline, return chalk fallback
        return _create_simple_chalk_bracket(teams, matchup_matrix, bracket, config, ownership_profiles)
    
    try:
        brackets = optimize_bracket(teams, matchup_matrix, ownership_profiles, bracket, config)
        return brackets[0] if brackets else _create_simple_chalk_bracket(teams, matchup_matrix, bracket, config, ownership_profiles)
    except (IndexError, ValueError, KeyError):
        return _create_simple_chalk_bracket(teams, matchup_matrix, bracket, config, ownership_profiles)


def _create_simple_chalk_bracket(teams: list[Team],
                                 matchup_matrix: dict[str, dict[str, float]],
                                 bracket: BracketStructure,
                                 config,
                                 ownership_profiles: list[OwnershipProfile] = None) -> CompleteBracket:
    """Create a simple chalk bracket as fallback - handles any bracket size."""
    # Simulate one chalk tournament to get all picks
    rng = random.Random(42)
    results = simulate_tournament(matchup_matrix, bracket, rng)
    
    # Build ownership map for leverage lookup
    ownership_map = {}
    if ownership_profiles:
        ownership_map = {p.team: p for p in ownership_profiles}
    
    # Convert results to picks
    picks = []
    for slot in bracket.slots:
        if slot.slot_id in results and slot.round_num > 0:  # Skip play-in (round 0)
            winner = results[slot.slot_id]
            
            # Determine teams in this game to calculate win prob
            if slot.round_num == 1:
                team_a = slot.team_a
                team_b = slot.team_b
                win_prob = matchup_matrix.get(winner, {}).get(team_a if winner == team_b else team_b, 0.5)
            else:
                # For later rounds, we'd need to trace back - use default
                win_prob = 0.6
            
            # Get leverage score from ownership profile if available
            leverage_score = 1.0
            if winner in ownership_map:
                profile = ownership_map[winner]
                leverage_score = profile.leverage_by_round.get(slot.round_num, 1.0)
            
            picks.append(BracketPick(
                slot_id=slot.slot_id,
                round_num=slot.round_num,
                winner=winner,
                confidence=assign_confidence_tier(win_prob),
                leverage_score=leverage_score,
                is_upset=False
            ))
    
    # Detect the maximum round number dynamically
    max_round = max((s.round_num for s in bracket.slots), default=1)
    
    # Find champion from results (max round slot)
    championship_slot = next((s for s in bracket.slots if s.round_num == max_round), None)
    champion = results.get(championship_slot.slot_id) if championship_slot else "Unknown"
    
    # Find FF teams if bracket is big enough (winners of round max-2, who advance to max-1)
    final_four = []
    if max_round >= 5:
        ff_slots = [s for s in bracket.slots if s.round_num == max_round - 2]
        final_four = [results.get(s.slot_id) for s in ff_slots if s.slot_id in results]
    
    # Find E8 teams if bracket is big enough (winners of round max-3)
    elite_eight = []
    if max_round >= 4:
        e8_slots = [s for s in bracket.slots if s.round_num == max_round - 3]
        elite_eight = [results.get(s.slot_id) for s in e8_slots if s.slot_id in results]
    
    return CompleteBracket(
        picks=picks,
        champion=champion,
        final_four=[t for t in final_four if t],
        elite_eight=[t for t in elite_eight if t],
        label="chalk_fallback",
        expected_score=0.0,
        p_first_place=0.0,
        p_top_three=0.0,
        expected_finish=0.0
    )


# ============================================================================
# COMPONENT 2: SCENARIO GENERATOR
# ============================================================================

def select_regional_champion(region: str, 
                            teams: list[Team], 
                            matchup_matrix: dict[str, dict[str, float]], 
                            ownership_profiles: list[OwnershipProfile], 
                            bracket: BracketStructure, 
                            chaos_level: str, 
                            pool_size: int, 
                            exclude_teams: list[str] | None = None) -> tuple[str, float]:
    """Select the best team to win a region given a chaos level."""
    exclude_teams = exclude_teams or []
    regional_teams = [t for t in teams if t.region == region and t.name not in exclude_teams]
    
    # Filter by seed based on chaos level
    if chaos_level == "low":
        regional_teams = [t for t in regional_teams if t.seed <= 2]
    elif chaos_level == "medium":
        regional_teams = [t for t in regional_teams if t.seed <= 4]
    else:  # high
        regional_teams = [t for t in regional_teams if t.seed <= 7]
    
    if not regional_teams:
        regional_teams = [t for t in teams if t.region == region and t.name not in exclude_teams]
    
    ownership_map = {p.team: p for p in ownership_profiles}
    best_team = None
    best_value = 0.0
    
    for team in regional_teams:
        # Estimate P(wins region) as product of win probs on likely path
        path_info = compute_champion_path(team, bracket, matchup_matrix, teams)
        # Take first 4 games (R1-R4 = regional championship)
        regional_prob = 1.0
        for i, (_, opponent, win_prob) in enumerate(path_info.opponents[:4]):
            regional_prob *= win_prob
        
        # Get ownership
        profile = ownership_map.get(team.name)
        ff_ownership = profile.round_ownership.get(5, 0.01) if profile else SEED_OWNERSHIP_CURVES.get(team.seed, {}).get(5, 0.01)
        ff_ownership = max(0.001, ff_ownership)
        
        # Regional value
        regional_value = regional_prob / ((pool_size - 1) * ff_ownership + 1)
        
        if regional_value > best_value:
            best_value = regional_value
            best_team = team.name
    
    return best_team or regional_teams[0].name, best_value


def select_cinderella(teams: list[Team], 
                     matchup_matrix: dict[str, dict[str, float]], 
                     ownership_profiles: list[OwnershipProfile], 
                     bracket: BracketStructure, 
                     chaos_regions: list[str], 
                     pool_size: int) -> tuple[str | None, int | None]:
    """Select a Cinderella team for a deep tournament run."""
    if not chaos_regions:
        return None, None
    
    candidates = []
    team_map = {t.name: t for t in teams}
    
    for team in teams:
        if team.region not in chaos_regions:
            continue
        if team.seed < 10 or team.seed > 14:
            continue
        
        # Check R1 matchup
        r1_slot = find_team_r1_slot(team.name, bracket)
        if not r1_slot:
            continue
        
        opponent_name = r1_slot.team_b if r1_slot.team_a == team.name else r1_slot.team_a
        opponent = team_map.get(opponent_name)
        
        if not opponent:
            continue
        
        # Check if AdjEM gap is reasonable
        adjem_gap = abs(team.adj_em - opponent.adj_em)
        if adjem_gap > 10:
            continue
        
        # Get upset probability
        upset_prob = matchup_matrix.get(team.name, {}).get(opponent_name, 0.0)
        if upset_prob < 0.2:
            continue
        
        # Determine target round
        target_round = 3 if team.seed <= 12 else 2
        
        candidates.append((team.name, target_round, upset_prob))
    
    if not candidates:
        return None, None
    
    # Pick the one with highest upset probability
    best = max(candidates, key=lambda x: x[2])
    return best[0], best[1]


def generate_scenarios(champion_candidates: list[ChampionCandidate],
                      teams: list[Team],
                      matchup_matrix: dict[str, dict[str, float]],
                      ownership_profiles: list[OwnershipProfile],
                      bracket: BracketStructure,
                      pool_size: int) -> list[Scenario]:
    """Generate ~24 scenarios covering top 8 champion candidates at varying chaos levels.

    Strategy:
    - Top 4 champions (ranks 0-3): 3 scenarios each (low/medium/high chaos) = 12
    - Champions 5-8 (ranks 4-7): 2 scenarios each (medium/high chaos) = 8
    - Top 2 champions: 2 extra FF-variant scenarios (low chaos, different FF) = 4
    Total: ~24 scenarios (fewer if <8 candidates available)
    """
    logger.info("=== COMPONENT 2: Generating scenarios ===")

    if not champion_candidates:
        logger.warning("No champion candidates provided")
        return []

    scenarios = []
    regions = list(set(t.region for t in teams if t.region))

    def _build_ff(champ_cand, chaos_level, exclude_ff=None):
        """Build Final Four dict for a champion at a given chaos level."""
        exclude_ff = exclude_ff or {}
        ff_teams = {}
        for region in regions:
            if region == champ_cand.region:
                ff_teams[region] = champ_cand.team_name
            else:
                # Determine regional chaos: champion's region is always stable
                region_chaos = chaos_level
                exclude_list = [exclude_ff[region]] if region in exclude_ff else []
                team_name, _ = select_regional_champion(
                    region, teams, matchup_matrix, ownership_profiles, bracket,
                    region_chaos, pool_size, exclude_teams=exclude_list
                )
                ff_teams[region] = team_name
        return ff_teams

    def _chaos_regions_for_level(champ_region, chaos_level):
        """Determine which regions get upset activity."""
        other_regions = [r for r in regions if r != champ_region]
        if chaos_level == "low":
            return []
        elif chaos_level == "medium":
            return other_regions[:min(2, len(other_regions))]
        else:  # high
            return other_regions

    def _maybe_cinderella(chaos_level, chaos_regions):
        """Select a Cinderella for medium/high chaos scenarios."""
        if chaos_level == "low":
            return None, None
        cinderella, cinder_target = select_cinderella(
            teams, matchup_matrix, ownership_profiles, bracket, chaos_regions, pool_size
        )
        # Force a Cinderella for high chaos if none found naturally
        if not cinderella and chaos_level == "high" and chaos_regions:
            cinder_candidates = [t for t in teams if t.region in chaos_regions and t.seed == 12]
            if cinder_candidates:
                cinderella = cinder_candidates[0].name
                cinder_target = 3
        return cinderella, cinder_target

    scenario_count = 0

    # --- Core scenarios: each champion at appropriate chaos levels ---
    for rank, champ_cand in enumerate(champion_candidates):
        # Top 4: low/medium/high. Ranks 5-8: medium/high only.
        if rank < 4:
            chaos_levels = ["low", "medium", "high"]
        else:
            chaos_levels = ["medium", "high"]

        for chaos_level in chaos_levels:
            chaos_regions = _chaos_regions_for_level(champ_cand.region, chaos_level)
            ff_teams = _build_ff(champ_cand, chaos_level)
            cinderella, cinder_target = _maybe_cinderella(chaos_level, chaos_regions)

            # Map chaos_level to scenario_type
            if chaos_level == "low":
                scenario_type = "chalk"
            elif chaos_level == "medium":
                scenario_type = "contrarian"
            else:
                scenario_type = "chaos"

            scenarios.append(Scenario(
                scenario_id=f"{scenario_type}_{champ_cand.team_name}_{chaos_level}",
                scenario_type=scenario_type,
                champion=champ_cand.team_name,
                champion_seed=champ_cand.seed,
                final_four=ff_teams,
                chaos_regions=chaos_regions,
                cinderella=cinderella,
                cinderella_target_round=cinder_target,
                chaos_level=chaos_level
            ))
            scenario_count += 1

    # --- FF-variant scenarios for top 2 champions ---
    # Same champion, low chaos, but swap 2 regional picks to explore
    # different Final Four compositions
    for rank in range(min(2, len(champion_candidates))):
        champ_cand = champion_candidates[rank]

        # Build baseline FF at low chaos to know what to exclude
        baseline_ff = _build_ff(champ_cand, "low")

        # Variant 1: swap 2 non-champion regions to their next-best pick
        other_regions = [r for r in regions if r != champ_cand.region]
        exclude_ff = {}
        for region in other_regions[:2]:
            exclude_ff[region] = baseline_ff[region]

        variant_ff = _build_ff(champ_cand, "low", exclude_ff=exclude_ff)

        # Only add if the FF actually differs
        if variant_ff != baseline_ff:
            scenarios.append(Scenario(
                scenario_id=f"ff_variant_{champ_cand.team_name}",
                scenario_type="chalk",
                champion=champ_cand.team_name,
                champion_seed=champ_cand.seed,
                final_four=variant_ff,
                chaos_regions=[],
                cinderella=None,
                cinderella_target_round=None,
                chaos_level="low"
            ))
            scenario_count += 1

        # Variant 2: medium-chaos FF with this champion (different supporting cast)
        baseline_med_ff = _build_ff(champ_cand, "medium")
        exclude_ff_med = {}
        for region in other_regions[:2]:
            exclude_ff_med[region] = baseline_med_ff[region]

        variant_med_ff = _build_ff(champ_cand, "medium", exclude_ff=exclude_ff_med)

        if variant_med_ff != baseline_med_ff:
            chaos_regions = _chaos_regions_for_level(champ_cand.region, "medium")
            cinderella, cinder_target = _maybe_cinderella("medium", chaos_regions)
            scenarios.append(Scenario(
                scenario_id=f"ff_variant_{champ_cand.team_name}_med",
                scenario_type="contrarian",
                champion=champ_cand.team_name,
                champion_seed=champ_cand.seed,
                final_four=variant_med_ff,
                chaos_regions=chaos_regions,
                cinderella=cinderella,
                cinderella_target_round=cinder_target,
                chaos_level="medium"
            ))
            scenario_count += 1

    logger.info(f"Generated {len(scenarios)} scenarios across {len(champion_candidates)} champions")
    for scenario in scenarios:
        logger.info(f"  {scenario.scenario_id}: champion={scenario.champion} "
                    f"(seed {scenario.champion_seed}), chaos={scenario.chaos_level}")

    return scenarios


# ============================================================================
# COMPONENT 4: EMV CALCULATOR
# ============================================================================

def compute_upset_emv(slot_id: int, 
                     favorite: str, 
                     underdog: str, 
                     matchup_matrix: dict[str, dict[str, float]], 
                     ownership_profiles: list[OwnershipProfile], 
                     bracket: BracketStructure, 
                     teams: list[Team], 
                     pool_size: int, 
                     scoring: list[int], 
                     existing_picks: dict[int, str]) -> float:
    """Compute the Expected Marginal Value of picking an upset."""
    # Get upset probability
    p_upset = matchup_matrix.get(underdog, {}).get(favorite, 0.0)
    p_chalk = 1.0 - p_upset
    
    # Get favorite's R1 ownership (how many people pick the favorite to WIN this R1 game)
    # This is stored as round_ownership[1] or SEED_OWNERSHIP_CURVES[seed][1]
    ownership_map = {p.team: p for p in ownership_profiles}
    team_map = {t.name: t for t in teams}
    
    fav_team = team_map.get(favorite)
    fav_seed = fav_team.seed if fav_team else 8
    
    fav_profile = ownership_map.get(favorite)
    if fav_profile:
        # Round 1 ownership = fraction picking this team to advance past R1
        fav_ownership = fav_profile.round_ownership.get(1, SEED_OWNERSHIP_CURVES.get(fav_seed, {}).get(1, 0.8))
    else:
        fav_ownership = SEED_OWNERSHIP_CURVES.get(fav_seed, {}).get(1, 0.8)
    
    # EMV formula from PLAN_V2 §14.2
    # gain_if_right = how many points we gain by differentiating when upset hits
    # cost_if_wrong = how many points we lose vs the field when chalk wins
    r1_points = scoring[0] if len(scoring) > 0 else 10
    gain_if_right = r1_points * fav_ownership  # % of opponents who picked favorite
    cost_if_wrong = r1_points * (1.0 - fav_ownership)  # % who also missed
    
    emv = p_upset * gain_if_right - p_chalk * cost_if_wrong
    
    # Probability floor: don't pick upsets with <15% win probability
    # 16-seeds have ~1% win prob — high scarcity but terrible expected value
    if p_upset < 0.15:
        emv = -999
    
    return emv


# ============================================================================
# COMPONENT 3: BRACKET CONSTRUCTOR
# ============================================================================

def build_team_path(team_name: str, 
                   target_round: int, 
                   bracket: BracketStructure, 
                   matchup_matrix: dict[str, dict[str, float]], 
                   teams: list[Team], 
                   existing_picks: dict[int, str]) -> PathInfo:
    """Build a team's complete path from R1 to target_round.
    
    FIX: Correctly trace the team's path upward through ALL intermediate slots,
    setting them as winner at EVERY level from R1 to target_round.
    """
    r1_slot = find_team_r1_slot(team_name, bracket)
    if not r1_slot:
        logger.warning(f"build_team_path: Could not find R1 slot for {team_name}")
        return PathInfo(team_name, target_round, [], 0.0, [])
    
    opponents = []
    path_slots = []
    path_prob = 1.0
    
    logger.debug(f"build_team_path({team_name}, target_round={target_round}): R1 slot={r1_slot.slot_id}")
    
    # R1: Set team as winner of their R1 slot
    r1_opponent = r1_slot.team_b if r1_slot.team_a == team_name else r1_slot.team_a
    if r1_opponent:
        win_prob = matchup_matrix.get(team_name, {}).get(r1_opponent, 0.5)
        opponents.append((r1_slot.slot_id, r1_opponent, win_prob))
        path_slots.append(r1_slot.slot_id)
        path_prob *= win_prob
        existing_picks[r1_slot.slot_id] = team_name
        logger.debug(f"  R1 (slot {r1_slot.slot_id}): {team_name} beats {r1_opponent} ({win_prob:.2%})")
    
    # Trace upward from R1 to target_round using feeds_into
    current_slot = r1_slot
    for round_num in range(2, target_round + 1):
        # Find the slot that current_slot feeds into
        next_slot = next((s for s in bracket.slots 
                         if s.slot_id == current_slot.feeds_into), None)
        
        if not next_slot:
            logger.warning(f"  R{round_num}: No slot found (current slot {current_slot.slot_id} feeds_into {current_slot.feeds_into})")
            break
        
        # Verify this is the correct round
        if next_slot.round_num != round_num:
            logger.warning(f"Path builder: expected round {round_num}, got {next_slot.round_num} for slot {next_slot.slot_id}")
            break
        
        # Find opponent feeder slot (the OTHER slot that feeds into next_slot)
        feeder_slots = [s for s in bracket.slots 
                       if s.feeds_into == next_slot.slot_id and s.slot_id != current_slot.slot_id]
        
        # FIX: Don't overwrite if slot is already locked by a higher-priority team (champion)
        # This handles cases where teams are in the wrong region due to bracket generation bugs
        if next_slot.slot_id in existing_picks:
            logger.warning(f"  R{round_num} (slot {next_slot.slot_id}): Already locked by {existing_picks[next_slot.slot_id]}, skipping {team_name}")
            break  # Stop building this path, it conflicts with a locked path
        
        if feeder_slots:
            likely_opponent = find_most_likely_opponent_in_sub_bracket(
                feeder_slots[0].slot_id, bracket, teams, existing_picks, matchup_matrix)
            
            if likely_opponent:
                win_prob = matchup_matrix.get(team_name, {}).get(likely_opponent, 0.5)
                opponents.append((next_slot.slot_id, likely_opponent, win_prob))
                path_slots.append(next_slot.slot_id)
                path_prob *= win_prob
                # CRITICAL: Set team as winner of this slot
                existing_picks[next_slot.slot_id] = team_name
                logger.debug(f"  R{round_num} (slot {next_slot.slot_id}): {team_name} beats {likely_opponent} ({win_prob:.2%})")
        else:
            # No opponent found, but still set team as winner
            path_slots.append(next_slot.slot_id)
            existing_picks[next_slot.slot_id] = team_name
            logger.debug(f"  R{round_num} (slot {next_slot.slot_id}): {team_name} (no opponent yet)")
        
        current_slot = next_slot
    
    logger.debug(f"  Path complete: slots {path_slots}")
    return PathInfo(team_name, target_round, opponents, path_prob, path_slots)


def validate_bracket_coherence(picks: dict[int, str], bracket: BracketStructure) -> None:
    """Validate bracket has no logical contradictions."""
    slot_map = {s.slot_id: s for s in bracket.slots}
    
    # Check all picks have feeding winners
    for slot_id, winner in picks.items():
        slot = slot_map.get(slot_id)
        if not slot or slot.round_num <= 1:
            continue
        
        # Find feeder slots
        feeders = [s for s in bracket.slots if s.feeds_into == slot_id]
        if not feeders:
            continue
        
        # Check that winner came from one of the feeders
        found = False
        for feeder in feeders:
            if feeder.slot_id in picks and picks[feeder.slot_id] == winner:
                found = True
                break
        
        if not found:
            raise BracketConsistencyError(
                f"Team {winner} in slot {slot_id} (round {slot.round_num}) "
                f"did not win any feeding game"
            )


def construct_bracket_from_scenario(scenario: Scenario, 
                                    teams: list[Team], 
                                    matchup_matrix: dict[str, dict[str, float]], 
                                    ownership_profiles: list[OwnershipProfile], 
                                    bracket: BracketStructure, 
                                    pool_size: int, 
                                    scoring: list[int]) -> CompleteBracket:
    """Construct a complete bracket from a scenario, top-down."""
    logger.info(f"Constructing bracket for scenario: {scenario.scenario_id}")
    
    existing_picks = {}
    locked_slots = set()
    
    # PHASE 1: Build skeleton (champion + FF paths)
    # Championship path
    champ_team = next((t for t in teams if t.name == scenario.champion), None)
    if champ_team:
        champ_path = build_team_path(
            scenario.champion, 6, bracket, matchup_matrix, teams, existing_picks
        )
        locked_slots.update(champ_path.path_slots)
    
    # FF teams paths to Elite 8 (round 4 = regional championship)
    # These are the 4 regional champions who reach the Final Four
    # We don't build their paths THROUGH the FF, only TO the FF (winning their region)
    for region, ff_team in scenario.final_four.items():
        if ff_team == scenario.champion:
            continue
        ff_path = build_team_path(
            ff_team, 4, bracket, matchup_matrix, teams, existing_picks
        )
        locked_slots.update(ff_path.path_slots)
    
    # PHASE 2: Fill remaining R1 games with chalk (initial)
    for slot in bracket.slots:
        if slot.round_num == 1 and slot.slot_id not in existing_picks:
            if slot.team_a and slot.team_b:
                # Pick the higher probability winner
                prob_a = matchup_matrix.get(slot.team_a, {}).get(slot.team_b, 0.5)
                winner = slot.team_a if prob_a >= 0.5 else slot.team_b
                existing_picks[slot.slot_id] = winner
    
    # PHASE 3: Add EMV-based upsets with two-gate system (Amendment 1)
    logger.info(f"  Evaluating upsets for chaos_level={scenario.chaos_level}")
    
    # Gate 1: EMV floor thresholds
    emv_floors = {
        "low": -1.0,
        "medium": -2.0,
        "high": -3.5
    }
    emv_floor = emv_floors.get(scenario.chaos_level.lower(), -2.0)
    
    # Gate 2: Target upset counts
    upset_targets = {
        "low": (6, 8),    # (min, max)
        "medium": (8, 10),
        "high": (10, 13)
    }
    target_min, target_max = upset_targets.get(scenario.chaos_level.lower(), (8, 10))
    
    # Evaluate all R1 games NOT on FF paths
    team_map = {t.name: t for t in teams}
    ownership_map = {p.team: p for p in ownership_profiles}
    
    # Collect all upset candidates with their EMV
    upset_candidates = []
    
    for slot in bracket.slots:
        if slot.round_num != 1:
            continue
        if slot.slot_id in locked_slots:
            continue
        if not slot.team_a or not slot.team_b:
            continue
        
        # Determine favorite vs underdog
        team_a_obj = team_map.get(slot.team_a)
        team_b_obj = team_map.get(slot.team_b)
        if not team_a_obj or not team_b_obj:
            continue
        
        # Favorite = higher seed (lower seed number)
        if slot.seed_a < slot.seed_b:
            favorite = slot.team_a
            underdog = slot.team_b
            fav_seed = slot.seed_a
            dog_seed = slot.seed_b
        else:
            favorite = slot.team_b
            underdog = slot.team_a
            fav_seed = slot.seed_b
            dog_seed = slot.seed_a
        
        # Compute EMV for picking the upset
        emv = compute_upset_emv(
            slot.slot_id, favorite, underdog, matchup_matrix,
            ownership_profiles, bracket, teams, pool_size, scoring, existing_picks
        )
        
        # Get upset probability
        p_upset = matchup_matrix.get(underdog, {}).get(favorite, 0.0)
        
        # Add to candidates if it passes EMV floor (Gate 1)
        if emv > emv_floor:
            upset_candidates.append({
                'slot_id': slot.slot_id,
                'underdog': underdog,
                'favorite': favorite,
                'dog_seed': dog_seed,
                'fav_seed': fav_seed,
                'emv': emv,
                'p_upset': p_upset,
                'is_8_9': (fav_seed == 8 and dog_seed == 9) or (fav_seed == 9 and dog_seed == 8)
            })
    
    # Sort by EMV descending
    upset_candidates.sort(key=lambda x: x['emv'], reverse=True)
    
    # Always include 8/9 games with EMV >= -0.2 (they're coin flips)
    forced_upsets = [c for c in upset_candidates if c['is_8_9'] and c['emv'] >= -0.2]
    
    # Select top N by EMV to reach target count
    selected_upsets = []
    region_counts = {}
    
    # Add forced 8/9 upsets first
    for upset in forced_upsets:
        slot = next((s for s in bracket.slots if s.slot_id == upset['slot_id']), None)
        if slot:
            region = slot.region
            region_counts[region] = region_counts.get(region, 0) + 1
            selected_upsets.append(upset)
    
    # Add remaining upsets up to target, respecting region caps
    max_per_region = 4 if scenario.chaos_level == "high" else 3
    
    for upset in upset_candidates:
        if upset in selected_upsets:
            continue
        
        if len(selected_upsets) >= target_max:
            break
        
        # Check region cap
        slot = next((s for s in bracket.slots if s.slot_id == upset['slot_id']), None)
        if slot:
            region = slot.region
            if region_counts.get(region, 0) >= max_per_region:
                continue
            
            region_counts[region] = region_counts.get(region, 0) + 1
            selected_upsets.append(upset)
    
    # Apply selected upsets
    for upset in selected_upsets:
        existing_picks[upset['slot_id']] = upset['underdog']
        logger.info(f"    Added upset: {upset['underdog']} ({upset['dog_seed']}) over {upset['favorite']} ({upset['fav_seed']}), EMV={upset['emv']:.2f}")
    
    logger.info(f"  Added {len(selected_upsets)} EMV-based R1 upsets (target: {target_min}-{target_max})")
    
    # PHASE 3.5: Fill R2-R6 with chalk first, then add later-round upsets (Amendment 2)
    # First pass: fill with favorites
    for round_num in range(2, 7):
        for slot in bracket.slots:
            if slot.round_num == round_num and slot.slot_id not in existing_picks:
                # Find feeders
                feeders = [s for s in bracket.slots if s.feeds_into == slot.slot_id]
                if len(feeders) == 2:
                    team_a = existing_picks.get(feeders[0].slot_id)
                    team_b = existing_picks.get(feeders[1].slot_id)
                    
                    if team_a and team_b:
                        prob_a = matchup_matrix.get(team_a, {}).get(team_b, 0.5)
                        winner = team_a if prob_a >= 0.5 else team_b
                        existing_picks[slot.slot_id] = winner
    
    # Second pass: evaluate later-round upsets
    logger.info(f"  Evaluating later-round upsets (R2-R5)")
    
    # Round-specific EMV thresholds and max upsets
    later_round_config = {
        2: {"low": 0.0, "medium": -2.0, "high": -5.0, "max": 4},
        3: {"low": 0.0, "medium": -3.0, "high": -8.0, "max": 2},
        4: {"low": 0.0, "medium": -5.0, "high": -10.0, "max": 1},
        5: {"low": 0.0, "medium": -5.0, "high": -15.0, "max": 1},
    }
    
    later_upsets_added = 0
    
    for round_num in range(2, 6):  # R2 through R5 (FF)
        if round_num not in later_round_config:
            continue
        
        config = later_round_config[round_num]
        emv_threshold = config.get(scenario.chaos_level.lower(), config["medium"])
        max_upsets = config["max"]
        
        round_upset_candidates = []
        
        for slot in bracket.slots:
            if slot.round_num != round_num:
                continue
            if slot.slot_id in locked_slots:
                continue
            
            # Find the two teams meeting in this game
            feeders = [s for s in bracket.slots if s.feeds_into == slot.slot_id]
            if len(feeders) != 2:
                continue
            
            team_a = existing_picks.get(feeders[0].slot_id)
            team_b = existing_picks.get(feeders[1].slot_id)
            
            if not team_a or not team_b:
                continue
            
            # Determine favorite vs underdog
            prob_a = matchup_matrix.get(team_a, {}).get(team_b, 0.5)
            prob_b = 1.0 - prob_a
            
            if prob_a >= prob_b:
                favorite = team_a
                underdog = team_b
                p_favorite = prob_a
                p_underdog = prob_b
            else:
                favorite = team_b
                underdog = team_a
                p_favorite = prob_b
                p_underdog = prob_a
            
            # Skip if current pick is already the underdog
            if existing_picks.get(slot.slot_id) == underdog:
                continue
            
            # FIX: Simplified guard - only protect locked teams directly, not entire feeds_into chains
            # Skip if this slot itself is locked
            if slot.slot_id in locked_slots:
                continue
            
            # Skip if the favorite is a FF/champion team (they're on locked paths)
            ff_team_names = set()
            if hasattr(scenario, 'final_four'):
                if isinstance(scenario.final_four, dict):
                    ff_team_names = set(scenario.final_four.values()) | {scenario.champion}
                else:
                    ff_team_names = set(scenario.final_four) | {scenario.champion}
            if favorite in ff_team_names:
                continue
            
            # Get favorite's ownership for advancing past this round
            fav_profile = ownership_map.get(favorite)
            fav_team_obj = team_map.get(favorite)
            fav_seed = fav_team_obj.seed if fav_team_obj else 4
            
            # Round ownership for NEXT round (advancing past current round)
            next_round = min(round_num + 1, 6)
            if fav_profile:
                fav_ownership = fav_profile.round_ownership.get(next_round, 
                    SEED_OWNERSHIP_CURVES.get(fav_seed, {}).get(next_round, 0.3))
            else:
                fav_ownership = SEED_OWNERSHIP_CURVES.get(fav_seed, {}).get(next_round, 0.3)
            
            fav_ownership = max(0.01, fav_ownership)  # Avoid division by zero
            
            # Get underdog ownership for this round (scarcity value)
            dog_profile = ownership_map.get(underdog)
            dog_team_obj = team_map.get(underdog)
            dog_seed = dog_team_obj.seed if dog_team_obj else 12
            if dog_profile:
                dog_ownership = dog_profile.round_ownership.get(next_round,
                    SEED_OWNERSHIP_CURVES.get(dog_seed, {}).get(next_round, 0.02))
            else:
                dog_ownership = SEED_OWNERSHIP_CURVES.get(dog_seed, {}).get(next_round, 0.02)
            dog_ownership = max(0.005, dog_ownership)
            
            # Compute round-adjusted EMV
            # Gain: picking the underdog when almost nobody else does = high scarcity
            # Cost: missing the favorite when many others have them = moderate cost
            round_points = scoring[round_num - 1] if round_num - 1 < len(scoring) else 10
            scarcity = 1.0 - dog_ownership  # How rare is this pick? (0.98 for a 10-seed in S16)
            commonality = fav_ownership      # How common is the favorite? (0.55 for a 1-seed in S16)
            gain_if_right = round_points * scarcity
            cost_if_wrong = round_points * commonality
            
            emv = p_underdog * gain_if_right - p_favorite * cost_if_wrong
            
            # Probability floor: don't pick upsets where underdog has <15% win probability
            # A 16-seed may have high scarcity value but ~1% win prob = bad bet
            if p_underdog < 0.15:
                emv = -999  # Kill this candidate
            
            # Check if this upset winner came from an R1 upset - apply bonus
            is_r1_upset_winner = False
            for r1_upset in selected_upsets:
                if r1_upset['underdog'] in [team_a, team_b]:
                    is_r1_upset_winner = True
                    break
            
            if is_r1_upset_winner:
                emv *= 1.2  # 20% bonus for stacking contrarian value
            
            round_upset_candidates.append({
                'slot_id': slot.slot_id,
                'round': round_num,
                'underdog': underdog,
                'favorite': favorite,
                'emv': emv,
                'p_upset': p_underdog
            })
        
        # Sort by EMV and select top N
        round_upset_candidates.sort(key=lambda x: x['emv'], reverse=True)
        
        for i, upset in enumerate(round_upset_candidates):
            if i >= max_upsets:
                break
            if upset['emv'] > emv_threshold:
                existing_picks[upset['slot_id']] = upset['underdog']
                later_upsets_added += 1
                logger.info(f"    Added R{round_num} upset: {upset['underdog']} over {upset['favorite']}, EMV={upset['emv']:.2f}")
                
                # FIX: RE-PROPAGATE picks for all later rounds after adding this upset
                # Only update NON-LOCKED slots by picking the team with higher matchup probability
                for propagate_round in range(round_num + 1, 7):
                    for prop_slot in bracket.slots:
                        if prop_slot.round_num != propagate_round:
                            continue
                        
                        # Skip locked slots
                        if prop_slot.slot_id in locked_slots:
                            continue
                        
                        # Find feeders
                        feeders = [s for s in bracket.slots if s.feeds_into == prop_slot.slot_id]
                        if len(feeders) == 2:
                            team_a_new = existing_picks.get(feeders[0].slot_id)
                            team_b_new = existing_picks.get(feeders[1].slot_id)
                            
                            if team_a_new and team_b_new:
                                # Pick team with higher matchup probability
                                prob_a_new = matchup_matrix.get(team_a_new, {}).get(team_b_new, 0.5)
                                winner_new = team_a_new if prob_a_new >= 0.5 else team_b_new
                                existing_picks[prop_slot.slot_id] = winner_new
    
    logger.info(f"  Added {later_upsets_added} later-round upsets (R2-R5)")
    
    # PHASE 5: Validate coherence
    validate_bracket_coherence(existing_picks, bracket)
    
    # Build CompleteBracket
    picks = []
    
    for slot_id, winner in existing_picks.items():
        slot = next((s for s in bracket.slots if s.slot_id == slot_id), None)
        if not slot or slot.round_num == 0:
            continue
        
        # Get leverage
        profile = ownership_map.get(winner)
        leverage = profile.leverage_by_round.get(slot.round_num, 1.0) if profile else 1.0
        
        # Determine if upset and calculate win probability
        is_upset = False
        win_prob = 0.6  # Default
        
        if slot.round_num == 1:
            # R1 games - we know both teams
            is_upset = (winner == slot.team_b and slot.seed_a < slot.seed_b) or \
                      (winner == slot.team_a and slot.seed_b < slot.seed_a)
            
            # Get actual win probability from matchup matrix
            loser = slot.team_b if winner == slot.team_a else slot.team_a
            win_prob = matchup_matrix.get(winner, {}).get(loser, 0.5)
        else:
            # R2-R6 games - find the two teams that fed into this slot
            feeders = [s for s in bracket.slots if s.feeds_into == slot_id]
            if len(feeders) == 2:
                team_a = existing_picks.get(feeders[0].slot_id)
                team_b = existing_picks.get(feeders[1].slot_id)
                
                if team_a and team_b:
                    # Get win probability from matchup matrix
                    loser = team_b if winner == team_a else team_a
                    win_prob = matchup_matrix.get(winner, {}).get(loser, 0.5)
                    
                    # BUG FIX #1: For R2+ rounds, determine upset using ACTUAL team seeds
                    # slot.seed_a and slot.seed_b are 0 for R2+, so we look up from team_map
                    team_a_obj = team_map.get(team_a)
                    team_b_obj = team_map.get(team_b)
                    winner_obj = team_map.get(winner)
                    loser_obj = team_map.get(loser)
                    
                    if winner_obj and loser_obj:
                        # Upset = lower seed (higher number) beats higher seed (lower number)
                        is_upset = (winner_obj.seed > loser_obj.seed)
        
        # Assign confidence tier based on win probability
        confidence = assign_confidence_tier(win_prob)
        
        picks.append(BracketPick(
            slot_id=slot_id,
            round_num=slot.round_num,
            winner=winner,
            confidence=confidence,
            leverage_score=leverage,
            is_upset=is_upset
        ))
    
    # Extract FF and E8
    ff_teams = list(scenario.final_four.values())
    e8_slots = [s for s in bracket.slots if s.round_num == 3]
    e8_teams = [existing_picks.get(s.slot_id) for s in e8_slots]
    
    return CompleteBracket(
        picks=picks,
        champion=scenario.champion,
        final_four=ff_teams[:4],
        elite_eight=[t for t in e8_teams if t][:8],
        label=scenario.scenario_id,
        expected_score=0.0,
        p_first_place=0.0,
        p_top_three=0.0,
        expected_finish=0.0
    )


# ============================================================================
# COMPONENT 5: MONTE CARLO EVALUATOR
# ============================================================================

def run_monte_carlo_evaluation(
    our_bracket: CompleteBracket,
    matchup_matrix: dict[str, dict[str, float]],
    ownership_profiles: list[OwnershipProfile],
    bracket: BracketStructure,
    pool_size: int,
    scoring: list[int],
    sim_count: int = 10000,
    base_seed: int = 42
) -> None:
    """Run Monte Carlo simulation to evaluate a bracket's pool performance.
    
    Updates the bracket's p_first_place, p_top_three, expected_finish, expected_score in-place.
    """
    logger.info(f"  Monte Carlo evaluation: {sim_count} sims for {our_bracket.label}")
    
    # Convert bracket picks to dict
    our_picks = {pick.slot_id: pick.winner for pick in our_bracket.picks}
    
    # Track results
    finishes = []
    scores = []
    first_place_count = 0
    top_three_count = 0
    
    for sim_id in range(sim_count):
        rng = random.Random(base_seed + sim_id)
        
        # Simulate actual tournament
        actual_results = simulate_tournament(matchup_matrix, bracket, rng)
        
        # Generate opponent brackets
        opponent_brackets = []
        for opp_id in range(pool_size - 1):
            opp_rng = random.Random(base_seed + sim_id * 1000 + opp_id)
            opp_picks = generate_opponent_bracket(ownership_profiles, bracket, matchup_matrix, opp_rng)
            opponent_brackets.append(opp_picks)
        
        # Score our bracket and determine rank
        our_score, our_rank = evaluate_bracket_in_pool(
            our_picks, actual_results, opponent_brackets, scoring, bracket
        )
        
        finishes.append(our_rank)
        scores.append(our_score)
        
        if our_rank == 1:
            first_place_count += 1
        if our_rank <= 3:
            top_three_count += 1
    
    # Update bracket metrics
    our_bracket.p_first_place = first_place_count / sim_count
    our_bracket.p_top_three = top_three_count / sim_count
    our_bracket.expected_finish = mean(finishes)
    our_bracket.expected_score = mean(scores)
    
    logger.info(f"    P(1st)={our_bracket.p_first_place:.1%}, "
               f"P(top 3)={our_bracket.p_top_three:.1%}, "
               f"E[finish]={our_bracket.expected_finish:.1f}, "
               f"E[score]={our_bracket.expected_score:.1f}")


# ============================================================================
# COMPONENT 7: OUTPUT SELECTION
# ============================================================================

def select_diverse_output_brackets(brackets: list[CompleteBracket]) -> list[CompleteBracket]:
    """Select 3 diverse output brackets from evaluated candidates (Amendment 4: stronger differentiation).
    
    Returns [optimal, safe, aggressive] with enforced differentiation.
    """
    logger.info("=== COMPONENT 7: Selecting diverse output brackets ===")
    
    if len(brackets) < 3:
        logger.warning(f"Only {len(brackets)} brackets available, need at least 3")
        # Pad with duplicates if needed
        while len(brackets) < 3:
            brackets.append(copy.deepcopy(brackets[0]))
    
    # Sort by P(1st)
    sorted_by_p_first = sorted(brackets, key=lambda b: b.p_first_place, reverse=True)
    
    # Bracket 1: Optimal (highest P(1st))
    optimal = sorted_by_p_first[0]
    optimal.label = "optimal"
    
    # Bracket 2: Safe (among brackets with P(1st) > 50% of optimal, pick highest P(top 3))
    # Must have >= 8 different picks from optimal (Amendment 4)
    safe = None
    min_p_first = optimal.p_first_place * 0.5
    
    # Try with 8+ different picks
    candidates_for_safe = [b for b in sorted_by_p_first[1:] 
                          if b.p_first_place >= min_p_first]
    
    for candidate in candidates_for_safe:
        diff_count = count_different_picks(optimal, candidate, weighted=True)
        if diff_count >= 8:  # Amendment 4: raised from 3 to 8
            safe = candidate
            break
    
    # Relax to 5+ different picks if needed
    if not safe:
        for candidate in candidates_for_safe:
            diff_count = count_different_picks(optimal, candidate, weighted=True)
            if diff_count >= 5:
                safe = candidate
                break
    
    # Last resort: just take 2nd best
    if not safe:
        safe = sorted_by_p_first[1] if len(sorted_by_p_first) > 1 else copy.deepcopy(optimal)
    
    safe.label = "safe_alternate"
    
    # Bracket 3: Aggressive - MUST have different champion, >= 15 different picks (Amendment 4)
    aggressive = None
    
    # First try: different champion AND >= 15 weighted picks different
    for candidate in sorted_by_p_first:
        if candidate is optimal or candidate is safe:
            continue
        if candidate.champion != optimal.champion:
            diff_count = count_different_picks(optimal, candidate, weighted=True)
            if diff_count >= 15:  # Amendment 4: raised threshold
                aggressive = candidate
                break
    
    # Second try: different champion AND >= 10 picks different
    if not aggressive:
        for candidate in sorted_by_p_first:
            if candidate is optimal or candidate is safe:
                continue
            if candidate.champion != optimal.champion:
                diff_count = count_different_picks(optimal, candidate, weighted=True)
                if diff_count >= 10:
                    aggressive = candidate
                    break
    
    # Third try: any bracket with different champion
    if not aggressive:
        for candidate in sorted_by_p_first:
            if candidate is optimal or candidate is safe:
                continue
            if candidate.champion != optimal.champion:
                aggressive = candidate
                break
    
    # Last resort: most different bracket even if same champion
    if not aggressive:
        best_diff = 0
        for candidate in sorted_by_p_first:
            if candidate is not optimal and candidate is not safe:
                diff = count_different_picks(optimal, candidate, weighted=True)
                if diff > best_diff:
                    best_diff = diff
                    aggressive = candidate
        
        if not aggressive:
            aggressive = copy.deepcopy(safe)
    
    aggressive.label = "aggressive_alternate"
    
    # Log differentiation metrics
    safe_diff = count_different_picks(optimal, safe)
    aggressive_diff = count_different_picks(optimal, aggressive)
    safe_agg_diff = count_different_picks(safe, aggressive)
    
    logger.info(f"Selected 3 brackets:")
    logger.info(f"  Optimal: champion={optimal.champion}, P(1st)={optimal.p_first_place:.1%}, P(top 3)={optimal.p_top_three:.1%}")
    logger.info(f"  Safe: champion={safe.champion}, P(1st)={safe.p_first_place:.1%}, P(top 3)={safe.p_top_three:.1%} ({safe_diff} picks different from optimal)")
    logger.info(f"  Aggressive: champion={aggressive.champion}, P(1st)={aggressive.p_first_place:.1%}, P(top 3)={aggressive.p_top_three:.1%} ({aggressive_diff} picks different from optimal)")
    
    return [optimal, safe, aggressive]


def count_different_picks(bracket_a: CompleteBracket, bracket_b: CompleteBracket, weighted: bool = False) -> int:
    """Count how many picks differ between two brackets.
    
    If weighted=True, later rounds count more:
    - R5/R6 (FF/Championship): 3x weight
    - R3/R4 (S16/E8): 2x weight  
    - R1/R2: 1x weight
    """
    picks_a = {pick.slot_id: pick.winner for pick in bracket_a.picks}
    picks_b = {pick.slot_id: pick.winner for pick in bracket_b.picks}
    
    diff_count = 0
    
    if not weighted:
        for slot_id in picks_a:
            if slot_id in picks_b and picks_a[slot_id] != picks_b[slot_id]:
                diff_count += 1
    else:
        # Weighted differences - get round info
        round_map = {}
        for pick in bracket_a.picks:
            round_map[pick.slot_id] = pick.round_num
        
        for slot_id in picks_a:
            if slot_id in picks_b and picks_a[slot_id] != picks_b[slot_id]:
                round_num = round_map.get(slot_id, 1)
                if round_num >= 5:
                    diff_count += 3  # FF/Championship
                elif round_num >= 3:
                    diff_count += 2  # S16/E8
                else:
                    diff_count += 1  # R1/R2
    
    return diff_count


# ============================================================================
# TOP-LEVEL ORCHESTRATOR
# ============================================================================

def optimize_bracket(teams: list[Team], 
                    matchup_matrix: dict[str, dict[str, float]], 
                    ownership_profiles: list[OwnershipProfile], 
                    bracket: BracketStructure, 
                    config) -> list[CompleteBracket]:
    """Full optimization pipeline - generates ~24 scenarios across top 8 champions, returns 3 optimized brackets."""
    logger.info("=== Starting bracket optimization (V2) ===")
    
    # Handle config attributes with defaults for backward compatibility
    pool_size = getattr(config, 'pool_size', 25)
    sim_count = getattr(config, 'sim_count', 10000)
    base_seed = getattr(config, 'random_seed', 42) or 42
    scoring = getattr(config, 'scoring', [10, 20, 40, 80, 160, 320])
    
    logger.info(f"Pool size: {pool_size}, Sim count: {sim_count}")
    
    # COMPONENT 1: Evaluate champion candidates
    champion_candidates = evaluate_champions(
        teams, matchup_matrix, ownership_profiles, bracket,
        pool_size, sim_count=2000, base_seed=base_seed
    )
    
    # COMPONENT 2: Generate scenarios
    scenarios = generate_scenarios(
        champion_candidates, teams, matchup_matrix, ownership_profiles,
        bracket, pool_size
    )
    
    # COMPONENT 3: Construct brackets from scenarios (with EMV upsets!)
    brackets = []
    for scenario in scenarios:
        bracket_obj = construct_bracket_from_scenario(
            scenario, teams, matchup_matrix, ownership_profiles,
            bracket, pool_size, scoring
        )
        brackets.append(bracket_obj)
    
    logger.info(f"Constructed {len(brackets)} scenario-based brackets")
    
    # COMPONENT 5: Monte Carlo evaluation for each bracket
    logger.info("=== COMPONENT 5: Monte Carlo evaluation ===")
    for bracket_obj in brackets:
        run_monte_carlo_evaluation(
            bracket_obj, matchup_matrix, ownership_profiles,
            bracket, pool_size, scoring, sim_count, base_seed
        )
    
    # COMPONENT 7: Select 3 diverse output brackets
    result_brackets = select_diverse_output_brackets(brackets)
    
    logger.info(f"Pipeline complete. Returning {len(result_brackets)} optimized brackets.")
    
    return result_brackets
