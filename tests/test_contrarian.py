"""Test ownership estimation and leverage calculation."""

import unittest
from src.contrarian import (
    estimate_seed_ownership,
    calculate_leverage,
    calculate_pool_leverage,
    build_ownership_profiles,
    find_value_picks,
    update_leverage_with_model
)
from src.models import Team, OwnershipProfile, BracketStructure


class TestContrarian(unittest.TestCase):
    """Test ownership and leverage analysis."""
    
    def test_estimate_seed_ownership_1_seed(self):
        """Test ownership estimation for 1 seed."""
        # 1 seeds should have very high Round 1 ownership
        r1_ownership = estimate_seed_ownership(1, 1)
        self.assertGreater(r1_ownership, 0.95)
        
        # Championship ownership should be lower but still significant
        champ_ownership = estimate_seed_ownership(1, 6)
        self.assertGreater(champ_ownership, 0.20)
        self.assertLess(champ_ownership, 0.30)
    
    def test_estimate_seed_ownership_16_seed(self):
        """Test ownership estimation for 16 seed."""
        # 16 seeds should have very low ownership
        r1_ownership = estimate_seed_ownership(16, 1)
        self.assertLess(r1_ownership, 0.05)
        
        # Championship ownership should be near zero
        champ_ownership = estimate_seed_ownership(16, 6)
        self.assertLess(champ_ownership, 0.001)
    
    def test_estimate_seed_ownership_5_12_matchup(self):
        """Test ownership for classic upset matchup."""
        # 5 seed
        ownership_5 = estimate_seed_ownership(5, 1)
        
        # 12 seed
        ownership_12 = estimate_seed_ownership(12, 1)
        
        # 5 seed should have higher ownership than 12
        self.assertGreater(ownership_5, ownership_12)
        
        # But not overwhelming (this is a classic upset spot)
        self.assertLess(ownership_5, 0.75)
    
    def test_calculate_leverage_high_value(self):
        """Test leverage calculation for high-value pick."""
        # Model: 30% to win, Public: 10% picking them
        leverage = calculate_leverage(0.30, 0.10)
        self.assertAlmostEqual(leverage, 3.0, delta=0.01)
    
    def test_calculate_leverage_low_value(self):
        """Test leverage calculation for low-value pick."""
        # Model: 40% to win, Public: 80% picking them
        leverage = calculate_leverage(0.40, 0.80)
        self.assertAlmostEqual(leverage, 0.5, delta=0.01)
    
    def test_calculate_leverage_floor(self):
        """Test that ownership has a floor to prevent infinite leverage."""
        # Very low ownership should be floored at 0.005
        leverage = calculate_leverage(0.10, 0.001)
        
        # Should use 0.005 floor, so 0.10 / 0.005 = 20
        self.assertAlmostEqual(leverage, 20.0, delta=1.0)
    
    def test_build_ownership_profiles(self):
        """Test building ownership profiles for teams."""
        teams = [
            Team(name="Duke", seed=1, kenpom_rank=1),
            Team(name="FAMU", seed=16, kenpom_rank=350),
            Team(name="Oregon", seed=5, kenpom_rank=20),
        ]
        
        profiles = build_ownership_profiles(teams, public_picks=None)
        
        self.assertEqual(len(profiles), 3)
        
        # Check Duke (1 seed)
        duke_profile = next(p for p in profiles if p.team == "Duke")
        self.assertGreater(duke_profile.title_ownership, 0.20)
        
        # Check FAMU (16 seed)
        famu_profile = next(p for p in profiles if p.team == "FAMU")
        self.assertLess(famu_profile.title_ownership, 0.01)
    
    def test_find_value_picks(self):
        """Test finding high-leverage picks."""
        profiles = [
            OwnershipProfile(
                team="Houston",
                seed=3,
                round_ownership={1: 0.85, 6: 0.15},
                leverage_by_round={1: 1.1, 6: 2.5},
                title_ownership=0.15,
                title_leverage=2.5
            ),
            OwnershipProfile(
                team="Duke",
                seed=1,
                round_ownership={1: 0.97, 6: 0.28},
                leverage_by_round={1: 1.0, 6: 0.9},
                title_ownership=0.28,
                title_leverage=0.9
            ),
        ]
        
        value_picks = find_value_picks(profiles, min_leverage=1.5)
        
        # Should find Houston's championship pick
        self.assertGreater(len(value_picks), 0)
        
        # Highest leverage pick should be Houston's title
        top_pick = value_picks[0]
        self.assertEqual(top_pick["team"], "Houston")
        self.assertGreaterEqual(top_pick["leverage"], 1.5)


class TestPoolLeverage(unittest.TestCase):
    """Test pool-size-aware leverage calculation."""

    def test_standard(self):
        """Pool=25, moderate ownership."""
        # 0.30 / (24 * 0.10 + 1) = 0.30 / 3.4
        result = calculate_pool_leverage(0.30, 0.10, 25)
        self.assertAlmostEqual(result, 0.30 / 3.4, places=4)

    def test_small_pool(self):
        """Pool=10, same prob/ownership gives higher leverage."""
        # 0.30 / (9 * 0.10 + 1) = 0.30 / 1.9
        result = calculate_pool_leverage(0.30, 0.10, 10)
        self.assertAlmostEqual(result, 0.30 / 1.9, places=4)

    def test_ownership_floor(self):
        """Very low ownership floors at 0.005."""
        # 0.10 / (24 * 0.005 + 1) = 0.10 / 1.12
        result = calculate_pool_leverage(0.10, 0.001, 25)
        self.assertAlmostEqual(result, 0.10 / 1.12, places=4)

    def test_high_ownership(self):
        """High ownership = very low leverage."""
        # 0.50 / (24 * 0.90 + 1) = 0.50 / 22.6
        result = calculate_pool_leverage(0.50, 0.90, 25)
        self.assertAlmostEqual(result, 0.50 / 22.6, places=4)


class TestLeverageFallback(unittest.TestCase):
    """Test update_leverage_with_model ownership fallback behavior."""

    def _run_update(self, seed, adj_em, round_ownership, pool_size=25):
        """Helper: run update_leverage_with_model with minimal inputs."""
        team = Team(name="T", seed=seed, adj_em=adj_em)
        profile = OwnershipProfile(
            team="T", seed=seed,
            round_ownership=round_ownership,
            leverage_by_round={r: 1.0 for r in round_ownership},
            title_ownership=round_ownership.get(6, 0.01),
            title_leverage=1.0
        )
        bracket = BracketStructure(slots=[], regions={}, play_in_games=[])
        update_leverage_with_model([profile], [team], {"T": {}}, bracket, pool_size)
        return profile

    def test_zero_ownership_triggers_fallback(self):
        """Zero ownership should fall back to seed-based estimate, not 0.5."""
        # Seed 5 R1 ownership from SEED_OWNERSHIP_CURVES = 0.650
        # round_probs[1] = 1.0 (hardcoded)
        # leverage = 1.0 / (24 * 0.650 + 1) = 1.0 / 16.6
        profile = self._run_update(5, 14.0, {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0})
        self.assertAlmostEqual(profile.leverage_by_round[1], 1.0 / 16.6, places=4)

    def test_nonzero_ownership_used_directly(self):
        """Nonzero ownership should be used as-is, not replaced."""
        # 1.0 / (24 * 0.80 + 1) = 1.0 / 20.2
        profile = self._run_update(5, 14.0, {1: 0.80, 2: 0.50, 3: 0.25, 4: 0.10, 5: 0.05, 6: 0.01})
        self.assertAlmostEqual(profile.leverage_by_round[1], 1.0 / 20.2, places=4)

    def test_fallback_does_not_use_half(self):
        """Seed-16 R6 fallback ownership should be ~0 (floored to 0.005), not 0.5."""
        profile = self._run_update(16, -2.0, {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0})
        # With seed 16 and adj_em <= 0, title prob is vanishingly small
        # If ownership defaulted to 0.5, leverage would be much larger
        self.assertLess(profile.leverage_by_round[6], 0.001)


if __name__ == '__main__':
    unittest.main()
