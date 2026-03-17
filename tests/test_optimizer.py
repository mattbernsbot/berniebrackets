"""Test Monte Carlo simulation, scoring, and optimizer pure functions."""

import unittest
import random
from src.optimizer import (
    simulate_tournament,
    score_bracket,
    evaluate_bracket_in_pool,
    assign_confidence_tier,
    compute_upset_emv,
    generate_opponent_bracket,
    find_champion_path,
)
from src.models import BracketStructure, BracketSlot, Team, OwnershipProfile


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


class TestConfidenceTier(unittest.TestCase):
    """Test assign_confidence_tier boundary logic."""

    def test_lock(self):
        self.assertEqual(assign_confidence_tier(0.90), "\U0001f512 Lock")

    def test_lock_boundary(self):
        self.assertEqual(assign_confidence_tier(0.75), "\U0001f512 Lock")

    def test_lean(self):
        self.assertEqual(assign_confidence_tier(0.65), "\U0001f44d Lean")

    def test_lean_boundary(self):
        self.assertEqual(assign_confidence_tier(0.55), "\U0001f44d Lean")

    def test_gamble(self):
        self.assertEqual(assign_confidence_tier(0.40), "\U0001f3b2 Gamble")

    def test_gamble_just_below_lean(self):
        self.assertEqual(assign_confidence_tier(0.549), "\U0001f3b2 Gamble")


class TestComputeUpsetEMV(unittest.TestCase):
    """Test EMV formula: p_upset * (pts * fav_own) - p_chalk * (pts * (1 - fav_own))."""

    def _make_emv_inputs(self, p_upset, fav_ownership):
        """Build minimal inputs for compute_upset_emv."""
        fav = Team(name="Fav", seed=5)
        dog = Team(name="Dog", seed=12)
        matrix = {"Dog": {"Fav": p_upset}, "Fav": {"Dog": 1.0 - p_upset}}
        profile = OwnershipProfile(
            team="Fav", seed=5,
            round_ownership={1: fav_ownership},
            leverage_by_round={1: 1.0},
            title_ownership=0.01, title_leverage=1.0
        )
        bracket = BracketStructure(slots=[], regions={}, play_in_games=[])
        scoring = [10, 20, 40, 80, 160, 320]
        return 1, "Fav", "Dog", matrix, [profile], bracket, [fav, dog], 25, scoring, {}

    def test_positive_emv(self):
        """40% upset prob, 65% favorite ownership -> EMV = 0.50."""
        args = self._make_emv_inputs(0.40, 0.65)
        emv = compute_upset_emv(*args)
        # 0.40 * (10 * 0.65) - 0.60 * (10 * 0.35) = 2.6 - 2.1 = 0.5
        self.assertAlmostEqual(emv, 0.5, places=4)

    def test_negative_emv(self):
        """20% upset prob, 65% favorite ownership -> EMV = -1.50."""
        args = self._make_emv_inputs(0.20, 0.65)
        emv = compute_upset_emv(*args)
        # 0.20 * 6.5 - 0.80 * 3.5 = 1.3 - 2.8 = -1.5
        self.assertAlmostEqual(emv, -1.5, places=4)

    def test_floor_below_15_pct(self):
        """Upset prob < 15% should return -999."""
        args = self._make_emv_inputs(0.10, 0.65)
        emv = compute_upset_emv(*args)
        self.assertEqual(emv, -999)

    def test_at_15_pct_boundary(self):
        """Exactly 15% should NOT trigger floor (< 0.15 is the condition)."""
        args = self._make_emv_inputs(0.15, 0.65)
        emv = compute_upset_emv(*args)
        # 0.15 * 6.5 - 0.85 * 3.5 = 0.975 - 2.975 = -2.0
        self.assertAlmostEqual(emv, -2.0, places=4)

    def test_high_fav_ownership(self):
        """35% upset prob, 97% favorite ownership -> EMV = 3.20."""
        args = self._make_emv_inputs(0.35, 0.97)
        emv = compute_upset_emv(*args)
        # 0.35 * (10 * 0.97) - 0.65 * (10 * 0.03) = 3.395 - 0.195 = 3.2
        self.assertAlmostEqual(emv, 3.2, places=4)


def _make_test_bracket():
    """Build the shared 7-slot bracket used by path and opponent tests."""
    slots = []
    for i in range(1, 5):
        slots.append(BracketSlot(
            slot_id=i, round_num=1, region="East",
            seed_a=i, seed_b=9 - i,
            team_a=f"Team{i}", team_b=f"Team{9 - i}",
            feeds_into=5 + (i - 1) // 2
        ))
    for i in range(5, 7):
        slots.append(BracketSlot(
            slot_id=i, round_num=2, region="East",
            seed_a=0, seed_b=0, feeds_into=7
        ))
    slots.append(BracketSlot(
        slot_id=7, round_num=3, region="East",
        seed_a=0, seed_b=0, feeds_into=0
    ))
    return BracketStructure(slots=slots, regions={"East": []}, play_in_games=[])


class TestFindChampionPath(unittest.TestCase):
    """Test the find_champion_path helper."""

    def setUp(self):
        self.bracket = _make_test_bracket()

    def test_path_team1(self):
        # Slot 1 feeds_into 5, slot 5 feeds_into 7, slot 7 feeds_into 0
        self.assertEqual(find_champion_path("Team1", self.bracket), [1, 5, 7])

    def test_path_team3(self):
        # Slot 3 feeds_into 6, slot 6 feeds_into 7
        self.assertEqual(find_champion_path("Team3", self.bracket), [3, 6, 7])

    def test_unknown_team_returns_empty(self):
        self.assertEqual(find_champion_path("TeamX", self.bracket), [])


class TestGenerateOpponentBracket(unittest.TestCase):
    """Test generate_opponent_bracket produces valid, champion-consistent brackets."""

    def setUp(self):
        self.bracket = _make_test_bracket()

        # Title ownership: Team1=60%, Team2=25%, Team3=10%, Team4=5%
        # Team5-8 have no title ownership (eliminated before championship in most brackets)
        team_data = [
            ("Team1", 1, 0.60), ("Team2", 2, 0.25),
            ("Team3", 3, 0.10), ("Team4", 4, 0.05),
            ("Team8", 8, 0.0),  ("Team7", 7, 0.0),
            ("Team6", 6, 0.0),  ("Team5", 5, 0.0),
        ]
        self.ownership_profiles = [
            OwnershipProfile(
                team=name, seed=seed,
                round_ownership={2: 0.7 if seed <= 4 else 0.3, 3: title_own, 4: title_own * 0.5},
                leverage_by_round={2: 1.0, 3: 1.0, 4: 1.0},
                title_ownership=title_own,
                title_leverage=1.0,
            )
            for name, seed, title_own in team_data
        ]
        teams = ["Team1", "Team2", "Team3", "Team4", "Team5", "Team6", "Team7", "Team8"]
        self.matchup_matrix = {a: {b: 0.5 for b in teams if b != a} for a in teams}

    def test_champion_wins_all_path_slots(self):
        """The team in the championship slot must also appear in their R1 slot."""
        picks = generate_opponent_bracket(
            self.ownership_profiles, self.bracket, self.matchup_matrix, random.Random(42)
        )
        champion = picks.get(7)
        self.assertIsNotNone(champion)
        r1_slot = next(
            (s for s in self.bracket.slots
             if s.round_num == 1 and (s.team_a == champion or s.team_b == champion)),
            None,
        )
        self.assertIsNotNone(r1_slot, f"{champion} has no R1 slot")
        self.assertEqual(picks[r1_slot.slot_id], champion,
                         f"Champion {champion} not in R1 slot {r1_slot.slot_id}")

    def test_bracket_is_valid(self):
        """For every round 2+ slot, the winner must have been picked in a feeder slot."""
        picks = generate_opponent_bracket(
            self.ownership_profiles, self.bracket, self.matchup_matrix, random.Random(99)
        )
        slot_map = {s.slot_id: s for s in self.bracket.slots}
        for slot_id, winner in picks.items():
            if slot_map[slot_id].round_num < 2:
                continue
            feeders = [s for s in self.bracket.slots if s.feeds_into == slot_id]
            feeder_winners = {picks.get(f.slot_id) for f in feeders}
            self.assertIn(winner, feeder_winners,
                          msg=f"Slot {slot_id}: {winner} not in feeder winners {feeder_winners}")

    def test_champion_distribution(self):
        """Team1 (60% title_ownership) should win ~60% of sampled championships."""
        counts: dict[str, int] = {}
        for i in range(2000):
            picks = generate_opponent_bracket(
                self.ownership_profiles, self.bracket, self.matchup_matrix, random.Random(i)
            )
            champ = picks.get(7)
            if champ:
                counts[champ] = counts.get(champ, 0) + 1

        total = sum(counts.values())
        team1_freq = counts.get("Team1", 0) / total
        self.assertGreater(team1_freq, 0.52,
                           msg=f"Team1 freq {team1_freq:.2%} too low (expected ~60%)")
        self.assertLess(team1_freq, 0.68,
                        msg=f"Team1 freq {team1_freq:.2%} too high (expected ~60%)")
        # Team4 at 5% should be rare but present
        team4_freq = counts.get("Team4", 0) / total
        self.assertGreater(team4_freq, 0.01)
        self.assertLess(team4_freq, 0.12)


if __name__ == '__main__':
    unittest.main()
