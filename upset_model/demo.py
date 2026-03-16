"""Demonstration of the upset prediction model."""

from predict import UpsetPredictor


def demo_predictions():
    """Show example predictions for various matchups."""
    
    print("=" * 70)
    print("UPSET PREDICTION MODEL - DEMONSTRATION")
    print("=" * 70)
    
    predictor = UpsetPredictor()
    
    print("\nModel Info:")
    info = predictor.get_model_info()
    print(f"  Type: {info['model_type']}")
    print(f"  Features: {info['n_features']}")
    print(f"  Training examples: {info['training_n']}")
    print(f"  Iterations: {info['n_iterations']}")
    
    print("\n" + "=" * 70)
    print("ROUND 1 MATCHUPS")
    print("=" * 70)
    
    # Classic 5v12 upset scenario
    matchup_5v12 = {
        "favorite": {
            "seed": 5,
            "adj_em": 14.5,
            "adj_o": 112.0,
            "adj_d": 97.5,
            "sos": 12.0,
            "srs": 14.2,
            "wins": 26,
            "losses": 7,
            "win_pct": 0.788
        },
        "underdog": {
            "seed": 12,
            "adj_em": 11.2,
            "adj_o": 108.5,
            "adj_d": 97.3,
            "sos": 8.5,
            "srs": 10.8,
            "wins": 24,
            "losses": 9,
            "win_pct": 0.727
        }
    }
    
    prob_5v12 = predictor.predict(**matchup_5v12, round_num=1)
    print(f"\n5-seed vs 12-seed (Classic upset opportunity):")
    print(f"  5-seed: AdjEM={matchup_5v12['favorite']['adj_em']:.1f}, Record={matchup_5v12['favorite']['wins']}-{matchup_5v12['favorite']['losses']}")
    print(f"  12-seed: AdjEM={matchup_5v12['underdog']['adj_em']:.1f}, Record={matchup_5v12['underdog']['wins']}-{matchup_5v12['underdog']['losses']}")
    print(f"  → P(upset) = {prob_5v12:.1%}")
    print(f"  → Historical 5v12 rate: 36.1%")
    
    # Mis-seeded 12-seed (better than expected)
    matchup_5v12_mis = {
        "favorite": {
            "seed": 5,
            "adj_em": 13.0,
            "adj_o": 110.0,
            "adj_d": 97.0,
            "sos": 10.0,
            "srs": 12.5,
            "wins": 25,
            "losses": 8,
            "win_pct": 0.758
        },
        "underdog": {
            "seed": 12,
            "adj_em": 15.5,  # MUCH better than typical 12-seed
            "adj_o": 114.0,
            "adj_d": 98.5,
            "sos": 5.0,
            "srs": 15.0,
            "wins": 28,
            "losses": 5,
            "win_pct": 0.848
        }
    }
    
    prob_5v12_mis = predictor.predict(**matchup_5v12_mis, round_num=1)
    print(f"\n5-seed vs MIS-SEEDED 12-seed (12-seed actually better):")
    print(f"  5-seed: AdjEM={matchup_5v12_mis['favorite']['adj_em']:.1f}")
    print(f"  12-seed: AdjEM={matchup_5v12_mis['underdog']['adj_em']:.1f} (better than 5!)")
    print(f"  → P(upset) = {prob_5v12_mis:.1%}")
    print(f"  → Model recognizes quality > seed!")
    
    # 1v16 - should be very low upset probability
    matchup_1v16 = {
        "favorite": {
            "seed": 1,
            "adj_em": 28.0,
            "adj_o": 118.0,
            "adj_d": 90.0,
            "sos": 16.0,
            "srs": 27.5,
            "wins": 32,
            "losses": 2,
            "win_pct": 0.941
        },
        "underdog": {
            "seed": 16,
            "adj_em": -5.0,
            "adj_o": 98.0,
            "adj_d": 103.0,
            "sos": -2.0,
            "srs": -5.5,
            "wins": 20,
            "losses": 14,
            "win_pct": 0.588
        }
    }
    
    prob_1v16 = predictor.predict(**matchup_1v16, round_num=1)
    print(f"\n1-seed vs 16-seed:")
    print(f"  1-seed: AdjEM={matchup_1v16['favorite']['adj_em']:.1f}")
    print(f"  16-seed: AdjEM={matchup_1v16['underdog']['adj_em']:.1f}")
    print(f"  → P(upset) = {prob_1v16:.1%}")
    print(f"  → Historical 1v16 upset rate: 1.4% (1 upset ever)")
    
    # 8v9 - coin flip
    matchup_8v9 = {
        "favorite": {
            "seed": 8,
            "adj_em": 7.5,
            "adj_o": 107.0,
            "adj_d": 99.5,
            "sos": 8.0,
            "srs": 7.2,
            "wins": 21,
            "losses": 12,
            "win_pct": 0.636
        },
        "underdog": {
            "seed": 9,
            "adj_em": 6.8,
            "adj_o": 106.5,
            "adj_d": 99.7,
            "sos": 7.5,
            "srs": 6.5,
            "wins": 22,
            "losses": 11,
            "win_pct": 0.667
        }
    }
    
    prob_8v9 = predictor.predict(**matchup_8v9, round_num=1)
    print(f"\n8-seed vs 9-seed (Toss-up):")
    print(f"  8-seed: AdjEM={matchup_8v9['favorite']['adj_em']:.1f}")
    print(f"  9-seed: AdjEM={matchup_8v9['underdog']['adj_em']:.1f}")
    print(f"  → P(upset) = {prob_8v9:.1%}")
    print(f"  → Historical 8v9 rate: 49.3% (near coin flip)")
    
    print("\n" + "=" * 70)
    print("ROUND-AWARE PREDICTIONS (Same matchup, different rounds)")
    print("=" * 70)
    
    # 3v2 matchup in different rounds
    matchup_3v2 = {
        "favorite": {
            "seed": 2,
            "adj_em": 22.0,
            "adj_o": 115.0,
            "adj_d": 93.0,
            "sos": 14.0,
            "srs": 21.5,
            "wins": 29,
            "losses": 4,
            "win_pct": 0.879
        },
        "underdog": {
            "seed": 3,
            "adj_em": 19.0,
            "adj_o": 113.0,
            "adj_d": 94.0,
            "sos": 13.0,
            "srs": 18.5,
            "wins": 28,
            "losses": 6,
            "win_pct": 0.824
        }
    }
    
    print(f"\n2-seed vs 3-seed (quality difference: {matchup_3v2['favorite']['adj_em'] - matchup_3v2['underdog']['adj_em']:.1f} AdjEM)")
    
    for round_num in [2, 3, 4, 5]:
        prob = predictor.predict(**matchup_3v2, round_num=round_num)
        round_names = {2: "Round 2", 3: "Sweet 16", 4: "Elite 8", 5: "Final Four"}
        print(f"  {round_names[round_num]:12s}: P(3-seed upset) = {prob:.1%}")
    
    print("\n" + "=" * 70)
    print("FEATURE EXPLANATIONS")
    print("=" * 70)
    
    # Explain the 5v12 mis-seeded matchup
    explanation = predictor.explain(**matchup_5v12_mis, round_num=1)
    
    print(f"\nExplaining: 5-seed vs MIS-SEEDED 12-seed")
    print(f"Predicted upset probability: {explanation['probability']:.1%}")
    print(f"\nTop 5 contributing features:")
    
    for i, factor in enumerate(explanation['top_factors'], 1):
        print(f"  {i}. {factor['name']:30s}")
        print(f"     Value: {factor['value']:8.3f}")
        print(f"     Contribution: {factor['contribution']:+8.3f} ({factor['direction']})")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    demo_predictions()
