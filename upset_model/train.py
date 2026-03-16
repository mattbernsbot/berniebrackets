#!/usr/bin/env python3
"""
Train upset prediction model on REAL NCAA tournament data.
Seed-only baseline due to KenPom being blocked.
"""
import json
import math
from logistic import train_logistic, predict_logistic_batch, brier_score

def load_tournament_data():
    """Load real NCAA tournament games."""
    with open('data/ncaa_tournament_real.json') as f:
        games = json.load(f)
    return games

def compute_features_seed_only(game):
    """Compute seed-only features."""
    seed_diff = game['seed_b'] - game['seed_a']
    return [seed_diff, seed_diff**2]

def compute_features_full(game):
    """Compute full features."""
    seed_a = game['seed_a']
    seed_b = game['seed_b']
    round_num = game['round_num']
    
    # Seed difference (positive means team_a is better seeded)
    seed_diff = seed_b - seed_a
    
    # Round features (one-hot encoding)
    round_features = [1 if round_num == i else 0 for i in range(7)]
    
    # Interaction: round × seed_diff
    round_seed_interactions = [r * seed_diff for r in round_features]
    
    # Basic features
    features = [
        seed_diff,
        seed_diff ** 2,
        round_num,
    ]
    
    # Add round indicators (skip round 0 as baseline)
    features.extend(round_features[1:])
    
    # Add interactions
    features.extend(round_seed_interactions[1:])
    
    return features

def prepare_dataset(games, feature_func):
    """Prepare X, y from games."""
    X = []
    y = []
    
    for game in games:
        features = feature_func(game)
        X.append(features)
        
        # Label: 1 if team_a won, 0 if team_b won
        y.append(1 if game['winner'] == 'a' else 0)
    
    return X, y

def compute_auc(y_true, y_pred):
    """Compute AUC-ROC."""
    n = len(y_true)
    pairs = sorted(zip(y_pred, y_true), reverse=True)
    
    n_pos = sum(y_true)
    n_neg = n - n_pos
    
    if n_pos == 0 or n_neg == 0:
        return 0.5
    
    concordant = 0
    for i in range(n):
        if pairs[i][1] == 1:  # positive instance
            for j in range(i+1, n):
                if pairs[j][1] == 0:
                    concordant += 1
    
    return concordant / (n_pos * n_neg)

def compute_calibration(y_true, y_pred):
    """Compute calibration by bins."""
    bins = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0)]
    calibration = []
    
    for low, high in bins:
        in_bin = [(p, y_true[i]) for i, p in enumerate(y_pred) 
                  if low <= p < high or (high == 1.0 and p == 1.0)]
        if in_bin:
            avg_pred = sum(p for p, _ in in_bin) / len(in_bin)
            avg_actual = sum(y for _, y in in_bin) / len(in_bin)
            count = len(in_bin)
            calibration.append((low, high, avg_pred, avg_actual, count))
    
    return calibration

def train_and_evaluate(train_games, test_games, feature_func, feature_names, model_name):
    """Train and evaluate a model."""
    print("\n" + "="*60)
    print(f"TRAINING {model_name}")
    print("="*60)
    
    X_train, y_train = prepare_dataset(train_games, feature_func)
    X_test, y_test = prepare_dataset(test_games, feature_func)
    
    model = train_logistic(
        X_train, y_train,
        learning_rate=0.01,
        max_iterations=2000,
        l2_lambda=0.01,
        verbose=False
    )
    
    model.feature_names = feature_names
    
    # Predict on test set
    y_pred = predict_logistic_batch(model, X_test)
    
    auc = compute_auc(y_test, y_pred)
    brier = brier_score(y_test, y_pred)
    calibration = compute_calibration(y_test, y_pred)
    
    print(f"\nTest Set Performance:")
    print(f"  AUC: {auc:.4f}")
    print(f"  Brier Score: {brier:.4f}")
    
    print(f"\nCalibration:")
    print(f"  {'Range':<12} {'Count':<8} {'Avg Pred':<10} {'Avg Actual':<10}")
    for low, high, avg_pred, avg_actual, count in calibration:
        print(f"  {low:.1f}-{high:.1f}     {count:<8} {avg_pred:.4f}     {avg_actual:.4f}")
    
    print(f"\nFeature Weights:")
    print(f"  Intercept: {model.coefficients[0]:.4f}")
    for i, name in enumerate(feature_names, 1):
        if i < len(model.coefficients):
            print(f"  {name:<25} {model.coefficients[i]:>8.4f}")
    
    return model, auc, brier

def main():
    """Main training pipeline."""
    print("="*60)
    print("NCAA UPSET PREDICTION MODEL - REAL DATA ONLY")
    print("="*60)
    
    # Load data
    games = load_tournament_data()
    
    print(f"\nDATA SUMMARY:")
    print(f"  Total real games: {len(games)}")
    print(f"  Years: {sorted(set(g['year'] for g in games))}")
    print(f"  Upsets: {sum(1 for g in games if g['is_upset'])}")
    print(f"  Upset rate: {100 * sum(1 for g in games if g['is_upset']) / len(games):.1f}%")
    
    # Split: train on years <= 2022, test on years >= 2023
    train_games = [g for g in games if g['year'] <= 2022]
    test_games = [g for g in games if g['year'] >= 2023]
    
    print(f"\n  Train set: {len(train_games)} games (years <= 2022)")
    print(f"  Test set:  {len(test_games)} games (years >= 2023)")
    
    print(f"\nNOTE: KenPom blocked (403 Forbidden), using seed-only features")
    print(f"      This is still REAL data, just without advanced team stats.")
    
    # Train seed-only baseline
    baseline_model, baseline_auc, baseline_brier = train_and_evaluate(
        train_games, test_games,
        compute_features_seed_only,
        ['Seed Diff', 'Seed Diff^2'],
        'SEED-ONLY BASELINE'
    )
    
    # Train full model
    full_feature_names = [
        'Seed Diff', 'Seed Diff^2', 'Round Num',
        'Round_1', 'Round_2', 'Round_3', 'Round_4', 'Round_5', 'Round_6',
        'Round_1×SeedDiff', 'Round_2×SeedDiff', 'Round_3×SeedDiff',
        'Round_4×SeedDiff', 'Round_5×SeedDiff', 'Round_6×SeedDiff'
    ]
    
    full_model, full_auc, full_brier = train_and_evaluate(
        train_games, test_games,
        compute_features_full,
        full_feature_names,
        'FULL MODEL'
    )
    
    # Compare
    print("\n" + "="*60)
    print("MODEL COMPARISON")
    print("="*60)
    print(f"\nSEED-ONLY BASELINE ({len(baseline_model.coefficients)} parameters):")
    print(f"  AUC:   {baseline_auc:.4f}")
    print(f"  Brier: {baseline_brier:.4f}")
    
    print(f"\nFULL MODEL ({len(full_model.coefficients)} parameters):")
    print(f"  AUC:   {full_auc:.4f}")
    print(f"  Brier: {full_brier:.4f}")
    
    if full_auc > baseline_auc:
        lift = 100 * (full_auc - baseline_auc) / baseline_auc
        print(f"\n  ✓ Lift over baseline: {lift:.1f}%")
    else:
        print(f"\n  ⚠ No improvement over baseline")
    
    # Save full model
    output_path = 'models/real_logistic_model.json'
    full_model.save(output_path)
    
    # Also save metadata
    metadata = {
        'test_auc': full_auc,
        'test_brier': full_brier,
        'baseline_auc': baseline_auc,
        'baseline_brier': baseline_brier,
        'data_source': 'Real NCAA tournament games from NCAA.com API',
        'training_years': sorted(set(g['year'] for g in train_games)),
        'test_years': sorted(set(g['year'] for g in test_games)),
        'total_games': len(games),
        'total_upsets': sum(1 for g in games if g['is_upset']),
        'features_used': 'Seeds + Round interactions (KenPom unavailable)'
    }
    
    with open('models/real_logistic_model_metadata.json', 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"\n✓ Model saved to: {output_path}")
    print(f"✓ Metadata saved to: models/real_logistic_model_metadata.json")
    print("\n" + "="*60)

if __name__ == '__main__':
    main()
