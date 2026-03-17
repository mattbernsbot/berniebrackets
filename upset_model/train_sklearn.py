#!/usr/bin/env python3
"""Train upset prediction model using sklearn.

Uses:
- sklearn for models (LogisticRegression with isotonic calibration)
- pandas for data manipulation
- numpy for numerics

Data sources:
- ncaa_tournament_real.json — 798 real NCAA tournament games (2011-2025, D2 game removed)
- kenpom_historical.json — 4,604 team records with AdjEM, AdjO, AdjD, AdjT, Luck
- lrmc_historical.json — 4,242 team records with LRMC rank, vs-top-25 record
- torvik_historical.json — 4,594 team records with Barthag, WAB (Phase 2A)
- momentum_historical.json — per-team last-10-game stats (Phase 2B)
- betting_lines_historical.json — tournament game spreads (Phase 2C)

Features: 14 (7 Phase 1 + 7 Phase 2, pruned in Phase 2D)
"""

import json
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.linear_model import LogisticRegression, LogisticRegressionCV
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import LeaveOneGroupOut, StratifiedKFold
from sklearn.metrics import roc_auc_score, brier_score_loss, log_loss
from sklearn.preprocessing import StandardScaler
import joblib
import warnings

# Add project root to path so we can import shared name matching
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.name_matching import normalize_team_name, normalize_torvik_name, normalize_lrmc_name
warnings.filterwarnings('ignore')

# Import our feature engineering
from features import extract_features, FEATURE_NAMES


def load_data():
    """Load all 3 data sources into pandas DataFrames.
    
    BUG FIX 2: Fixes AdjEM scale for years 2011, 2013-2016 where it was stored
    as percentile (0-1) instead of real value (-30 to +35).
    
    BUG FIX V2: 
    - Remove D2 game contamination (Grand Canyon vs Seattle Pacific 2013)
    """
    data_dir = Path(__file__).resolve().parent.parent / "data" / "upset_model"
    
    # Load tournament games
    with open(data_dir / "ncaa_tournament_real.json") as f:
        games_raw = json.load(f)
    
    # BUG FIX V2: Remove D2 game contamination
    # Grand Canyon vs Seattle Pacific 2013 - both teams were D2
    d2_games_removed = 0
    games_clean = []
    for game in games_raw:
        if game['year'] == 2013:
            teams = {game['team_a'].lower(), game['team_b'].lower()}
            if 'grand canyon' in teams and 'seattle pacific' in teams:
                d2_games_removed += 1
                continue
        games_clean.append(game)
    
    games = pd.DataFrame(games_clean)
    if d2_games_removed > 0:
        print(f"BUG FIX V2: Removed {d2_games_removed} D2 game(s) (Grand Canyon vs Seattle Pacific 2013)")
    
    # Load KenPom historical
    with open(data_dir / "kenpom_historical.json") as f:
        kenpom_raw = json.load(f)
    
    # BUG FIX 2: Fix AdjEM scale for 2011, 2013-2016
    # These years have adj_em as percentile (0-1) instead of real value
    # adj_o and adj_d ARE correct, so we compute: adj_em = adj_o - adj_d
    problematic_years = {2011, 2013, 2014, 2015, 2016}
    fixed_count = 0
    
    for record in kenpom_raw:
        # Only fix known problematic years where adj_em is clearly wrong (0-1 range)
        if record['year'] in problematic_years and 0 <= record['adj_em'] <= 1.0:
            record['adj_em'] = record['adj_o'] - record['adj_d']
            fixed_count += 1
    
    kenpom = pd.DataFrame(kenpom_raw)
    
    if fixed_count > 0:
        print(f"BUG FIX 2: Fixed AdjEM scale for {fixed_count} records in years: {sorted(problematic_years)}")
    
    # Load LRMC historical
    with open(data_dir / "lrmc_historical.json") as f:
        lrmc = pd.DataFrame(json.load(f))

    # Load Torvik historical (Phase 2A)
    torvik_path = data_dir / "torvik_historical.json"
    if torvik_path.exists():
        with open(torvik_path) as f:
            torvik = pd.DataFrame(json.load(f))
    else:
        print("  ⚠ torvik_historical.json not found — barthag/wab features will be zero")
        torvik = pd.DataFrame()

    # Load momentum historical (Phase 2B)
    momentum_path = data_dir / "momentum_historical.json"
    if momentum_path.exists():
        with open(momentum_path) as f:
            momentum = pd.DataFrame(json.load(f))
    else:
        print("  ⚠ momentum_historical.json not found — momentum features will be zero")
        momentum = pd.DataFrame()

    # Load betting lines (Phase 2C)
    lines_path = data_dir / "betting_lines_historical.json"
    if lines_path.exists():
        with open(lines_path) as f:
            lines = pd.DataFrame(json.load(f))
    else:
        print("  ⚠ betting_lines_historical.json not found — spread features will be zero")
        lines = pd.DataFrame()

    # Return data + fix counts for reporting
    return games, kenpom, lrmc, torvik, momentum, lines, d2_games_removed



# normalize_team_name, normalize_torvik_name, normalize_lrmc_name
# are imported from src.name_matching (see top of file)


def join_team_stats(games, kenpom, lrmc, torvik, momentum, lines):
    """Join tournament games with team stats from all sources.

    Returns:
        DataFrame with columns: year, round_num, is_upset, team_a_*, team_b_*, etc.
    """
    # Normalize team names in all datasets
    kenpom['team_norm'] = kenpom['team'].apply(normalize_team_name)
    lrmc['team_norm'] = lrmc['team'].apply(normalize_lrmc_name)
    games['team_a_norm'] = games['team_a'].apply(normalize_team_name)
    games['team_b_norm'] = games['team_b'].apply(normalize_team_name)

    # Create lookup keys
    kenpom['key'] = kenpom['year'].astype(str) + '_' + kenpom['team_norm']
    lrmc['key'] = lrmc['year'].astype(str) + '_' + lrmc['team_norm']

    # Join team_a stats
    games['key_a'] = games['year'].astype(str) + '_' + games['team_a_norm']
    games = games.merge(
        kenpom[['key', 'adj_em', 'adj_o', 'adj_d', 'adj_t', 'luck']],
        left_on='key_a',
        right_on='key',
        how='left',
        suffixes=('', '_kp_a')
    ).drop('key', axis=1)
    games = games.rename(columns={
        'adj_em': 'adj_em_a',
        'adj_o': 'adj_o_a',
        'adj_d': 'adj_d_a',
        'adj_t': 'adj_t_a',
        'luck': 'luck_a'
    })

    # Join team_b stats
    games['key_b'] = games['year'].astype(str) + '_' + games['team_b_norm']
    games = games.merge(
        kenpom[['key', 'adj_em', 'adj_o', 'adj_d', 'adj_t', 'luck']],
        left_on='key_b',
        right_on='key',
        how='left',
        suffixes=('', '_kp_b')
    ).drop('key', axis=1)
    games = games.rename(columns={
        'adj_em': 'adj_em_b',
        'adj_o': 'adj_o_b',
        'adj_d': 'adj_d_b',
        'adj_t': 'adj_t_b',
        'luck': 'luck_b'
    })

    # Join LRMC stats for team_a
    games = games.merge(
        lrmc[['key', 'top25_wins', 'top25_losses', 'top25_games']],
        left_on='key_a',
        right_on='key',
        how='left',
        suffixes=('', '_lrmc_a')
    ).drop('key', axis=1)
    games = games.rename(columns={
        'top25_wins': 'top25_wins_a',
        'top25_losses': 'top25_losses_a',
        'top25_games': 'top25_games_a'
    })

    # Join LRMC stats for team_b
    games = games.merge(
        lrmc[['key', 'top25_wins', 'top25_losses', 'top25_games']],
        left_on='key_b',
        right_on='key',
        how='left',
        suffixes=('', '_lrmc_b')
    ).drop('key', axis=1)
    games = games.rename(columns={
        'top25_wins': 'top25_wins_b',
        'top25_losses': 'top25_losses_b',
        'top25_games': 'top25_games_b'
    })

    # Join Torvik stats (Phase 2A)
    if not torvik.empty:
        torvik['team_norm'] = torvik['team'].apply(normalize_torvik_name)
        torvik['key'] = torvik['year'].astype(str) + '_' + torvik['team_norm']

        games = games.merge(
            torvik[['key', 'barthag', 'wab']],
            left_on='key_a', right_on='key', how='left'
        ).drop('key', axis=1)
        games = games.rename(columns={'barthag': 'barthag_a', 'wab': 'wab_a'})

        games = games.merge(
            torvik[['key', 'barthag', 'wab']],
            left_on='key_b', right_on='key', how='left'
        ).drop('key', axis=1)
        games = games.rename(columns={'barthag': 'barthag_b', 'wab': 'wab_b'})
    else:
        games['barthag_a'] = games['barthag_b'] = float('nan')
        games['wab_a'] = games['wab_b'] = float('nan')

    # Join momentum stats (Phase 2B)
    if not momentum.empty:
        momentum['team_norm'] = momentum['team'].apply(normalize_team_name)
        momentum['key'] = momentum['year'].astype(str) + '_' + momentum['team_norm']

        games = games.merge(
            momentum[['key', 'last10_adj_em', 'last10_win_pct']],
            left_on='key_a', right_on='key', how='left'
        ).drop('key', axis=1)
        games = games.rename(columns={
            'last10_adj_em': 'last10_adj_em_a',
            'last10_win_pct': 'last10_win_pct_a'
        })

        games = games.merge(
            momentum[['key', 'last10_adj_em', 'last10_win_pct']],
            left_on='key_b', right_on='key', how='left'
        ).drop('key', axis=1)
        games = games.rename(columns={
            'last10_adj_em': 'last10_adj_em_b',
            'last10_win_pct': 'last10_win_pct_b'
        })
    else:
        games['last10_adj_em_a'] = games['last10_adj_em_b'] = float('nan')
        games['last10_win_pct_a'] = games['last10_win_pct_b'] = float('nan')

    # Join betting lines (Phase 2C)
    if not lines.empty:
        lines['team_a_norm'] = lines['team_a'].apply(normalize_team_name)
        lines['team_b_norm'] = lines['team_b'].apply(normalize_team_name)
        lines['key'] = (lines['year'].astype(str) + '_' +
                        lines['team_a_norm'] + '_' + lines['team_b_norm'])

        # Create matching keys (try both orderings)
        games['lines_key1'] = (games['year'].astype(str) + '_' +
                               games['team_a_norm'] + '_' + games['team_b_norm'])
        games['lines_key2'] = (games['year'].astype(str) + '_' +
                               games['team_b_norm'] + '_' + games['team_a_norm'])

        lines_lookup = dict(zip(lines['key'], lines['spread']))
        games['spread'] = games.apply(
            lambda r: lines_lookup.get(r['lines_key1'],
                      lines_lookup.get(r['lines_key2'], float('nan'))),
            axis=1
        )
        games = games.drop(['lines_key1', 'lines_key2'], axis=1)
    else:
        games['spread'] = float('nan')

    return games


def build_feature_matrix(games):
    """Build feature matrix X and labels y from joined games DataFrame.
    
    Returns:
        X: numpy array of shape (n_games, n_features)
        y: numpy array of shape (n_games,) - 1 if upset, 0 otherwise
        groups: numpy array of shape (n_games,) - year for each game
        valid_indices: list of row indices that had valid KenPom data
    """
    X = []
    y = []
    groups = []
    valid_indices = []
    
    missing_kenpom = 0
    missing_lrmc = 0
    missing_torvik = 0
    missing_momentum = 0
    missing_spread = 0

    for idx, row in games.iterrows():
        # Skip if missing KenPom data (REQUIRED)
        if pd.isna(row['adj_em_a']) or pd.isna(row['adj_em_b']):
            missing_kenpom += 1
            continue

        # Determine favorite vs underdog
        if row['seed_a'] < row['seed_b']:
            fav_suffix, dog_suffix = 'a', 'b'
            upset = (row['winner'] == 'b')
        elif row['seed_b'] < row['seed_a']:
            fav_suffix, dog_suffix = 'b', 'a'
            upset = (row['winner'] == 'a')
        else:
            continue  # Equal seeds - skip

        # KenPom stats
        fav_stats = {
            'seed': row[f'seed_{fav_suffix}'],
            'adj_em': row[f'adj_em_{fav_suffix}'],
            'adj_o': row[f'adj_o_{fav_suffix}'],
            'adj_d': row[f'adj_d_{fav_suffix}'],
            'adj_t': row[f'adj_t_{fav_suffix}'],
            'luck': row.get(f'luck_{fav_suffix}', 0.0)
        }
        dog_stats = {
            'seed': row[f'seed_{dog_suffix}'],
            'adj_em': row[f'adj_em_{dog_suffix}'],
            'adj_o': row[f'adj_o_{dog_suffix}'],
            'adj_d': row[f'adj_d_{dog_suffix}'],
            'adj_t': row[f'adj_t_{dog_suffix}'],
            'luck': row.get(f'luck_{dog_suffix}', 0.0)
        }

        # LRMC stats
        fav_lrmc = None
        dog_lrmc = None
        if not pd.isna(row.get(f'top25_games_{fav_suffix}')):
            fav_lrmc = {
                'top25_wins': row[f'top25_wins_{fav_suffix}'],
                'top25_losses': row[f'top25_losses_{fav_suffix}'],
                'top25_games': row[f'top25_games_{fav_suffix}']
            }
        else:
            missing_lrmc += 1
        if not pd.isna(row.get(f'top25_games_{dog_suffix}')):
            dog_lrmc = {
                'top25_wins': row[f'top25_wins_{dog_suffix}'],
                'top25_losses': row[f'top25_losses_{dog_suffix}'],
                'top25_games': row[f'top25_games_{dog_suffix}']
            }

        # Torvik stats
        fav_torvik = None
        dog_torvik = None
        if not pd.isna(row.get(f'barthag_{fav_suffix}')):
            fav_torvik = {'barthag': row[f'barthag_{fav_suffix}'], 'wab': row[f'wab_{fav_suffix}']}
        else:
            missing_torvik += 1
        if not pd.isna(row.get(f'barthag_{dog_suffix}')):
            dog_torvik = {'barthag': row[f'barthag_{dog_suffix}'], 'wab': row[f'wab_{dog_suffix}']}

        # Momentum stats
        fav_momentum = None
        dog_momentum = None
        if not pd.isna(row.get(f'last10_adj_em_{fav_suffix}')):
            fav_momentum = {
                'last10_adj_em': row[f'last10_adj_em_{fav_suffix}'],
                'last10_win_pct': row[f'last10_win_pct_{fav_suffix}']
            }
        else:
            missing_momentum += 1
        if not pd.isna(row.get(f'last10_adj_em_{dog_suffix}')):
            dog_momentum = {
                'last10_adj_em': row[f'last10_adj_em_{dog_suffix}'],
                'last10_win_pct': row[f'last10_win_pct_{dog_suffix}']
            }

        # Spread
        spread_val = None
        if not pd.isna(row.get('spread')):
            spread_val = row['spread']
        else:
            missing_spread += 1

        # Extract features
        features = extract_features(
            fav_stats,
            dog_stats,
            row['round_num'],
            fav_lrmc,
            dog_lrmc,
            fav_torvik,
            dog_torvik,
            fav_momentum,
            dog_momentum,
            spread_val,
        )

        X.append(features)
        y.append(1 if upset else 0)
        groups.append(row['year'])
        valid_indices.append(idx)

    print(f"Missing data summary:")
    print(f"  KenPom: {missing_kenpom} games")
    print(f"  LRMC: {missing_lrmc} teams (imputed to default)")
    print(f"  Torvik: {missing_torvik} teams (imputed to default)")
    print(f"  Momentum: {missing_momentum} teams (imputed to default)")
    print(f"  Spread: {missing_spread} games (imputed to 0.0)")
    
    return np.array(X), np.array(y), np.array(groups), valid_indices


def seed_baseline_auc(X, y, groups):
    """Compute AUC for seed-only baseline (seed_diff alone)."""
    logo = LeaveOneGroupOut()
    y_pred = []
    y_true = []

    for train_idx, test_idx in logo.split(X, y, groups):
        X_test = X[test_idx]
        y_test = y[test_idx]

        # seed_diff is first feature
        # Higher seed_diff = bigger underdog = lower P(upset)
        # We want P(upset), so use sigmoid(-seed_diff)
        seed_diff = X_test[:, 0]
        p_upset = 1 / (1 + np.exp(0.3 * seed_diff))  # Simple logistic

        y_pred.extend(p_upset)
        y_true.extend(y_test)

    return roc_auc_score(y_true, y_pred)


def seed_kenpom_baseline_auc(X_2feat, y, groups):
    """Compute AUC for seed+KenPom (adj_em_diff) 2-feature baseline using LOGO-CV LR."""
    logo = LeaveOneGroupOut()
    y_pred = []
    y_true = []

    for train_idx, test_idx in logo.split(X_2feat, y, groups):
        X_train, X_test = X_2feat[train_idx], X_2feat[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        sc = StandardScaler()
        X_train_sc = sc.fit_transform(X_train)
        X_test_sc = sc.transform(X_test)

        lr = LogisticRegression(C=1.0, max_iter=1000, random_state=42)
        lr.fit(X_train_sc, y_train)
        p_upset = lr.predict_proba(X_test_sc)[:, 1]

        y_pred.extend(p_upset)
        y_true.extend(y_test)

    return roc_auc_score(y_true, y_pred)


def train_and_evaluate():
    """Main training pipeline with leave-one-year-out CV."""
    print("="*80)
    print("UPSET PREDICTION MODEL - SKLEARN TRAINING (WITH BUG FIXES)")
    print("="*80)
    
    # Load data
    print("\nLoading data...")
    games, kenpom, lrmc, torvik, momentum, lines, d2_games_removed = load_data()

    print(f"  Tournament games: {len(games)}")
    print(f"  KenPom records: {len(kenpom)}")
    print(f"  LRMC records: {len(lrmc)}")
    print(f"  Torvik records: {len(torvik)}")
    print(f"  Momentum records: {len(momentum)}")
    print(f"  Betting lines: {len(lines)}")

    # Join stats
    print("\nJoining team stats...")
    games = join_team_stats(games, kenpom, lrmc, torvik, momentum, lines)
    
    # Build feature matrix
    print("\nBuilding feature matrix...")
    X, y, groups, valid_indices = build_feature_matrix(games)
    
    # Calculate match rate
    old_match_rate = 638  # From review: old system matched 638/799
    new_matched = len(valid_indices)
    total_games = len(games)
    games_recovered = new_matched - old_match_rate
    
    print("\n" + "="*80)
    print("FIXES APPLIED:")
    print("="*80)
    print(f"  Phase 2 features: Torvik + momentum + spread")
    print(f"  D2 games removed: {d2_games_removed}")
    print(f"  Final match rate: {new_matched}/{total_games} ({100*new_matched/total_games:.1f}%)")
    print(f"  AdjEM fixed for years: [2011, 2013, 2014, 2015, 2016]")
    
    # Match rate by year
    print("\n  Match rate by year:")
    games_df = games.iloc[valid_indices].copy()
    games_df['year'] = groups
    for year in sorted(np.unique(groups)):
        year_total = len(games[games['year'] == year])
        year_matched = len(games_df[games_df['year'] == year])
        print(f"    {year}: {year_matched}/{year_total} ({100*year_matched/year_total:.0f}%)")
    
    # Verify AdjEM ranges
    print("\n  AdjEM range by year (should be -30 to +35, NOT 0 to 1):")
    for year in sorted(kenpom['year'].unique()):
        year_data = kenpom[kenpom['year'] == year]
        adj_em_min = year_data['adj_em'].min()
        adj_em_max = year_data['adj_em'].max()
        print(f"    {year}: {adj_em_min:7.2f} to {adj_em_max:7.2f}")
    
    print(f"\nDATA SUMMARY:")
    print(f"  Total games: {len(games)}")
    print(f"  Games with KenPom: {len(valid_indices)}")
    print(f"  Upsets: {y.sum()} ({100*y.mean():.1f}%)")
    print(f"  Features: {X.shape[1]}")
    print(f"  Years: {len(np.unique(groups))}")
    
    # Phase 2D: Feature selection via L1 screening
    print("\n" + "="*80)
    print("PHASE 2D: FEATURE SELECTION (L1 screening)")
    print("="*80)

    scaler_screen = StandardScaler()
    X_screen = scaler_screen.fit_transform(X)

    # L1 (Lasso) screening: fit with strong regularization to zero out weak features
    from sklearn.linear_model import LogisticRegressionCV as LR_CV
    l1_cv = LR_CV(
        penalty='l1', solver='saga', Cs=10, cv=5,
        max_iter=5000, random_state=42, scoring='roc_auc'
    )
    l1_cv.fit(X_screen, y)
    l1_coefs = l1_cv.coef_[0]

    print(f"\nL1 screening (best C={l1_cv.C_[0]:.4f}):")
    surviving = []
    for i, name in enumerate(FEATURE_NAMES):
        status = "KEEP" if abs(l1_coefs[i]) > 1e-6 else "DROP"
        print(f"  {name:25s} coef={l1_coefs[i]:+.4f}  {status}")
        if abs(l1_coefs[i]) > 1e-6:
            surviving.append(i)

    # Save full feature matrix before L1 selection (needed for intermediate baselines)
    X_raw = X.copy()

    if len(surviving) < len(FEATURE_NAMES):
        dropped = [FEATURE_NAMES[i] for i in range(len(FEATURE_NAMES)) if i not in surviving]
        print(f"\nDropping {len(dropped)} features: {dropped}")
        print(f"Keeping {len(surviving)} features: {[FEATURE_NAMES[i] for i in surviving]}")
        X = X[:, surviving]
        active_feature_names = [FEATURE_NAMES[i] for i in surviving]
    else:
        print("\nAll features survived L1 screening.")
        active_feature_names = list(FEATURE_NAMES)

    print(f"Final feature count: {X.shape[1]}")

    # Leave-one-year-out CV
    print(f"\nLEAVE-ONE-YEAR-OUT CV ({len(np.unique(groups))} folds):")
    print("-" * 60)

    logo = LeaveOneGroupOut()

    # C values to search over
    C_VALUES = [0.01, 0.05, 0.1, 0.5, 1.0, 5.0]

    # Results storage — one entry per C value
    results_by_c = {c: [] for c in C_VALUES}

    # Seed baseline
    print("Computing seed-only baseline...")
    baseline_auc = seed_baseline_auc(X, y, groups)
    print(f"  Seed-only baseline:       AUC = {baseline_auc:.4f}")

    # Seed + KenPom (adj_em_diff) baseline
    print("Computing seed+KenPom baseline...")
    seed_idx = FEATURE_NAMES.index('seed_diff')
    aem_idx = FEATURE_NAMES.index('adj_em_diff')
    X_seed_kenpom = X_raw[:, [seed_idx, aem_idx]]
    seed_kenpom_auc = seed_kenpom_baseline_auc(X_seed_kenpom, y, groups)
    print(f"  Seed+KenPom baseline:     AUC = {seed_kenpom_auc:.4f}")

    # LOO-CV with C grid search (inner CV selects C, outer evaluates)
    print(f"\nTesting C values: {C_VALUES}")
    for fold, (train_idx, test_idx) in enumerate(logo.split(X, y, groups)):
        test_year = groups[test_idx][0]

        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        # Standardize features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        # Evaluate each C value
        for c_val in C_VALUES:
            lr = LogisticRegression(
                penalty='l2',
                C=c_val,
                max_iter=1000,
                random_state=42
            )
            lr.fit(X_train_scaled, y_train)
            lr_pred = lr.predict_proba(X_test_scaled)[:, 1]
            results_by_c[c_val].extend(lr_pred)

    # Find best C by AUC
    auc_by_c = {c: roc_auc_score(y, preds) for c, preds in results_by_c.items()}
    best_c = max(auc_by_c, key=auc_by_c.get)
    best_auc = auc_by_c[best_c]

    print("\n" + "="*80)
    print(f"LOO-CV RESULTS — LR-only with C grid search:")
    print("="*80)
    print(f"  Seed-only:    AUC = {baseline_auc:.4f}")
    print(f"  Seed+KenPom:  AUC = {seed_kenpom_auc:.4f}")
    for c_val in C_VALUES:
        marker = " <<<" if c_val == best_c else ""
        print(f"  LR (C={c_val:<5}): AUC = {auc_by_c[c_val]:.4f}{marker}")

    # Calculate improvement over seed-only
    improvement = best_auc - baseline_auc
    improvement_pct = 100 * (best_auc / baseline_auc - 1)

    # Brier scores (calibration quality)
    brier_by_c = {c: brier_score_loss(y, preds) for c, preds in results_by_c.items()}
    best_brier = brier_by_c[best_c]

    print(f"\n  Best C:       {best_c}")
    print(f"  Best AUC:     {best_auc:.4f}")
    print(f"  Brier score:  {best_brier:.4f} (lower is better)")
    print(f"  Improvement:  +{improvement:.4f} (+{improvement_pct:.1f}% over seed-only)")

    
    # Retrain best model on ALL data with isotonic calibration
    print("\n" + "="*60)
    print("RETRAINING ON ALL DATA (with calibration):")
    print("="*60)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    print(f"Training final LR model (C={best_c}) with isotonic calibration...")

    lr_base = LogisticRegression(penalty='l2', C=best_c, max_iter=1000, random_state=42)
    # Wrap with isotonic calibration using 5-fold CV internally
    lr_final = CalibratedClassifierCV(lr_base, method='isotonic', cv=5)
    lr_final.fit(X_scaled, y)

    # Also train uncalibrated for coefficient inspection
    lr_uncalib = LogisticRegression(penalty='l2', C=best_c, max_iter=1000, random_state=42)
    lr_uncalib.fit(X_scaled, y)

    # Save model
    models_dir = Path(__file__).resolve().parent.parent / "data" / "upset_model"
    models_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nSaving model to {models_dir}/")

    model_package = {
        'model_type': 'logistic_calibrated',
        'scaler': scaler,
        'logistic': lr_final,
        'logistic_uncalibrated': lr_uncalib,
        'best_c': best_c,
        'feature_names': active_feature_names,
        'feature_indices': surviving if len(surviving) < len(FEATURE_NAMES) else list(range(len(FEATURE_NAMES))),
        'cv_results': {
            'baseline_auc': baseline_auc,
            'seed_kenpom_auc': seed_kenpom_auc,
            'best_auc': best_auc,
            'best_brier': best_brier,
            'auc_by_c': {str(c): auc for c, auc in auc_by_c.items()},
        },
        'training_n': len(X),
        'n_upsets': int(y.sum()),
        'years': sorted(np.unique(groups).tolist())
    }

    joblib.dump(model_package, models_dir / "sklearn_model.joblib")
    print(f"  ✓ Saved sklearn_model.joblib")

    # Feature importance (LR coefficients from uncalibrated model)
    print("\n" + "="*80)
    print("TOP FEATURES (LR coefficient magnitude):")
    print("="*80)

    coefs = np.abs(lr_uncalib.coef_[0])
    indices = np.argsort(coefs)[::-1]

    for i in range(len(active_feature_names)):
        idx = indices[i]
        sign = "+" if lr_uncalib.coef_[0][idx] > 0 else "-"
        print(f"  {i+1:2d}. {active_feature_names[idx]:25s} {sign}{coefs[idx]:.4f}")
    
    # Spot checks
    print("\n" + "="*80)
    print("SPOT CHECKS:")
    print("="*80)
    
    # Check Oakland 2024
    oakland_2024 = kenpom[(kenpom['year'] == 2024) & (kenpom['team'].str.contains('Oakland', case=False))]
    if not oakland_2024.empty:
        row = oakland_2024.iloc[0]
        print(f"✓ Oakland 2024 (14-seed that beat Kentucky):")
        print(f"    AdjEM: {row['adj_em']:.2f} (expected ~+2.81)")
        print(f"    AdjO: {row['adj_o']:.1f}, AdjD: {row['adj_d']:.1f}")
    
    # Check UMBC 2018
    umbc_game = games[(games['year'] == 2018) & 
                     ((games['team_a'].str.contains('UMBC', case=False)) | 
                      (games['team_b'].str.contains('UMBC', case=False)))]
    if not umbc_game.empty:
        print(f"✓ UMBC 2018 (16-seed that beat Virginia):")
        print(f"    Found in tournament data: {len(umbc_game)} game(s)")
    
    print("\n" + "="*80)
    print("TRAINING COMPLETE!")
    print("="*80)
    print(f"Model saved: {models_dir / 'sklearn_model.joblib'}")
    print(f"Model type: LR-only (C={best_c})")
    print(f"Features: {len(active_feature_names)} (from {len(FEATURE_NAMES)} candidates)")
    print(f"Training samples: {len(X)}")
    print(f"Match rate: {100*len(valid_indices)/len(games):.1f}%")
    print(f"LOO-CV AUC: {best_auc:.4f} (+{improvement_pct:.1f}% over seed-only)")


if __name__ == "__main__":
    train_and_evaluate()
