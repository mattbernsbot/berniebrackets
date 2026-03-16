#!/usr/bin/env python3
"""Test the sklearn-based prediction API."""

from predict import UpsetPredictor

def test_basic_prediction():
    """Test basic prediction with KenPom stats only."""
    print("Testing sklearn-based UpsetPredictor...")
    print("="*60)
    
    predictor = UpsetPredictor()
    
    # Test case 1: Classic 5-12 matchup
    print("\nTest 1: 5-seed vs 12-seed matchup")
    team_a = {
        'seed': 5,
        'adj_em': 15.2,
        'adj_o': 112.5,
        'adj_d': 97.3,
        'adj_t': 68.5,
        'luck': 0.02
    }
    team_b = {
        'seed': 12,
        'adj_em': 8.1,
        'adj_o': 108.2,
        'adj_d': 100.1,
        'adj_t': 66.2,
        'luck': -0.01
    }
    
    p_upset = predictor.predict(team_a, team_b, round_num=1)
    print(f"  Favorite: 5-seed (AdjEM: {team_a['adj_em']})")
    print(f"  Underdog: 12-seed (AdjEM: {team_b['adj_em']})")
    print(f"  P(upset) = {p_upset:.3f} ({100*p_upset:.1f}%)")
    
    # Test case 2: Big upset potential (1 vs 16)
    print("\nTest 2: 1-seed vs 16-seed matchup")
    team_a = {
        'seed': 1,
        'adj_em': 28.5,
        'adj_o': 118.3,
        'adj_d': 89.8,
        'adj_t': 67.1,
        'luck': 0.01
    }
    team_b = {
        'seed': 16,
        'adj_em': -5.2,
        'adj_o': 98.5,
        'adj_d': 103.7,
        'adj_t': 65.0,
        'luck': 0.03
    }
    
    p_upset = predictor.predict(team_a, team_b, round_num=1)
    print(f"  Favorite: 1-seed (AdjEM: {team_a['adj_em']})")
    print(f"  Underdog: 16-seed (AdjEM: {team_b['adj_em']})")
    print(f"  P(upset) = {p_upset:.3f} ({100*p_upset:.1f}%)")
    
    # Test case 3: Close matchup (3 vs 6)
    print("\nTest 3: 3-seed vs 6-seed matchup")
    team_a = {
        'seed': 3,
        'adj_em': 18.7,
        'adj_o': 114.2,
        'adj_d': 95.5,
        'adj_t': 69.3,
        'luck': -0.02
    }
    team_b = {
        'seed': 6,
        'adj_em': 14.3,
        'adj_o': 111.8,
        'adj_d': 97.5,
        'adj_t': 67.8,
        'luck': 0.01
    }
    
    p_upset = predictor.predict(team_a, team_b, round_num=1)
    print(f"  Favorite: 3-seed (AdjEM: {team_a['adj_em']})")
    print(f"  Underdog: 6-seed (AdjEM: {team_b['adj_em']})")
    print(f"  P(upset) = {p_upset:.3f} ({100*p_upset:.1f}%)")
    
    # Test case 4: With full Barttorvik + LRMC stats
    print("\nTest 4: 4-seed vs 13-seed with full stats")
    team_a = {
        'seed': 4,
        'adj_em': 17.5,
        'adj_o': 113.5,
        'adj_d': 96.0,
        'adj_t': 70.2,
        'luck': 0.03
    }
    team_b = {
        'seed': 13,
        'adj_em': 6.8,
        'adj_o': 107.1,
        'adj_d': 100.3,
        'adj_t': 64.5,
        'luck': -0.02
    }
    
    team_a_bt = {
        'efg': 54.2,
        'to_rate': 15.8,
        'or_pct': 32.1,
        'ft_rate': 35.7
    }
    team_b_bt = {
        'efg': 49.8,
        'to_rate': 18.2,
        'or_pct': 28.5,
        'ft_rate': 31.2
    }
    
    team_a_lrmc = {
        'top25_wins': 4,
        'top25_losses': 2,
        'top25_games': 6
    }
    team_b_lrmc = {
        'top25_wins': 1,
        'top25_losses': 4,
        'top25_games': 5
    }
    
    p_upset = predictor.predict(
        team_a, team_b, round_num=1,
        team_a_bt=team_a_bt, team_b_bt=team_b_bt,
        team_a_lrmc=team_a_lrmc, team_b_lrmc=team_b_lrmc
    )
    print(f"  Favorite: 4-seed (AdjEM: {team_a['adj_em']}, vs-top-25: 4-2)")
    print(f"  Underdog: 13-seed (AdjEM: {team_b['adj_em']}, vs-top-25: 1-4)")
    print(f"  P(upset) = {p_upset:.3f} ({100*p_upset:.1f}%)")
    
    # Model info
    print("\n" + "="*60)
    print("MODEL INFO:")
    print("="*60)
    info = predictor.get_model_info()
    print(f"  Model type: {info['model_type']}")
    print(f"  Models: {', '.join(info['models'])}")
    print(f"  Ensemble method: {info['ensemble_method']}")
    print(f"  Training samples: {info['training_n']}")
    print(f"  Training upsets: {info['n_upsets']}")
    print(f"  Years: {min(info['years'])}-{max(info['years'])}")
    print(f"  CV AUC: {info['cv_auc']:.4f}")
    print(f"  Baseline AUC: {info['baseline_auc']:.4f}")
    print(f"  Improvement: +{100*(info['cv_auc']/info['baseline_auc'] - 1):.1f}%")
    
    print("\n✓ All tests passed!")


if __name__ == "__main__":
    test_basic_prediction()
