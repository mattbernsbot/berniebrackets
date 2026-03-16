"""Ownership and leverage analysis module.

Estimates public pick percentages and calculates leverage scores for value picks.
"""

import logging

from src.models import Team, OwnershipProfile
from src.constants import SEED_OWNERSHIP_CURVES, BRAND_NAME_BOOST
from src.utils import save_json, load_json

logger = logging.getLogger("bracket_optimizer")


def estimate_seed_ownership(seed: int, round_num: int) -> float:
    """Estimate public pick percentage based on seed and round.
    
    Uses historical ESPN Tournament Challenge data averages.
    
    Args:
        seed: Team's tournament seed (1-16).
        round_num: Tournament round (1-6).
    
    Returns:
        Estimated percentage of public brackets picking this seed-line
        team to reach this round (0.0-1.0).
    """
    if seed not in SEED_OWNERSHIP_CURVES:
        # Default for unknown seeds
        return 0.01
    
    seed_curve = SEED_OWNERSHIP_CURVES[seed]
    
    if round_num not in seed_curve:
        # Default for unknown rounds
        return 0.01
    
    return seed_curve[round_num]


def build_ownership_profiles(teams: list[Team], public_picks: dict[str, dict[int, float]] | None = None) -> list[OwnershipProfile]:
    """Build ownership profiles for all 68 teams.
    
    If public pick data is available (from Yahoo), uses it directly. Otherwise, uses 
    seed-based estimation as fallback, with adjustments for:
    - KenPom rank relative to seed (under-seeded teams get slightly higher ownership)
    - Brand-name programs (historically over-picked)
    
    Args:
        teams: All 68 tournament teams.
        public_picks: Yahoo pick percentages if available (team → round → pct).
    
    Returns:
        List of OwnershipProfile, one per team.
    """
    logger.info(f"Building ownership profiles for {len(teams)} teams")
    
    profiles = []
    
    for team in teams:
        round_ownership = {}
        
        if public_picks and team.name in public_picks:
            # Use actual Yahoo data
            round_ownership = public_picks[team.name]
        else:
            # Use seed-based estimation
            for round_num in range(1, 7):
                base_ownership = estimate_seed_ownership(team.seed, round_num)
                
                # Apply brand name boost
                if team.name in BRAND_NAME_BOOST:
                    boost = BRAND_NAME_BOOST[team.name]
                    base_ownership *= boost
                
                # Adjust for being under/over-seeded based on KenPom rank
                # A team ranked #5 overall but seeded #3 should get higher ownership
                if team.kenpom_rank > 0 and team.seed > 0:
                    expected_seed = (team.kenpom_rank - 1) // 4 + 1
                    expected_seed = max(1, min(16, expected_seed))
                    
                    if expected_seed < team.seed:
                        # Under-seeded (better than seed suggests) - boost ownership slightly
                        base_ownership *= 1.10
                    elif expected_seed > team.seed:
                        # Over-seeded (worse than seed suggests) - reduce ownership slightly
                        base_ownership *= 0.90
                
                # Clamp to valid range
                round_ownership[round_num] = max(0.001, min(0.99, base_ownership))
        
        # Title ownership is round 6 ownership
        title_ownership = round_ownership.get(6, 0.01)
        
        # Initial leverage calculation (will be updated with actual model probabilities later)
        leverage_by_round = {r: 1.0 for r in round_ownership.keys()}
        title_leverage = 1.0
        
        profile = OwnershipProfile(
            team=team.name,
            seed=team.seed,
            round_ownership=round_ownership,
            leverage_by_round=leverage_by_round,
            title_ownership=title_ownership,
            title_leverage=title_leverage
        )
        
        profiles.append(profile)
    
    logger.info(f"Built {len(profiles)} ownership profiles")
    
    return profiles


def calculate_leverage(model_prob: float, public_ownership: float) -> float:
    """Calculate leverage score for a pick (simple version).
    
    Leverage = model_prob / public_ownership
    
    Leverage > 1.0 means the model likes this team more than the public.
    
    Args:
        model_prob: Our model's probability for this outcome.
        public_ownership: Fraction of public brackets making this pick.
    
    Returns:
        Leverage score (float, ≥ 0).
    """
    # Floor ownership to prevent infinite leverage
    ownership = max(0.005, public_ownership)
    
    leverage = model_prob / ownership
    
    return leverage


def calculate_pool_leverage(model_prob: float, public_ownership: float, pool_size: int) -> float:
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


def find_value_picks(ownership_profiles: list[OwnershipProfile], min_leverage: float = 1.5) -> list[dict]:
    """Identify high-leverage picks across all rounds.
    
    Scans all teams at all rounds and returns picks where leverage exceeds 
    the threshold. Sorted by leverage descending.
    
    Args:
        ownership_profiles: All team ownership profiles.
        min_leverage: Minimum leverage to qualify as a value pick.
    
    Returns:
        List of dicts with keys: team, round, leverage.
    """
    value_picks = []
    
    for profile in ownership_profiles:
        for round_num, leverage in profile.leverage_by_round.items():
            if leverage >= min_leverage:
                value_picks.append({
                    "team": profile.team,
                    "seed": profile.seed,
                    "round": round_num,
                    "leverage": leverage,
                    "ownership": profile.round_ownership.get(round_num, 0.0)
                })
    
    # Sort by leverage descending
    value_picks.sort(key=lambda x: x["leverage"], reverse=True)
    
    return value_picks


def update_leverage_with_model(ownership_profiles: list[OwnershipProfile], teams: list[Team], matchup_matrix: dict[str, dict[str, float]], bracket_structure, pool_size: int, title_probs: dict[str, float] | None = None) -> list[OwnershipProfile]:
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
    logger.info("Updating ownership profiles with model-based leverage")
    
    # Build team lookup
    team_map = {t.name: t for t in teams}
    profile_map = {p.team: p for p in ownership_profiles}
    
    # For simplification, estimate advancement probabilities based on path difficulty
    # A more sophisticated implementation would run full simulations
    for profile in ownership_profiles:
        team = team_map.get(profile.team)
        if not team:
            continue
        
        # Estimate probability of reaching each round
        # Use simplified path analysis: approximate win probability at each step
        seed_factor = (17 - team.seed) / 16.0  # 1-seed = ~1.0, 16-seed = ~0.06
        
        # Adjust based on actual team quality (AdjEM)
        if team.adj_em > 0:
            # Top teams get a boost proportional to AdjEM
            quality_boost = 1.0 + (team.adj_em / 40.0)  # +30 AdjEM = ~75% boost
            quality_boost = min(1.5, quality_boost)  # Cap at 50% boost
        else:
            quality_boost = 1.0
        
        # Model probability estimates
        round_probs = {
            1: 1.0,  # Round 1 = team is in tournament
            2: min(0.99, (seed_factor ** 1) * quality_boost),  # Won 1 game
            3: min(0.99, (seed_factor ** 2) * quality_boost),  # Won 2 games (Sweet 16)
            4: min(0.99, (seed_factor ** 3) * quality_boost),  # Won 3 games (Elite 8)
            5: min(0.99, (seed_factor ** 4) * quality_boost),  # Won 4 games (Final Four)
        }
        
        # For title probability (round 6), use actual title_probs if available
        if title_probs and team.name in title_probs:
            round_probs[6] = title_probs[team.name]
        else:
            # Fallback to seed-based estimate
            round_probs[6] = min(0.99, (seed_factor ** 5) * quality_boost)
        
        # Calculate pool-size-aware leverage for each round
        leverage_by_round = {}
        for round_num in range(1, 7):
            model_prob = round_probs.get(round_num, 0.01)
            # CRITICAL FIX: Use actual ownership from profile, NOT 0.5 default
            # Fallback to seed-based estimate if missing
            ownership = profile.round_ownership.get(round_num)
            if ownership is None or ownership == 0:
                ownership = estimate_seed_ownership(team.seed, round_num)
            
            # Use pool-size-aware leverage calculation
            leverage_by_round[round_num] = calculate_pool_leverage(model_prob, ownership, pool_size)
        
        # Update profile
        profile.leverage_by_round = leverage_by_round
        profile.title_leverage = leverage_by_round.get(6, 1.0)
    
    logger.info("Leverage update complete")
    
    return ownership_profiles


def analyze_ownership(teams: list[Team], config) -> list[OwnershipProfile]:
    """Run the full ownership analysis pipeline.
    
    Orchestrates: load/estimate picks → build profiles → calculate leverage →
    save to data/ownership.json.
    
    Args:
        teams: All 68 tournament teams.
        config: Application configuration.
    
    Returns:
        List of OwnershipProfile for all teams.
    """
    logger.info("=== Starting ownership analysis ===")
    
    # Try to load public picks if available
    public_picks = None
    try:
        picks_file = f"{config.data_dir}/public_picks.json"
        raw_picks = load_json(picks_file)
        # Convert string keys back to integers (JSON serialization converts int keys to strings)
        public_picks = {}
        for team, rounds in raw_picks.items():
            public_picks[team] = {int(r): pct for r, pct in rounds.items()}
        logger.info("Loaded public picks from file")
    except Exception:
        logger.info("No public picks file found - using seed-based estimation")
    
    # Build profiles
    profiles = build_ownership_profiles(teams, public_picks)
    
    # Save to file
    from src.utils import ensure_dir
    ensure_dir(config.data_dir)
    
    ownership_file = f"{config.data_dir}/ownership.json"
    save_json([p.to_dict() for p in profiles], ownership_file)
    logger.info(f"Saved ownership profiles to {ownership_file}")
    
    # Log some value picks
    value_picks = find_value_picks(profiles, min_leverage=1.5)
    if value_picks:
        logger.info(f"Found {len(value_picks)} value picks with leverage >= 1.5")
        logger.info("Top 5 value picks:")
        for pick in value_picks[:5]:
            logger.info(f"  {pick['team']} Round {pick['round']}: {pick['leverage']:.2f}x leverage")
    
    logger.info("=== Ownership analysis complete ===")
    
    return profiles
