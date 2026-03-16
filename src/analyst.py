"""Output generation module - creates human-readable bracket analysis.

Generates markdown reports and ASCII bracket visualizations.
"""

import logging

from src.models import CompleteBracket, Team, OwnershipProfile, AggregateResults, BracketStructure
from src.utils import save_json, ensure_dir

logger = logging.getLogger("bracket_optimizer")


def assign_confidence_tier(win_prob: float) -> str:
    """Assign a confidence tier emoji to a pick.
    
    🔒 Lock: win_prob ≥ 0.75 (heavy favorite)
    👍 Lean: 0.55 ≤ win_prob < 0.75 (model-favored)
    🎲 Gamble: win_prob < 0.55 (upset pick)
    
    Args:
        win_prob: Win probability for the picked team.
    
    Returns:
        One of "🔒 Lock", "👍 Lean", "🎲 Gamble".
    """
    if win_prob >= 0.75:
        return "🔒 Lock"
    elif win_prob >= 0.55:
        return "👍 Lean"
    else:
        return "🎲 Gamble"


def explain_pick(team_name: str, opponent_name: str, team: Team, leverage: float, ownership: float) -> str:
    """Generate a human-readable explanation for a pick.
    
    Args:
        team_name: Name of picked team.
        opponent_name: Name of opponent.
        team: Full team data for the picked team.
        leverage: Leverage score for this pick.
        ownership: Public ownership percentage.
    
    Returns:
        Markdown-formatted explanation paragraph.
    """
    explanation = f"**{team_name}** over {opponent_name}"
    
    if leverage > 1.5:
        explanation += f" — High value pick (Leverage: {leverage:.2f}x). "
        explanation += f"Public ownership: {ownership*100:.1f}%, "
        explanation += f"but strong metrics (AdjEM: {team.adj_em:+.1f}, KenPom #{team.kenpom_rank})."
    elif team.seed > 8:
        explanation += f" — Contrarian upset pick. "
        explanation += f"{team.seed}-seed with solid efficiency (AdjEM: {team.adj_em:+.1f})."
    else:
        explanation += f" — Chalk pick. {team.seed}-seed favorite."
    
    return explanation


def generate_analysis_report(bracket: CompleteBracket, teams: list[Team], ownership_profiles: list[OwnershipProfile], matchup_matrix: dict[str, dict[str, float]]) -> str:
    """Generate the full markdown analysis report.
    
    Sections:
    - Executive Summary
    - Key Differentiators
    - Round-by-Round Breakdown
    - Risk Assessment
    
    Args:
        bracket: The optimal bracket.
        teams: All team data.
        ownership_profiles: Ownership/leverage data.
        matchup_matrix: For win probabilities.
    
    Returns:
        Complete markdown report as string.
    """
    lines = []
    
    # Header
    lines.append("# 🏀 March Madness Bracket Optimizer — Analysis Report")
    lines.append("")
    
    # Executive Summary
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"**Champion:** {bracket.champion}")
    lines.append(f"**Final Four:** {', '.join(bracket.final_four)}")
    lines.append(f"**Elite Eight:** {', '.join(bracket.elite_eight)}")
    lines.append("")
    lines.append(f"**P(1st place):** {bracket.p_first_place:.1%}")
    lines.append(f"**P(Top 3):** {bracket.p_top_three:.1%}")
    lines.append(f"**Expected finish:** {bracket.expected_finish:.1f}")
    lines.append(f"**Expected score:** {bracket.expected_score:.0f} points")
    lines.append("")
    
    # Strategy label
    lines.append(f"**Strategy:** {bracket.label}")
    lines.append("")
    
    # Build team lookup
    team_map = {t.name: t for t in teams}
    ownership_map = {p.team: p for p in ownership_profiles}
    
    # Key Differentiators
    lines.append("## Key Differentiators")
    lines.append("")
    lines.append("These picks separate your bracket from the field:")
    lines.append("")
    
    # BUG FIX #3: Pool-aware leverage produces values like 0.04-0.10, not 1.5+
    # Adjusted threshold from 1.5 to 0.02 to match actual scale
    # Alternative: use top N picks regardless of threshold
    high_leverage_picks = [p for p in bracket.picks if p.leverage_score > 0.02]
    high_leverage_picks.sort(key=lambda x: x.leverage_score, reverse=True)
    
    # Show top 8-12 differentiators if we have them
    display_count = min(12, len(high_leverage_picks))
    
    for idx, pick in enumerate(high_leverage_picks[:display_count], 1):
        team = team_map.get(pick.winner)
        ownership = ownership_map.get(pick.winner)
        
        if team and ownership:
            round_name = ["R64", "R32", "S16", "E8", "F4", "CHAMP"][pick.round_num - 1]
            lines.append(f"{idx}. **{pick.winner}** to {round_name} "
                        f"(Leverage: {pick.leverage_score:.4f}, "
                        f"Seed: {team.seed}, "
                        f"Ownership: {ownership.round_ownership.get(pick.round_num, 0)*100:.1f}%)")
    
    if not high_leverage_picks:
        lines.append("_(No high-leverage picks found — this is a chalk-heavy bracket)_")
    
    lines.append("")
    
    # Round breakdown
    lines.append("## Round-by-Round Breakdown")
    lines.append("")
    
    picks_by_round = {}
    for pick in bracket.picks:
        if pick.round_num not in picks_by_round:
            picks_by_round[pick.round_num] = []
        picks_by_round[pick.round_num].append(pick)
    
    round_names = {
        1: "Round of 64",
        2: "Round of 32",
        3: "Sweet 16",
        4: "Elite 8",
        5: "Final Four",
        6: "Championship"
    }
    
    for round_num in sorted(picks_by_round.keys()):
        if round_num == 0:
            continue  # Skip play-in for now
        
        lines.append(f"### {round_names.get(round_num, f'Round {round_num}')}")
        lines.append("")
        
        round_picks = picks_by_round[round_num]
        
        # Show upsets and key picks
        upsets = [p for p in round_picks if p.is_upset]
        if upsets:
            lines.append(f"**Upsets:** {len(upsets)}")
            for pick in upsets:
                team = team_map.get(pick.winner)
                if team:
                    lines.append(f"- {pick.winner} ({team.seed}-seed) — {pick.confidence}")
        
        lines.append("")
    
    # Risk Assessment
    lines.append("## Risk Assessment")
    lines.append("")
    lines.append("**What needs to go right:**")
    lines.append(f"- {bracket.champion} must reach the championship game")
    lines.append(f"- At least 2-3 Final Four teams must advance as predicted")
    lines.append("")
    lines.append("**Biggest vulnerabilities:**")
    
    # Find riskiest picks (lowest win prob)
    risky_picks = [p for p in bracket.picks if p.confidence == "🎲 Gamble"]
    if risky_picks:
        lines.append(f"- {len(risky_picks)} gamble picks that could bust early")
    
    lines.append("")
    
    return "\n".join(lines)


def generate_ascii_bracket(bracket: CompleteBracket, bracket_structure: BracketStructure) -> str:
    """Generate an ASCII-art bracket visualization.
    
    Renders a text-based bracket with team names, seeds, and round progression.
    Shows matchup pairings and winners advancing through rounds.
    
    Args:
        bracket: The bracket to render.
        bracket_structure: For positional layout.
    
    Returns:
        ASCII bracket as multi-line string.
    """
    lines = []
    
    lines.append("=" * 100)
    lines.append(" " * 35 + "MARCH MADNESS BRACKET")
    lines.append("=" * 100)
    lines.append("")
    
    # Build pick lookup and team lookup
    pick_map = {p.slot_id: p for p in bracket.picks}
    slot_map = {s.slot_id: s for s in bracket_structure.slots}
    
    # Group picks by round for easier navigation
    picks_by_round = {}
    for pick in bracket.picks:
        if pick.round_num not in picks_by_round:
            picks_by_round[pick.round_num] = []
        picks_by_round[pick.round_num].append(pick)
    
    # Round names
    round_names = {
        1: "ROUND OF 64",
        2: "ROUND OF 32", 
        3: "SWEET 16",
        4: "ELITE 8",
        5: "FINAL FOUR",
        6: "CHAMPIONSHIP"
    }
    
    # Display by round showing matchups
    for round_num in sorted([r for r in picks_by_round.keys() if r > 0]):
        lines.append("")
        lines.append(f"{'─' * 40} {round_names.get(round_num, f'ROUND {round_num}')} {'─' * 40}")
        lines.append("")
        
        round_picks = picks_by_round[round_num]
        
        # For Round 1, show initial matchups
        if round_num == 1:
            # Show who plays who
            for pick in sorted(round_picks, key=lambda p: p.slot_id):
                slot = slot_map.get(pick.slot_id)
                if slot and slot.team_a and slot.team_b:
                    winner_marker_a = " ✓" if pick.winner == slot.team_a else ""
                    winner_marker_b = " ✓" if pick.winner == slot.team_b else ""
                    
                    seed_a = f"({slot.seed_a})" if slot.seed_a else ""
                    seed_b = f"({slot.seed_b})" if slot.seed_b else ""
                    
                    upset = " [UPSET]" if pick.is_upset else ""
                    
                    lines.append(f"  {slot.team_a:25s} {seed_a:4s}{winner_marker_a}")
                    lines.append(f"  {slot.team_b:25s} {seed_b:4s}{winner_marker_b}")
                    lines.append(f"    → Winner: {pick.winner} {pick.confidence}{upset}")
                    lines.append("")
        else:
            # For later rounds, show who advanced and who they play
            for pick in sorted(round_picks, key=lambda p: p.slot_id):
                slot = slot_map.get(pick.slot_id)
                if not slot:
                    continue
                
                # Find the teams feeding into this game
                feeder_teams = []
                for prev_slot_id, prev_pick in pick_map.items():
                    prev_slot = slot_map.get(prev_slot_id)
                    if prev_slot and prev_slot.feeds_into == slot.slot_id:
                        feeder_teams.append(prev_pick.winner)
                
                if len(feeder_teams) == 2:
                    winner_marker_a = " ✓" if pick.winner == feeder_teams[0] else ""
                    winner_marker_b = " ✓" if pick.winner == feeder_teams[1] else ""
                    
                    upset = " [UPSET]" if pick.is_upset else ""
                    
                    lines.append(f"  {feeder_teams[0]:30s}{winner_marker_a}")
                    lines.append(f"      vs")
                    lines.append(f"  {feeder_teams[1]:30s}{winner_marker_b}")
                    lines.append(f"    → Winner: {pick.winner} {pick.confidence}{upset}")
                    lines.append("")
                else:
                    # Fallback if we can't determine matchup
                    lines.append(f"  Winner: {pick.winner} {pick.confidence}")
                    lines.append("")
    
    # Summary
    lines.append("")
    lines.append("=" * 100)
    lines.append(f"CHAMPION: {bracket.champion}")
    lines.append(f"FINAL FOUR: {', '.join(bracket.final_four)}")
    lines.append(f"ELITE EIGHT: {', '.join(bracket.elite_eight)}")
    lines.append("")
    lines.append(f"Expected Score: {bracket.expected_score:.0f} points")
    lines.append(f"P(1st Place): {bracket.p_first_place:.1%}")
    lines.append(f"Expected Finish: {bracket.expected_finish:.1f}")
    lines.append("=" * 100)
    
    return "\n".join(lines)


def generate_all_output(brackets: list[CompleteBracket], teams: list[Team], ownership_profiles: list[OwnershipProfile], matchup_matrix: dict[str, dict[str, float]], bracket_structure: BracketStructure, config) -> None:
    """Run the full output pipeline.
    
    Generates and saves:
    - output/analysis.md: Full analysis report
    - output/bracket.txt: ASCII bracket visualization
    - output/summary.json: Machine-readable summary
    
    Args:
        brackets: Top 3 brackets [optimal, safe, aggressive].
        teams: All team data.
        ownership_profiles: Ownership data.
        matchup_matrix: Win probability matrix.
        bracket_structure: Bracket layout.
        config: Configuration.
    """
    logger.info("=== Generating output files ===")
    
    ensure_dir(config.output_dir)
    
    # Use optimal bracket for main output
    optimal = brackets[0]
    
    # Generate analysis report
    analysis = generate_analysis_report(optimal, teams, ownership_profiles, matchup_matrix)
    analysis_file = f"{config.output_dir}/analysis.md"
    with open(analysis_file, 'w', encoding='utf-8') as f:
        f.write(analysis)
    logger.info(f"Saved analysis to {analysis_file}")
    
    # Generate ASCII bracket
    ascii_bracket = generate_ascii_bracket(optimal, bracket_structure)
    bracket_file = f"{config.output_dir}/bracket.txt"
    with open(bracket_file, 'w', encoding='utf-8') as f:
        f.write(ascii_bracket)
    logger.info(f"Saved ASCII bracket to {bracket_file}")
    
    # Generate JSON summary
    summary = {
        "optimal_bracket": optimal.to_dict(),
        "alternates": [b.to_dict() for b in brackets[1:]],
        "champion": optimal.champion,
        "final_four": optimal.final_four,
        "p_first_place": optimal.p_first_place,
        "expected_score": optimal.expected_score
    }
    summary_file = f"{config.output_dir}/summary.json"
    save_json(summary, summary_file)
    logger.info(f"Saved summary to {summary_file}")
    
    logger.info("=== Output generation complete ===")
