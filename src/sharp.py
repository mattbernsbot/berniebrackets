"""Statistical modeling module - converts team stats to win probabilities.

Implements the ensemble upset model (LR + RF) with seed-based fallback.
"""

import logging
import math
import os
from pathlib import Path

from src.models import Team, Matchup
from src.constants import HISTORICAL_SEED_WIN_RATES, POWER_CONFERENCES
from src.utils import save_json, load_json

logger = logging.getLogger("bracket_optimizer")

# Global predictor instance (lazy loaded)
_predictor = None

def get_predictor():
    """Get or create the UpsetPredictor instance."""
    global _predictor
    if _predictor is None:
        try:
            # Import here to avoid circular dependencies
            import sys
            project_root = Path(__file__).parent.parent
            sys.path.insert(0, str(project_root))
            
            from upset_model.predict import UpsetPredictor
            _predictor = UpsetPredictor()
            logger.info("Loaded ensemble upset model successfully")
        except Exception as e:
            logger.warning(f"Could not load ensemble model: {e}. Using fallback.")
            _predictor = None
    return _predictor


def adj_em_to_win_prob(adj_em_a: float, adj_em_b: float, tempo_a: float = 67.5, tempo_b: float = 67.5) -> float:
    """Convert AdjEM differential to win probability using logistic model.
    
    Uses the formula: P(A wins) = 1 / (1 + 10^(-ΔEM / κ))
    where ΔEM = adj_em_a - adj_em_b and κ = 13.0 (tournament-specific).
    
    κ = 13.0 (vs 11.5 for regular season) reflects higher variance in tournament games
    due to single-elimination pressure, extended preparation time, and neutral sites.
    
    The tempo parameters estimate expected possessions, affecting variance.
    
    Args:
        adj_em_a: Team A's Adjusted Efficiency Margin.
        adj_em_b: Team B's Adjusted Efficiency Margin.
        tempo_a: Team A's adjusted tempo. Default is D1 average.
        tempo_b: Team B's adjusted tempo. Default is D1 average.
    
    Returns:
        Probability that Team A wins, between 0.0 and 1.0.
    """
    # Base logistic model - tournament-specific kappa
    kappa = 13.0  # Higher than regular season (11.5) to compress probabilities
    delta_em = adj_em_a - adj_em_b
    
    # Possession-based variance adjustment
    # Note: This adjustment is REDUCED for tournament games since fewer possessions
    # actually help underdogs in single-elimination contexts
    expected_possessions = (tempo_a + tempo_b) / 2 * 0.4
    avg_possessions = 67.5 * 0.4
    
    if expected_possessions > 0:
        # Dampen the variance adjustment for tournaments
        variance_factor = math.sqrt(avg_possessions / expected_possessions)
        # Only apply 50% of the variance adjustment
        variance_factor = 1.0 + (variance_factor - 1.0) * 0.5
        adjusted_delta = delta_em * variance_factor
    else:
        adjusted_delta = delta_em
    
    # Logistic function
    try:
        prob = 1.0 / (1.0 + math.pow(10, -adjusted_delta / kappa))
    except (OverflowError, ValueError):
        # Handle extreme values
        prob = 0.999 if adjusted_delta > 0 else 0.001
    
    # Clamp to valid range
    return max(0.01, min(0.99, prob))


def compute_upset_propensity_score(favorite: Team, underdog: Team) -> float:
    """Compute the Upset Propensity Score (UPS) for a matchup.
    
    Evaluates 6 features that predict upset likelihood beyond raw AdjEM:
    - tempo_mismatch: Slow defensive underdogs compress variance
    - experience_edge: Tournament-tested underdogs handle pressure
    - momentum: Hot teams (auto-bid, recent wins) carry momentum
    - efficiency_gap_small: Small AdjEM gap = closer than seed suggests
    - underdog_quality: Better than their seed expects
    - free_throw_edge: Late-game execution (placeholder, needs FT% data)
    
    Args:
        favorite: The higher-seeded (lower seed number) team.
        underdog: The lower-seeded (higher seed number) team.
    
    Returns:
        UPS value between 0.0 and 1.0. Higher = more upset-prone.
        0.5 = neutral, >0.7 = strong upset candidate, <0.3 = chalk is safe.
    """
    from src.constants import UPS_WEIGHTS, SEED_DEFAULT_ADJEM
    
    # Feature 1: Tempo mismatch
    # 1.0 if underdog is slow-defensive AND favorite is fast
    tempo_mismatch = 0.0
    if underdog.adj_t < 64.0 and underdog.adj_d < 94.0 and favorite.adj_t > 69.0:
        tempo_mismatch = 1.0
    elif underdog.adj_t < 66.0 and underdog.adj_d < 96.0 and favorite.adj_t > 68.0:
        tempo_mismatch = 0.5
    
    # Feature 2: Experience edge
    # Scale 0-1 based on underdog's tournament experience
    experience_edge = min(1.0, underdog.tournament_appearances / 3.0)
    
    # Feature 3: Momentum
    # 1.0 if underdog won conf tourney, 0.5 if strong recent record
    momentum = 0.0
    if underdog.is_auto_bid:
        momentum = 1.0
    # Could add last-10 record here if available
    
    # Feature 4: Efficiency gap small
    # 1.0 if AdjEM gap < 6, scales down linearly to 0 at gap = 12
    delta_em = abs(favorite.adj_em - underdog.adj_em)
    efficiency_gap_small = max(0.0, 1.0 - delta_em / 12.0)
    
    # Feature 5: Underdog quality
    # How much better is the underdog than their seed expects?
    expected_em = SEED_DEFAULT_ADJEM.get(underdog.seed, 0.0)
    quality_bonus = (underdog.adj_em - expected_em) / 10.0
    underdog_quality = max(0.0, min(1.0, quality_bonus))
    
    # Feature 6: Free throw edge (placeholder - would need FT% data)
    # For now, default to 0.5 (neutral)
    free_throw_edge = 0.5
    
    # Weighted combination
    ups = (
        UPS_WEIGHTS["tempo_mismatch"] * tempo_mismatch +
        UPS_WEIGHTS["experience_edge"] * experience_edge +
        UPS_WEIGHTS["momentum"] * momentum +
        UPS_WEIGHTS["efficiency_gap_small"] * efficiency_gap_small +
        UPS_WEIGHTS["underdog_quality"] * underdog_quality +
        UPS_WEIGHTS["free_throw_edge"] * free_throw_edge
    )
    
    return max(0.0, min(1.0, ups))


def apply_upset_propensity_modifier(base_prob_favorite: float, ups: float, seed_fav: int, seed_dog: int) -> float:
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
    from src.constants import UPS_MAX_ADJUSTMENT
    
    # Get max adjustment for this seed matchup
    max_adj = UPS_MAX_ADJUSTMENT.get((seed_fav, seed_dog), 0.05)
    
    # UPS of 0.5 = no change; >0.5 = upset more likely; <0.5 = favorite safer
    # Map UPS [0,1] to adjustment [-max_adj, +max_adj]
    # UPS=0.5 -> 0, UPS=1.0 -> -max_adj, UPS=0.0 -> +max_adj
    adjustment = (0.5 - ups) * 2.0 * max_adj
    
    adjusted_prob = base_prob_favorite + adjustment
    
    return max(0.01, min(0.99, adjusted_prob))


def apply_tournament_experience_modifier(base_prob: float, team_a_appearances: int, team_b_appearances: int) -> float:
    """Adjust win probability based on recent tournament experience.
    
    Teams with Sweet 16+ appearances in the last 3 years get a boost.
    "Been there before" matters in high-pressure tournament games.
    
    Modifier: +0.03 per appearance for the more experienced team, capped at +0.06.
    (Increased from +0.02/+0.05 to make experience more impactful)
    
    Args:
        base_prob: Pre-modifier win probability for Team A.
        team_a_appearances: Team A's Sweet 16+ appearances in last 3 years.
        team_b_appearances: Team B's Sweet 16+ appearances in last 3 years.
    
    Returns:
        Modified win probability, clamped to [0.01, 0.99].
    """
    diff = team_a_appearances - team_b_appearances
    
    # Cap at ±2 appearances difference
    diff = max(-2, min(2, diff))
    
    modifier = 0.03 * diff
    
    adjusted_prob = base_prob + modifier
    
    return max(0.01, min(0.99, adjusted_prob))


def apply_tempo_mismatch_modifier(base_prob: float, tempo_a: float, tempo_b: float, adj_d_a: float, adj_d_b: float) -> float:
    """Adjust for slow-tempo defensive teams' tournament advantage.
    
    In single-elimination tournament play, teams with elite defense and slow tempo
    tend to slightly outperform their regular-season metrics.
    
    A team is "slow defensive" if tempo < 65.0 AND AdjD < 95.0 (lower is better).
    
    Args:
        base_prob: Pre-modifier win probability for Team A.
        tempo_a: Team A's adjusted tempo.
        tempo_b: Team B's adjusted tempo.
        adj_d_a: Team A's adjusted defensive efficiency (lower = better).
        adj_d_b: Team B's adjusted defensive efficiency.
    
    Returns:
        Modified win probability, clamped to [0.01, 0.99].
    """
    slow_defensive_a = (tempo_a < 65.0 and adj_d_a < 95.0)
    slow_defensive_b = (tempo_b < 65.0 and adj_d_b < 95.0)
    
    modifier = 0.0
    
    if slow_defensive_a and not slow_defensive_b:
        modifier = 0.03
    elif slow_defensive_b and not slow_defensive_a:
        modifier = -0.03
    
    adjusted_prob = base_prob + modifier
    
    return max(0.01, min(0.99, adjusted_prob))


def apply_conference_momentum_modifier(base_prob: float, team_a: Team, team_b: Team) -> float:
    """Adjust for conference tournament momentum (auto-bid hot teams).
    
    ALL teams that earned an auto-bid get a boost - not just power conferences.
    A mid-major that won 4 games in 4 days is peaking and battle-tested.
    
    Modifier: +0.015 for any auto-bid team.
    (Changed from power-conference-only to ALL conferences)
    
    Args:
        base_prob: Pre-modifier win probability for Team A.
        team_a: Full Team object for Team A.
        team_b: Full Team object for Team B.
    
    Returns:
        Modified win probability, clamped to [0.01, 0.99].
    """
    modifier = 0.0
    
    # Any team that won their conference tournament gets momentum boost
    a_momentum = team_a.is_auto_bid
    b_momentum = team_b.is_auto_bid
    
    if a_momentum and not b_momentum:
        modifier = 0.015
    elif b_momentum and not a_momentum:
        modifier = -0.015
    
    adjusted_prob = base_prob + modifier
    
    return max(0.01, min(0.99, adjusted_prob))


def apply_seed_prior(model_prob: float, seed_a: int, seed_b: int, round_num: int = 1) -> float:
    """Blend model probability with historical seed-based upset rates.
    
    Uses Bayesian-style blending: final = w * model_prob + (1-w) * historical_prob
    where w varies by round (more historical weight in early rounds with larger samples).
    
    Round-dependent weights:
    - R1: w=0.60 (40% historical - 156+ games per matchup type)
    - R2: w=0.65 (35% historical - ~78 games per matchup type)
    - S16: w=0.70 (30% historical - fewer samples)
    - E8+: w=0.80 (20% historical - limited samples, model dominates)
    
    Args:
        model_prob: Model-derived win probability for the team with seed_a.
        seed_a: Seed of Team A.
        seed_b: Seed of Team B.
        round_num: Tournament round (1-6).
    
    Returns:
        Blended win probability.
    """
    # Get historical win rate for this seed matchup
    if seed_a < seed_b:
        key = (seed_a, seed_b)
        historical_prob = HISTORICAL_SEED_WIN_RATES.get(key, model_prob)
    elif seed_b < seed_a:
        key = (seed_b, seed_a)
        historical_prob = 1.0 - HISTORICAL_SEED_WIN_RATES.get(key, 1.0 - model_prob)
    else:
        # Same seed - use model
        historical_prob = model_prob
    
    # Round-dependent blending weight
    if round_num == 1:
        w = 0.60  # R1: trust historical more (large sample)
    elif round_num == 2:
        w = 0.65  # R2: still strong historical data
    elif round_num == 3:
        w = 0.70  # S16: moderate historical data
    else:
        w = 0.80  # E8+: limited historical, model dominates
    
    blended = w * model_prob + (1 - w) * historical_prob
    
    return max(0.01, min(0.99, blended))


def compute_matchup_probability(team_a: Team, team_b: Team, round_num: int = 1) -> Matchup:
    """Compute the full win probability for a matchup using the ensemble model.
    
    Uses the trained ensemble (LR + RF) model when available.
    Falls back to seed-based estimation if model is unavailable.
    
    Args:
        team_a: Full Team object.
        team_b: Full Team object.
        round_num: Tournament round (1-6).
    
    Returns:
        Matchup with win_prob_a, raw_prob_a, and modifiers_applied populated.
    """
    predictor = get_predictor()
    
    if predictor is not None:
        # Use ensemble model
        try:
            # Determine favorite/underdog by seed
            if team_a.seed <= team_b.seed:
                # team_a is favorite (or equal seed)
                p_upset = predictor.predict_from_teams(favorite=team_a, underdog=team_b, round_num=round_num)
                prob = 1.0 - p_upset  # P(team_a wins) = 1 - P(upset)
            else:
                # team_b is favorite, team_a is underdog
                p_upset = predictor.predict_from_teams(favorite=team_b, underdog=team_a, round_num=round_num)
                prob = p_upset  # P(team_a wins) = P(upset) since team_a is the underdog
            
            # Sanity check: clamp extreme matchups to historical base rates
            # The ensemble can miscalibrate on extreme seed gaps (16v1, 15v2)
            seed_gap = abs(team_a.seed - team_b.seed)
            if seed_gap >= 14:  # 1v15, 1v16
                prob = max(0.93, min(0.99, prob)) if team_a.seed < team_b.seed else min(0.07, max(0.01, prob))
            elif seed_gap >= 12:  # 2v14, 1v13-ish  
                prob = max(0.85, min(0.97, prob)) if team_a.seed < team_b.seed else min(0.15, max(0.03, prob))
            
            # Also compute raw AdjEM prob for comparison
            raw_prob = adj_em_to_win_prob(team_a.adj_em, team_b.adj_em, team_a.adj_t, team_b.adj_t)
            
            modifiers = ["ensemble_model", "extreme_seed_clamp"] if seed_gap >= 12 else ["ensemble_model"]
            
            matchup = Matchup(
                team_a=team_a.name,
                team_b=team_b.name,
                round_num=round_num,
                win_prob_a=prob,
                raw_prob_a=raw_prob,
                modifiers_applied=modifiers
            )
            
            return matchup
        
        except Exception as e:
            logger.warning(f"Ensemble model prediction failed: {e}. Using fallback.")
    
    # FALLBACK: Use seed-based estimation if model unavailable
    logger.debug("Using seed-based fallback for matchup probability")
    
    # Get historical win rate for this seed matchup
    if team_a.seed < team_b.seed:
        key = (team_a.seed, team_b.seed)
        prob = HISTORICAL_SEED_WIN_RATES.get(key, 0.5)
    elif team_b.seed < team_a.seed:
        key = (team_b.seed, team_a.seed)
        prob = 1.0 - HISTORICAL_SEED_WIN_RATES.get(key, 0.5)
    else:
        # Same seed - use AdjEM
        prob = adj_em_to_win_prob(team_a.adj_em, team_b.adj_em, team_a.adj_t, team_b.adj_t)
    
    raw_prob = adj_em_to_win_prob(team_a.adj_em, team_b.adj_em, team_a.adj_t, team_b.adj_t)
    
    matchup = Matchup(
        team_a=team_a.name,
        team_b=team_b.name,
        round_num=round_num,
        win_prob_a=prob,
        raw_prob_a=raw_prob,
        modifiers_applied=["seed_based_fallback"]
    )
    
    return matchup


def build_matchup_matrix(teams: list[Team]) -> dict[str, dict[str, float]]:
    """Build the full NxN matchup probability matrix for all 68 teams.
    
    Computes P(A beats B) for every possible pairing.
    
    Args:
        teams: List of all 68 tournament teams with stats and seedings.
    
    Returns:
        Nested dict: matchup_matrix[team_a_name][team_b_name] = P(A beats B).
        Also saves to data/matchup_probabilities.json.
    """
    logger.info(f"Building matchup matrix for {len(teams)} teams")
    
    matrix: dict[str, dict[str, float]] = {}
    
    # Initialize matrix
    for team in teams:
        matrix[team.name] = {}
    
    # Compute all pairwise probabilities
    total_pairs = len(teams) * (len(teams) - 1) // 2
    computed = 0
    
    for i, team_a in enumerate(teams):
        for j, team_b in enumerate(teams):
            if i == j:
                continue
            
            if j > i:
                # Compute for upper triangle
                matchup = compute_matchup_probability(team_a, team_b)
                prob_a = matchup.win_prob_a
                matrix[team_a.name][team_b.name] = prob_a
                matrix[team_b.name][team_a.name] = 1.0 - prob_a
                
                computed += 1
                if computed % 100 == 0:
                    logger.debug(f"Computed {computed}/{total_pairs} matchup probabilities")
    
    logger.info(f"Computed {computed} unique matchup probabilities")
    
    return matrix


def analyze_matchups(teams: list[Team], config) -> dict[str, dict[str, float]]:
    """Run the full matchup analysis pipeline.
    
    Args:
        teams: All tournament teams.
        config: Application configuration.
    
    Returns:
        Complete matchup probability matrix.
    """
    logger.info("=== Starting matchup analysis ===")
    
    matrix = build_matchup_matrix(teams)
    
    # Save to file
    from src.utils import ensure_dir
    ensure_dir(config.data_dir)
    
    matrix_file = f"{config.data_dir}/matchup_probabilities.json"
    save_json(matrix, matrix_file)
    logger.info(f"Saved matchup matrix to {matrix_file}")
    
    logger.info("=== Matchup analysis complete ===")
    
    return matrix
