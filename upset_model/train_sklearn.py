#!/usr/bin/env python3
"""Train upset prediction model using sklearn with proper libraries.

Uses:
- sklearn for models (LogisticRegression, RandomForestClassifier, GradientBoostingClassifier)
- pandas for data manipulation
- numpy for numerics
- scipy for statistics (if needed)

Data sources:
- ncaa_tournament_real.json — 798 real NCAA tournament games (2011-2025, D2 game removed)
- kenpom_historical.json — 4,604 team records with AdjEM, AdjO, AdjD, AdjT, Luck
- lrmc_historical.json — 4,242 team records with LRMC rank, vs-top-25 record

Features: 16 (9 original + 7 KenPom/LRMC)
"""

import json
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.metrics import roc_auc_score, brier_score_loss, log_loss
from sklearn.preprocessing import StandardScaler
import joblib
import warnings
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
    data_dir = Path(__file__).parent / "data"
    
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
    
    # Return data + fix counts for reporting
    return games, kenpom, lrmc, d2_games_removed


def normalize_team_name(name: str) -> str:
    """Normalize team names for joining (handle common aliases).
    
    BUG FIX 1 & 3: Expanded from 23 to 63 aliases to recover 120+ dropped games.
    BUG FIX 3: Removed circular USC alias (kept 'Southern California' as canonical).
    """
    # Remove common suffixes/numbers
    name = name.strip()
    
    # Common aliases (expanded to recover dropped games)
    aliases = {
        # Original aliases
        'Ohio St. 1': 'Ohio St.',
        'Ohio State': 'Ohio St.',
        'UConn': 'Connecticut',
        'St. John\'s': 'St. John\'s (NY)',
        'Miami': 'Miami FL',
        'Southern California': 'USC',  # Canonical: USC
        # BUG FIX 3: REMOVED circular 'USC': 'Southern California'
        'LSU': 'Louisiana St.',
        'VCU': 'Virginia Commonwealth',
        'UNLV': 'Nevada Las Vegas',
        'UNC': 'North Carolina',
        'UCSB': 'UC Santa Barbara',
        'UCF': 'Central Florida',
        'SMU': 'Southern Methodist',
        'BYU': 'Brigham Young',
        'TCU': 'Texas Christian',
        'LIU': 'Long Island',
        'UMBC': 'Maryland Baltimore County',
        'UNC Asheville': 'UNC Asheville',
        'St. Mary\'s': 'Saint Mary\'s',
        'St. Bonaventure': 'St. Bonaventure',
        'Mississippi': 'Ole Miss',
        'College of Charleston': 'Col. of Charleston',
        
        # BUG FIX 1: NEW ALIASES (40+ additions)
        'Miami (FL)': 'Miami FL',
        'St. Mary\'s (CA)': 'Saint Mary\'s',
        'Saint Mary\'s (CA)': 'Saint Mary\'s',
        'NC State': 'N.C. State',
        'North Carolina St.': 'N.C. State',  # KenPom used this 2011-2019, now uses N.C. State
        'FGCU': 'Florida Gulf Coast',
        'FDU': 'Fairleigh Dickinson',
        'SFA': 'Stephen F. Austin',
        'UNI': 'Northern Iowa',
        'Middle Tenn.': 'Middle Tennessee',
        'Northern Ky.': 'Northern Kentucky',
        'Eastern Wash.': 'Eastern Washington',
        'Coastal Caro.': 'Coastal Carolina',
        'Western Ky.': 'Western Kentucky',
        'Northern Colo.': 'Northern Colorado',
        'Boston U.': 'Boston University',
        'App State': 'Appalachian St.',
        'Mt. St. Mary\'s': 'Mount St. Mary\'s',
        'Albany (NY)': 'Albany',
        'Fla. Atlantic': 'Florida Atlantic',
        'Col. of Charleston': 'Charleston',
        'College of Charleston': 'Charleston',
        'Gardner-Webb': 'Gardner Webb',
        'Loyola (IL)': 'Loyola Chicago',
        'UALR': 'Arkansas Little Rock',
        'Bakersfield': 'Cal St. Bakersfield',
        'Saint Peter\'s': 'St. Peter\'s',
        'UTSA': 'Texas San Antonio',
        'Grambling': 'Grambling St.',
        'McNeese': 'McNeese St.',
        'Omaha': 'Nebraska Omaha',
        'UNCW': 'UNC Wilmington',
        'Southern U.': 'Southern',
        'N.C. Central': 'North Carolina Central',
        'N.C. A&T': 'North Carolina A&T',
        'East Tenn. St.': 'East Tennessee St.',
        'Eastern Ky.': 'Eastern Kentucky',
        'Western Mich.': 'Western Michigan',
        'Prairie View': 'Prairie View A&M',
        'A&M-Corpus Christi': 'Texas A&M Corpus Chris',
        'Southeast Mo. St.': 'Southeast Missouri St.',
        'Saint Louis': 'St. Louis',
        
        # BUG FIX V2: Fix remaining 5 alias mismatches
        'NC Asheville': 'UNC Asheville',  # Add missing 2011 alias
        'Little Rock': 'Arkansas Little Rock',  # Add missing alias
        'Louisiana': 'Louisiana Lafayette',  # Add missing alias
    }
    
    # Apply alias mapping
    for alias, canonical in aliases.items():
        if name == alias:
            return canonical
    
    # Remove trailing numbers (e.g., "Ohio St. 1" -> "Ohio St.")
    import re
    name = re.sub(r'\s+\d+$', '', name)
    
    return name


def join_team_stats(games, kenpom, lrmc):
    """Join tournament games with team stats from all sources.
    
    Returns:
        DataFrame with columns: year, round_num, is_upset, team_a_*, team_b_*, etc.
    """
    # Normalize team names in all datasets
    kenpom['team_norm'] = kenpom['team'].apply(normalize_team_name)
    lrmc['team_norm'] = lrmc['team'].apply(normalize_team_name)
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
    
    for idx, row in games.iterrows():
        # Skip if missing KenPom data (REQUIRED)
        if pd.isna(row['adj_em_a']) or pd.isna(row['adj_em_b']):
            missing_kenpom += 1
            continue
        
        # Determine favorite vs underdog
        if row['seed_a'] < row['seed_b']:
            # team_a is favorite
            fav_stats = {
                'seed': row['seed_a'],
                'adj_em': row['adj_em_a'],
                'adj_o': row['adj_o_a'],
                'adj_d': row['adj_d_a'],
                'adj_t': row['adj_t_a'],
                'luck': row.get('luck_a', 0.0)
            }
            dog_stats = {
                'seed': row['seed_b'],
                'adj_em': row['adj_em_b'],
                'adj_o': row['adj_o_b'],
                'adj_d': row['adj_d_b'],
                'adj_t': row['adj_t_b'],
                'luck': row.get('luck_b', 0.0)
            }
            fav_lrmc = None
            dog_lrmc = None
            
            # LRMC stats
            if not pd.isna(row.get('top25_games_a')):
                fav_lrmc = {
                    'top25_wins': row['top25_wins_a'],
                    'top25_losses': row['top25_losses_a'],
                    'top25_games': row['top25_games_a']
                }
            else:
                missing_lrmc += 1
                
            if not pd.isna(row.get('top25_games_b')):
                dog_lrmc = {
                    'top25_wins': row['top25_wins_b'],
                    'top25_losses': row['top25_losses_b'],
                    'top25_games': row['top25_games_b']
                }
            
            upset = (row['winner'] == 'b')
            
        elif row['seed_b'] < row['seed_a']:
            # team_b is favorite
            fav_stats = {
                'seed': row['seed_b'],
                'adj_em': row['adj_em_b'],
                'adj_o': row['adj_o_b'],
                'adj_d': row['adj_d_b'],
                'adj_t': row['adj_t_b'],
                'luck': row.get('luck_b', 0.0)
            }
            dog_stats = {
                'seed': row['seed_a'],
                'adj_em': row['adj_em_a'],
                'adj_o': row['adj_o_a'],
                'adj_d': row['adj_d_a'],
                'adj_t': row['adj_t_a'],
                'luck': row.get('luck_a', 0.0)
            }
            fav_lrmc = None
            dog_lrmc = None
            
            # LRMC stats
            if not pd.isna(row.get('top25_games_b')):
                fav_lrmc = {
                    'top25_wins': row['top25_wins_b'],
                    'top25_losses': row['top25_losses_b'],
                    'top25_games': row['top25_games_b']
                }
            else:
                missing_lrmc += 1
                
            if not pd.isna(row.get('top25_games_a')):
                dog_lrmc = {
                    'top25_wins': row['top25_wins_a'],
                    'top25_losses': row['top25_losses_a'],
                    'top25_games': row['top25_games_a']
                }
            
            upset = (row['winner'] == 'a')
        else:
            # Equal seeds - skip
            continue
        
        # Extract features
        features = extract_features(
            fav_stats,
            dog_stats,
            row['round_num'],
            fav_lrmc,
            dog_lrmc
        )
        
        X.append(features)
        y.append(1 if upset else 0)
        groups.append(row['year'])
        valid_indices.append(idx)
    
    print(f"Missing data summary:")
    print(f"  KenPom: {missing_kenpom} games")
    print(f"  LRMC: {missing_lrmc} teams (imputed to default)")
    
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


def train_and_evaluate():
    """Main training pipeline with leave-one-year-out CV."""
    print("="*80)
    print("UPSET PREDICTION MODEL - SKLEARN TRAINING (WITH BUG FIXES)")
    print("="*80)
    
    # Load data
    print("\nLoading data...")
    games, kenpom, lrmc, d2_games_removed = load_data()
    
    print(f"  Tournament games: {len(games)}")
    print(f"  KenPom records: {len(kenpom)}")
    print(f"  LRMC records: {len(lrmc)}")
    
    # Join stats
    print("\nJoining team stats...")
    games = join_team_stats(games, kenpom, lrmc)
    
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
    print(f"  Barttorvik features: REMOVED (reverted to 16 features)")
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
    
    # Leave-one-year-out CV
    print(f"\nLEAVE-ONE-YEAR-OUT CV ({len(np.unique(groups))} folds):")
    print("-" * 60)
    
    logo = LeaveOneGroupOut()
    
    # Results storage
    results = {
        'seed_baseline': [],
        'logistic': [],
        'random_forest': [],
        'gradient_boosting': [],
        'ensemble': []
    }
    
    # Seed baseline
    print("Computing seed-only baseline...")
    baseline_auc = seed_baseline_auc(X, y, groups)
    print(f"  Seed-only baseline:       AUC = {baseline_auc:.4f}")
    
    # Train each model
    for fold, (train_idx, test_idx) in enumerate(logo.split(X, y, groups)):
        test_year = groups[test_idx][0]
        
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]
        
        # Standardize features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        
        # Logistic Regression
        lr = LogisticRegression(
            penalty='l2',
            C=0.1,
            max_iter=1000,
            random_state=42
        )
        lr.fit(X_train_scaled, y_train)
        lr_pred = lr.predict_proba(X_test_scaled)[:, 1]
        results['logistic'].extend(lr_pred)
        
        # Random Forest
        rf = RandomForestClassifier(
            n_estimators=300,
            max_depth=8,
            min_samples_split=10,
            min_samples_leaf=5,
            random_state=42,
            n_jobs=-1
        )
        rf.fit(X_train, y_train)
        rf_pred = rf.predict_proba(X_test)[:, 1]
        results['random_forest'].extend(rf_pred)
        
        # Gradient Boosting
        gb = GradientBoostingClassifier(
            n_estimators=200,
            max_depth=5,
            learning_rate=0.05,
            min_samples_split=10,
            min_samples_leaf=5,
            subsample=0.8,
            random_state=42
        )
        gb.fit(X_train, y_train)
        gb_pred = gb.predict_proba(X_test)[:, 1]
        results['gradient_boosting'].extend(gb_pred)
        
        # Ensemble (average of all three)
        ensemble_pred = (lr_pred + rf_pred + gb_pred) / 3.0
        results['ensemble'].extend(ensemble_pred)
    
    # Compute final AUCs
    lr_auc = roc_auc_score(y, results['logistic'])
    rf_auc = roc_auc_score(y, results['random_forest'])
    gb_auc = roc_auc_score(y, results['gradient_boosting'])
    ensemble_auc = roc_auc_score(y, results['ensemble'])
    
    print("\n" + "="*80)
    print(f"LOO-CV RESULTS (16 features):")
    print("="*80)
    print(f"  Seed-only:    AUC = {baseline_auc:.4f}")
    print(f"  Logistic:     AUC = {lr_auc:.4f}")
    print(f"  Random For:   AUC = {rf_auc:.4f}")
    print(f"  Grad Boost:   AUC = {gb_auc:.4f}")
    print(f"  Ensemble:     AUC = {ensemble_auc:.4f}")
    
    # Calculate improvement over seed-only
    improvement = ensemble_auc - baseline_auc
    improvement_pct = 100 * (ensemble_auc / baseline_auc - 1)
    
    print(f"  Improvement:  +{improvement:.4f} (+{improvement_pct:.1f}%)")

    
    # Retrain best model (or ensemble) on ALL data
    print("\n" + "="*60)
    print("RETRAINING ON ALL DATA:")
    print("="*60)
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # Train all models for ensemble
    print("Training final models...")
    
    lr_final = LogisticRegression(penalty='l2', C=0.1, max_iter=1000, random_state=42)
    lr_final.fit(X_scaled, y)
    
    rf_final = RandomForestClassifier(
        n_estimators=300,
        max_depth=8,
        min_samples_split=10,
        min_samples_leaf=5,
        random_state=42,
        n_jobs=-1
    )
    rf_final.fit(X, y)
    
    gb_final = GradientBoostingClassifier(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.05,
        min_samples_split=10,
        min_samples_leaf=5,
        subsample=0.8,
        random_state=42
    )
    gb_final.fit(X, y)
    
    # Save models
    models_dir = Path(__file__).parent / "models"
    models_dir.mkdir(exist_ok=True)
    
    print(f"\nSaving models to {models_dir}/")
    
    # Save all models + scaler as ensemble
    model_package = {
        'scaler': scaler,
        'logistic': lr_final,
        'random_forest': rf_final,
        'gradient_boosting': gb_final,
        'feature_names': FEATURE_NAMES,
        'cv_results': {
            'baseline_auc': baseline_auc,
            'logistic_auc': lr_auc,
            'random_forest_auc': rf_auc,
            'gradient_boosting_auc': gb_auc,
            'ensemble_auc': ensemble_auc
        },
        'training_n': len(X),
        'n_upsets': int(y.sum()),
        'years': sorted(np.unique(groups).tolist())
    }
    
    joblib.dump(model_package, models_dir / "sklearn_model.joblib")
    print(f"  ✓ Saved sklearn_model.joblib")
    
    # Feature importance (from Random Forest)
    print("\n" + "="*80)
    print("TOP FEATURES (Random Forest importance):")
    print("="*80)
    
    importances = rf_final.feature_importances_
    indices = np.argsort(importances)[::-1]
    
    for i in range(min(15, len(FEATURE_NAMES))):
        idx = indices[i]
        print(f"  {i+1:2d}. {FEATURE_NAMES[idx]:25s} {importances[idx]:.4f}")
    
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
    print("V2 TRAINING COMPLETE!")
    print("="*80)
    print(f"Model saved: {models_dir / 'sklearn_model.joblib'}")
    print(f"Features: {len(FEATURE_NAMES)} (down from 21)")
    print(f"Training samples: {len(X)}")
    print(f"Match rate: {100*len(valid_indices)/len(games):.1f}%")
    print(f"Ensemble AUC: {ensemble_auc:.4f}")


if __name__ == "__main__":
    train_and_evaluate()
