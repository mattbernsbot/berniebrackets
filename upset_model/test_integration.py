"""Integration tests for the upset model."""

import json
from pathlib import Path
from predict import UpsetPredictor
from features import extract_features, build_feature_matrix
from logistic import brier_score
from train import compute_auc


def test_predictor_api():
    """Test the UpsetPredictor public API."""
    print("Testing UpsetPredictor API...")
    
    predictor = UpsetPredictor()
    
    # Test basic prediction
    prob = predictor.predict(
        favorite={"seed": 5, "adj_em": 14.0, "adj_o": 112.0, "adj_d": 98.0},
        underdog={"seed": 12, "adj_em": 11.0, "adj_o": 108.0, "adj_d": 97.0},
        round_num=1
    )
    
    assert 0.0 < prob < 1.0, "Probability out of range"
    assert 0.3 < prob < 0.7, f"5v12 upset prob ({prob:.3f}) outside expected range [0.3, 0.7]"
    
    print(f"  ✓ Basic prediction: {prob:.3f}")
    
    # Test predict_matchup (auto-detect favorite)
    prob_a = predictor.predict_matchup(
        team_a={"seed": 5, "adj_em": 14.0, "adj_o": 112.0, "adj_d": 98.0},
        team_b={"seed": 12, "adj_em": 11.0, "adj_o": 108.0, "adj_d": 97.0},
        round_num=1
    )
    
    # team_a is favorite, so prob_a = 1 - prob_upset
    # Small tolerance for clamping effects
    assert abs(prob_a - (1.0 - prob)) < 0.02, f"predict_matchup inconsistent: {prob_a} vs {1-prob}"
    
    print(f"  ✓ predict_matchup: {prob_a:.3f}")
    
    # Test model info
    info = predictor.get_model_info()
    assert info["model_type"] == "logistic"
    assert info["n_features"] == 14
    
    print(f"  ✓ Model info: {info['n_features']} features")
    
    # Test explain
    explanation = predictor.explain(
        favorite={"seed": 5, "adj_em": 14.0, "adj_o": 112.0, "adj_d": 98.0},
        underdog={"seed": 12, "adj_em": 16.0, "adj_o": 114.0, "adj_d": 98.0},  # Better than 5!
        round_num=1
    )
    
    assert "probability" in explanation
    assert "top_factors" in explanation
    assert len(explanation["top_factors"]) == 5
    
    # Should recognize mis-seeded team
    assert explanation["probability"] > 0.6, "Should detect mis-seeded 12-seed"
    
    print(f"  ✓ Explain: {len(explanation['top_factors'])} top factors")
    
    print("✅ UpsetPredictor API tests passed\n")


def test_feature_extraction():
    """Test feature extraction."""
    print("Testing feature extraction...")
    
    fav = {"seed": 5, "adj_em": 14.0, "adj_o": 112.0, "adj_d": 98.0, "sos": 10.0, "srs": 13.5}
    dog = {"seed": 12, "adj_em": 11.0, "adj_o": 108.0, "adj_d": 97.0, "sos": 8.0, "srs": 10.5}
    
    features = extract_features(fav, dog, round_num=1)
    
    # Check key features
    assert features["seed_diff"] == 7.0, "seed_diff should be 12-5=7"
    assert features["adj_em_diff"] == -3.0, "adj_em_diff should be 11-14=-3"
    assert features["round_num"] == 1.0
    assert features["seed_x_adj_em"] == 7.0 * -3.0
    
    print(f"  ✓ Extracted {len(features)} features")
    print(f"  ✓ seed_diff = {features['seed_diff']}")
    print(f"  ✓ seed_x_adj_em = {features['seed_x_adj_em']}")
    
    print("✅ Feature extraction tests passed\n")


def test_on_real_data():
    """Test model on the actual test set."""
    print("Testing on real data (test set)...")
    
    # Load games
    data_path = Path(__file__).parent / "data" / "training" / "tournament_games.json"
    with open(data_path) as f:
        games = json.load(f)
    
    # Get test games (2022-2025)
    test_games = [g for g in games if g["year"] >= 2022]
    
    print(f"  Test games: {len(test_games)}")
    
    # Build feature matrix
    from train import FEATURE_NAMES
    X_test, y_test = build_feature_matrix(test_games, FEATURE_NAMES)
    
    # Predict using API
    predictor = UpsetPredictor()
    predictions = []
    
    for game in test_games:
        seed_a = game.get("seed_a", 1)
        seed_b = game.get("seed_b", 16)
        
        if seed_a < seed_b:
            fav = {**game.get("stats_a", {}), "seed": seed_a}
            dog = {**game.get("stats_b", {}), "seed": seed_b}
        else:
            fav = {**game.get("stats_b", {}), "seed": seed_b}
            dog = {**game.get("stats_a", {}), "seed": seed_a}
        
        prob = predictor.predict(fav, dog, game.get("round", 1))
        predictions.append(prob)
    
    # Compute metrics
    test_brier = brier_score(y_test, predictions)
    test_auc = compute_auc(y_test, predictions)
    
    print(f"  ✓ Brier: {test_brier:.4f} (target: <0.20)")
    print(f"  ✓ AUC: {test_auc:.4f} (target: >0.65)")
    
    assert test_brier < 0.20, "Brier score too high"
    assert test_auc > 0.65, "AUC too low"
    
    print("✅ Real data tests passed\n")


def test_edge_cases():
    """Test edge cases and boundary conditions."""
    print("Testing edge cases...")
    
    predictor = UpsetPredictor()
    
    # 1v16 - should be very low upset prob
    prob_1v16 = predictor.predict(
        favorite={"seed": 1, "adj_em": 28.0},
        underdog={"seed": 16, "adj_em": -5.0},
        round_num=1
    )
    assert prob_1v16 < 0.15, f"1v16 upset prob ({prob_1v16:.3f}) too high"
    print(f"  ✓ 1v16 upset prob: {prob_1v16:.3f} (low as expected)")
    
    # Same seed, different quality
    prob_same_seed = predictor.predict_matchup(
        team_a={"seed": 5, "adj_em": 14.0},
        team_b={"seed": 5, "adj_em": 16.0},  # Better quality
        round_num=1
    )
    assert prob_same_seed < 0.50, "Lower quality team should have <50% win prob"
    print(f"  ✓ Same seed (team_a worse): P(A wins) = {prob_same_seed:.3f}")
    
    # Round effect - later rounds should have different probs
    prob_r1 = predictor.predict(
        favorite={"seed": 2, "adj_em": 22.0},
        underdog={"seed": 3, "adj_em": 19.0},
        round_num=1
    )
    prob_r5 = predictor.predict(
        favorite={"seed": 2, "adj_em": 22.0},
        underdog={"seed": 3, "adj_em": 19.0},
        round_num=5
    )
    print(f"  ✓ 2v3 Round 1: {prob_r1:.3f}")
    print(f"  ✓ 2v3 Round 5: {prob_r5:.3f}")
    # They should be different (round interaction terms)
    assert abs(prob_r1 - prob_r5) > 0.01, "Round should affect predictions"
    
    print("✅ Edge case tests passed\n")


def main():
    """Run all integration tests."""
    print("=" * 70)
    print("UPSET MODEL - INTEGRATION TESTS")
    print("=" * 70)
    print()
    
    test_feature_extraction()
    test_predictor_api()
    test_on_real_data()
    test_edge_cases()
    
    print("=" * 70)
    print("✅ ALL TESTS PASSED")
    print("=" * 70)


if __name__ == "__main__":
    main()
