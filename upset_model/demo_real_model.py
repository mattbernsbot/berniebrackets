#!/usr/bin/env python3
"""Demo script showing the real-data model in action."""

import json
from pathlib import Path
from logistic import LogisticModel, predict_logistic
import math


def predict_upset_probability(model, fav_seed, dog_seed, round_num, 
                              fav_stats, dog_stats):
    """Predict upset probability for a matchup."""
    
    # Compute features
    seed_diff = dog_seed - fav_seed
    
    features = {
        'seed_diff': float(seed_diff),
        'round_num': float(round_num),
        'log_seed_ratio': math.log(dog_seed / fav_seed),
        'srs_diff': dog_stats['srs'] - fav_stats['srs'],
        'off_rtg_diff': dog_stats['off_rtg'] - fav_stats['off_rtg'],
        'def_rtg_diff': fav_stats['def_rtg'] - dog_stats['def_rtg'],  # Flipped
        'pace_diff': dog_stats['pace'] - fav_stats['pace'],
        'seed_x_srs': seed_diff * (dog_stats['srs'] - fav_stats['srs']),
        'round_x_seed_diff': round_num * seed_diff
    }
    
    # Convert to vector
    x = [features[name] for name in model.feature_names]
    
    # Predict
    prob = predict_logistic(model, x)
    return prob


def main():
    """Run demo predictions."""
    print("=" * 60)
    print("NCAA UPSET MODEL - REAL DATA DEMO")
    print("=" * 60)
    
    # Load model
    model_path = Path(__file__).parent / "models" / "logistic_model_real.json"
    model = LogisticModel.load(model_path)
    
    print(f"\nLoaded model with {len(model.feature_names)} features:")
    for i, name in enumerate(model.feature_names):
        print(f"  {i+1}. {name:20s} coef={model.coefficients[i+1]:7.3f}")
    
    # Define some example matchups
    print("\n" + "=" * 60)
    print("EXAMPLE PREDICTIONS")
    print("=" * 60)
    
    examples = [
        # Classic 1 vs 16 (should be low upset probability)
        {
            'name': '1 seed vs 16 seed (Round 1)',
            'fav_seed': 1, 'dog_seed': 16, 'round': 1,
            'fav_stats': {'srs': 28.0, 'off_rtg': 118.0, 'def_rtg': 92.0, 'pace': 68.0},
            'dog_stats': {'srs': -5.0, 'off_rtg': 98.0, 'def_rtg': 108.0, 'pace': 68.0}
        },
        
        # 5 vs 12 (historically ~36% upset rate)
        {
            'name': '5 seed vs 12 seed (Round 1)',
            'fav_seed': 5, 'dog_seed': 12, 'round': 1,
            'fav_stats': {'srs': 13.0, 'off_rtg': 110.5, 'def_rtg': 95.5, 'pace': 69.0},
            'dog_stats': {'srs': 3.0, 'off_rtg': 105.5, 'def_rtg': 98.5, 'pace': 70.0}
        },
        
        # 8 vs 9 (coin flip)
        {
            'name': '8 seed vs 9 seed (Round 1)',
            'fav_seed': 8, 'dog_seed': 9, 'round': 1,
            'fav_stats': {'srs': 7.0, 'off_rtg': 107.5, 'def_rtg': 97.5, 'pace': 67.0},
            'dog_stats': {'srs': 6.0, 'off_rtg': 107.0, 'def_rtg': 98.0, 'pace': 68.0}
        },
        
        # 4 vs 13 with strong underdog stats (higher upset chance)
        {
            'name': '4 seed vs 13 seed - Strong underdog',
            'fav_seed': 4, 'dog_seed': 13, 'round': 1,
            'fav_stats': {'srs': 15.0, 'off_rtg': 111.5, 'def_rtg': 94.8, 'pace': 66.0},
            'dog_stats': {'srs': 8.0, 'off_rtg': 108.0, 'def_rtg': 96.0, 'pace': 71.0}  # Hot shooting team
        },
        
        # Elite 8: 2 vs 3 seed
        {
            'name': '2 seed vs 3 seed (Elite 8)',
            'fav_seed': 2, 'dog_seed': 3, 'round': 4,
            'fav_stats': {'srs': 24.0, 'off_rtg': 116.0, 'def_rtg': 93.6, 'pace': 68.5},
            'dog_stats': {'srs': 20.0, 'off_rtg': 114.0, 'def_rtg': 94.0, 'pace': 69.0}
        }
    ]
    
    for ex in examples:
        prob = predict_upset_probability(
            model,
            ex['fav_seed'], ex['dog_seed'], ex['round'],
            ex['fav_stats'], ex['dog_stats']
        )
        
        print(f"\n{ex['name']}")
        print(f"  Favorite: {ex['fav_seed']} seed (SRS={ex['fav_stats']['srs']:.1f}, "
              f"ORtg={ex['fav_stats']['off_rtg']:.1f})")
        print(f"  Underdog: {ex['dog_seed']} seed (SRS={ex['dog_stats']['srs']:.1f}, "
              f"ORtg={ex['dog_stats']['off_rtg']:.1f})")
        print(f"  → Upset Probability: {prob:.1%}")
        
        if prob < 0.10:
            verdict = "Very unlikely upset"
        elif prob < 0.25:
            verdict = "Underdog has a shot"
        elif prob < 0.45:
            verdict = "Pick'em / toss-up"
        else:
            verdict = "Upset is likely!"
        
        print(f"  → {verdict}")
    
    print("\n" + "=" * 60)
    print("Model ready for bracket optimization!")
    print("=" * 60)


if __name__ == '__main__':
    main()
