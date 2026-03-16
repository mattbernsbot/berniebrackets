"""Training pipeline for upset prediction model using REAL tournament data."""

import json
import statistics
from pathlib import Path
from logistic import (
    train_logistic, predict_logistic_batch, brier_score, 
    accuracy, compute_aic, compute_bic
)

# Feature set to use
FEATURE_NAMES = [
    "seed_diff",
    "round_num",
    "log_seed_ratio",
    "srs_diff",
    "off_rtg_diff",
    "def_rtg_diff",
    "pace_diff",
    "seed_x_srs",
    "round_x_seed_diff",
]


def build_feature_matrix_real(games: list, stats_by_team_year: dict, feature_names: list) -> tuple:
    """Build feature matrix from real tournament games.
    
    Args:
        games: List of game dicts
        stats_by_team_year: Dict of (team, year) → stats
        feature_names: Ordered list of features
    
    Returns:
        (X, y) feature matrix and labels
    """
    import math
    
    X = []
    y = []
    
    for game in games:
        seed_a = game.get('seed_a')
        seed_b = game.get('seed_b')
        winner = game.get('winner')
        
        if seed_a is None or seed_b is None:
            continue
        
        # Determine favorite and underdog
        if seed_a < seed_b:
            fav_seed = seed_a
            dog_seed = seed_b
            upset = 1 if winner == 1 else 0  # Winner is team_b (index 1)
        else:
            fav_seed = seed_b
            dog_seed = seed_a
            upset = 1 if winner == 0 else 0  # Winner is team_a (index 0)
        
        # Extract features
        seed_diff = dog_seed - fav_seed
        round_num = game.get('round_num', 1)
        
        # Get team stats if available
        team_a_key = (game['team_a'], game['year'])
        team_b_key = (game['team_b'], game['year'])
        
        stats_a = stats_by_team_year.get(team_a_key, {})
        stats_b = stats_by_team_year.get(team_b_key, {})
        
        # Build feature vector
        features = {}
        features['seed_diff'] = float(seed_diff)
        features['round_num'] = float(round_num)
        features['log_seed_ratio'] = math.log(max(dog_seed, 1) / max(fav_seed, 1))
        
        # Add stat-based features if available
        if stats_a and stats_b:
            if seed_a < seed_b:  # team_a is favorite
                fav_stats = stats_a
                dog_stats = stats_b
            else:
                fav_stats = stats_b
                dog_stats = stats_a
            
            srs_fav = fav_stats.get('srs', 0) or 0
            srs_dog = dog_stats.get('srs', 0) or 0
            
            if 'srs' in fav_stats and 'srs' in dog_stats:
                features['srs_diff'] = srs_dog - srs_fav
            if 'off_rtg' in fav_stats and 'off_rtg' in dog_stats:
                features['off_rtg_diff'] = (dog_stats.get('off_rtg', 0) or 0) - (fav_stats.get('off_rtg', 0) or 0)
            if 'def_rtg' in fav_stats and 'def_rtg' in dog_stats:
                # Lower is better for def_rtg, so flip it
                features['def_rtg_diff'] = (fav_stats.get('def_rtg', 0) or 0) - (dog_stats.get('def_rtg', 0) or 0)
            if 'pace' in fav_stats and 'pace' in dog_stats:
                features['pace_diff'] = (dog_stats.get('pace', 0) or 0) - (fav_stats.get('pace', 0) or 0)
            
            # Interaction features
            features['seed_x_srs'] = seed_diff * (srs_dog - srs_fav)
        
        # Other interactions
        features['round_x_seed_diff'] = round_num * seed_diff
        
        # Convert to vector
        x = [features.get(name, 0.0) for name in feature_names]
        
        X.append(x)
        y.append(upset)
    
    return X, y


def temporal_split(games: list, train_end: int = 2021, test_start: int = 2022):
    """Split games by year into train/test sets."""
    train = [g for g in games if g["year"] <= train_end]
    test = [g for g in games if g["year"] >= test_start]
    return train, test


def compute_auc(y_true: list, y_pred: list) -> float:
    """Compute AUC via Wilcoxon-Mann-Whitney statistic."""
    pos_preds = [p for y, p in zip(y_true, y_pred) if y == 1]
    neg_preds = [p for y, p in zip(y_true, y_pred) if y == 0]
    
    if not pos_preds or not neg_preds:
        return 0.5
    
    concordant = 0
    total = len(pos_preds) * len(neg_preds)
    
    for pos_p in pos_preds:
        for neg_p in neg_preds:
            if pos_p > neg_p:
                concordant += 1
            elif pos_p == neg_p:
                concordant += 0.5
    
    return concordant / total if total > 0 else 0.5


def calibration_table(y_true: list, y_pred: list, n_bins: int = 10) -> list:
    """Compute calibration statistics."""
    bins = []
    bin_size = 1.0 / n_bins
    
    for i in range(n_bins):
        bin_start = i * bin_size
        bin_end = (i + 1) * bin_size
        
        bin_preds = []
        bin_labels = []
        for y, p in zip(y_true, y_pred):
            if bin_start <= p < bin_end or (i == n_bins - 1 and p == 1.0):
                bin_preds.append(p)
                bin_labels.append(y)
        
        if bin_preds:
            bins.append({
                "bin": f"[{bin_start:.1f}, {bin_end:.1f})",
                "n_samples": len(bin_preds),
                "mean_predicted": statistics.mean(bin_preds),
                "mean_actual": statistics.mean(bin_labels),
                "calibration_error": abs(statistics.mean(bin_preds) - statistics.mean(bin_labels))
            })
    
    return bins


def train_baseline_model(X_train, y_train, X_test, y_test):
    """Train seed-only baseline model."""
    print("\n" + "=" * 60)
    print("TRAINING SEED-ONLY BASELINE")
    print("=" * 60)
    
    # Extract just seed_diff (index 0)
    X_train_seed = [[row[0]] for row in X_train]
    X_test_seed = [[row[0]] for row in X_test]
    
    model = train_logistic(
        X_train_seed,
        y_train,
        learning_rate=0.01,
        max_iterations=1000,
        tolerance=1e-6,
        l2_lambda=0.0,
        verbose=True
    )
    
    # Evaluate
    train_preds = predict_logistic_batch(model, X_train_seed)
    test_preds = predict_logistic_batch(model, X_test_seed)
    
    train_brier = brier_score(y_train, train_preds)
    test_brier = brier_score(y_test, test_preds)
    test_auc = compute_auc(y_test, test_preds)
    test_acc = accuracy(y_test, test_preds)
    
    print(f"\nBaseline Results:")
    print(f"  Train Brier: {train_brier:.4f}")
    print(f"  Test Brier:  {test_brier:.4f}")
    print(f"  Test AUC:    {test_auc:.4f}")
    print(f"  Test Acc:    {test_acc:.4f}")
    print(f"  Coefficient: {model.coefficients[1]:.4f}")
    
    return model, test_brier, test_auc


def train_full_model(X_train, y_train, X_test, y_test, feature_names):
    """Train full model with all features."""
    print("\n" + "=" * 60)
    print("TRAINING FULL MODEL")
    print("=" * 60)
    print(f"Features: {len(feature_names)}")
    for i, name in enumerate(feature_names):
        print(f"  {i+1}. {name}")
    
    model = train_logistic(
        X_train,
        y_train,
        learning_rate=0.01,
        max_iterations=5000,
        tolerance=1e-7,
        l2_lambda=0.01,
        verbose=True
    )
    
    model.feature_names = feature_names
    
    # Evaluate
    train_preds = predict_logistic_batch(model, X_train)
    test_preds = predict_logistic_batch(model, X_test)
    
    train_brier = brier_score(y_train, train_preds)
    test_brier = brier_score(y_test, test_preds)
    test_auc = compute_auc(y_test, test_preds)
    test_acc = accuracy(y_test, test_preds)
    
    ll_test = sum(
        y * statistics.log(max(p, 1e-15)) + (1 - y) * statistics.log(max(1 - p, 1e-15))
        for y, p in zip(y_test, test_preds)
    )
    aic = compute_aic(ll_test, len(feature_names) + 1)
    bic = compute_bic(ll_test, len(feature_names) + 1, len(y_test))
    
    print(f"\nFull Model Results:")
    print(f"  Train Brier: {train_brier:.4f}")
    print(f"  Test Brier:  {test_brier:.4f}")
    print(f"  Test AUC:    {test_auc:.4f}")
    print(f"  Test Acc:    {test_acc:.4f}")
    print(f"  AIC:         {aic:.2f}")
    print(f"  BIC:         {bic:.2f}")
    
    print(f"\nFeature Coefficients:")
    for i, name in enumerate(feature_names):
        coef = model.coefficients[i + 1]
        print(f"  {name:30s}: {coef:8.4f}")
    print(f"  {'(intercept)':30s}: {model.coefficients[0]:8.4f}")
    
    # Calibration
    print(f"\nCalibration Table:")
    cal_table = calibration_table(y_test, test_preds, n_bins=10)
    for bin_info in cal_table:
        print(f"  {bin_info['bin']:12s} n={bin_info['n_samples']:3d}  "
              f"pred={bin_info['mean_predicted']:.3f}  "
              f"actual={bin_info['mean_actual']:.3f}  "
              f"err={bin_info['calibration_error']:.3f}")
    
    return model, test_brier, test_auc


def main():
    """Run the full training pipeline."""
    # Load real tournament games
    data_path = Path(__file__).parent / "data" / "real_tournament_games.json"
    stats_path = Path(__file__).parent / "data" / "real_team_stats.json"
    
    with open(data_path) as f:
        games = json.load(f)
    
    with open(stats_path) as f:
        all_stats = json.load(f)
    
    # Build stats lookup
    stats_by_team_year = {}
    for stat in all_stats:
        key = (stat['team'], stat['year'])
        stats_by_team_year[key] = stat
    
    print(f"Loaded {len(games)} games")
    print(f"Loaded {len(all_stats)} team-year stat records")
    print(f"Years: {min(g['year'] for g in games)} - {max(g['year'] for g in games)}")
    
    # Split data
    train_games, test_games = temporal_split(games, train_end=2021, test_start=2022)
    
    print(f"\nTrain: {len(train_games)} games (≤2021)")
    print(f"Test:  {len(test_games)} games (≥2022)")
    
    # Build feature matrices
    X_train, y_train = build_feature_matrix_real(train_games, stats_by_team_year, FEATURE_NAMES)
    X_test, y_test = build_feature_matrix_real(test_games, stats_by_team_year, FEATURE_NAMES)
    
    train_upset_rate = sum(y_train) / len(y_train)
    test_upset_rate = sum(y_test) / len(y_test)
    
    print(f"\nTrain upset rate: {train_upset_rate:.3f}")
    print(f"Test upset rate:  {test_upset_rate:.3f}")
    
    # Train baseline
    baseline_model, baseline_brier, baseline_auc = train_baseline_model(
        X_train, y_train, X_test, y_test
    )
    
    # Train full model
    full_model, full_brier, full_auc = train_full_model(
        X_train, y_train, X_test, y_test, FEATURE_NAMES
    )
    
    # Compare
    print("\n" + "=" * 60)
    print("MODEL COMPARISON")
    print("=" * 60)
    print(f"\nSeed-Only Baseline:")
    print(f"  Brier: {baseline_brier:.4f}")
    print(f"  AUC:   {baseline_auc:.4f}")
    print(f"\nFull Model ({len(FEATURE_NAMES)} features):")
    print(f"  Brier: {full_brier:.4f}")
    print(f"  AUC:   {full_auc:.4f}")
    print(f"\nImprovement:")
    brier_improvement = (baseline_brier - full_brier) / baseline_brier * 100
    auc_improvement = (full_auc - baseline_auc) / baseline_auc * 100
    print(f"  Brier: {brier_improvement:+.1f}%")
    print(f"  AUC:   {auc_improvement:+.1f}%")
    
    # Save model
    output_dir = Path(__file__).parent / "models"
    output_dir.mkdir(exist_ok=True)
    
    model_path = output_dir / "logistic_model_real.json"
    full_model.save(model_path)
    print(f"\nModel saved to: {model_path}")
    
    return full_model


if __name__ == "__main__":
    main()
