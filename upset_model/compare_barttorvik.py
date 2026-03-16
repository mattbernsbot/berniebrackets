#!/usr/bin/env python3
"""Compare model performance WITH and WITHOUT Barttorvik features.

Trains two models:
1. WITHOUT Barttorvik (16 features)
2. WITH Barttorvik (20 features)

Shows AUC comparison to determine if Barttorvik data improves predictions.
"""

import json
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler
import warnings
warnings.filterwarnings('ignore')

# Import feature extraction
from features import extract_features, FEATURE_NAMES


def load_data():
    """Load all data sources."""
    data_dir = Path(__file__).parent / "data"
    
    # Load tournament games
    with open(data_dir / "ncaa_tournament_real.json") as f:
        games_raw = json.load(f)
    
    # Remove D2 game
    games_clean = []
    for game in games_raw:
        if game['year'] == 2013:
            teams = {game['team_a'].lower(), game['team_b'].lower()}
            if 'grand canyon' in teams and 'seattle pacific' in teams:
                continue
        games_clean.append(game)
    
    games = pd.DataFrame(games_clean)
    
    # Load KenPom
    with open(data_dir / "kenpom_historical.json") as f:
        kenpom_raw = json.load(f)
    
    # Fix AdjEM scale
    problematic_years = {2011, 2013, 2014, 2015, 2016}
    for record in kenpom_raw:
        if record['year'] in problematic_years and 0 <= record['adj_em'] <= 1.0:
            record['adj_em'] = record['adj_o'] - record['adj_d']
    
    kenpom = pd.DataFrame(kenpom_raw)
    
    # Load LRMC
    with open(data_dir / "lrmc_historical.json") as f:
        lrmc = pd.DataFrame(json.load(f))
    
    # Load Barttorvik
    with open(data_dir / "barttorvik_teamstats.json") as f:
        barttorvik_raw = pd.DataFrame(json.load(f))
    
    # Rename fields
    barttorvik_raw = barttorvik_raw.rename(columns={
        'efg_off': 'efg',
        'to_off': 'to_rate',
        'or_off': 'or_pct',
        'ft_rate_off': 'ft_rate'
    })
    
    # Deduplicate Barttorvik
    barttorvik = barttorvik_raw.drop_duplicates(subset=['year', 'team'], keep='first')
    
    return games, kenpom, lrmc, barttorvik


def normalize_team_name(name):
    """Normalize team names for matching."""
    name = name.strip()
    
    aliases = {
        'Ohio St. 1': 'Ohio St.',
        'Ohio State': 'Ohio St.',
        'UConn': 'Connecticut',
        'St. John\'s': 'St. John\'s (NY)',
        'Miami': 'Miami FL',
        'Southern California': 'USC',
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
        'Miami (FL)': 'Miami FL',
        'St. Mary\'s (CA)': 'Saint Mary\'s',
        'Saint Mary\'s (CA)': 'Saint Mary\'s',
        'NC State': 'N.C. State',
        'North Carolina St.': 'N.C. State',
        'FGCU': 'Florida Gulf Coast',
        'FDU': 'Fairleigh Dickinson',
        'SFA': 'Stephen F. Austin',
        'UNI': 'Northern Iowa',
        'Col. of Charleston': 'Charleston',
        'College of Charleston': 'Charleston',
        'NC Asheville': 'UNC Asheville',
        'Little Rock': 'Arkansas Little Rock',
        'Louisiana': 'Louisiana Lafayette',
    }
    
    for alias, canonical in aliases.items():
        if name == alias:
            return canonical
    
    import re
    name = re.sub(r'\s+\d+$', '', name)
    
    return name


def join_team_stats(games, kenpom, lrmc, barttorvik):
    """Join all team stats."""
    # Normalize team names
    kenpom['team_norm'] = kenpom['team'].apply(normalize_team_name)
    lrmc['team_norm'] = lrmc['team'].apply(normalize_team_name)
    barttorvik['team_norm'] = barttorvik['team'].apply(normalize_team_name)
    games['team_a_norm'] = games['team_a'].apply(normalize_team_name)
    games['team_b_norm'] = games['team_b'].apply(normalize_team_name)
    
    # Create lookup keys
    kenpom['key'] = kenpom['year'].astype(str) + '_' + kenpom['team_norm']
    lrmc['key'] = lrmc['year'].astype(str) + '_' + lrmc['team_norm']
    barttorvik['key'] = barttorvik['year'].astype(str) + '_' + barttorvik['team_norm']
    
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
    
    # Join LRMC stats
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
    
    # Join Barttorvik stats
    games = games.merge(
        barttorvik[['key', 'efg', 'to_rate', 'or_pct', 'ft_rate']],
        left_on='key_a',
        right_on='key',
        how='left',
        suffixes=('', '_bt_a')
    ).drop('key', axis=1)
    games = games.rename(columns={
        'efg': 'efg_a',
        'to_rate': 'to_rate_a',
        'or_pct': 'or_pct_a',
        'ft_rate': 'ft_rate_a'
    })
    
    games = games.merge(
        barttorvik[['key', 'efg', 'to_rate', 'or_pct', 'ft_rate']],
        left_on='key_b',
        right_on='key',
        how='left',
        suffixes=('', '_bt_b')
    ).drop('key', axis=1)
    games = games.rename(columns={
        'efg': 'efg_b',
        'to_rate': 'to_rate_b',
        'or_pct': 'or_pct_b',
        'ft_rate': 'ft_rate_b'
    })
    
    return games


def build_feature_matrix(games, include_barttorvik=True):
    """Build feature matrix."""
    X = []
    y = []
    groups = []
    
    for idx, row in games.iterrows():
        # Skip if missing KenPom
        if pd.isna(row['adj_em_a']) or pd.isna(row['adj_em_b']):
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
            
            fav_bt = None
            dog_bt = None
            if include_barttorvik:
                if not pd.isna(row.get('efg_a')):
                    fav_bt = {
                        'efg': row['efg_a'],
                        'to_rate': row['to_rate_a'],
                        'or_pct': row['or_pct_a'],
                        'ft_rate': row['ft_rate_a']
                    }
                if not pd.isna(row.get('efg_b')):
                    dog_bt = {
                        'efg': row['efg_b'],
                        'to_rate': row['to_rate_b'],
                        'or_pct': row['or_pct_b'],
                        'ft_rate': row['ft_rate_b']
                    }
            
            fav_lrmc = None
            dog_lrmc = None
            if not pd.isna(row.get('top25_games_a')):
                fav_lrmc = {
                    'top25_wins': row['top25_wins_a'],
                    'top25_losses': row['top25_losses_a'],
                    'top25_games': row['top25_games_a']
                }
            if not pd.isna(row.get('top25_games_b')):
                dog_lrmc = {
                    'top25_wins': row['top25_wins_b'],
                    'top25_losses': row['top25_losses_b'],
                    'top25_games': row['top25_games_b']
                }
            
            upset = (row['winner'] == 'b')
            
        else:
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
            
            fav_bt = None
            dog_bt = None
            if include_barttorvik:
                if not pd.isna(row.get('efg_b')):
                    fav_bt = {
                        'efg': row['efg_b'],
                        'to_rate': row['to_rate_b'],
                        'or_pct': row['or_pct_b'],
                        'ft_rate': row['ft_rate_b']
                    }
                if not pd.isna(row.get('efg_a')):
                    dog_bt = {
                        'efg': row['efg_a'],
                        'to_rate': row['to_rate_a'],
                        'or_pct': row['or_pct_a'],
                        'ft_rate': row['ft_rate_a']
                    }
            
            fav_lrmc = None
            dog_lrmc = None
            if not pd.isna(row.get('top25_games_b')):
                fav_lrmc = {
                    'top25_wins': row['top25_wins_b'],
                    'top25_losses': row['top25_losses_b'],
                    'top25_games': row['top25_games_b']
                }
            if not pd.isna(row.get('top25_games_a')):
                dog_lrmc = {
                    'top25_wins': row['top25_wins_a'],
                    'top25_losses': row['top25_losses_a'],
                    'top25_games': row['top25_games_a']
                }
            
            upset = (row['winner'] == 'a')
        
        # Extract features
        features = extract_features(
            fav_stats,
            dog_stats,
            row['round_num'],
            fav_bt,
            dog_bt,
            fav_lrmc,
            dog_lrmc
        )
        
        X.append(features)
        y.append(int(upset))
        groups.append(row['year'])
    
    return np.array(X), np.array(y), np.array(groups)


def train_ensemble(X, y, groups):
    """Train ensemble model with LOO-CV."""
    logo = LeaveOneGroupOut()
    
    results = {
        'logistic': [],
        'random_forest': [],
        'gradient_boosting': [],
        'ensemble': []
    }
    
    for fold, (train_idx, test_idx) in enumerate(logo.split(X, y, groups)):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]
        
        # Standardize
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        
        # Logistic Regression
        lr = LogisticRegression(penalty='l2', C=0.1, max_iter=1000, random_state=42)
        lr.fit(X_train_scaled, y_train)
        lr_pred = lr.predict_proba(X_test_scaled)[:, 1]
        results['logistic'].extend(lr_pred)
        
        # Random Forest
        rf = RandomForestClassifier(
            n_estimators=300, max_depth=8, min_samples_split=10,
            min_samples_leaf=5, random_state=42, n_jobs=-1
        )
        rf.fit(X_train, y_train)
        rf_pred = rf.predict_proba(X_test)[:, 1]
        results['random_forest'].extend(rf_pred)
        
        # Gradient Boosting
        gb = GradientBoostingClassifier(
            n_estimators=200, max_depth=5, learning_rate=0.05,
            min_samples_split=10, min_samples_leaf=5, subsample=0.8, random_state=42
        )
        gb.fit(X_train, y_train)
        gb_pred = gb.predict_proba(X_test)[:, 1]
        results['gradient_boosting'].extend(gb_pred)
        
        # Ensemble
        ensemble_pred = (lr_pred + rf_pred + gb_pred) / 3.0
        results['ensemble'].extend(ensemble_pred)
    
    # Compute AUCs
    lr_auc = roc_auc_score(y, results['logistic'])
    rf_auc = roc_auc_score(y, results['random_forest'])
    gb_auc = roc_auc_score(y, results['gradient_boosting'])
    ensemble_auc = roc_auc_score(y, results['ensemble'])
    
    return {
        'lr_auc': lr_auc,
        'rf_auc': rf_auc,
        'gb_auc': gb_auc,
        'ensemble_auc': ensemble_auc
    }


def main():
    print("="*80)
    print("BARTTORVIK FEATURE COMPARISON")
    print("="*80)
    print("\nLoading data...")
    
    games, kenpom, lrmc, barttorvik = load_data()
    joined = join_team_stats(games, kenpom, lrmc, barttorvik)
    
    print(f"  Tournament games: {len(games)}")
    print(f"  Barttorvik records: {len(barttorvik)}")
    
    # Train WITHOUT Barttorvik (16 features)
    print("\n" + "="*80)
    print("TRAINING WITHOUT BARTTORVIK (16 features)")
    print("="*80)
    X_no_bt, y_no_bt, groups_no_bt = build_feature_matrix(joined, include_barttorvik=False)
    print(f"  Samples: {len(X_no_bt)}")
    print(f"  Features: {X_no_bt.shape[1]}")
    print(f"  Upsets: {sum(y_no_bt)} ({100*sum(y_no_bt)/len(y_no_bt):.1f}%)")
    
    results_no_bt = train_ensemble(X_no_bt, y_no_bt, groups_no_bt)
    
    print("\nResults WITHOUT Barttorvik:")
    print(f"  Logistic:     AUC = {results_no_bt['lr_auc']:.4f}")
    print(f"  Random For:   AUC = {results_no_bt['rf_auc']:.4f}")
    print(f"  Grad Boost:   AUC = {results_no_bt['gb_auc']:.4f}")
    print(f"  Ensemble:     AUC = {results_no_bt['ensemble_auc']:.4f}")
    
    # Train WITH Barttorvik (20 features)
    print("\n" + "="*80)
    print("TRAINING WITH BARTTORVIK (20 features)")
    print("="*80)
    X_with_bt, y_with_bt, groups_with_bt = build_feature_matrix(joined, include_barttorvik=True)
    print(f"  Samples: {len(X_with_bt)}")
    print(f"  Features: {X_with_bt.shape[1]}")
    print(f"  Upsets: {sum(y_with_bt)} ({100*sum(y_with_bt)/len(y_with_bt):.1f}%)")
    
    results_with_bt = train_ensemble(X_with_bt, y_with_bt, groups_with_bt)
    
    print("\nResults WITH Barttorvik:")
    print(f"  Logistic:     AUC = {results_with_bt['lr_auc']:.4f}")
    print(f"  Random For:   AUC = {results_with_bt['rf_auc']:.4f}")
    print(f"  Grad Boost:   AUC = {results_with_bt['gb_auc']:.4f}")
    print(f"  Ensemble:     AUC = {results_with_bt['ensemble_auc']:.4f}")
    
    # Comparison
    print("\n" + "="*80)
    print("COMPARISON")
    print("="*80)
    
    improvement = results_with_bt['ensemble_auc'] - results_no_bt['ensemble_auc']
    improvement_pct = 100 * improvement / results_no_bt['ensemble_auc']
    
    print(f"\nEnsemble AUC:")
    print(f"  Without Barttorvik (16 features): {results_no_bt['ensemble_auc']:.4f}")
    print(f"  With Barttorvik (20 features):    {results_with_bt['ensemble_auc']:.4f}")
    print(f"  Improvement:                      +{improvement:.4f} (+{improvement_pct:.2f}%)")
    
    if improvement > 0:
        print("\n✅ BARTTORVIK IMPROVES THE MODEL!")
    else:
        print("\n❌ BARTTORVIK DOES NOT IMPROVE THE MODEL")
    
    print("\n" + "="*80)


if __name__ == '__main__':
    main()
