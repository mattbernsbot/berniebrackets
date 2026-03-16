#!/usr/bin/env python3
"""
Demo: Make upset predictions using the real KenPom model
"""

import json
import math

def load_model():
    with open('models/real_logistic_model.json') as f:
        return json.load(f)

def sigmoid(z):
    z = max(-500, min(500, z))
    return 1.0 / (1.0 + math.exp(-z))

def predict_upset_probability(dog_seed, fav_seed, dog_kenpom, fav_kenpom, round_num, model):
    """
    Predict probability that underdog wins.
    
    Args:
        dog_seed: Underdog seed (higher number)
        fav_seed: Favorite seed (lower number)
        dog_kenpom: Dict with {adj_em, adj_o, adj_d, adj_t}
        fav_kenpom: Dict with {adj_em, adj_o, adj_d, adj_t}
        round_num: 0=First Four, 1=R64, 2=R32, 3=Sweet16, 4=Elite8, 5=Final4, 6=Championship
        model: Loaded model dict
    """
    # Extract features
    seed_diff = dog_seed - fav_seed
    adj_em_diff = dog_kenpom['adj_em'] - fav_kenpom['adj_em']
    adj_o_diff = dog_kenpom['adj_o'] - fav_kenpom['adj_o']
    adj_d_diff = fav_kenpom['adj_d'] - dog_kenpom['adj_d']  # Inverted (lower is better)
    adj_t_diff = dog_kenpom['adj_t'] - fav_kenpom['adj_t']
    
    # Normalize features
    raw_features = {
        'seed_diff': seed_diff,
        'adj_em_diff': adj_em_diff,
        'adj_o_diff': adj_o_diff,
        'adj_d_diff': adj_d_diff,
        'adj_t_diff': adj_t_diff,
        'round_num': round_num
    }
    
    normalized = {}
    for name in model['feature_names']:
        mean, std = model['feature_stats'][name]
        normalized[name] = (raw_features[name] - mean) / std if std > 0 else 0
    
    # Build feature vector with interactions
    features = [
        1.0,  # intercept
        normalized['seed_diff'],
        normalized['adj_em_diff'],
        normalized['adj_o_diff'],
        normalized['adj_d_diff'],
        normalized['adj_t_diff'],
        normalized['round_num'],
        normalized['seed_diff'] * normalized['adj_em_diff'],
        normalized['round_num'] * normalized['seed_diff'],
        normalized['round_num'] * normalized['adj_em_diff'],
    ]
    
    # Compute probability
    z = sum(f * w for f, w in zip(features, model['weights']))
    prob = sigmoid(z)
    
    return prob

if __name__ == '__main__':
    print("🏀 Real KenPom Upset Predictor Demo\n")
    
    model = load_model()
    print(f"Model loaded: Test AUC = {model['test_auc']:.4f}\n")
    
    # Example 1: Classic 12 vs 5 upset scenario
    print("=" * 60)
    print("Example 1: 12-seed vs 5-seed (First Round)")
    print("-" * 60)
    
    # Strong 12-seed with good KenPom stats
    dog_12 = {'adj_em': 15.0, 'adj_o': 110.5, 'adj_d': 95.5, 'adj_t': 68.0}
    fav_5 = {'adj_em': 18.0, 'adj_o': 112.0, 'adj_d': 94.0, 'adj_t': 67.0}
    
    prob = predict_upset_probability(12, 5, dog_12, fav_5, 1, model)
    print(f"12-seed KenPom: AdjEM={dog_12['adj_em']}, AdjO={dog_12['adj_o']}, AdjD={dog_12['adj_d']}")
    print(f"5-seed KenPom:  AdjEM={fav_5['adj_em']}, AdjO={fav_5['adj_o']}, AdjD={fav_5['adj_d']}")
    print(f"\nUpset probability: {prob:.1%}")
    print(f"Implied odds: {100/prob:.1f}-1" if prob > 0.01 else "Very unlikely")
    
    # Example 2: 15 vs 2 - rare upset
    print("\n" + "=" * 60)
    print("Example 2: 15-seed vs 2-seed (First Round)")
    print("-" * 60)
    
    dog_15 = {'adj_em': 5.0, 'adj_o': 102.0, 'adj_d': 97.0, 'adj_t': 65.0}
    fav_2 = {'adj_em': 28.0, 'adj_o': 120.0, 'adj_d': 92.0, 'adj_t': 68.0}
    
    prob = predict_upset_probability(15, 2, dog_15, fav_2, 1, model)
    print(f"15-seed KenPom: AdjEM={dog_15['adj_em']}, AdjO={dog_15['adj_o']}, AdjD={dog_15['adj_d']}")
    print(f"2-seed KenPom:  AdjEM={fav_2['adj_em']}, AdjO={fav_2['adj_o']}, AdjD={fav_2['adj_d']}")
    print(f"\nUpset probability: {prob:.1%}")
    
    # Example 3: 10 vs 7 - close game
    print("\n" + "=" * 60)
    print("Example 3: 10-seed vs 7-seed (First Round)")
    print("-" * 60)
    
    dog_10 = {'adj_em': 12.0, 'adj_o': 108.0, 'adj_d': 96.0, 'adj_t': 66.0}
    fav_7 = {'adj_em': 13.5, 'adj_o': 109.0, 'adj_d': 95.5, 'adj_t': 67.0}
    
    prob = predict_upset_probability(10, 7, dog_10, fav_7, 1, model)
    print(f"10-seed KenPom: AdjEM={dog_10['adj_em']}, AdjO={dog_10['adj_o']}, AdjD={dog_10['adj_d']}")
    print(f"7-seed KenPom:  AdjEM={fav_7['adj_em']}, AdjO={fav_7['adj_o']}, AdjD={fav_7['adj_d']}")
    print(f"\nUpset probability: {prob:.1%}")
    print(f"Almost a toss-up!" if prob > 0.4 else "")
    
    # Example 4: Dangerous underdog (good KenPom, bad seed)
    print("\n" + "=" * 60)
    print("Example 4: 11-seed vs 6-seed (First Round) - Dangerous Underdog")
    print("-" * 60)
    
    # 11-seed playing way above their seed
    dog_11 = {'adj_em': 20.0, 'adj_o': 115.0, 'adj_d': 95.0, 'adj_t': 70.0}
    fav_6 = {'adj_em': 16.0, 'adj_o': 111.0, 'adj_d': 95.0, 'adj_t': 66.0}
    
    prob = predict_upset_probability(11, 6, dog_11, fav_6, 1, model)
    print(f"11-seed KenPom: AdjEM={dog_11['adj_em']}, AdjO={dog_11['adj_o']}, AdjD={dog_11['adj_d']}")
    print(f"6-seed KenPom:  AdjEM={fav_6['adj_em']}, AdjO={fav_6['adj_o']}, AdjD={fav_6['adj_d']}")
    print(f"\nUpset probability: {prob:.1%}")
    print(f"⚠️  ALERT: Underdog has BETTER KenPom stats than favorite!")
    
    print("\n" + "=" * 60)
    print("\n✓ Demo complete! Model predictions look reasonable.\n")
