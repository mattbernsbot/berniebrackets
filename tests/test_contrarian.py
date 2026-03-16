"""Test ownership estimation and leverage calculation."""

import unittest
from src.contrarian import (
    estimate_seed_ownership,
    calculate_leverage,
    build_ownership_profiles,
    find_value_picks
)
from src.models import Team, OwnershipProfile


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
        
        profiles = build_ownership_profiles(teams, espn_picks=None)
        
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


if __name__ == '__main__':
    unittest.main()
