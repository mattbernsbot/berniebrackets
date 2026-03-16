"""Train the ensemble model (LR + RF) on real NCAA tournament data.

Loads real games and KenPom data, joins them, trains the ensemble, and evaluates.
"""

import json
import math
import statistics
import random
from pathlib import Path

from ensemble import train_ensemble, predict_ensemble, save_model, sigmoid
from features import extract_features, FEATURE_NAMES


# Team name aliases for matching NCAA tournament data with KenPom/Barttorvik/LRMC data
TEAM_ALIASES = {
    # NCAA name → canonical name
    "Miami (FL)": "Miami FL",
    "St. John's (NY)": "St. John's",
    "Saint Joseph's": "St. Joseph's PA",
    "Saint Mary's (CA)": "St. Mary's CA",
    "Col. of Charleston": "Col. Charleston",
    "UNC Asheville": "UNC Asheville",
    "UNC Wilmington": "UNC Wilmington",
    "UNC Greensboro": "UNC Greensboro",
    "A&M-Corpus Christi": "Texas A&M Corpus Chris",
    "Saint Peter's": "St. Peter's",
    "Southern California": "USC",
    "SFA": "SF Austin",
    "VCU": "Virginia Commonwealth",
    "UConn": "Connecticut",
    "LSU": "Louisiana St.",
    "Southern U.": "Southern",
    "UNI": "Northern Iowa",
    "UNLV": "UNLV",
    "USC": "USC",
    "UAB": "UAB",
    "UALR": "Little Rock",
    "UMBC": "Maryland BC",
    "Loyola (IL)": "Loyola Chicago",
    "Loyola Chicago": "Loyola Chicago",
    "N.C. Central": "North Carolina Central",
    "N.C. A&T": "North Carolina A&T",
    # Barttorvik-specific aliases
    "Connecticut": "Connecticut",  # Barttorvik uses full name
    "N.C. State": "NC State",
}


def load_ncaa_games(path: str) -> list:
    """Load NCAA tournament games from JSON."""
    with open(path) as f:
        return json.load(f)


def load_kenpom_data(path: str) -> dict:
    """Load KenPom historical data.
    
    Returns:
        Dict mapping (year, team_name) → stats
    """
    with open(path) as f:
        records = json.load(f)
    
    kenpom_dict = {}
    for rec in records:
        year = rec.get("year")
        team = rec.get("team")
        if year and team:
            kenpom_dict[(year, team)] = rec
    
    return kenpom_dict


def load_barttorvik_data(path: str) -> dict:
    """Load Barttorvik historical data.
    
    Returns:
        Dict mapping (year, team_name) → stats
    """
    try:
        with open(path) as f:
            records = json.load(f)
    except FileNotFoundError:
        return {}
    
    bt_dict = {}
    for rec in records:
        year = rec.get("year")
        team = rec.get("team")
        if year and team:
            bt_dict[(year, team)] = rec
    
    return bt_dict


def load_lrmc_data(path: str) -> dict:
    """Load LRMC historical data.
    
    Returns:
        Dict mapping (year, team_name) → stats
    """
    try:
        with open(path) as f:
            records = json.load(f)
    except FileNotFoundError:
        return {}
    
    lrmc_dict = {}
    for rec in records:
        year = rec.get("year")
        team = rec.get("team")
        if year and team:
            lrmc_dict[(year, team)] = rec
    
    return lrmc_dict


def normalize_team_name(name: str) -> str:
    """Normalize team name for matching."""
    # Apply alias first
    if name in TEAM_ALIASES:
        name = TEAM_ALIASES[name]
    
    # Basic cleanup
    name = name.strip()
    name = name.replace("St.", "St")
    name = name.replace("Saint", "St")
    
    return name


def find_team_stats(team_name: str, year: int, data_dict: dict, defaults: dict) -> dict:
    """Find team stats in any data source.
    
    Args:
        team_name: Team name from tournament data
        year: Year
        data_dict: Dict mapping (year, team_name) → stats
        defaults: Default values if not found
    
    Returns:
        Stats dict or defaults if not found
    """
    norm_name = normalize_team_name(team_name)
    
    # Try exact match first
    if (year, norm_name) in data_dict:
        return data_dict[(year, norm_name)]
    
    # Try original name
    if (year, team_name) in data_dict:
        return data_dict[(year, team_name)]
    
    # Try fuzzy match
    for (y, t), stats in data_dict.items():
        if y == year and (norm_name in t or t in norm_name):
            return stats
    
    # Return defaults
    return defaults


def build_training_data(games: list, kenpom_dict: dict, bt_dict: dict = None, lrmc_dict: dict = None, 
                         use_new_features: bool = True) -> tuple:
    """Build feature matrix and labels from games + all data sources.
    
    Args:
        games: List of tournament games
        kenpom_dict: KenPom data mapping (year, team) → stats
        bt_dict: Optional Barttorvik data mapping (year, team) → stats
        lrmc_dict: Optional LRMC data mapping (year, team) → stats
        use_new_features: If True, extract 21 features; if False, extract 9 original features
    
    Returns:
        (X, y, metadata) where X is [n][21] or [n][9], y is [n], metadata is list of game dicts
    """
    if bt_dict is None:
        bt_dict = {}
    if lrmc_dict is None:
        lrmc_dict = {}
    
    X = []
    y = []
    metadata = []
    
    kenpom_defaults = {"adj_em": 0.0, "adj_o": 105.0, "adj_d": 95.0, "adj_t": 67.0, "luck": 0.0}
    bt_defaults = {"efg": 50.0, "to_rate": 17.0, "or_pct": 29.0, "ft_rate": 33.0}
    lrmc_defaults = {"top25_wins": 0, "top25_losses": 0, "top25_games": 0}
    
    for game in games:
        year = game.get("year")
        round_num = game.get("round_num", 1)
        
        # Get team stats
        team_a_name = game.get("team_a")
        team_b_name = game.get("team_b")
        seed_a = game.get("seed_a")
        seed_b = game.get("seed_b")
        
        # KenPom stats
        stats_a = find_team_stats(team_a_name, year, kenpom_dict, kenpom_defaults)
        stats_b = find_team_stats(team_b_name, year, kenpom_dict, kenpom_defaults)
        
        # Add seeds to stats
        stats_a["seed"] = seed_a
        stats_b["seed"] = seed_b
        
        # Barttorvik stats (optional)
        bt_a = find_team_stats(team_a_name, year, bt_dict, bt_defaults) if use_new_features else None
        bt_b = find_team_stats(team_b_name, year, bt_dict, bt_defaults) if use_new_features else None
        
        # LRMC stats (optional)
        lrmc_a = find_team_stats(team_a_name, year, lrmc_dict, lrmc_defaults) if use_new_features else None
        lrmc_b = find_team_stats(team_b_name, year, lrmc_dict, lrmc_defaults) if use_new_features else None
        
        # Determine favorite/underdog
        if seed_a < seed_b:
            fav, dog = stats_a, stats_b
            fav_bt, dog_bt = bt_a, bt_b
            fav_lrmc, dog_lrmc = lrmc_a, lrmc_b
            upset = 1 if game.get("winner") == 'b' else 0
        elif seed_b < seed_a:
            fav, dog = stats_b, stats_a
            fav_bt, dog_bt = bt_b, bt_a
            fav_lrmc, dog_lrmc = lrmc_b, lrmc_a
            upset = 1 if game.get("winner") == 'a' else 0
        else:
            # Same seed - use adj_em to determine favorite
            if stats_a.get("adj_em", 0) >= stats_b.get("adj_em", 0):
                fav, dog = stats_a, stats_b
                fav_bt, dog_bt = bt_a, bt_b
                fav_lrmc, dog_lrmc = lrmc_a, lrmc_b
                upset = 1 if game.get("winner") == 'b' else 0
            else:
                fav, dog = stats_b, stats_a
                fav_bt, dog_bt = bt_b, bt_a
                fav_lrmc, dog_lrmc = lrmc_b, lrmc_a
                upset = 1 if game.get("winner") == 'a' else 0
        
        # Extract features
        if use_new_features:
            features = extract_features(fav, dog, round_num, fav_bt, dog_bt, fav_lrmc, dog_lrmc)
        else:
            # Old 9-feature extraction (for comparison)
            features = extract_features(fav, dog, round_num)[:9]
        
        X.append(features)
        y.append(upset)
        metadata.append({
            "year": year,
            "round_num": round_num,
            "fav": fav.get("seed"),
            "dog": dog.get("seed"),
            "upset": upset
        })
    
    return X, y, metadata


def compute_auc(y_true: list, y_pred: list) -> float:
    """Compute AUC (Area Under ROC Curve) using trapezoid rule."""
    # Sort by predicted probability
    pairs = sorted(zip(y_pred, y_true), reverse=True)
    
    n_pos = sum(y_true)
    n_neg = len(y_true) - n_pos
    
    if n_pos == 0 or n_neg == 0:
        return 0.5
    
    # Count concordant and discordant pairs
    concordant = 0
    for i in range(len(pairs)):
        if pairs[i][1] == 1:  # Positive case
            # Count negatives ranked below
            for j in range(i + 1, len(pairs)):
                if pairs[j][1] == 0:
                    concordant += 1
    
    auc = concordant / (n_pos * n_neg)
    return auc


def compute_brier_score(y_true: list, y_pred: list) -> float:
    """Compute Brier score: mean((p - y)²)."""
    return statistics.mean((p - y) ** 2 for y, p in zip(y_true, y_pred))


def compute_log_loss(y_true: list, y_pred: list) -> float:
    """Compute log loss: -mean(y*log(p) + (1-y)*log(1-p))."""
    return -statistics.mean(
        y * math.log(max(1e-15, p)) + (1 - y) * math.log(max(1e-15, 1 - p))
        for y, p in zip(y_true, y_pred)
    )


def leave_one_year_out_cv(X: list, y: list, metadata: list, verbose: bool = True) -> tuple:
    """Perform Leave-One-Year-Out cross-validation.
    
    Args:
        X: Feature matrix
        y: Labels
        metadata: List of dicts with 'year' key
        verbose: Print progress
    
    Returns:
        (all_predictions, all_labels) - predictions and true labels from held-out years
    """
    years = sorted(set(m['year'] for m in metadata))
    
    all_predictions = []
    all_labels = []
    
    for fold_idx, test_year in enumerate(years, 1):
        if verbose:
            print(f"    Fold {fold_idx}/{len(years)} (year {test_year})...", end=' ', flush=True)
        
        # Split train/test by year
        train_X, train_y = [], []
        test_X, test_y = [], []
        
        for i, m in enumerate(metadata):
            if m['year'] == test_year:
                test_X.append(X[i])
                test_y.append(y[i])
            else:
                train_X.append(X[i])
                train_y.append(y[i])
        
        if not test_X or not train_X:
            continue
        
        # Train ensemble on training years (quietly)
        model = train_ensemble(train_X, train_y, lr_weight=0.5, n_trees=300, max_depth=8, verbose=False)
        
        # Predict on held-out year
        for x in test_X:
            p = predict_ensemble(model, x)
            all_predictions.append(p)
        
        all_labels.extend(test_y)
        
        if verbose:
            print(f"train={len(train_X)}, test={len(test_X)}")
    
    return all_predictions, all_labels


def seed_only_baseline(X: list, y: list, metadata: list) -> tuple:
    """Compute seed-only baseline predictions using LOO-CV.
    
    The model: P(upset) = logistic(a * seed_diff)
    where seed_diff is feature[0].
    
    Returns:
        (all_predictions, all_labels)
    """
    years = sorted(set(m['year'] for m in metadata))
    
    all_predictions = []
    all_labels = []
    
    for test_year in years:
        # Split train/test by year
        train_seed_diffs, train_y = [], []
        test_seed_diffs, test_y = [], []
        
        for i, m in enumerate(metadata):
            seed_diff = X[i][0]  # First feature is seed_diff
            if m['year'] == test_year:
                test_seed_diffs.append(seed_diff)
                test_y.append(y[i])
            else:
                train_seed_diffs.append(seed_diff)
                train_y.append(y[i])
        
        if not test_seed_diffs or not train_seed_diffs:
            continue
        
        # Fit simple logistic model: P(upset) = sigmoid(a * seed_diff)
        # Use gradient descent to find a
        a = 0.0
        lr = 0.01
        for _ in range(1000):
            grad = 0.0
            for sd, label in zip(train_seed_diffs, train_y):
                p = sigmoid(a * sd)
                grad += (label - p) * sd
            a += lr * grad / len(train_seed_diffs)
        
        # Predict on test year
        for sd in test_seed_diffs:
            p = sigmoid(a * sd)
            all_predictions.append(p)
        
        all_labels.extend(test_y)
    
    return all_predictions, all_labels


def main():
    """Train and evaluate the ensemble model with LOO-CV comparison."""
    print("=" * 70)
    print("UPSET MODEL TRAINING: OLD (9 FEAT) vs NEW (21 FEAT)")
    print("=" * 70)
    
    # Paths
    base_dir = Path(__file__).parent
    games_path = base_dir / "data" / "ncaa_tournament_real.json"
    kenpom_path = base_dir / "data" / "kenpom_historical.json"
    bt_path = base_dir / "data" / "barttorvik_historical.json"
    lrmc_path = base_dir / "data" / "lrmc_historical.json"
    model_path = base_dir / "models" / "ensemble_model.json"
    
    # Load data
    print(f"\nLoading data sources...")
    games = load_ncaa_games(str(games_path))
    kenpom_dict = load_kenpom_data(str(kenpom_path))
    bt_dict = load_barttorvik_data(str(bt_path))
    lrmc_dict = load_lrmc_data(str(lrmc_path))
    
    print(f"  NCAA tournament games: {len(games)}")
    print(f"  KenPom records: {len(kenpom_dict)}")
    print(f"  Barttorvik records: {len(bt_dict)}")
    print(f"  LRMC records: {len(lrmc_dict)}")
    
    # Build OLD model feature matrix (9 features)
    print("\n" + "=" * 70)
    print("BUILDING OLD MODEL (9 features)")
    print("=" * 70)
    X_old, y_old, metadata_old = build_training_data(games, kenpom_dict, use_new_features=False)
    print(f"  Feature matrix: {len(X_old)} samples × {len(X_old[0])} features")
    print(f"  Upsets: {sum(y_old)} / {len(y_old)} ({100*sum(y_old)/len(y_old):.1f}%)")
    
    # Build NEW model feature matrix (21 features)
    print("\n" + "=" * 70)
    print("BUILDING NEW MODEL (21 features)")
    print("=" * 70)
    X_new, y_new, metadata_new = build_training_data(games, kenpom_dict, bt_dict, lrmc_dict, use_new_features=True)
    print(f"  Feature matrix: {len(X_new)} samples × {len(X_new[0])} features")
    print(f"  Upsets: {sum(y_new)} / {len(y_new)} ({100*sum(y_new)/len(y_new):.1f}%)")
    
    # LEAVE-ONE-YEAR-OUT CROSS-VALIDATION
    print("\n" + "=" * 70)
    print("LEAVE-ONE-YEAR-OUT CROSS-VALIDATION")
    print("=" * 70)
    
    # Seed-only baseline
    print("\n[1/3] Seed-only baseline...")
    pred_seed, y_seed = seed_only_baseline(X_old, y_old, metadata_old)
    auc_seed = compute_auc(y_seed, pred_seed)
    brier_seed = compute_brier_score(y_seed, pred_seed)
    print(f"  AUC = {auc_seed:.4f}, Brier = {brier_seed:.4f}")
    
    # Old 9-feature model
    print("\n[2/3] Old model (9 features)...")
    pred_old, y_test_old = leave_one_year_out_cv(X_old, y_old, metadata_old)
    auc_old = compute_auc(y_test_old, pred_old)
    brier_old = compute_brier_score(y_test_old, pred_old)
    print(f"  AUC = {auc_old:.4f}, Brier = {brier_old:.4f}")
    
    # New 21-feature model
    print("\n[3/3] New model (21 features)...")
    pred_new, y_test_new = leave_one_year_out_cv(X_new, y_new, metadata_new)
    auc_new = compute_auc(y_test_new, pred_new)
    brier_new = compute_brier_score(y_test_new, pred_new)
    print(f"  AUC = {auc_new:.4f}, Brier = {brier_new:.4f}")
    
    # RESULTS SUMMARY
    print("\n" + "=" * 70)
    print("LEAVE-ONE-YEAR-OUT CROSS-VALIDATION RESULTS")
    print("=" * 70)
    print(f"\nSeed-only baseline:    AUC = {auc_seed:.4f}  Brier = {brier_seed:.4f}")
    print(f"Old model (9 feat):    AUC = {auc_old:.4f}  Brier = {brier_old:.4f}  " +
          f"({100*(auc_old-auc_seed)/auc_seed:+.1f}% vs baseline)")
    print(f"New model (21 feat):   AUC = {auc_new:.4f}  Brier = {brier_new:.4f}  " +
          f"({100*(auc_new-auc_seed)/auc_seed:+.1f}% vs baseline)")
    
    if auc_new > auc_old:
        lift_pct = 100 * (auc_new - auc_old) / auc_old
        print(f"\n✓ NEW MODEL WINS! +{lift_pct:.1f}% AUC improvement over old model")
    else:
        print(f"\n✗ New features did not improve performance")
    
    # Train final model on ALL data with new features
    print("\n" + "=" * 70)
    print("TRAINING FINAL MODEL (all data, 21 features)")
    print("=" * 70)
    
    model = train_ensemble(X_new, y_new, lr_weight=0.5, n_trees=500, max_depth=8)
    model["feature_names"] = FEATURE_NAMES
    
    # Save model
    model_path.parent.mkdir(parents=True, exist_ok=True)
    save_model(model, str(model_path))
    print(f"\n✓ Model saved to: {model_path}")
    print("=" * 70)


if __name__ == "__main__":
    random.seed(42)  # For reproducible RF training
    main()
