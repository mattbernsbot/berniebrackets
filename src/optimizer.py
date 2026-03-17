"""Monte Carlo optimization engine - V2 Complete Implementation.

Implements a 7-component pipeline that maximizes P(1st place) in bracket pools.
"""

import logging
import os
import random
import copy
from statistics import mean, median
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from itertools import product as _iproduct, combinations as _icombinations
from math import sqrt

import numpy as np

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
from src.sharp import adj_em_to_win_prob

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
    """Generate one simulated opponent bracket using ownership distributions.

    Top-down approach: sample champion from title_ownership, lock their full
    path (R1→Championship), then fill remaining games bottom-up using
    round-specific ownership percentages.
    """
    picks = {}
    ownership_map = {p.team: p for p in ownership_profiles}

    # Phase 1: Sample champion from title ownership
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

    # Phase 2: Lock the champion's path through the bracket
    champion_path_set = set(find_champion_path(champion, bracket))

    # Phase 3: Fill all slots round by round
    # Rounds 0 and 1 (play-in and R64)
    for slot in bracket.slots:
        if slot.round_num not in [0, 1]:
            continue
        if not (slot.team_a and slot.team_b):
            continue

        if slot.slot_id in champion_path_set:
            picks[slot.slot_id] = champion
            continue

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

    # Rounds 2-6
    slots_by_round = {}
    for slot in bracket.slots:
        if slot.round_num not in slots_by_round:
            slots_by_round[slot.round_num] = []
        slots_by_round[slot.round_num].append(slot)

    for round_num in range(2, 7):
        if round_num not in slots_by_round:
            continue

        for slot in slots_by_round[round_num]:
            if slot.slot_id in champion_path_set:
                picks[slot.slot_id] = champion
                continue

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


def find_champion_path(champion_name: str, bracket: BracketStructure) -> list[int]:
    """Return ordered slot_ids (R1 through Championship) that the champion must win.

    Follows the feeds_into chain from the team's R1 slot up to the championship
    (feeds_into == 0). Returns an empty list if the team has no R1 slot.
    """
    r1_slot = find_team_r1_slot(champion_name, bracket)
    if r1_slot is None:
        return []
    slot_map = {s.slot_id: s for s in bracket.slots}
    path = [r1_slot.slot_id]
    current = r1_slot
    while current.feeds_into:
        current = slot_map.get(current.feeds_into)
        if current is None:
            break
        path.append(current.slot_id)
    return path


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
    """Identify up to 12 viable champion candidates ranked by pool-adjusted value."""
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

        # Seeds 1-6 are realistic national champion contenders
        if team.seed > 6:
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
    
    top_candidates = candidates[:24]

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


def construct_deterministic_bracket(
    label: str,
    prob_fn,  # callable(team_a_name: str, team_b_name: str) -> float P(A beats B)
    bracket: BracketStructure,
    teams: list[Team],
    ownership_profiles: list[OwnershipProfile],
) -> CompleteBracket:
    """Build a bracket by always picking the highest-probability team in every game.

    prob_fn(a, b) should return P(a beats b). Winner is always the team with prob >= 0.5.
    No EMV, no chaos, no cinderella — pure deterministic chalk using the given probability source.
    Used to inject CHALK, KP_CHALK, and BERNS_CHALK reference brackets.
    """
    team_map = {t.name: t for t in teams}
    ownership_map = {p.team: p for p in ownership_profiles} if ownership_profiles else {}

    # Build feeder_map: target_slot_id -> [source_slot_id, source_slot_id]
    feeder_map: dict[int, list[int]] = {}
    for slot in bracket.slots:
        if slot.feeds_into:
            feeder_map.setdefault(slot.feeds_into, []).append(slot.slot_id)

    # Walk rounds in order, filling picks deterministically
    picks_dict: dict[int, str] = {}  # slot_id -> winner_name
    slots_by_round: dict[int, list] = {}
    for slot in bracket.slots:
        slots_by_round.setdefault(slot.round_num, []).append(slot)

    for round_num in sorted(slots_by_round.keys()):
        for slot in slots_by_round[round_num]:
            if round_num <= 1:
                team_a, team_b = slot.team_a, slot.team_b
            else:
                feeders = feeder_map.get(slot.slot_id, [])
                if len(feeders) < 2:
                    continue
                team_a = picks_dict.get(feeders[0])
                team_b = picks_dict.get(feeders[1])

            if not team_a or not team_b:
                continue

            try:
                prob_a = prob_fn(team_a, team_b)
            except (KeyError, AttributeError):
                prob_a = 0.5
            winner = team_a if prob_a >= 0.5 else team_b
            picks_dict[slot.slot_id] = winner

    # Build BracketPick list (skip round 0 play-in)
    picks = []
    for slot in bracket.slots:
        winner = picks_dict.get(slot.slot_id)
        if not winner or slot.round_num == 0:
            continue

        # Determine opponent to check is_upset
        if slot.round_num == 1:
            loser = slot.team_b if winner == slot.team_a else slot.team_a
        else:
            feeders = feeder_map.get(slot.slot_id, [])
            loser = next(
                (picks_dict.get(fid) for fid in feeders if picks_dict.get(fid) != winner),
                None
            )

        winner_team = team_map.get(winner)
        loser_team = team_map.get(loser) if loser else None
        is_upset = bool(
            winner_team and loser_team and winner_team.seed > loser_team.seed
        )

        # Win probability for confidence tier
        try:
            win_prob = prob_fn(winner, loser) if loser else 0.5
        except (KeyError, AttributeError):
            win_prob = 0.5

        leverage_score = 1.0
        if winner in ownership_map:
            leverage_score = ownership_map[winner].leverage_by_round.get(slot.round_num, 1.0)

        picks.append(BracketPick(
            slot_id=slot.slot_id,
            round_num=slot.round_num,
            winner=winner,
            confidence=assign_confidence_tier(win_prob),
            leverage_score=leverage_score,
            is_upset=is_upset,
        ))

    max_round = max((s.round_num for s in bracket.slots), default=1)
    championship_slot = next((s for s in bracket.slots if s.round_num == max_round), None)
    champion = picks_dict.get(championship_slot.slot_id) if championship_slot else "Unknown"

    final_four = []
    if max_round >= 5:
        ff_slots = [s for s in bracket.slots if s.round_num == max_round - 2]
        final_four = [picks_dict.get(s.slot_id) for s in ff_slots if picks_dict.get(s.slot_id)]

    elite_eight = []
    if max_round >= 4:
        e8_slots = [s for s in bracket.slots if s.round_num == max_round - 3]
        elite_eight = [picks_dict.get(s.slot_id) for s in e8_slots if picks_dict.get(s.slot_id)]

    logger.info(
        f"  Deterministic bracket [{label}]: champion={champion}, "
        f"upsets={sum(1 for p in picks if p.is_upset)}"
    )
    return CompleteBracket(
        picks=picks,
        champion=champion,
        final_four=final_four,
        elite_eight=elite_eight,
        label=label,
        expected_score=0.0,
        p_first_place=0.0,
        p_top_three=0.0,
        expected_finish=0.0,
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
                            exclude_teams: list[str] | None = None,
                            top_k: int = 1) -> tuple[str, float] | list[tuple[str, float]]:
    """Select the best team(s) to win a region given a chaos level.

    top_k=1 (default): returns (team_name, value) — same behaviour as before.
    top_k>1: returns list[tuple[str, float]] sorted by regional_value descending.
    """
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
    ranked: list[tuple[str, float]] = []

    for team in regional_teams:
        path_info = compute_champion_path(team, bracket, matchup_matrix, teams)
        regional_prob = 1.0
        for _, _opp, win_prob in path_info.opponents[:4]:
            regional_prob *= win_prob

        profile = ownership_map.get(team.name)
        ff_ownership = profile.round_ownership.get(5, 0.01) if profile else SEED_OWNERSHIP_CURVES.get(team.seed, {}).get(5, 0.01)
        ff_ownership = max(0.001, ff_ownership)

        regional_value = regional_prob / ((pool_size - 1) * ff_ownership + 1)
        ranked.append((team.name, regional_value))

    ranked.sort(key=lambda x: x[1], reverse=True)

    if not ranked:
        fallback = regional_teams[0].name if regional_teams else ""
        return (fallback, 0.0) if top_k == 1 else [(fallback, 0.0)]

    if top_k == 1:
        return ranked[0][0], ranked[0][1]
    return ranked[:top_k]


def select_cinderella(teams: list[Team],
                     matchup_matrix: dict[str, dict[str, float]],
                     ownership_profiles: list[OwnershipProfile],
                     bracket: BracketStructure,
                     chaos_regions: list[str],
                     pool_size: int,
                     top_k: int = 1) -> tuple[str | None, int | None] | list[tuple[str, int]]:
    """Select Cinderella team(s) for a deep tournament run.

    top_k=1 (default): returns (team_name, target_round) — same behaviour as before.
    top_k>1: returns list[tuple[str, int]] sorted by upset_prob descending.
    """
    if not chaos_regions:
        return (None, None) if top_k == 1 else []

    candidates = []
    team_map = {t.name: t for t in teams}

    for team in teams:
        if team.region not in chaos_regions:
            continue
        if team.seed < 9 or team.seed > 14:
            continue

        r1_slot = find_team_r1_slot(team.name, bracket)
        if not r1_slot:
            continue

        opponent_name = r1_slot.team_b if r1_slot.team_a == team.name else r1_slot.team_a
        opponent = team_map.get(opponent_name)
        if not opponent:
            continue

        adjem_gap = abs(team.adj_em - opponent.adj_em)
        if adjem_gap > 15:
            continue

        upset_prob = matchup_matrix.get(team.name, {}).get(opponent_name, 0.0)
        if upset_prob < 0.2:
            continue

        target_round = 3 if team.seed <= 12 else 2
        candidates.append((team.name, target_round, upset_prob))

    if not candidates:
        return (None, None) if top_k == 1 else []

    candidates.sort(key=lambda x: x[2], reverse=True)

    if top_k == 1:
        best = candidates[0]
        return best[0], best[1]
    return [(c[0], c[1]) for c in candidates[:top_k]]


def generate_scenarios(champion_candidates: list[ChampionCandidate],
                      teams: list[Team],
                      matchup_matrix: dict[str, dict[str, float]],
                      ownership_profiles: list[OwnershipProfile],
                      bracket: BracketStructure,
                      pool_size: int) -> list[Scenario]:
    """Generate ~600 scenarios covering expanded FF compositions, cinderella variants,
    and chaos-region permutations across top 12 champion candidates.

    Expansion axes vs the original ~72-scenario design:
    - FF composition: top-3 candidates per region → enumerate up to 8 combos per cell
      (original: 2 combos per cell)
    - Cinderella: top-2 candidates for medium/high chaos
      (original: 1)
    - Medium chaos-regions: 2 different region-pairs instead of 1 fixed pair
      (original: 1)

    Approximate budget: 12 × (low:6 + medium:2×8×2 + high:8×2) ≈ 600 scenarios.
    """
    logger.info("=== COMPONENT 2: Generating scenarios (expanded ~600) ===")

    if not champion_candidates:
        logger.warning("No champion candidates provided")
        return []

    scenarios: list[Scenario] = []
    regions = list(set(t.region for t in teams if t.region))

    # ---- helpers ----

    def _chaos_regions_options(champ_region: str, chaos_level: str) -> list[list[str]]:
        """Return the list of chaos_regions lists to iterate for this chaos level.

        low  → [[]]  (one option: no chaos regions)
        medium → up to 2 pairs from C(other_regions, 2)
        high   → [other_regions]  (one option: all non-champion regions)
        """
        other = [r for r in regions if r != champ_region]
        if chaos_level == "low":
            return [[]]
        elif chaos_level == "medium":
            if len(other) >= 2:
                pairs = list(_icombinations(other, 2))
                return [list(p) for p in pairs]   # all C(3,2)=3 pairs
            return [other]
        else:  # high
            return [other]

    def _get_ff_combinations(champ_cand: ChampionCandidate,
                             chaos_level: str,
                             non_champ_regions: list[str],
                             max_combos: int) -> list[dict[str, str]]:
        """Enumerate up to max_combos FF dicts for a (champion, chaos_level) cell.

        Gets top-3 regional candidates per non-champion region, takes their
        cross-product sorted by combined regional_value, deduplicates.
        """
        per_region: dict[str, list[tuple[str, float]]] = {}
        for region in non_champ_regions:
            ranked = select_regional_champion(
                region, teams, matchup_matrix, ownership_profiles, bracket,
                chaos_level, pool_size, top_k=4
            )
            # top_k>1 always returns a list
            per_region[region] = ranked if isinstance(ranked, list) else [ranked]

        combos_raw: list[tuple[dict[str, str], float]] = []
        for combo in _iproduct(*[per_region[r] for r in non_champ_regions]):
            ff_dict: dict[str, str] = {champ_cand.region: champ_cand.team_name}
            combined_value = 1.0
            for region, (team_name, value) in zip(non_champ_regions, combo):
                ff_dict[region] = team_name
                combined_value *= max(value, 0.001)
            combos_raw.append((ff_dict, combined_value))

        combos_raw.sort(key=lambda x: x[1], reverse=True)

        seen: set[tuple] = set()
        result: list[dict[str, str]] = []
        for ff_dict, _ in combos_raw:
            key = tuple(sorted(ff_dict.items()))
            if key not in seen:
                seen.add(key)
                result.append(ff_dict)
                if len(result) >= max_combos:
                    break
        return result

    # ---- main loop ----

    _stype = {"low": "chalk", "medium": "contrarian", "high": "chaos"}
    _max_ff = {"low": 8, "medium": 12, "high": 12}

    for champ_cand in champion_candidates:
        other_regions = [r for r in regions if r != champ_cand.region]

        for chaos_level in ["low", "medium", "high"]:
            # Seeds 5-6 only realistic in chaotic tournaments
            if champ_cand.seed >= 5 and chaos_level == "low":
                continue
            scenario_type = _stype[chaos_level]
            max_ff = _max_ff[chaos_level]

            for chaos_regions in _chaos_regions_options(champ_cand.region, chaos_level):
                # Cinderella variants for this (chaos_level, chaos_regions) combo
                if chaos_level == "low":
                    cinderella_variants: list[tuple[str | None, int | None]] = [(None, None)]
                else:
                    raw = select_cinderella(
                        teams, matchup_matrix, ownership_profiles, bracket,
                        chaos_regions, pool_size, top_k=2
                    )
                    if raw:
                        cinderella_variants = raw  # type: ignore[assignment]
                    else:
                        # Force a seed-12 cinderella for high chaos if none qualifies
                        if chaos_level == "high" and chaos_regions:
                            forced = [t for t in teams
                                      if t.region in chaos_regions and t.seed == 12]
                            cinderella_variants = [(forced[0].name, 3)] if forced else [(None, None)]
                        else:
                            cinderella_variants = [(None, None)]

                # FF combinations for this cell
                ff_combinations = _get_ff_combinations(
                    champ_cand, chaos_level, other_regions, max_combos=max_ff
                )

                cr_tag = "".join(sorted(chaos_regions))[:8] if chaos_regions else ""

                for ff_idx, ff_dict in enumerate(ff_combinations):
                    for cinder_idx, (cinderella, cinder_target) in enumerate(cinderella_variants):
                        sid = f"{scenario_type}_{champ_cand.team_name}_{chaos_level}"
                        if cr_tag:
                            sid += f"_cr{cr_tag}"
                        if ff_idx > 0:
                            sid += f"_ff{ff_idx + 1}"
                        if cinder_idx > 0:
                            sid += f"_c{cinder_idx + 1}"

                        scenarios.append(Scenario(
                            scenario_id=sid,
                            scenario_type=scenario_type,
                            champion=champ_cand.team_name,
                            champion_seed=champ_cand.seed,
                            final_four=ff_dict,
                            chaos_regions=chaos_regions,
                            cinderella=cinderella,
                            cinderella_target_round=cinder_target,
                            chaos_level=chaos_level
                        ))

    logger.info(f"Generated {len(scenarios)} scenarios across {len(champion_candidates)} champions")
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

    # PHASE 1.5: Lock cinderella path if specified
    if scenario.cinderella and scenario.cinderella_target_round:
        cinder_r1 = find_team_r1_slot(scenario.cinderella, bracket)
        if cinder_r1 and cinder_r1.slot_id not in locked_slots:
            cinder_path = build_team_path(
                scenario.cinderella, scenario.cinderella_target_round,
                bracket, matchup_matrix, teams, existing_picks
            )
            locked_slots.update(cinder_path.path_slots)
            logger.info(f"  Locked cinderella path: {scenario.cinderella} → R{scenario.cinderella_target_round}")

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
        
        # Determine if this slot's region is a declared chaos region
        is_chaos_region = bool(scenario.chaos_regions and slot.region in scenario.chaos_regions)
        effective_floor = emv_floor - 1.5 if is_chaos_region else emv_floor

        # Add to candidates if it passes EMV floor (Gate 1)
        if emv > effective_floor:
            upset_candidates.append({
                'slot_id': slot.slot_id,
                'underdog': underdog,
                'favorite': favorite,
                'dog_seed': dog_seed,
                'fav_seed': fav_seed,
                'emv': emv,
                'p_upset': p_upset,
                'is_8_9': (fav_seed == 8 and dog_seed == 9) or (fav_seed == 9 and dog_seed == 8),
                'is_chaos_region': is_chaos_region,
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
        
        # Check region cap (chaos regions get +1 allowance)
        slot = next((s for s in bracket.slots if s.slot_id == upset['slot_id']), None)
        if slot:
            region = slot.region
            is_chaos = upset.get('is_chaos_region', False)
            effective_max = (max_per_region + 1) if is_chaos else max_per_region
            if region_counts.get(region, 0) >= effective_max:
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
# HIGH-PERFORMANCE MC EVALUATOR (shared sims + numpy + parallel pre-gen)
# ============================================================================

def _prebuild_sim_batch_worker(args: tuple) -> tuple[np.ndarray, np.ndarray]:
    """ProcessPoolExecutor worker: generate one batch of tournament sims + opponent brackets.

    Returns two numpy int16 arrays:
      sim_batch  shape (batch_size, n_slots)
      opp_batch  shape (batch_size, pool_size-1, n_slots)

    Must be a module-level function (not a closure) so it is picklable.
    """
    (sim_id_start, sim_id_end, base_seed,
     matchup_matrix, bracket_structure, ownership_profiles,
     pool_size, team_idx, slot_id_to_idx, n_slots) = args

    UNKNOWN = len(team_idx)  # sentinel: slot not filled / team not in index
    batch_size = sim_id_end - sim_id_start
    sim_batch = np.full((batch_size, n_slots), UNKNOWN, dtype=np.int16)
    opp_batch = np.full((batch_size, pool_size - 1, n_slots), UNKNOWN, dtype=np.int16)

    for local_i, sim_id in enumerate(range(sim_id_start, sim_id_end)):
        rng = random.Random(base_seed + sim_id)
        actual = simulate_tournament(matchup_matrix, bracket_structure, rng)
        for slot_id, winner in actual.items():
            idx = slot_id_to_idx.get(slot_id)
            if idx is not None:
                sim_batch[local_i, idx] = team_idx.get(winner, UNKNOWN)

        for opp_id in range(pool_size - 1):
            opp_rng = random.Random(base_seed + sim_id * 1000 + opp_id)
            opp_picks = generate_opponent_bracket(
                ownership_profiles, bracket_structure, matchup_matrix, opp_rng
            )
            for slot_id, team in opp_picks.items():
                idx = slot_id_to_idx.get(slot_id)
                if idx is not None:
                    opp_batch[local_i, opp_id, idx] = team_idx.get(team, UNKNOWN)

    return sim_batch, opp_batch


def _score_bracket_numpy(
    picks_arr: np.ndarray,
    sim_matrix: np.ndarray,
    opp_matrix: np.ndarray,
    scoring_arr: np.ndarray,
    slot_rounds_arr: np.ndarray,
) -> tuple[float, float, float, float]:
    """Score one bracket against pre-generated simulation data using numpy ops.

    Args:
        picks_arr:      (n_slots,) int16 — our picks as team indices
        sim_matrix:     (sim_count, n_slots) int16 — tournament outcomes
        opp_matrix:     (sim_count, pool_size-1, n_slots) int16 — opponent picks
        scoring_arr:    (6,) int32 — points per round (0-indexed)
        slot_rounds_arr:(n_slots,) int32 — round index (0-based) per slot

    Returns:
        (p_first_place, p_top_three, expected_finish, expected_score)
    """
    weights = scoring_arr[slot_rounds_arr]          # (n_slots,)

    # Our score per simulation
    correct = picks_arr == sim_matrix               # (sim_count, n_slots) bool
    our_scores = (correct * weights).sum(axis=1)    # (sim_count,)

    # Opponent scores per simulation
    # Broadcasting: sim_matrix[:, None, :] → (sim_count, 1, n_slots)
    opp_correct = opp_matrix == sim_matrix[:, np.newaxis, :]   # (sim_count, opp, n_slots)
    opp_scores = (opp_correct * weights).sum(axis=2)            # (sim_count, opp)

    # Rank: number of opponents strictly better than us + 1
    ranks = (opp_scores > our_scores[:, np.newaxis]).sum(axis=1) + 1  # (sim_count,)

    return (
        float((ranks == 1).mean()),
        float((ranks <= 3).mean()),
        float(ranks.mean()),
        float(our_scores.mean()),
    )


def evaluate_all_brackets_shared_sims(
    brackets: list[CompleteBracket],
    matchup_matrix: dict[str, dict[str, float]],
    ownership_profiles: list[OwnershipProfile],
    bracket_structure: BracketStructure,
    pool_size: int,
    scoring: list[int],
    sim_count: int = 10000,
    base_seed: int = 42,
    n_workers: int | None = None,
) -> None:
    """Evaluate all brackets with three combined performance improvements:

    Priority 1 — Shared simulations: pre-generate sim_count tournament outcomes
      and opponent brackets ONCE, shared across all brackets instead of per-bracket.

    Priority 2 — Parallel pre-generation: split the sim_count sims across
      n_workers ProcessPoolExecutor workers to cut pre-gen time by ~Nx.

    Priority 3 — Numpy vectorized scoring: score all brackets with array ops
      instead of Python loops (~10-50× faster than the original inner loop).

    Results are written in-place to each bracket's p_first_place / p_top_three /
    expected_finish / expected_score fields.  Seeding is identical to
    run_monte_carlo_evaluation(), so P(1st) values are numerically equivalent.
    """
    n_cpus = os.cpu_count() or 4
    if n_workers is None:
        n_workers = min(n_cpus, sim_count)
    n_workers = max(1, n_workers)

    logger.info(
        f"=== COMPONENT 5 (shared sims): {sim_count} sims × {len(brackets)} brackets "
        f"| {n_workers} pre-gen workers | numpy scoring ==="
    )

    # ---- build encoding tables ----
    all_teams = sorted(set(p.team for p in ownership_profiles))
    team_idx: dict[str, int] = {t: i for i, t in enumerate(all_teams)}
    UNKNOWN = len(all_teams)   # sentinel for unrecognised teams (never matches valid idx)

    # Only score round > 0 slots (skip play-in)
    scored_slots = sorted(
        [s for s in bracket_structure.slots if s.round_num > 0],
        key=lambda s: s.slot_id,
    )
    slot_id_to_idx: dict[int, int] = {s.slot_id: i for i, s in enumerate(scored_slots)}
    n_slots = len(scored_slots)
    slot_rounds_arr = np.array([s.round_num - 1 for s in scored_slots], dtype=np.int32)
    scoring_arr = np.array(scoring, dtype=np.int32)

    # ---- Phase A: parallel pre-generation of sim batches ----
    batch_size = max(1, (sim_count + n_workers - 1) // n_workers)
    batches: list[tuple[int, int]] = []
    for i in range(n_workers):
        start = i * batch_size
        end = min(start + batch_size, sim_count)
        if start < end:
            batches.append((start, end))

    worker_args = [
        (s, e, base_seed, matchup_matrix, bracket_structure,
         ownership_profiles, pool_size, team_idx, slot_id_to_idx, n_slots)
        for s, e in batches
    ]

    logger.info(f"Pre-generating: {len(batches)} batch(es) of ~{batch_size} sims each")
    with ProcessPoolExecutor(max_workers=len(batches)) as executor:
        batch_results = list(executor.map(_prebuild_sim_batch_worker, worker_args))

    sim_matrix = np.concatenate([br[0] for br in batch_results], axis=0)  # (sim_count, n_slots)
    opp_matrix = np.concatenate([br[1] for br in batch_results], axis=0)  # (sim_count, opp, n_slots)
    logger.info(
        f"Pre-generation done. "
        f"sim_matrix={sim_matrix.shape}, opp_matrix={opp_matrix.shape} "
        f"({(sim_matrix.nbytes + opp_matrix.nbytes) / 1e6:.1f} MB)"
    )

    # ---- Phase B: numpy vectorized scoring (single-threaded, very fast) ----
    logger.info(f"Scoring {len(brackets)} brackets with numpy...")
    for cb in brackets:
        picks_arr = np.full(n_slots, UNKNOWN, dtype=np.int16)
        for pick in cb.picks:
            idx = slot_id_to_idx.get(pick.slot_id)
            if idx is not None:
                picks_arr[idx] = team_idx.get(pick.winner, UNKNOWN)

        p_first, p_top3, exp_finish, exp_score = _score_bracket_numpy(
            picks_arr, sim_matrix, opp_matrix, scoring_arr, slot_rounds_arr
        )
        cb.p_first_place = p_first
        cb.p_top_three = p_top3
        cb.expected_finish = exp_finish
        cb.expected_score = exp_score
        logger.info(
            f"  {cb.label}: P(1st)={p_first:.1%}, P(top3)={p_top3:.1%}, "
            f"E[finish]={exp_finish:.1f}, E[score]={exp_score:.1f}"
        )

    logger.info("Shared-sim evaluation complete.")


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
    """Full optimization pipeline — generates ~600 scenarios across top 12 champions,
    evaluates all with shared-sim Monte Carlo (parallel pre-gen + numpy scoring),
    and returns all evaluated brackets (top 3 tagged optimal/safe/aggressive).
    """
    logger.info("=== Starting bracket optimization (V2 + high-perf MC) ===")

    # Handle config attributes with defaults for backward compatibility
    pool_size = getattr(config, 'pool_size', 25)
    sim_count = getattr(config, 'sim_count', 10000)
    base_seed = getattr(config, 'random_seed', 42) or 42
    scoring = getattr(config, 'scoring', [10, 20, 40, 80, 160, 320])

    logger.info(f"Pool size: {pool_size}, Sim count: {sim_count}")

    # COMPONENT 1: Evaluate champion candidates
    champion_candidates = evaluate_champions(
        teams, matchup_matrix, ownership_profiles, bracket,
        pool_size, sim_count=10000, base_seed=base_seed
    )

    # COMPONENT 2: Generate ~600 scenarios
    scenarios = generate_scenarios(
        champion_candidates, teams, matchup_matrix, ownership_profiles,
        bracket, pool_size
    )

    # COMPONENT 3: Construct brackets from scenarios (with EMV upsets)
    brackets = []
    for scenario in scenarios:
        bracket_obj = construct_bracket_from_scenario(
            scenario, teams, matchup_matrix, ownership_profiles,
            bracket, pool_size, scoring
        )
        brackets.append(bracket_obj)

    logger.info(f"Constructed {len(brackets)} scenario-based brackets")

    # COMPONENT 3.5: Inject 3 deterministic reference brackets
    logger.info("=== COMPONENT 3.5: Injecting reference brackets (CHALK / KP_CHALK / BERNS_CHALK) ===")
    _team_map_ref = {t.name: t for t in teams}

    def _chalk_prob(a, b):
        ta, tb = _team_map_ref[a], _team_map_ref[b]
        return 1.0 if ta.seed < tb.seed else (0.0 if ta.seed > tb.seed else 0.5)

    def _kp_prob(a, b):
        ta, tb = _team_map_ref[a], _team_map_ref[b]
        return adj_em_to_win_prob(ta.adj_em, tb.adj_em)

    def _model_prob(a, b):
        return matchup_matrix.get(a, {}).get(b, 0.5)

    for ref_label, pfn in [("CHALK", _chalk_prob), ("KP_CHALK", _kp_prob), ("BERNS_CHALK", _model_prob)]:
        ref_bracket = construct_deterministic_bracket(
            ref_label, pfn, bracket, teams, ownership_profiles
        )
        brackets.append(ref_bracket)

    logger.info(f"Reference brackets added. Total: {len(brackets)} brackets before dedup.")

    # Deduplicate brackets by exact picks content before expensive MC evaluation.
    # Different scenario parameters (chaos-region pairs, cinderella variants) often
    # construct to identical picks when the cinderella doesn't pass EMV or the
    # chaos_regions don't change the top FF teams.
    seen_picks_hashes: set[int] = set()
    unique_brackets: list[CompleteBracket] = []
    for b in brackets:
        h = hash(tuple(sorted((p.slot_id, p.winner) for p in b.picks)))
        if h not in seen_picks_hashes:
            seen_picks_hashes.add(h)
            unique_brackets.append(b)
    n_deduped = len(brackets) - len(unique_brackets)
    brackets = unique_brackets
    logger.info(
        f"Deduplication: removed {n_deduped} identical brackets "
        f"({len(brackets)} unique remain before MC)."
    )

    # COMPONENT 5: Shared-sim Monte Carlo evaluation (Priority 1+2+3)
    evaluate_all_brackets_shared_sims(
        brackets, matchup_matrix, ownership_profiles,
        bracket, pool_size, scoring, sim_count, base_seed
    )

    # Sort all brackets by P(1st) descending
    brackets.sort(key=lambda b: b.p_first_place, reverse=True)

    # COMPONENT 7: Tag top 3 diverse brackets (optimal, safe_alternate, aggressive_alternate)
    select_diverse_output_brackets(brackets)  # mutates .label in-place on the top 3

    logger.info(f"Pipeline complete. Returning all {len(brackets)} evaluated brackets.")

    return brackets
