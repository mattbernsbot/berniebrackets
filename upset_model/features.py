"""Feature extraction for upset prediction model.

THIS IS THE ONLY PLACE FEATURE COMPUTATION HAPPENS.

Extracts 16 features from team stats (9 original + 7 KenPom/LRMC):

Original (1-9):
1. seed_diff
2. round_num
3. adj_em_diff
4. adj_o_diff
5. adj_d_diff
6. adj_t_diff
7. seed×adj_em
8. round×seed
9. round×adj_em

KenPom/LRMC (10-16):
10. luck_diff (fav.luck - dog.luck)
11. favorite_luck
12. tempo_mismatch (|fav.adj_t - dog.adj_t|)
13. slow_dog_vs_fast_fav
14. top25_winpct_diff (LRMC)
15. dog_top25_winpct (LRMC)
16. luck_x_seed_diff (interaction)
"""

from typing import List, Optional


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
    team_b_lrmc: Optional[dict] = None
) -> List[float]:
    """Extract all 16 features for a matchup.
    
    Args:
        team_a: Favorite team stats (KenPom) with keys: seed, adj_em, adj_o, adj_d, adj_t, luck
        team_b: Underdog team stats (KenPom) with keys: seed, adj_em, adj_o, adj_d, adj_t, luck
        round_num: Tournament round (1-6)
        team_a_lrmc: Optional LRMC stats for team_a (top25_wins, top25_losses, top25_games)
        team_b_lrmc: Optional LRMC stats for team_b (top25_wins, top25_losses, top25_games)
    
    Returns:
        List of 16 float features
    
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
    adj_d_a = team_a.get("adj_d", 95.0)
    adj_d_b = team_b.get("adj_d", 95.0)
    adj_t_a = team_a.get("adj_t", 67.0)
    adj_t_b = team_b.get("adj_t", 67.0)
    luck_a = team_a.get("luck", 0.0)
    luck_b = team_b.get("luck", 0.0)
    
    # Original 9 features: KenPom differentials
    seed_diff = float(seed_b - seed_a)
    adj_em_diff = adj_em_b - adj_em_a
    adj_o_diff = adj_o_b - adj_o_a
    adj_d_diff = adj_d_b - adj_d_a
    adj_t_diff = adj_t_b - adj_t_a
    
    # Original interactions
    seed_x_adj_em = seed_diff * adj_em_diff
    round_x_seed = float(round_num) * seed_diff
    round_x_adj_em = float(round_num) * adj_em_diff
    
    # NEW FEATURE 10-11: Luck features
    luck_diff = luck_a - luck_b  # fav.luck - dog.luck (positive = fav is luckier = upset signal)
    favorite_luck = luck_a
    
    # NEW FEATURE 12-13: Tempo features
    tempo_mismatch = abs(adj_t_a - adj_t_b)
    slow_dog_vs_fast_fav = 1.0 if (adj_t_b < 65.0 and adj_t_a > 69.0) else 0.0
    
    # NEW FEATURE 14-15: LRMC top-25 performance
    top25_winpct_a = compute_top25_winpct(team_a_lrmc)
    top25_winpct_b = compute_top25_winpct(team_b_lrmc)
    top25_winpct_diff = top25_winpct_a - top25_winpct_b  # fav - dog (small gap = dangerous dog)
    dog_top25_winpct = top25_winpct_b  # standalone underdog battle-tested signal
    
    # NEW FEATURE 16: Interaction
    luck_x_seed_diff = luck_diff * seed_diff
    
    return [
        # Original 9 features (1-9)
        seed_diff,
        float(round_num),
        adj_em_diff,
        adj_o_diff,
        adj_d_diff,
        adj_t_diff,
        seed_x_adj_em,
        round_x_seed,
        round_x_adj_em,
        # KenPom/LRMC features (10-16)
        luck_diff,
        favorite_luck,
        tempo_mismatch,
        slow_dog_vs_fast_fav,
        top25_winpct_diff,
        dog_top25_winpct,
        luck_x_seed_diff
    ]


# Feature names in the same order as extract_features() output
FEATURE_NAMES = [
    # Original 9 features
    "seed_diff",
    "round_num",
    "adj_em_diff",
    "adj_o_diff",
    "adj_d_diff",
    "adj_t_diff",
    "seed_x_adj_em",
    "round_x_seed",
    "round_x_adj_em",
    # KenPom/LRMC features (10-16)
    "luck_diff",
    "favorite_luck",
    "tempo_mismatch",
    "slow_dog_vs_fast_fav",
    "top25_winpct_diff",
    "dog_top25_winpct",
    "luck_x_seed_diff"
]
