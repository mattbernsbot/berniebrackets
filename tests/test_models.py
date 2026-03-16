"""Test data models serialization and validation."""

import unittest
from src.models import Team, Matchup, BracketSlot, BracketStructure, CompleteBracket, BracketPick, OwnershipProfile, Config


class TestModels(unittest.TestCase):
    """Test all dataclass models."""
    
    def test_team_serialization(self):
        """Test Team to_dict and from_dict."""
        team = Team(
            name="Duke",
            seed=1,
            region="East",
            kenpom_rank=1,
            adj_em=28.5,
            adj_o=120.0,
            adj_d=91.5,
            adj_t=70.0,
            sos=10.5,
            wins=30,
            losses=4,
            conference="ACC",
            tournament_appearances=3,
            is_auto_bid=True,
            bracket_position=1
        )
        
        # Serialize
        data = team.to_dict()
        self.assertIsInstance(data, dict)
        self.assertEqual(data["name"], "Duke")
        self.assertEqual(data["seed"], 1)
        
        # Deserialize
        team2 = Team.from_dict(data)
        self.assertEqual(team.name, team2.name)
        self.assertEqual(team.adj_em, team2.adj_em)
    
    def test_matchup_serialization(self):
        """Test Matchup to_dict and from_dict."""
        matchup = Matchup(
            team_a="Duke",
            team_b="UNC",
            round_num=6,
            win_prob_a=0.65,
            raw_prob_a=0.62,
            modifiers_applied=["seed_prior", "experience"]
        )
        
        data = matchup.to_dict()
        matchup2 = Matchup.from_dict(data)
        
        self.assertEqual(matchup.team_a, matchup2.team_a)
        self.assertEqual(matchup.win_prob_a, matchup2.win_prob_a)
        self.assertEqual(matchup.modifiers_applied, matchup2.modifiers_applied)
    
    def test_bracket_slot_serialization(self):
        """Test BracketSlot to_dict and from_dict."""
        slot = BracketSlot(
            slot_id=1,
            round_num=1,
            region="East",
            seed_a=1,
            seed_b=16,
            team_a="Duke",
            team_b="FAMU",
            feeds_into=33
        )
        
        data = slot.to_dict()
        slot2 = BracketSlot.from_dict(data)
        
        self.assertEqual(slot.slot_id, slot2.slot_id)
        self.assertEqual(slot.team_a, slot2.team_a)
    
    def test_config_defaults(self):
        """Test Config default values."""
        config = Config()
        
        self.assertEqual(config.pool_size, 25)
        self.assertEqual(config.scoring, [10, 20, 40, 80, 160, 320])
        self.assertEqual(config.sim_count, 10000)
        self.assertEqual(config.risk_profile, "auto")
    
    def test_config_serialization(self):
        """Test Config to_dict and from_dict."""
        config = Config(
            pool_size=50,
            sim_count=5000,
            risk_profile="aggressive"
        )
        
        data = config.to_dict()
        config2 = Config.from_dict(data)
        
        self.assertEqual(config.pool_size, config2.pool_size)
        self.assertEqual(config.sim_count, config2.sim_count)
        self.assertEqual(config.risk_profile, config2.risk_profile)
    
    def test_ownership_profile_serialization(self):
        """Test OwnershipProfile with dict keys conversion."""
        profile = OwnershipProfile(
            team="Duke",
            seed=1,
            round_ownership={1: 0.97, 2: 0.88, 3: 0.72},
            leverage_by_round={1: 1.0, 2: 1.2, 3: 1.5},
            title_ownership=0.25,
            title_leverage=2.0
        )
        
        data = profile.to_dict()
        
        # Check that integer keys are converted to strings for JSON
        self.assertIn("1", data["round_ownership"])
        
        # Deserialize
        profile2 = OwnershipProfile.from_dict(data)
        
        # Check that keys are converted back to ints
        self.assertIn(1, profile2.round_ownership)
        self.assertEqual(profile.round_ownership[1], profile2.round_ownership[1])
    
    def test_complete_bracket_serialization(self):
        """Test CompleteBracket complex serialization."""
        picks = [
            BracketPick(1, 1, "Duke", "lock", 1.0, False),
            BracketPick(2, 1, "UNC", "lean", 1.2, False)
        ]
        
        bracket = CompleteBracket(
            picks=picks,
            champion="Duke",
            final_four=["Duke", "UNC", "Kansas", "Gonzaga"],
            elite_eight=["Duke"] * 8,
            label="optimal",
            expected_score=1100.0,
            p_first_place=0.085,
            p_top_three=0.197,
            expected_finish=6.2
        )
        
        data = bracket.to_dict()
        bracket2 = CompleteBracket.from_dict(data)
        
        self.assertEqual(len(bracket.picks), len(bracket2.picks))
        self.assertEqual(bracket.champion, bracket2.champion)
        self.assertEqual(bracket.p_first_place, bracket2.p_first_place)


if __name__ == '__main__':
    unittest.main()
