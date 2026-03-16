"""Test statistical modeling functions."""

import unittest
from src.sharp import (
    adj_em_to_win_prob,
    apply_tournament_experience_modifier,
    apply_tempo_mismatch_modifier,
    apply_conference_momentum_modifier,
    apply_seed_prior,
    compute_matchup_probability,
    compute_upset_propensity_score,
    apply_upset_propensity_modifier
)
from src.models import Team


class TestSharp(unittest.TestCase):
    """Test win probability calculations and modifiers."""
    
    def test_adj_em_equal_teams(self):
        """Test that equal teams give 50% probability."""
        prob = adj_em_to_win_prob(10.0, 10.0)
        self.assertAlmostEqual(prob, 0.5, delta=0.01)
    
    def test_adj_em_favorite(self):
        """Test that strong favorite has high probability."""
        # 1 seed (~+28) vs 16 seed (~-15) = +43 difference
        prob = adj_em_to_win_prob(28.0, -15.0)
        self.assertGreater(prob, 0.95)
        self.assertLessEqual(prob, 0.99)  # Should be clamped
    
    def test_adj_em_moderate_favorite(self):
        """Test moderate favorite."""
        # +10 difference should be around 70-90%
        prob = adj_em_to_win_prob(15.0, 5.0)
        self.assertGreater(prob, 0.70)
        self.assertLess(prob, 0.95)
    
    def test_adj_em_clamping(self):
        """Test that probabilities are clamped to [0.01, 0.99]."""
        # Extreme cases
        prob_high = adj_em_to_win_prob(50.0, -50.0)
        self.assertLessEqual(prob_high, 0.99)
        
        prob_low = adj_em_to_win_prob(-50.0, 50.0)
        self.assertGreaterEqual(prob_low, 0.01)
    
    def test_experience_modifier(self):
        """Test tournament experience modifier."""
        base_prob = 0.60
        
        # Team A has 3 appearances, Team B has 0
        modified = apply_tournament_experience_modifier(base_prob, 3, 0)
        self.assertGreater(modified, base_prob)
        
        # Reverse
        modified2 = apply_tournament_experience_modifier(base_prob, 0, 3)
        self.assertLess(modified2, base_prob)
        
        # Equal experience - no change
        modified3 = apply_tournament_experience_modifier(base_prob, 2, 2)
        self.assertAlmostEqual(modified3, base_prob, delta=0.001)
    
    def test_tempo_mismatch_modifier(self):
        """Test tempo mismatch modifier for slow defensive teams."""
        base_prob = 0.55
        
        # Team A is slow defensive, Team B is not
        modified = apply_tempo_mismatch_modifier(base_prob, 62.0, 72.0, 92.0, 100.0)
        self.assertGreater(modified, base_prob)
        
        # Neither team qualifies
        modified2 = apply_tempo_mismatch_modifier(base_prob, 70.0, 72.0, 100.0, 100.0)
        self.assertAlmostEqual(modified2, base_prob, delta=0.001)
    
    def test_conference_momentum_modifier(self):
        """Test conference momentum for auto-bid teams."""
        base_prob = 0.60
        
        team_a = Team(
            name="Duke",
            conference="ACC",
            is_auto_bid=True
        )
        team_b = Team(
            name="Kansas",
            conference="Big 12",
            is_auto_bid=False
        )
        
        modified = apply_conference_momentum_modifier(base_prob, team_a, team_b)
        self.assertGreater(modified, base_prob)
    
    def test_seed_prior_blending(self):
        """Test seed prior blending with historical data."""
        # 1 seed vs 16 seed
        model_prob = 0.90
        blended = apply_seed_prior(model_prob, 1, 16)
        
        # Should blend with historical ~99.3% win rate
        # Result should be between model and historical
        self.assertGreater(blended, model_prob)
        self.assertLess(blended, 0.995)
    
    def test_compute_matchup_probability_integration(self):
        """Test full matchup computation with all modifiers."""
        team_a = Team(
            name="Duke",
            seed=1,
            adj_em=28.0,
            adj_o=120.0,
            adj_d=92.0,
            adj_t=70.0,
            conference="ACC",
            tournament_appearances=3,
            is_auto_bid=True
        )
        
        team_b = Team(
            name="Norfolk State",
            seed=16,
            adj_em=-10.0,
            adj_o=100.0,
            adj_d=110.0,
            adj_t=68.0,
            conference="MEAC",
            tournament_appearances=0,
            is_auto_bid=True
        )
        
        matchup = compute_matchup_probability(team_a, team_b)
        
        self.assertEqual(matchup.team_a, "Duke")
        self.assertEqual(matchup.team_b, "Norfolk State")
        self.assertGreater(matchup.win_prob_a, 0.90)
        self.assertLessEqual(matchup.win_prob_a, 0.99)
        self.assertIsInstance(matchup.modifiers_applied, list)
    
    def test_upset_propensity_score_neutral(self):
        """Test UPS for neutral matchup (no upset indicators)."""
        favorite = Team(
            name="Kentucky", seed=5, region="East", kenpom_rank=20,
            adj_em=14.0, adj_o=115.0, adj_d=100.0, adj_t=68.0,
            sos=5.0, wins=25, losses=8, conference="SEC",
            tournament_appearances=0, is_auto_bid=False, bracket_position=19
        )
        underdog = Team(
            name="Murray State", seed=12, region="East", kenpom_rank=45,
            adj_em=8.0, adj_o=110.0, adj_d=102.0, adj_t=68.0,
            sos=1.0, wins=28, losses=5, conference="OVC",
            tournament_appearances=0, is_auto_bid=True, bracket_position=19
        )
        
        ups = compute_upset_propensity_score(favorite, underdog)
        
        # Should be around 0.5 (neutral) or slightly above due to small gap
        self.assertGreater(ups, 0.3)
        self.assertLess(ups, 0.7)
    
    def test_upset_propensity_score_high(self):
        """Test UPS for strong upset candidate (slow defensive underdog, small gap)."""
        favorite = Team(
            name="North Carolina", seed=5, region="East", kenpom_rank=18,
            adj_em=16.0, adj_o=118.0, adj_d=102.0, adj_t=72.0,  # Fast tempo
            sos=6.0, wins=26, losses=7, conference="ACC",
            tournament_appearances=0, is_auto_bid=False, bracket_position=19
        )
        underdog = Team(
            name="VCU", seed=12, region="East", kenpom_rank=35,
            adj_em=12.0, adj_o=105.0, adj_d=92.0, adj_t=62.0,  # Slow defensive
            sos=3.0, wins=29, losses=4, conference="A-10",
            tournament_appearances=2, is_auto_bid=True, bracket_position=19
        )
        
        ups = compute_upset_propensity_score(favorite, underdog)
        
        # Should be high due to tempo mismatch, experience, small AdjEM gap, auto-bid
        self.assertGreater(ups, 0.6)
    
    def test_upset_propensity_modifier_neutral(self):
        """Test UPS modifier with neutral score doesn't change probability much."""
        base_prob = 0.65  # 5-seed favorite
        ups = 0.5  # Neutral
        
        adjusted = apply_upset_propensity_modifier(base_prob, ups, 5, 12)
        
        # UPS=0.5 should result in no change
        self.assertAlmostEqual(adjusted, base_prob, delta=0.01)
    
    def test_upset_propensity_modifier_high_upset_risk(self):
        """Test UPS modifier with high score increases underdog chances."""
        base_prob = 0.70  # 5-seed favorite
        ups = 0.85  # High upset propensity
        
        adjusted = apply_upset_propensity_modifier(base_prob, ups, 5, 12)
        
        # High UPS should reduce favorite's probability
        self.assertLess(adjusted, base_prob)
        self.assertLess(adjusted, 0.65)  # Should drop noticeably
    
    def test_adj_em_kappa_13(self):
        """Test that κ=13.0 compresses probabilities vs κ=11.5."""
        # With ΔEM of 10, κ=13.0 with reduced variance adjustment
        # The formula is 1/(1+10^(-ΔEM/13)) which for ΔEM=10 gives ~84%
        # (vs ~87% with κ=11.5)
        prob = adj_em_to_win_prob(15.0, 5.0)

        # Should be slightly compressed but still strong favorite
        self.assertGreater(prob, 0.80)
        self.assertLess(prob, 0.90)

    def test_matchup_antisymmetry_1v16(self):
        """P(1-seed beats 16) + P(16-seed beats 1) == 1.0."""
        a = Team(name="Fav", seed=1, adj_em=28.0)
        b = Team(name="Dog", seed=16, adj_em=-10.0)
        m_ab = compute_matchup_probability(a, b)
        m_ba = compute_matchup_probability(b, a)
        self.assertAlmostEqual(m_ab.win_prob_a + m_ba.win_prob_a, 1.0, places=6)

    def test_matchup_antisymmetry_5v12(self):
        """P(5-seed beats 12) + P(12-seed beats 5) == 1.0."""
        a = Team(name="Five", seed=5, adj_em=14.0)
        b = Team(name="Twelve", seed=12, adj_em=6.0)
        m_ab = compute_matchup_probability(a, b)
        m_ba = compute_matchup_probability(b, a)
        self.assertAlmostEqual(m_ab.win_prob_a + m_ba.win_prob_a, 1.0, places=6)

if __name__ == '__main__':
    unittest.main()
