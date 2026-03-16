#!/usr/bin/env python3
"""
Train upset prediction model with REAL KenPom data from Wayback Machine.
"""

import json
import math

# Team name aliases to handle NCAA vs KenPom naming differences
TEAM_ALIASES = {
    # Common abbreviations
    'UConn': 'Connecticut',
    'UNC': 'North Carolina',
    'USC': 'Southern California',
    'LSU': 'Louisiana St.',
    'TCU': 'Texas Christian',
    'SMU': 'Southern Methodist',
    'BYU': 'Brigham Young',
    'VCU': 'Virginia Commonwealth',
    'UNLV': 'Nevada Las Vegas',
    'UCF': 'Central Florida',
    'UCLA': 'California Los Angeles',
    'UCSB': 'UC Santa Barbara',
    'UTEP': 'Texas El Paso',
    'UAB': 'Alabama Birmingham',
    'UNI': 'Northern Iowa',
    'UNCW': 'UNC Wilmington',
    'UMBC': 'Maryland Baltimore County',
    'LIU': 'Long Island',
    'SIU': 'Southern Illinois',
    
    # State abbreviations
    'St.': 'St.',
    'State': 'St.',
    
    # Specific teams with known differences
    'Miami': 'Miami FL',
    'Miami (FL)': 'Miami FL',
    'St. Mary\'s': 'Saint Mary\'s',
    'Saint Mary\'s (CA)': 'Saint Mary\'s',
    'College of Charleston': 'Col. of Charleston',
    'UNC Asheville': 'North Carolina Asheville',
    'Little Rock': 'Arkansas Little Rock',
    'Penn': 'Pennsylvania',
    'Texas A&M Corpus Chris': 'Texas A&M Corpus Christi',
    'UNC Greensboro': 'North Carolina Greensboro',
    'LIU Brooklyn': 'Long Island',
    'North Carolina Central': 'NC Central',
    'Stephen F. Austin': 'SF Austin',
    'Mount St. Mary\'s': 'Mt. St. Mary\'s',
    'Mississippi St.': 'Mississippi St.',
    'Michigan St.': 'Michigan St.',
    'Kansas St.': 'Kansas St.',
    'Colorado St.': 'Colorado St.',
    'Iowa St.': 'Iowa St.',
    'Oklahoma St.': 'Oklahoma St.',
    'Oregon St.': 'Oregon St.',
    'Washington St.': 'Washington St.',
    'Arizona St.': 'Arizona St.',
    'Boise St.': 'Boise St.',
    'San Diego St.': 'San Diego St.',
    'Utah St.': 'Utah St.',
    'Montana St.': 'Montana St.',
    'New Mexico St.': 'New Mexico St.',
    'Fresno St.': 'Fresno St.',
    'Grambling': 'Grambling St.',
    
    # Additional missing teams
    'Fla. Atlantic': 'Florida Atlantic',
    'FAU': 'Florida Atlantic',
    'NC State': 'North Carolina St.',
    'N.C. State': 'North Carolina St.',
    'Loyola (IL)': 'Loyola Chicago',
    'Loyola Chicago': 'Loyola Chicago',
    'FDU': 'Fairleigh Dickinson',
    'Ole Miss': 'Mississippi',
    'N.C. A&T': 'North Carolina A&T',
    'FGCU': 'Florida Gulf Coast',
    'UALR': 'Arkansas Little Rock',
    'Middle Tenn.': 'Middle Tennessee',
    'MTSU': 'Middle Tennessee',
    'Mt. St. Mary\'s': 'Mount St. Mary\'s',
    'St. Mary\'s (CA)': 'St. Mary\'s',
    'A&M-Corpus Christi': 'Texas A&M Corpus Chris',
    'Northern Colo.': 'Northern Colorado',
    'UTSA': 'Texas San Antonio',
    'Boston U.': 'Boston University',
    'Saint Peter\'s': 'St. Peter\'s',
}

def normalize_team_name(name):
    """Normalize team name for matching."""
    # Try direct alias lookup
    if name in TEAM_ALIASES:
        return TEAM_ALIASES[name]
    
    # Remove common suffixes/prefixes for fuzzy matching
    normalized = name.replace(' St.', ' St.')
    normalized = normalized.replace(' State', ' St.')
    
    return normalized

def find_kenpom_stats(team_name, year, kenpom_data):
    """
    Find KenPom stats for a team in a given year.
    Returns dict with stats or None if not found.
    """
    # First try exact match
    normalized = normalize_team_name(team_name)
    
    for entry in kenpom_data:
        if entry['year'] == year:
            kenpom_team = entry['team']
            
            # Exact match
            if kenpom_team == normalized or kenpom_team == team_name:
                return entry
            
            # Fuzzy match - check if one contains the other
            if normalized.lower() in kenpom_team.lower() or kenpom_team.lower() in normalized.lower():
                # Make sure it's a reasonable match (at least 50% overlap)
                shorter = min(len(normalized), len(kenpom_team))
                if shorter >= 4:  # Avoid matching very short names
                    return entry
    
    return None

def build_training_dataset():
    """
    Join tournament games with KenPom stats and create training dataset.
    """
    print("Loading data...")
    
    # Load tournament games
    with open('data/ncaa_tournament_real.json') as f:
        games = json.load(f)
    
    # Load KenPom stats
    with open('data/kenpom_historical.json') as f:
        kenpom_data = json.load(f)
    
    print(f"  Tournament games: {len(games)}")
    print(f"  KenPom entries: {len(kenpom_data)}")
    
    # Build training examples
    training_data = []
    matched_count = 0
    unmatched_teams = {}
    
    for game in games:
        year = game['year']
        
        # Find KenPom stats for both teams
        stats_a = find_kenpom_stats(game['team_a'], year, kenpom_data)
        stats_b = find_kenpom_stats(game['team_b'], year, kenpom_data)
        
        if stats_a and stats_b:
            # Determine underdog and favorite
            seed_a = game['seed_a']
            seed_b = game['seed_b']
            
            if seed_a > seed_b:
                # Team A is underdog
                dog_seed = seed_a
                fav_seed = seed_b
                dog_stats = stats_a
                fav_stats = stats_b
                underdog_won = (game['winner'] == 'a')
            else:
                # Team B is underdog (or equal seeds - skip these)
                if seed_a == seed_b:
                    continue
                dog_seed = seed_b
                fav_seed = seed_a
                dog_stats = stats_b
                fav_stats = stats_a
                underdog_won = (game['winner'] == 'b')
            
            # Create features
            features = {
                'year': year,
                'round_num': game['round_num'],
                'dog_seed': dog_seed,
                'fav_seed': fav_seed,
                'seed_diff': dog_seed - fav_seed,
                
                # KenPom stats (underdog - favorite, so positive = underdog better)
                'adj_em_diff': dog_stats['adj_em'] - fav_stats['adj_em'],
                'adj_o_diff': dog_stats['adj_o'] - fav_stats['adj_o'],
                'adj_d_diff': fav_stats['adj_d'] - dog_stats['adj_d'],  # Lower defense is better
                'adj_t_diff': dog_stats['adj_t'] - fav_stats['adj_t'],
                
                'underdog_won': 1 if underdog_won else 0
            }
            
            training_data.append(features)
            matched_count += 1
        else:
            # Track unmatched teams
            if not stats_a:
                key = f"{year} {game['team_a']}"
                unmatched_teams[key] = unmatched_teams.get(key, 0) + 1
            if not stats_b:
                key = f"{year} {game['team_b']}"
                unmatched_teams[key] = unmatched_teams.get(key, 0) + 1
    
    print(f"\n{'='*60}")
    print("DATA SUMMARY:")
    print(f"  Total games: {len(games)}")
    print(f"  Games with KenPom stats: {len(training_data)} ({100*len(training_data)/len(games):.1f}%)")
    print(f"  Games without stats: {len(games) - matched_count}")
    
    if unmatched_teams:
        print(f"\n  ⚠ Unmatched teams (top 10):")
        sorted_unmatched = sorted(unmatched_teams.items(), key=lambda x: x[1], reverse=True)[:10]
        for team, count in sorted_unmatched:
            print(f"    {team}: {count} games")
    
    return training_data

def train_model(training_data):
    """
    Train logistic regression model with real KenPom features.
    """
    import random
    
    # Split into train/test by year
    train_examples = [x for x in training_data if x['year'] <= 2022]
    test_examples = [x for x in training_data if x['year'] > 2022]
    
    print(f"\n{'='*60}")
    print("TRAINING:")
    print(f"  Train set: {len(train_examples)} games (years ≤ 2022)")
    print(f"  Test set: {len(test_examples)} games (years > 2022)")
    
    # Compute feature statistics for normalization
    def compute_stats(examples, feature_name):
        values = [x[feature_name] for x in examples]
        mean = sum(values) / len(values)
        var = sum((x - mean) ** 2 for x in values) / len(values)
        std = math.sqrt(var) if var > 0 else 1.0
        return mean, std
    
    feature_names = ['seed_diff', 'adj_em_diff', 'adj_o_diff', 'adj_d_diff', 'adj_t_diff', 'round_num']
    feature_stats = {name: compute_stats(train_examples, name) for name in feature_names}
    
    # Normalize features
    def normalize_features(example):
        normalized = {}
        for name in feature_names:
            mean, std = feature_stats[name]
            normalized[name] = (example[name] - mean) / std if std > 0 else 0
        return normalized
    
    # Add interaction features
    def create_features(example):
        norm = normalize_features(example)
        features = [
            1.0,  # intercept
            norm['seed_diff'],
            norm['adj_em_diff'],
            norm['adj_o_diff'],
            norm['adj_d_diff'],
            norm['adj_t_diff'],
            norm['round_num'],
            norm['seed_diff'] * norm['adj_em_diff'],  # Interaction
            norm['round_num'] * norm['seed_diff'],
            norm['round_num'] * norm['adj_em_diff'],
        ]
        return features
    
    # Initialize weights
    num_features = 10
    weights = [0.0] * num_features
    
    # Logistic regression training via gradient descent
    learning_rate = 0.01
    num_epochs = 1000
    
    def sigmoid(z):
        z = max(-500, min(500, z))  # Prevent overflow
        return 1.0 / (1.0 + math.exp(-z))
    
    def predict_proba(features, weights):
        z = sum(f * w for f, w in zip(features, weights))
        return sigmoid(z)
    
    # Train
    for epoch in range(num_epochs):
        # Shuffle training data
        random.shuffle(train_examples)
        
        for example in train_examples:
            features = create_features(example)
            y_true = example['underdog_won']
            y_pred = predict_proba(features, weights)
            
            # Gradient descent update
            error = y_pred - y_true
            for i in range(num_features):
                weights[i] -= learning_rate * error * features[i]
    
    # Evaluate
    def evaluate(examples, name):
        predictions = []
        actuals = []
        
        for example in examples:
            features = create_features(example)
            prob = predict_proba(features, weights)
            predictions.append(prob)
            actuals.append(example['underdog_won'])
        
        # AUC (Wilcoxon-Mann-Whitney U statistic)
        positives = [(p, a) for p, a in zip(predictions, actuals) if a == 1]
        negatives = [(p, a) for p, a in zip(predictions, actuals) if a == 0]
        
        if len(positives) == 0 or len(negatives) == 0:
            auc = 0.5
        else:
            concordant = 0
            discordant = 0
            ties = 0
            
            for pos_pred, _ in positives:
                for neg_pred, _ in negatives:
                    if pos_pred > neg_pred:
                        concordant += 1
                    elif pos_pred < neg_pred:
                        discordant += 1
                    else:
                        ties += 1
            
            auc = (concordant + 0.5 * ties) / (len(positives) * len(negatives))
        
        # Brier score
        brier = sum((p - a) ** 2 for p, a in zip(predictions, actuals)) / len(predictions)
        
        print(f"\n{name}:")
        print(f"  AUC: {auc:.4f}")
        print(f"  Brier: {brier:.4f}")
        
        return auc, brier
    
    # Evaluate baseline first (before overwriting weights)
    print(f"\n{'='*60}")
    print("RESULTS:")
    print("\nSEED-ONLY BASELINE:")
    
    # Temporarily swap weights for baseline
    trained_weights = weights[:]
    baseline_weights = [0.0] * num_features
    baseline_weights[0] = -1.5  # intercept (upsets are rare)
    baseline_weights[1] = -0.5  # seed_diff only (bigger diff = less likely upset)
    weights = baseline_weights
    
    baseline_train_auc, baseline_train_brier = evaluate(train_examples, "  Train")
    baseline_test_auc, baseline_test_brier = evaluate(test_examples, "  Test")
    
    # Restore trained weights
    weights = trained_weights
    
    print("\n\nFULL MODEL (with KenPom):")
    train_auc, train_brier = evaluate(train_examples, "  Train")
    test_auc, test_brier = evaluate(test_examples, "  Test")
    
    lift = ((test_auc - baseline_test_auc) / baseline_test_auc) * 100
    print(f"\n  Lift over baseline: {lift:.1f}%")
    
    print(f"\n{'='*60}")
    print("FEATURE COEFFICIENTS:")
    feature_labels = ['intercept', 'seed_diff', 'adj_em_diff', 'adj_o_diff', 'adj_d_diff', 
                      'adj_t_diff', 'round_num', 'seed×adj_em', 'round×seed', 'round×adj_em']
    for label, weight in zip(feature_labels, weights):
        print(f"  {label:20s}: {weight:7.3f}")
    
    # Save model
    model_data = {
        'weights': weights,
        'feature_stats': feature_stats,
        'feature_names': feature_names,
        'feature_labels': feature_labels,
        'train_auc': train_auc,
        'test_auc': test_auc,
        'train_brier': train_brier,
        'test_brier': test_brier,
    }
    
    with open('models/real_logistic_model.json', 'w') as f:
        json.dump(model_data, f, indent=2)
    
    print(f"\n✓ Model saved to models/real_logistic_model.json")

if __name__ == '__main__':
    print("🏀 NCAA Upset Model Training (with REAL KenPom data)")
    print("=" * 60)
    
    training_data = build_training_dataset()
    
    if len(training_data) < 100:
        print("\n❌ ERROR: Not enough training data!")
    else:
        train_model(training_data)
    
    print("\n" + "=" * 60)
    print("✓ Training complete!\n")
