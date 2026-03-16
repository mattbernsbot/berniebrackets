"""Constants and historical data for the bracket optimizer.

Contains seed matchup win rates, ownership curves, conference lists, and other
static data used throughout the system.
"""

# URLs for data scraping
KENPOM_URL = "https://kenpom.com"
ESPN_BRACKET_URL = "https://www.espn.com/mens-college-basketball/bracketology"
ESPN_PICKS_URL = "https://fantasy.espn.com/tournament-challenge-bracket/"

# Historical NCAA tournament seed matchup win rates
# Maps (higher_seed, lower_seed) -> P(higher seed wins)
# Data from NCAA tournament results 1985-2024
HISTORICAL_SEED_WIN_RATES: dict[tuple[int, int], float] = {
    # First round matchups
    (1, 16): 0.993,
    (2, 15): 0.938,
    (3, 14): 0.851,
    (4, 13): 0.793,
    (5, 12): 0.649,
    (6, 11): 0.625,
    (7, 10): 0.607,
    (8, 9): 0.519,
    # Later round common matchups (higher seed advantage)
    (1, 8): 0.775,
    (1, 9): 0.798,
    (2, 7): 0.702,
    (2, 10): 0.723,
    (3, 6): 0.629,
    (3, 11): 0.651,
    (4, 5): 0.538,
    (4, 12): 0.670,
    (1, 4): 0.651,
    (1, 5): 0.672,
    (2, 3): 0.528,
    (1, 2): 0.573,
    (1, 3): 0.612,
    (2, 6): 0.634,
}

# Default ownership curves by seed and round
# Maps seed -> {round_num: avg_public_pick_pct}
SEED_OWNERSHIP_CURVES: dict[int, dict[int, float]] = {
    1: {1: 0.970, 2: 0.880, 3: 0.720, 4: 0.550, 5: 0.350, 6: 0.250},
    2: {1: 0.940, 2: 0.790, 3: 0.580, 4: 0.370, 5: 0.180, 6: 0.110},
    3: {1: 0.850, 2: 0.630, 3: 0.390, 4: 0.190, 5: 0.070, 6: 0.040},
    4: {1: 0.790, 2: 0.540, 3: 0.290, 4: 0.120, 5: 0.040, 6: 0.020},
    5: {1: 0.650, 2: 0.380, 3: 0.180, 4: 0.060, 5: 0.020, 6: 0.008},
    6: {1: 0.630, 2: 0.340, 3: 0.140, 4: 0.045, 5: 0.012, 6: 0.005},
    7: {1: 0.610, 2: 0.310, 3: 0.115, 4: 0.035, 5: 0.009, 6: 0.003},
    8: {1: 0.520, 2: 0.240, 3: 0.080, 4: 0.022, 5: 0.006, 6: 0.002},
    9: {1: 0.480, 2: 0.210, 3: 0.065, 4: 0.018, 5: 0.005, 6: 0.001},
    10: {1: 0.390, 2: 0.160, 3: 0.048, 4: 0.012, 5: 0.003, 6: 0.001},
    11: {1: 0.375, 2: 0.145, 3: 0.042, 4: 0.010, 5: 0.002, 6: 0.001},
    12: {1: 0.351, 2: 0.125, 3: 0.035, 4: 0.008, 5: 0.002, 6: 0.001},
    13: {1: 0.207, 2: 0.065, 3: 0.015, 4: 0.003, 5: 0.001, 6: 0.000},
    14: {1: 0.149, 2: 0.042, 3: 0.009, 4: 0.002, 5: 0.000, 6: 0.000},
    15: {1: 0.062, 2: 0.015, 3: 0.003, 4: 0.001, 5: 0.000, 6: 0.000},
    16: {1: 0.007, 2: 0.001, 3: 0.000, 4: 0.000, 5: 0.000, 6: 0.000},
}

# Brand name teams that public overvalues
# Maps team name -> ownership multiplier
BRAND_NAME_BOOST: dict[str, float] = {
    "Duke": 1.30,
    "Kentucky": 1.25,
    "North Carolina": 1.25,
    "Kansas": 1.20,
    "Michigan State": 1.15,
    "Villanova": 1.15,
    "UCLA": 1.15,
    "Indiana": 1.10,
    "Louisville": 1.10,
    "Syracuse": 1.10,
    "Michigan": 1.08,
    "Ohio State": 1.08,
    "Arizona": 1.08,
    "Florida": 1.05,
    "UConn": 1.12,
    "Connecticut": 1.12,
}

# Power conferences (get momentum modifier)
POWER_CONFERENCES = [
    "SEC",
    "Big Ten",
    "Big 12",
    "ACC",
    "Big East",
    "AAC",
]

# ESPN standard scoring
SCORING_ESPN_STANDARD = [10, 20, 40, 80, 160, 320]

# Standard bracket seed matchup order within a region
BRACKET_SEED_ORDER = [
    (1, 16),
    (8, 9),
    (5, 12),
    (4, 13),
    (6, 11),
    (3, 14),
    (7, 10),
    (2, 15),
]

# Team name aliases for fuzzy matching between KenPom and ESPN
TEAM_NAME_ALIASES: dict[str, str] = {
    "Connecticut": "UConn",
    "UConn": "Connecticut",
    "St. John's (NY)": "St. John's",
    "Saint John's": "St. John's",
    "St. Mary's (CA)": "St. Mary's",
    "Saint Mary's": "St. Mary's",
    "LSU": "Louisiana State",
    "Louisiana State": "LSU",
    "Ole Miss": "Mississippi",
    "Mississippi": "Ole Miss",
    "Miami (FL)": "Miami",
    "Miami FL": "Miami",
    "USC": "Southern California",
    "Southern California": "USC",
    "VCU": "Virginia Commonwealth",
    "Virginia Commonwealth": "VCU",
    "SMU": "Southern Methodist",
    "Southern Methodist": "SMU",
    "TCU": "Texas Christian",
    "Texas Christian": "TCU",
    "BYU": "Brigham Young",
    "Brigham Young": "BYU",
    "UCF": "Central Florida",
    "Central Florida": "UCF",
    "UNLV": "Nevada Las Vegas",
    "Nevada Las Vegas": "UNLV",
    "Penn": "Pennsylvania",
    "Pennsylvania": "Penn",
    "Pitt": "Pittsburgh",
    "Pittsburgh": "Pitt",
}

# Seed-based default AdjEM values (fallback if KenPom data missing)
# CORRECTED: All tournament teams should have positive or near-positive AdjEM
SEED_DEFAULT_ADJEM: dict[int, float] = {
    1: 28.0,
    2: 23.0,
    3: 19.0,
    4: 16.0,
    5: 14.0,
    6: 12.0,
    7: 10.0,
    8: 8.0,
    9: 7.0,
    10: 6.0,
    11: 5.0,
    12: 6.0,  # 12-seeds often underrated - can be strong mid-majors
    13: 3.0,
    14: 2.0,
    15: 0.0,
    16: -2.0,
}

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

# Champion seed distribution (historical %)
CHAMPION_SEED_FREQUENCY: dict[int, float] = {
    1: 0.60, 2: 0.18, 3: 0.10, 4: 0.04, 5: 0.02,
    6: 0.03, 7: 0.02, 8: 0.01, 9: 0.00, 10: 0.00,
    11: 0.00, 12: 0.00, 13: 0.00, 14: 0.00, 15: 0.00, 16: 0.00,
}


# DEPRECATED: Kept for backward compatibility with tests only
# DO NOT USE - the V2 optimizer uses pool-size-aware formulas instead
STRATEGY_CHAMPION_SEEDS: dict[str, list[int]] = {
    "conservative": [1, 2],
    "balanced": [1, 2, 3, 4],
    "aggressive": [1, 2, 3, 4, 5, 6],  # Fixed: no longer excludes 1-seeds
}
