"""Feature extraction for upset prediction model.

THIS IS THE ONLY PLACE FEATURE COMPUTATION HAPPENS.

Extracts features from team stats (selected via L1 screening + ablation in Phase 2D):

 1. seed_diff          — seed gap (e.g., 1v16 = 15)
 2. adj_em_diff        — KenPom net efficiency differential
 3. adj_o_diff         — offensive efficiency differential
 4. adj_t_diff         — tempo differential
 5. seed_x_adj_em      — seed × efficiency interaction
 6. top25_winpct_diff  — LRMC vs-top-25 win% differential (fav - dog)
 7. dog_top25_winpct   — underdog's vs-top-25 win% (battle-tested signal)
 8. barthag_diff       — Torvik win-probability differential (partially independent of AdjEM)
 9. wab_diff           — Torvik wins-above-bubble differential (strength of resume)
10. momentum_diff      — last-10-game AdjEM differential
11. dog_momentum       — underdog's last-10-game AdjEM (hot streaks)
12. dog_last10_winpct  — underdog's last-10 win percentage
13. spread             — Vegas point spread (negative = fav favored)
14. spread_vs_expected — actual spread minus seed-expected spread (market surprise)
"""

from typing import List, Optional


# Expected spread by seed matchup (seed_diff -> expected spread)
# Derived from historical median spreads for common matchups.
_SEED_EXPECTED_SPREAD = {
    1: -1.5, 2: -3.0, 3: -4.5, 4: -6.0, 5: -7.0, 6: -8.0,
    7: -8.5, 8: -9.5, 9: -10.5, 10: -11.5, 11: -13.0,
    12: -15.0, 13: -17.0, 14: -20.0, 15: -23.0,
}


def compute_top25_winpct(lrmc_stats: Optional[dict]) -> float:
    """Compute top 25 win percentage using Matt's rule.

    If fewer than 4 games vs top 25, return 0.0 (small sample = unreliable).
    """
    if not lrmc_stats:
        return 0.0

    games = lrmc_stats.get('top25_games', 0)
    if games < 4:
        return 0.0

    wins = lrmc_stats.get('top25_wins', 0)
    return wins / games


def extract_features(
    team_a: dict,
    team_b: dict,
    round_num: int,
    team_a_lrmc: Optional[dict] = None,
    team_b_lrmc: Optional[dict] = None,
    team_a_torvik: Optional[dict] = None,
    team_b_torvik: Optional[dict] = None,
    team_a_momentum: Optional[dict] = None,
    team_b_momentum: Optional[dict] = None,
    spread: Optional[float] = None,
) -> List[float]:
    """Extract all features for a matchup.

    Args:
        team_a: Favorite team stats (KenPom) with keys: seed, adj_em, adj_o, adj_d, adj_t
        team_b: Underdog team stats (KenPom) with keys: seed, adj_em, adj_o, adj_d, adj_t
        round_num: Tournament round (1-6). Not used as a feature but kept for API compat.
        team_a_lrmc: Optional LRMC stats for team_a (top25_wins, top25_losses, top25_games)
        team_b_lrmc: Optional LRMC stats for team_b
        team_a_torvik: Optional Torvik stats for team_a (barthag, wab)
        team_b_torvik: Optional Torvik stats for team_b
        team_a_momentum: Optional momentum stats for team_a (last10_adj_em, last10_win_pct)
        team_b_momentum: Optional momentum stats for team_b
        spread: Optional Vegas point spread (negative = favorite favored)

    Returns:
        List of float features (length = len(FEATURE_NAMES))

    Note:
        Team A should be the FAVORITE (lower seed).
        Team B should be the UNDERDOG (higher seed).
        Missing data uses D-I averages / neutral values.
    """
    # Extract raw KenPom stats with defaults
    seed_a = team_a.get("seed", 8)
    seed_b = team_b.get("seed", 8)
    adj_em_a = team_a.get("adj_em", 0.0)
    adj_em_b = team_b.get("adj_em", 0.0)
    adj_o_a = team_a.get("adj_o", 105.0)
    adj_o_b = team_b.get("adj_o", 105.0)
    adj_t_a = team_a.get("adj_t", 67.0)
    adj_t_b = team_b.get("adj_t", 67.0)

    # Core differentials
    seed_diff = float(seed_b - seed_a)
    adj_em_diff = adj_em_b - adj_em_a
    adj_o_diff = adj_o_b - adj_o_a
    adj_t_diff = adj_t_b - adj_t_a

    # Interaction
    seed_x_adj_em = seed_diff * adj_em_diff

    # LRMC top-25 performance
    top25_winpct_a = compute_top25_winpct(team_a_lrmc)
    top25_winpct_b = compute_top25_winpct(team_b_lrmc)
    top25_winpct_diff = top25_winpct_a - top25_winpct_b
    dog_top25_winpct = top25_winpct_b

    # Torvik features (barthag = win probability, wab = wins above bubble)
    barthag_a = team_a_torvik.get('barthag', 0.5) if team_a_torvik else 0.5
    barthag_b = team_b_torvik.get('barthag', 0.5) if team_b_torvik else 0.5
    wab_a = team_a_torvik.get('wab', 0.0) if team_a_torvik else 0.0
    wab_b = team_b_torvik.get('wab', 0.0) if team_b_torvik else 0.0
    barthag_diff = barthag_b - barthag_a
    wab_diff = wab_b - wab_a

    # Momentum features (last 10 games performance)
    mom_a = team_a_momentum.get('last10_adj_em', 0.0) if team_a_momentum else 0.0
    mom_b = team_b_momentum.get('last10_adj_em', 0.0) if team_b_momentum else 0.0
    dog_last10_win = team_b_momentum.get('last10_win_pct', 0.5) if team_b_momentum else 0.5
    momentum_diff = mom_b - mom_a
    dog_momentum = mom_b
    dog_last10_winpct = dog_last10_win

    # Spread features
    if spread is not None:
        spread_val = spread
        expected = _SEED_EXPECTED_SPREAD.get(int(seed_diff), -seed_diff * 1.5)
        spread_vs_expected = spread_val - expected
    else:
        spread_val = 0.0
        spread_vs_expected = 0.0

    return [
        seed_diff,
        adj_em_diff,
        adj_o_diff,
        adj_t_diff,
        seed_x_adj_em,
        top25_winpct_diff,
        dog_top25_winpct,
        barthag_diff,
        wab_diff,
        momentum_diff,
        dog_momentum,
        dog_last10_winpct,
        spread_val,
        spread_vs_expected,
    ]


# Feature names in the same order as extract_features() output
FEATURE_NAMES = [
    "seed_diff",
    "adj_em_diff",
    "adj_o_diff",
    "adj_t_diff",
    "seed_x_adj_em",
    "top25_winpct_diff",
    "dog_top25_winpct",
    "barthag_diff",
    "wab_diff",
    "momentum_diff",
    "dog_momentum",
    "dog_last10_winpct",
    "spread",
    "spread_vs_expected",
]
