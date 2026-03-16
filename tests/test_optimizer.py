"""Test Monte Carlo simulation and bracket construction."""

import unittest
import random
from src.optimizer import (
    simulate_tournament,
    score_bracket,
    evaluate_bracket_in_pool
)
from src.models import BracketStructure, BracketSlot


class TestOptimizer(unittest.TestCase):
    """Test tournament simulation and scoring."""
    
    def setUp(self):
        """Create a simple test bracket."""
        slots = []
        
        # Round 1 - 4 games
        for i in range(1, 5):
            slot = BracketSlot(
                slot_id=i,
                round_num=1,
                region="East",
                seed_a=i,
                seed_b=9-i,
                team_a=f"Team{i}",
                team_b=f"Team{9-i}",
                feeds_into=5 + (i-1)//2
            )
            slots.append(slot)
        
        # Round 2 - 2 games
        for i in range(5, 7):
            slot = BracketSlot(
                slot_id=i,
                round_num=2,
                region="East",
                seed_a=0,
                seed_b=0,
                feeds_into=7
            )
            slots.append(slot)
        
        # Championship
        slot = BracketSlot(
            slot_id=7,
            round_num=3,
            region="East",
            seed_a=0,
            seed_b=0,
            feeds_into=0
        )
        slots.append(slot)
        
        self.bracket = BracketStructure(
            slots=slots,
            regions={"East": []},
            play_in_games=[]
        )
    
    def test_simulate_tournament_deterministic(self):
        """Test that simulation with fixed seed is deterministic."""
        matchup_matrix = {
            "Team1": {"Team8": 0.9, "Team2": 0.6, "Team3": 0.7, "Team4": 0.8},
            "Team2": {"Team1": 0.4, "Team7": 0.8, "Team3": 0.5, "Team4": 0.6},
            "Team3": {"Team1": 0.3, "Team2": 0.5, "Team6": 0.75, "Team4": 0.55},
            "Team4": {"Team1": 0.2, "Team2": 0.4, "Team3": 0.45, "Team5": 0.7},
            "Team5": {"Team4": 0.3},
            "Team6": {"Team3": 0.25},
            "Team7": {"Team2": 0.2},
            "Team8": {"Team1": 0.1},
        }
        
        rng1 = random.Random(42)
        results1 = simulate_tournament(matchup_matrix, self.bracket, rng1)
        
        rng2 = random.Random(42)
        results2 = simulate_tournament(matchup_matrix, self.bracket, rng2)
        
        # Same seed should give same results
        self.assertEqual(results1, results2)
    
    def test_simulate_tournament_1_vs_16(self):
        """Test that 1 seed beats 16 seed in most simulations."""
        # Create heavily favored matchup
        matchup_matrix = {
            "Team1": {"Team8": 0.95},
            "Team8": {"Team1": 0.05},
        }
        
        wins = 0
        trials = 100
        
        for i in range(trials):
            rng = random.Random(i)
            results = simulate_tournament(matchup_matrix, self.bracket, rng)
            
            # Check slot 1 result
            if 1 in results and results[1] == "Team1":
                wins += 1
        
        # Should win ~95% of the time
        self.assertGreater(wins, 85)
        self.assertLess(wins, 100)
    
    def test_score_bracket_perfect(self):
        """Test scoring a perfect bracket."""
        picks = {
            1: "Team1",
            2: "Team2",
            3: "Team3",
            4: "Team4",
            5: "Team1",
            6: "Team3",
            7: "Team1"
        }
        
        actual = picks.copy()
        
        scoring = [10, 20, 40]
        
        score = score_bracket(picks, actual, scoring, self.bracket)
        
        # 4 R1 games * 10 = 40
        # 2 R2 games * 20 = 40
        # 1 R3 game * 40 = 40
        # Total = 120
        self.assertEqual(score, 120)
    
    def test_score_bracket_partial(self):
        """Test scoring a partially correct bracket."""
        picks = {
            1: "Team1",  # Correct
            2: "Team7",  # Wrong
            3: "Team3",  # Correct
            4: "Team4",  # Correct
            5: "Team1",  # Correct (Team1 won slot 1)
            6: "Team3",  # Correct (Team3 won slot 3)
            7: "Team1"   # Correct
        }
        
        actual = {
            1: "Team1",
            2: "Team2",  # Team2 won, not Team7
            3: "Team3",
            4: "Team4",
            5: "Team1",
            6: "Team3",
            7: "Team1"
        }
        
        scoring = [10, 20, 40]
        
        score = score_bracket(picks, actual, scoring, self.bracket)
        
        # R1: 3 correct * 10 = 30
        # R2: 2 correct * 20 = 40
        # R3: 1 correct * 40 = 40
        # Total = 110
        self.assertEqual(score, 110)
    
    def test_evaluate_bracket_in_pool_win(self):
        """Test ranking when we win the pool."""
        our_picks = {1: "Team1", 2: "Team2", 7: "Team1"}
        actual = {1: "Team1", 2: "Team2", 7: "Team1"}
        
        # Opponent brackets that score worse
        opponents = [
            {1: "Team8", 2: "Team2", 7: "Team1"},  # Wrong R1 pick
            {1: "Team1", 2: "Team7", 7: "Team1"},  # Wrong R1 pick
        ]
        
        scoring = [10, 20, 40]
        
        our_score, our_rank = evaluate_bracket_in_pool(
            our_picks, actual, opponents, scoring, self.bracket
        )
        
        # We should rank 1st
        self.assertEqual(our_rank, 1)
    
    def test_evaluate_bracket_in_pool_lose(self):
        """Test ranking when we lose."""
        our_picks = {1: "Team8", 2: "Team7", 7: "Team8"}  # All wrong
        actual = {1: "Team1", 2: "Team2", 7: "Team1"}
        
        # Opponent brackets that are better
        opponents = [
            {1: "Team1", 2: "Team2", 7: "Team1"},  # Perfect
            {1: "Team1", 2: "Team2", 7: "Team2"},  # Almost perfect
        ]
        
        scoring = [10, 20, 40]
        
        our_score, our_rank = evaluate_bracket_in_pool(
            our_picks, actual, opponents, scoring, self.bracket
        )
        
        # We should rank 3rd (last)
        self.assertEqual(our_rank, 3)
        self.assertEqual(our_score, 0)


    def test_construct_candidate_bracket_completeness(self):
        """Test that construct_candidate_bracket creates all 63 picks."""
        from src.optimizer import construct_candidate_bracket
        from src.models import Team, OwnershipProfile
        
        # Create mock teams
        teams = []
        for i in range(1, 69):
            team = Team(
                name=f"Team{i}",
                seed=(i - 1) % 16 + 1,
                region=["East", "West", "South", "Midwest"][(i - 1) // 17],
                kenpom_rank=i,
                adj_em=30.0 - i * 0.5,
                adj_o=110.0,
                adj_d=95.0,
                adj_t=67.5,
                sos=10.0,
                wins=25,
                losses=5,
                conference="Big Ten",
                tournament_appearances=0,
                is_auto_bid=False,
                bracket_position=i
            )
            teams.append(team)
        
        # Create mock matchup matrix
        matchup_matrix = {}
        for team_a in teams:
            matchup_matrix[team_a.name] = {}
            for team_b in teams:
                if team_a.name != team_b.name:
                    # Higher ranked team wins more often
                    prob = 0.5 + (team_b.kenpom_rank - team_a.kenpom_rank) * 0.01
                    prob = max(0.1, min(0.9, prob))
                    matchup_matrix[team_a.name][team_b.name] = prob
        
        # Create mock ownership profiles
        ownership_profiles = []
        for team in teams:
            profile = OwnershipProfile(
                team=team.name,
                seed=team.seed,
                round_ownership={1: 1.0, 2: 0.5, 3: 0.25, 4: 0.1, 5: 0.05, 6: 0.01},
                leverage_by_round={1: 1.0, 2: 1.5, 3: 2.0, 4: 2.5, 5: 3.0, 6: 3.5},
                title_ownership=0.01,
                title_leverage=3.5
            )
            ownership_profiles.append(profile)
        
        # Create larger bracket structure (simplified - just enough slots)
        slots = []
        slot_id = 1
        
        # Round 1: 32 games
        for i in range(32):
            slot = BracketSlot(
                slot_id=slot_id,
                round_num=1,
                region=["East", "West", "South", "Midwest"][i // 8],
                seed_a=(i % 16) + 1,
                seed_b=17 - (i % 16),
                team_a=teams[i * 2].name,
                team_b=teams[i * 2 + 1].name,
                feeds_into=33 + i // 2
            )
            slots.append(slot)
            slot_id += 1
        
        # Round 2: 16 games
        for i in range(16):
            slot = BracketSlot(
                slot_id=slot_id,
                round_num=2,
                region=["East", "West", "South", "Midwest"][i // 4],
                seed_a=0,
                seed_b=0,
                feeds_into=49 + i // 2
            )
            slots.append(slot)
            slot_id += 1
        
        # Round 3: 8 games (Sweet 16)
        for i in range(8):
            slot = BracketSlot(
                slot_id=slot_id,
                round_num=3,
                region=["East", "West", "South", "Midwest"][i // 2],
                seed_a=0,
                seed_b=0,
                feeds_into=57 + i // 2
            )
            slots.append(slot)
            slot_id += 1
        
        # Round 4: 4 games (Elite 8)
        for i in range(4):
            slot = BracketSlot(
                slot_id=slot_id,
                round_num=4,
                region=["East", "West", "South", "Midwest"][i],
                seed_a=0,
                seed_b=0,
                feeds_into=61 + i // 2
            )
            slots.append(slot)
            slot_id += 1
        
        # Round 5: 2 games (Final Four)
        for i in range(2):
            slot = BracketSlot(
                slot_id=slot_id,
                round_num=5,
                region="FinalFour",
                seed_a=0,
                seed_b=0,
                feeds_into=63
            )
            slots.append(slot)
            slot_id += 1
        
        # Round 6: 1 game (Championship)
        slot = BracketSlot(
            slot_id=63,
            round_num=6,
            region="FinalFour",
            seed_a=0,
            seed_b=0,
            feeds_into=0
        )
        slots.append(slot)
        
        bracket = BracketStructure(
            slots=slots,
            regions={"East": [], "West": [], "South": [], "Midwest": []},
            play_in_games=[]
        )
        
        # Mock config
        class MockConfig:
            random_seed = 42
        
        config = MockConfig()
        
        # Test construction
        complete_bracket = construct_candidate_bracket(
            teams, matchup_matrix, ownership_profiles, bracket, config, "balanced"
        )
        
        # Verify we have 63 picks
        self.assertEqual(len(complete_bracket.picks), 63, 
                        f"Expected 63 picks, got {len(complete_bracket.picks)}")
        
        # Verify we have picks for all 6 rounds
        rounds = {p.round_num for p in complete_bracket.picks}
        self.assertEqual(rounds, {1, 2, 3, 4, 5, 6}, 
                        f"Expected all 6 rounds, got {rounds}")
        
        # Verify correct number of picks per round
        picks_by_round = {}
        for pick in complete_bracket.picks:
            picks_by_round[pick.round_num] = picks_by_round.get(pick.round_num, 0) + 1
        
        self.assertEqual(picks_by_round[1], 32, "Round 1 should have 32 picks")
        self.assertEqual(picks_by_round[2], 16, "Round 2 should have 16 picks")
        self.assertEqual(picks_by_round[3], 8, "Round 3 should have 8 picks")
        self.assertEqual(picks_by_round[4], 4, "Round 4 should have 4 picks")
        self.assertEqual(picks_by_round[5], 2, "Round 5 should have 2 picks")
        self.assertEqual(picks_by_round[6], 1, "Round 6 should have 1 pick")
        
        # Verify champion is set
        self.assertIsNotNone(complete_bracket.champion)
        self.assertNotEqual(complete_bracket.champion, "Unknown")
        
        # Verify Final Four has 4 teams
        self.assertEqual(len(complete_bracket.final_four), 4, 
                        f"Final Four should have 4 teams, got {len(complete_bracket.final_four)}")
        
        # Verify Elite Eight has 8 teams
        self.assertEqual(len(complete_bracket.elite_eight), 8,
                        f"Elite Eight should have 8 teams, got {len(complete_bracket.elite_eight)}")
    
    def test_bracket_consistency(self):
        """Test that bracket picks are consistent (winners must have won prior rounds)."""
        from src.optimizer import construct_candidate_bracket
        from src.models import Team, OwnershipProfile
        
        # Use same setup as above
        teams = []
        for i in range(1, 9):  # Smaller bracket for speed
            team = Team(
                name=f"Team{i}",
                seed=(i - 1) % 4 + 1,
                region=["East", "West"][i // 5],
                kenpom_rank=i,
                adj_em=30.0 - i,
                adj_o=110.0,
                adj_d=95.0,
                adj_t=67.5,
                sos=10.0,
                wins=25,
                losses=5,
                conference="Big Ten",
                tournament_appearances=0,
                is_auto_bid=False,
                bracket_position=i
            )
            teams.append(team)
        
        matchup_matrix = {}
        for team_a in teams:
            matchup_matrix[team_a.name] = {}
            for team_b in teams:
                if team_a.name != team_b.name:
                    matchup_matrix[team_a.name][team_b.name] = 0.6
        
        ownership_profiles = []
        for team in teams:
            profile = OwnershipProfile(
                team=team.name,
                seed=team.seed,
                round_ownership={1: 1.0, 2: 0.5, 3: 0.25},
                leverage_by_round={1: 1.0, 2: 1.5, 3: 2.0},
                title_ownership=0.01,
                title_leverage=2.0
            )
            ownership_profiles.append(profile)
        
        # Simplified bracket: 4 R1 games → 2 R2 games → 1 R3 game
        slots = [
            BracketSlot(1, 1, "East", 1, 4, teams[0].name, teams[3].name, 5),
            BracketSlot(2, 1, "East", 2, 3, teams[1].name, teams[2].name, 5),
            BracketSlot(3, 1, "West", 1, 4, teams[4].name, teams[7].name, 6),
            BracketSlot(4, 1, "West", 2, 3, teams[5].name, teams[6].name, 6),
            BracketSlot(5, 2, "East", 0, 0, None, None, 7),
            BracketSlot(6, 2, "West", 0, 0, None, None, 7),
            BracketSlot(7, 3, "Final", 0, 0, None, None, 0),
        ]
        
        bracket = BracketStructure(
            slots=slots,
            regions={"East": [], "West": []},
            play_in_games=[]
        )
        
        class MockConfig:
            random_seed = 42
        
        config = MockConfig()
        
        complete_bracket = construct_candidate_bracket(
            teams, matchup_matrix, ownership_profiles, bracket, config, "balanced"
        )
        
        # Build a map of slot_id to winner
        winners = {p.slot_id: p.winner for p in complete_bracket.picks}
        
        # Verify consistency: champion must have won their semifinal
        champion = winners.get(7)
        self.assertIsNotNone(champion)
        
        # Champion must be winner of slot 5 or slot 6
        semifinal_winners = {winners.get(5), winners.get(6)}
        self.assertIn(champion, semifinal_winners, 
                     "Champion must have won their semifinal game")
        
        # Each R2 winner must have won an R1 game
        for slot in [5, 6]:
            r2_winner = winners.get(slot)
            # Find which R1 games feed into this slot
            r1_winners_for_this_slot = []
            for s in slots:
                if s.feeds_into == slot and s.round_num == 1:
                    r1_winner = winners.get(s.slot_id)
                    if r1_winner:
                        r1_winners_for_this_slot.append(r1_winner)
            
            self.assertIn(r2_winner, r1_winners_for_this_slot,
                         f"R2 winner {r2_winner} must have won an R1 game")
    
    def test_leverage_scores_not_all_one(self):
        """Test that leverage scores are calculated, not hardcoded to 1.0."""
        from src.optimizer import construct_candidate_bracket
        from src.models import Team, OwnershipProfile
        
        # Create 4 teams for 2 games -> 1 game bracket
        teams = [
            Team("Team1", 1, "East", 1, 25.0, 110, 90, 67, 10, 28, 3, "ACC", 3, True, 1),
            Team("Team2", 16, "East", 50, -5.0, 95, 105, 65, 5, 15, 15, "MEAC", 0, True, 2),
            Team("Team3", 8, "East", 25, 10.0, 105, 100, 66, 8, 20, 10, "Big Ten", 1, False, 3),
            Team("Team4", 9, "East", 30, 8.0, 104, 101, 66, 7, 19, 11, "Pac-12", 0, False, 4),
        ]
        
        matchup_matrix = {
            "Team1": {"Team2": 0.95, "Team3": 0.85, "Team4": 0.87},
            "Team2": {"Team1": 0.05, "Team3": 0.3, "Team4": 0.35},
            "Team3": {"Team1": 0.15, "Team2": 0.7, "Team4": 0.55},
            "Team4": {"Team1": 0.13, "Team2": 0.65, "Team3": 0.45}
        }
        
        # Set different ownership to create leverage variation
        ownership_profiles = [
            OwnershipProfile("Team1", 1, {1: 1.0, 2: 0.90, 3: 0.5}, {1: 1.0, 2: 1.2, 3: 1.5}, 0.3, 2.0),
            OwnershipProfile("Team2", 16, {1: 1.0, 2: 0.01, 3: 0.001}, {1: 1.0, 2: 5.0, 3: 10.0}, 0.001, 10.0),
            OwnershipProfile("Team3", 8, {1: 1.0, 2: 0.50, 3: 0.1}, {1: 1.0, 2: 1.8, 3: 3.0}, 0.05, 3.0),
            OwnershipProfile("Team4", 9, {1: 1.0, 2: 0.45, 3: 0.08}, {1: 1.0, 2: 2.0, 3: 3.5}, 0.04, 3.5),
        ]
        
        slots = [
            BracketSlot(1, 1, "East", 1, 16, "Team1", "Team2", 3),
            BracketSlot(2, 1, "East", 8, 9, "Team3", "Team4", 3),
            BracketSlot(3, 2, "East", 0, 0, None, None, 0),
        ]
        
        bracket = BracketStructure(slots, {"East": []}, [])
        
        class MockConfig:
            random_seed = 42
        
        complete_bracket = construct_candidate_bracket(
            teams, matchup_matrix, ownership_profiles, bracket, MockConfig(), "balanced"
        )
        
        # Check that not all leverage scores are 1.0
        leverage_scores = [p.leverage_score for p in complete_bracket.picks]
        
        # Should have at least one score that's not 1.0
        self.assertFalse(all(score == 1.0 for score in leverage_scores),
                        "Not all leverage scores should be 1.0")
        
        # Should have some variation (at least 2 different values)
        unique_scores = set(leverage_scores)
        self.assertGreater(len(unique_scores), 1,
                          f"Should have leverage variation, got: {leverage_scores}")


if __name__ == '__main__':
    unittest.main()
