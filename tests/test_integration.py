"""Integration tests for the full pipeline."""

import unittest
import tempfile
import shutil
import os
from pathlib import Path

from src.config import load_config
from src.models import Team, Config


class TestIntegration(unittest.TestCase):
    """Test end-to-end workflows."""
    
    def setUp(self):
        """Create temporary directory for test outputs."""
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = os.path.join(self.temp_dir, "data")
        self.output_dir = os.path.join(self.temp_dir, "output")
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)
    
    def tearDown(self):
        """Clean up temporary directory."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_config_loading_defaults(self):
        """Test loading config with defaults."""
        config = load_config("nonexistent.json", {})
        
        self.assertEqual(config.pool_size, 25)
        self.assertEqual(config.sim_count, 10000)
        # Auto risk profile gets converted based on pool size (25 -> balanced)
        self.assertEqual(config.risk_profile, "balanced")
    
    def test_config_loading_with_overrides(self):
        """Test loading config with CLI overrides."""
        overrides = {
            "pool_size": 50,
            "sim_count": 5000,
            "risk_profile": "aggressive"
        }
        
        config = load_config("nonexistent.json", overrides)
        
        self.assertEqual(config.pool_size, 50)
        self.assertEqual(config.sim_count, 5000)
        self.assertEqual(config.risk_profile, "aggressive")
    
    def test_team_list_creation(self):
        """Test creating and serializing team list."""
        teams = [
            Team(name="Duke", seed=1, kenpom_rank=1, adj_em=28.0),
            Team(name="UNC", seed=2, kenpom_rank=5, adj_em=22.0),
            Team(name="Kansas", seed=1, kenpom_rank=2, adj_em=27.0),
        ]
        
        # Serialize
        team_dicts = [t.to_dict() for t in teams]
        
        # Deserialize
        teams2 = [Team.from_dict(d) for d in team_dicts]
        
        self.assertEqual(len(teams), len(teams2))
        self.assertEqual(teams[0].name, teams2[0].name)
    
    def test_minimal_pipeline_mock(self):
        """Test a minimal pipeline with mock data."""
        from src.models import BracketStructure, BracketSlot
        from src.sharp import build_matchup_matrix
        from src.contrarian import build_ownership_profiles
        
        # Create minimal mock data
        teams = [
            Team(name=f"Team{i}", seed=i, kenpom_rank=i, 
                 adj_em=30-i*2, adj_o=110.0, adj_d=95.0, adj_t=68.0, conference="Test")
            for i in range(1, 9)
        ]
        
        # Build matchup matrix
        matrix = build_matchup_matrix(teams)
        
        # Check matrix structure
        self.assertEqual(len(matrix), 8)
        for team in teams:
            self.assertIn(team.name, matrix)
        
        # Check antisymmetry
        prob_ab = matrix["Team1"]["Team2"]
        prob_ba = matrix["Team2"]["Team1"]
        self.assertAlmostEqual(prob_ab + prob_ba, 1.0, delta=0.01)
        
        # Build ownership profiles
        profiles = build_ownership_profiles(teams, None)
        
        self.assertEqual(len(profiles), 8)
        
        # 1 seed should have higher ownership than 8 seed
        profile_1 = next(p for p in profiles if p.seed == 1)
        profile_8 = next(p for p in profiles if p.seed == 8)
        
        self.assertGreater(profile_1.title_ownership, profile_8.title_ownership)


if __name__ == '__main__':
    unittest.main()
