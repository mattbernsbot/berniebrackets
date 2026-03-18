"""Output generation module - creates human-readable bracket analysis.

Generates markdown reports, ASCII bracket visualizations, JSON summaries,
and an interactive HTML bracket viewer.
"""

import json
import logging
from collections import Counter

from src.models import CompleteBracket, Team, OwnershipProfile, AggregateResults, BracketStructure
from src.utils import save_json, ensure_dir

logger = logging.getLogger("bracket_optimizer")


def assign_confidence_tier(win_prob: float) -> str:
    """Assign a confidence tier emoji to a pick.

    🔒 Lock: win_prob >= 0.75 (heavy favorite)
    👍 Lean: 0.55 <= win_prob < 0.75 (model-favored)
    🎲 Gamble: win_prob < 0.55 (upset pick)
    """
    if win_prob >= 0.75:
        return "🔒 Lock"
    elif win_prob >= 0.55:
        return "👍 Lean"
    else:
        return "🎲 Gamble"


def explain_pick(team_name: str, opponent_name: str, team: Team, leverage: float, ownership: float) -> str:
    """Generate a human-readable explanation for a pick."""
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


# ============================================================================
# CROSS-BRACKET STATISTICS
# ============================================================================

def compute_cross_bracket_stats(brackets: list[CompleteBracket]) -> dict:
    """Compute aggregate statistics across all brackets.

    Returns dict with:
        champion_dist: list of (team, count) sorted by count desc
        ff_freq: list of (team, count) sorted by count desc
        e8_freq: list of (team, count) sorted by count desc
        consensus_picks: list of (slot_id, round_num, team, pct) for picks in >90% of brackets
        upset_consensus: list of (team, round_num, count, pct) for upsets in >50% of brackets
        pick_by_slot: dict[slot_id -> Counter of team picks]
    """
    n = len(brackets)
    if n == 0:
        return {}

    # Champion distribution
    champ_counts = Counter(b.champion for b in brackets)
    champion_dist = champ_counts.most_common()

    # Final Four frequency
    ff_counts = Counter()
    for b in brackets:
        for team in b.final_four:
            ff_counts[team] += 1
    ff_freq = ff_counts.most_common()

    # Elite Eight frequency
    e8_counts = Counter()
    for b in brackets:
        for team in b.elite_eight:
            e8_counts[team] += 1
    e8_freq = e8_counts.most_common()

    # Per-slot pick distribution
    pick_by_slot = {}
    for b in brackets:
        for pick in b.picks:
            if pick.slot_id not in pick_by_slot:
                pick_by_slot[pick.slot_id] = {"counter": Counter(), "round_num": pick.round_num}
            pick_by_slot[pick.slot_id]["counter"][pick.winner] += 1

    # Consensus picks (>90% agreement)
    consensus_picks = []
    for slot_id, info in pick_by_slot.items():
        top_team, top_count = info["counter"].most_common(1)[0]
        pct = top_count / n
        if pct >= 0.9:
            consensus_picks.append((slot_id, info["round_num"], top_team, pct))
    consensus_picks.sort(key=lambda x: (-x[1], -x[3]))  # later rounds first, then by pct

    # Upset consensus (upsets in >50% of brackets)
    upset_counts = Counter()  # (team, round_num) -> count
    for b in brackets:
        for pick in b.picks:
            if pick.is_upset:
                upset_counts[(pick.winner, pick.round_num)] += 1
    upset_consensus = []
    for (team, round_num), count in upset_counts.items():
        pct = count / n
        if pct >= 0.5:
            upset_consensus.append((team, round_num, count, pct))
    upset_consensus.sort(key=lambda x: (-x[1], -x[3]))  # later rounds first

    return {
        "champion_dist": champion_dist,
        "ff_freq": ff_freq,
        "e8_freq": e8_freq,
        "consensus_picks": consensus_picks,
        "upset_consensus": upset_consensus,
        "pick_by_slot": pick_by_slot,
        "n": n,
    }


# ============================================================================
# ANALYSIS REPORT (MARKDOWN)
# ============================================================================

def generate_analysis_report(all_brackets: list[CompleteBracket], teams: list[Team],
                             ownership_profiles: list[OwnershipProfile],
                             matchup_matrix: dict[str, dict[str, float]]) -> str:
    """Generate a comprehensive markdown analysis report using all evaluated brackets."""
    lines = []
    team_map = {t.name: t for t in teams}
    ownership_map = {p.team: p for p in ownership_profiles}
    n = len(all_brackets)

    optimal = next((b for b in all_brackets if b.label == "optimal"), all_brackets[0])
    stats = compute_cross_bracket_stats(all_brackets)

    round_labels = {1: "R64", 2: "R32", 3: "S16", 4: "E8", 5: "F4", 6: "CHAMP"}

    # ── Header ──
    lines.append("# March Madness Bracket Optimizer -- Analysis Report")
    lines.append("")

    # ── Executive Summary ──
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"**Champion:** {optimal.champion}")
    lines.append(f"**Final Four:** {', '.join(optimal.final_four)}")
    lines.append(f"**Elite Eight:** {', '.join(optimal.elite_eight)}")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| P(1st place) | {optimal.p_first_place:.1%} |")
    lines.append(f"| P(Top 3) | {optimal.p_top_three:.1%} |")
    lines.append(f"| Expected finish | {optimal.expected_finish:.1f} |")
    lines.append(f"| Expected score | {optimal.expected_score:.0f} pts |")
    lines.append(f"| Brackets evaluated | {n} |")
    lines.append(f"| Strategy | {optimal.label} |")
    lines.append("")

    # ── Cross-Bracket Analysis ──
    lines.append("## Cross-Bracket Analysis")
    lines.append("")
    lines.append(f"Aggregate view across all {n} evaluated brackets.")
    lines.append("")

    # Champion distribution
    lines.append("### Champion Distribution")
    lines.append("")
    lines.append("| Team | Seed | Count | % of Brackets |")
    lines.append("|------|------|-------|---------------|")
    for team_name, count in stats["champion_dist"]:
        team = team_map.get(team_name)
        seed = team.seed if team else "?"
        lines.append(f"| {team_name} | {seed} | {count}/{n} | {count/n:.0%} |")
    lines.append("")

    # Final Four frequency
    lines.append("### Final Four Frequency")
    lines.append("")
    lines.append("| Team | Seed | Appearances | % |")
    lines.append("|------|------|-------------|---|")
    for team_name, count in stats["ff_freq"][:12]:
        team = team_map.get(team_name)
        seed = team.seed if team else "?"
        lines.append(f"| {team_name} | {seed} | {count}/{n} | {count/n:.0%} |")
    lines.append("")

    # Consensus upsets
    if stats["upset_consensus"]:
        lines.append("### Consensus Upsets")
        lines.append("")
        lines.append("Upsets the model picks in >50% of brackets -- these are real.")
        lines.append("")
        lines.append("| Team | Round | Frequency | % |")
        lines.append("|------|-------|-----------|---|")
        for team_name, round_num, count, pct in stats["upset_consensus"]:
            team = team_map.get(team_name)
            seed_str = f" ({team.seed})" if team else ""
            lines.append(f"| {team_name}{seed_str} | {round_labels.get(round_num, f'R{round_num}')} | {count}/{n} | {pct:.0%} |")
        lines.append("")

    # ── All Brackets Comparison ──
    lines.append("## All Brackets")
    lines.append("")
    lines.append("| # | Label | Champion | P(1st) | P(Top 3) | E[Score] | E[Finish] | Upsets |")
    lines.append("|---|-------|----------|--------|----------|----------|-----------|--------|")
    for i, b in enumerate(all_brackets, 1):
        upset_count = sum(1 for p in b.picks if p.is_upset)
        tag = ""
        if b.label in ("optimal", "safe_alternate", "aggressive_alternate"):
            tag = f" **[{b.label.upper()}]**"
        lines.append(
            f"| {i} | {b.label}{tag} | {b.champion} | {b.p_first_place:.1%} "
            f"| {b.p_top_three:.1%} | {b.expected_score:.0f} | {b.expected_finish:.1f} "
            f"| {upset_count} |"
        )
    lines.append("")

    # ── Model vs Public ──
    lines.append("## Model vs Public Ownership")
    lines.append("")
    lines.append("Top teams by model title probability vs public championship ownership.")
    lines.append("")
    lines.append("| Team | Seed | Model Title % | Public Title % | Leverage |")
    lines.append("|------|------|---------------|----------------|----------|")

    # Collect teams that appear as champion in any bracket, sorted by frequency
    champ_teams = [team_name for team_name, _ in stats["champion_dist"]]
    # Also add any team with high title ownership
    for profile in sorted(ownership_profiles, key=lambda p: p.title_ownership, reverse=True)[:10]:
        if profile.team not in champ_teams:
            champ_teams.append(profile.team)

    for team_name in champ_teams[:12]:
        team = team_map.get(team_name)
        profile = ownership_map.get(team_name)
        if not team or not profile:
            continue
        # Approximate model title prob from champion distribution
        champ_count = dict(stats["champion_dist"]).get(team_name, 0)
        model_pct = champ_count / n if n > 0 else 0
        pub_pct = profile.title_ownership
        leverage = profile.title_leverage if profile.title_leverage else (model_pct / pub_pct if pub_pct > 0 else 0)
        lines.append(f"| {team_name} | {team.seed} | {model_pct:.1%} | {pub_pct:.1%} | {leverage:.2f} |")
    lines.append("")

    # ── Key Differentiators (optimal bracket) ──
    lines.append("## Key Differentiators (Optimal Bracket)")
    lines.append("")
    lines.append("High-leverage picks that separate the optimal bracket from the field:")
    lines.append("")

    high_leverage_picks = [p for p in optimal.picks if p.leverage_score > 0.02]
    high_leverage_picks.sort(key=lambda x: x.leverage_score, reverse=True)
    display_count = min(12, len(high_leverage_picks))

    for idx, pick in enumerate(high_leverage_picks[:display_count], 1):
        team = team_map.get(pick.winner)
        ownership = ownership_map.get(pick.winner)
        if team and ownership:
            rnd = round_labels.get(pick.round_num, f"R{pick.round_num}")
            own_pct = ownership.round_ownership.get(pick.round_num, 0) * 100
            # How many of our brackets make this same pick at this slot?
            slot_info = stats["pick_by_slot"].get(pick.slot_id, {})
            slot_counter = slot_info.get("counter", Counter()) if isinstance(slot_info, dict) else Counter()
            bracket_pct = slot_counter.get(pick.winner, 0) / n if n > 0 else 0
            lines.append(
                f"{idx}. **{pick.winner}** to {rnd} -- "
                f"Leverage: {pick.leverage_score:.4f}, "
                f"Seed: {team.seed}, "
                f"Public: {own_pct:.1f}%, "
                f"In {bracket_pct:.0%} of our brackets"
            )

    if not high_leverage_picks:
        lines.append("_(No high-leverage picks found -- chalk-heavy bracket)_")
    lines.append("")

    # ── Round-by-Round Breakdown (optimal) ──
    lines.append("## Round-by-Round Breakdown (Optimal)")
    lines.append("")

    picks_by_round = {}
    for pick in optimal.picks:
        picks_by_round.setdefault(pick.round_num, []).append(pick)

    round_names = {1: "Round of 64", 2: "Round of 32", 3: "Sweet 16",
                   4: "Elite 8", 5: "Final Four", 6: "Championship"}

    for round_num in sorted(picks_by_round.keys()):
        if round_num == 0:
            continue
        round_picks = picks_by_round[round_num]
        upsets = [p for p in round_picks if p.is_upset]
        lines.append(f"### {round_names.get(round_num, f'Round {round_num}')}")
        lines.append("")
        if upsets:
            lines.append(f"**Upsets:** {len(upsets)}")
            for pick in upsets:
                team = team_map.get(pick.winner)
                if team:
                    lines.append(f"- {pick.winner} ({team.seed}-seed) -- {pick.confidence}")
        else:
            lines.append("No upsets.")
        lines.append("")

    # ── Risk Assessment ──
    lines.append("## Risk Assessment")
    lines.append("")

    # Champion dependency
    champ_picks = [p for p in optimal.picks if p.winner == optimal.champion]
    scoring = [10, 20, 40, 80, 160, 320]
    champ_points = sum(scoring[p.round_num - 1] for p in champ_picks if 1 <= p.round_num <= 6)
    total_points = optimal.expected_score if optimal.expected_score > 0 else 1
    champ_dep = champ_points / total_points * 100

    lines.append(f"**Champion dependency:** {optimal.champion} path accounts for "
                 f"{champ_points} potential points ({champ_dep:.0f}% of expected score)")
    lines.append("")

    # Gamble picks by round
    lines.append("**Gamble picks by round:**")
    for round_num in sorted(picks_by_round.keys()):
        if round_num == 0:
            continue
        gambles = [p for p in picks_by_round[round_num] if p.confidence == "\U0001f3b2 Gamble"]
        total = len(picks_by_round[round_num])
        if gambles:
            lines.append(f"- {round_names.get(round_num, f'R{round_num}')}: {len(gambles)}/{total}")
    lines.append("")

    # Chalk overlap
    chalk_picks = [p for p in optimal.picks if not p.is_upset and p.round_num > 0]
    total_picks = [p for p in optimal.picks if p.round_num > 0]
    chalk_pct = len(chalk_picks) / len(total_picks) * 100 if total_picks else 0
    lines.append(f"**Chalk overlap:** {len(chalk_picks)}/{len(total_picks)} picks match chalk ({chalk_pct:.0f}%)")
    lines.append("")

    return "\n".join(lines)


# ============================================================================
# ASCII BRACKET (unchanged -- optimal only, for terminal viewing)
# ============================================================================

def generate_ascii_bracket(bracket: CompleteBracket, bracket_structure: BracketStructure) -> str:
    """Generate an ASCII-art bracket visualization."""
    lines = []

    lines.append("=" * 100)
    lines.append(" " * 35 + "MARCH MADNESS BRACKET")
    lines.append("=" * 100)
    lines.append("")

    pick_map = {p.slot_id: p for p in bracket.picks}
    slot_map = {s.slot_id: s for s in bracket_structure.slots}

    picks_by_round = {}
    for pick in bracket.picks:
        picks_by_round.setdefault(pick.round_num, []).append(pick)

    round_names = {1: "ROUND OF 64", 2: "ROUND OF 32", 3: "SWEET 16",
                   4: "ELITE 8", 5: "FINAL FOUR", 6: "CHAMPIONSHIP"}

    for round_num in sorted([r for r in picks_by_round.keys() if r > 0]):
        lines.append("")
        lines.append(f"{'─' * 40} {round_names.get(round_num, f'ROUND {round_num}')} {'─' * 40}")
        lines.append("")

        round_picks = picks_by_round[round_num]

        if round_num == 1:
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
                    lines.append(f"    -> Winner: {pick.winner} {pick.confidence}{upset}")
                    lines.append("")
        else:
            for pick in sorted(round_picks, key=lambda p: p.slot_id):
                slot = slot_map.get(pick.slot_id)
                if not slot:
                    continue
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
                    lines.append(f"    -> Winner: {pick.winner} {pick.confidence}{upset}")
                    lines.append("")
                else:
                    lines.append(f"  Winner: {pick.winner} {pick.confidence}")
                    lines.append("")

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


# ============================================================================
# SUMMARY JSON
# ============================================================================

def generate_summary_json(all_brackets: list[CompleteBracket]) -> dict:
    """Build enhanced summary.json with aggregate stats."""
    optimal = next((b for b in all_brackets if b.label == "optimal"), all_brackets[0])
    safe = next((b for b in all_brackets if b.label == "safe_alternate"), None)
    aggressive = next((b for b in all_brackets if b.label == "aggressive_alternate"), None)

    stats = compute_cross_bracket_stats(all_brackets)
    n = len(all_brackets)

    return {
        "optimal_bracket": optimal.to_dict(),
        "safe_alternate": safe.to_dict() if safe else None,
        "aggressive_alternate": aggressive.to_dict() if aggressive else None,
        "champion": optimal.champion,
        "final_four": optimal.final_four,
        "p_first_place": optimal.p_first_place,
        "expected_score": optimal.expected_score,
        "total_brackets_evaluated": n,
        "champion_distribution": {team: count for team, count in stats.get("champion_dist", [])},
        "final_four_frequency": {team: count for team, count in stats.get("ff_freq", [])},
        "aggregate_stats": {
            "mean_p_first": sum(b.p_first_place for b in all_brackets) / n if n else 0,
            "max_p_first": max((b.p_first_place for b in all_brackets), default=0),
            "mean_expected_score": sum(b.expected_score for b in all_brackets) / n if n else 0,
        },
    }


# ============================================================================
# HTML BRACKET VIEWER
# ============================================================================

def generate_bracket_html(brackets: list[CompleteBracket],
                          bracket_structure: BracketStructure,
                          teams: list[Team],
                          ownership_profiles: list[OwnershipProfile],
                          matchup_matrix: dict[str, dict[str, float]] = None) -> str:
    """Generate a self-contained interactive HTML bracket viewer."""

    # Prepare data for embedding
    bracket_data = []
    for b in brackets:
        upset_count = sum(1 for p in b.picks if p.is_upset)
        bracket_data.append({
            "label": b.label,
            "champion": b.champion,
            "final_four": b.final_four,
            "elite_eight": b.elite_eight,
            "p_first_place": round(b.p_first_place, 4),
            "p_top_three": round(b.p_top_three, 4),
            "expected_score": round(b.expected_score, 1),
            "expected_finish": round(b.expected_finish, 1),
            "upset_count": upset_count,
            "picks": {str(p.slot_id): {
                "winner": p.winner,
                "confidence": p.confidence,
                "is_upset": p.is_upset,
                "round_num": p.round_num,
                "leverage": round(p.leverage_score, 4),
            } for p in b.picks}
        })

    structure_data = [s.to_dict() for s in bracket_structure.slots]

    team_data = {t.name: {
        "seed": t.seed,
        "region": t.region,
        "kenpom_rank": t.kenpom_rank,
        "adj_em": round(t.adj_em, 1),
        "adj_o": round(t.adj_o, 1),
        "adj_d": round(t.adj_d, 1),
        "adj_t": round(t.adj_t, 1) if t.adj_t else None,
        "record": f"{t.wins}-{t.losses}",
        "conference": t.conference or "",
        "barthag": round(t.barthag, 3) if t.barthag else None,
        "wab": round(t.wab, 1) if t.wab else None,
        "top25_wins": getattr(t, 'top25_wins', None),
        "top25_losses": getattr(t, 'top25_losses', None),
    } for t in teams}

    ownership_data = {p.team: {
        "round_ownership": {str(k): round(v, 4) for k, v in p.round_ownership.items()},
        "leverage_by_round": {str(k): round(v, 4) for k, v in p.leverage_by_round.items()},
        "title_ownership": round(p.title_ownership, 4),
        "title_leverage": round(p.title_leverage, 2),
    } for p in ownership_profiles}

    # Build matchup data — only include teams in the bracket to keep size reasonable
    bracket_teams = set(team_data.keys())
    matchup_data = {}
    if matchup_matrix:
        for team_a, opponents in matchup_matrix.items():
            if team_a not in bracket_teams:
                continue
            matchup_data[team_a] = {
                team_b: round(prob, 4)
                for team_b, prob in opponents.items()
                if team_b in bracket_teams
            }

    # Fetch model internals for client-side prediction in the Model modal
    model_data = {}
    try:
        from upset_model.predict import UpsetPredictor
        _p = UpsetPredictor()
        model_data = _p.get_model_internals()
    except Exception:
        pass  # graceful degradation — modal shows static text only

    html = _HTML_TEMPLATE
    html = html.replace("__BRACKET_DATA__", json.dumps(bracket_data))
    html = html.replace("__STRUCTURE_DATA__", json.dumps(structure_data))
    html = html.replace("__TEAM_DATA__", json.dumps(team_data))
    html = html.replace("__OWNERSHIP_DATA__", json.dumps(ownership_data))
    html = html.replace("__MATCHUP_DATA__", json.dumps(matchup_data))
    html = html.replace("__MODEL_DATA__", json.dumps(model_data))

    return html


_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BernieBrackets - Bracket Viewer</title>
<style>
:root {
  --bg: #f8f9fa;
  --card: #fff;
  --border: #dee2e6;
  --text: #212529;
  --muted: #6c757d;
  --accent: #0d6efd;
  --upset: #fd7e14;
  --gold: #ffc107;
  --winner-bg: #d4edda;
  --loser: #adb5bd;
  --panel-bg: #1a1a2e;
  --panel-text: #e0e0e0;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); font-size: 13px; }

/* Header */
.header { background: #1a1a2e; color: #fff; padding: 16px 24px; display: flex; align-items: center; gap: 20px; flex-wrap: wrap; }
.header h1 { font-size: 20px; font-weight: 700; white-space: nowrap; }
.header select { padding: 6px 10px; border-radius: 6px; border: 1px solid #444; background: #16213e; color: #fff; font-size: 13px; cursor: pointer; max-width: 45vw; overflow: hidden; text-overflow: ellipsis; }
.header select:focus { outline: 2px solid var(--accent); }
.selector-group { display: flex; align-items: center; gap: 8px; }
#winner-selector { min-width: 100px; max-width: 35vw; }
#bracket-selector { min-width: 160px; max-width: 45vw; }
.header-spacer { flex: 1; }
.glossary-btn { padding: 6px 14px; border-radius: 6px; border: 1px solid #555; background: transparent; color: #ccc; font-size: 12px; cursor: pointer; letter-spacing: 0.5px; }
.glossary-btn:hover { background: #16213e; color: #fff; border-color: var(--accent); }
.why-chalk-btn { padding: 6px 14px; border-radius: 6px; border: 1px solid #dc3545; background: #dc3545; color: #fff; font-size: 12px; cursor: pointer; letter-spacing: 0.5px; font-weight: 600; }
.why-chalk-btn:hover { background: #bb2d3b; border-color: #bb2d3b; }
.header-btns { display: flex; gap: 8px; align-items: center; flex-shrink: 0; }
@media (max-width: 600px) {
  .header { padding: 12px 12px; gap: 10px; }
  .selector-group { flex-wrap: wrap; width: 100%; }
  .header select { max-width: 60vw; font-size: 12px; }
  #bracket-selector { min-width: 0; flex: 1 1 auto; }
  #winner-selector { min-width: 0; flex: 1 1 auto; }
  .header-btns button { padding: 5px 8px; font-size: 11px; letter-spacing: 0; }
}

/* Stats bar */
.stats-bar { background: #16213e; color: #e0e0e0; padding: 10px 24px; display: flex; gap: 24px; flex-wrap: wrap; font-size: 12px; }
.stat { display: flex; flex-direction: column; }
.stat-label { color: #8899aa; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; }
.stat-value { font-weight: 700; font-size: 15px; color: #fff; }
.stat-value.highlight { color: var(--gold); }

/* Bracket container */
.bracket-wrap { display: flex; justify-content: center; overflow-x: auto; padding: 20px 10px; }
.bracket-container { display: grid; grid-template-columns: 1fr auto 1fr; gap: 0; align-items: start; min-width: 1200px; }

/* Side (left or right) */
.bracket-side { display: flex; flex-direction: column; gap: 24px; }
.bracket-side.right .region { direction: rtl; }
.bracket-side.right .region > * { direction: ltr; }

/* Region */
.region { padding: 8px 0; }
.region-label { font-weight: 700; font-size: 14px; text-transform: uppercase; letter-spacing: 1px; color: var(--muted); padding: 0 8px 6px; }
.bracket-side.right .region-label { text-align: right; }
.rounds { display: flex; align-items: stretch; }
.bracket-side.right .rounds { flex-direction: row-reverse; }

/* Round column */
.round-col { display: flex; flex-direction: column; justify-content: space-around; min-width: 140px; padding: 0 2px; }

/* Game cell */
.game { margin: 2px 0; border: 1px solid var(--border); border-radius: 4px; background: var(--card); overflow: hidden; font-size: 11px; min-width: 130px; cursor: pointer; transition: box-shadow 0.15s; }
.game:hover { box-shadow: 0 0 0 2px var(--accent); }
.game.upset { border-left: 3px solid var(--upset); }
.game-team { display: flex; justify-content: space-between; padding: 3px 6px; border-bottom: 1px solid #eee; gap: 4px; white-space: nowrap; }
.game-team:last-child { border-bottom: none; }
.game-team.winner { background: var(--winner-bg); font-weight: 600; }
.game-team.loser { color: var(--loser); }
.game-team .seed { color: var(--muted); font-size: 10px; min-width: 18px; }
.game-team .name { flex: 1; overflow: hidden; text-overflow: ellipsis; }
.game-team .conf { font-size: 10px; }
.game.champ-path { box-shadow: 0 0 0 2px var(--gold); }
.game.champ-path:hover { box-shadow: 0 0 0 2px var(--accent); }

/* Center (Final Four + Championship) */
.bracket-center { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 0 12px; gap: 10px; min-width: 180px; }
.ff-label { font-weight: 700; font-size: 13px; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; }
.championship-label { font-weight: 700; font-size: 14px; color: var(--gold); text-transform: uppercase; letter-spacing: 1px; }
.center-game { min-width: 160px; }
.champion-box { text-align: center; padding: 10px; background: linear-gradient(135deg, #ffc107, #ff9800); color: #1a1a2e; border-radius: 8px; font-weight: 700; font-size: 16px; margin-top: 4px; }
.champion-box .champ-seed { font-size: 11px; font-weight: 400; opacity: 0.8; }

/* Detail Panel (right sidebar) */
.detail-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: 100; }
.detail-overlay.open { display: block; }
.detail-backdrop { position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.3); }
.detail-panel { position: absolute; top: 0; right: 0; width: 380px; height: 100%; background: var(--panel-bg); color: var(--panel-text); overflow-y: auto; box-shadow: -4px 0 20px rgba(0,0,0,0.3); padding: 0; }
.detail-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid #2a2a4e; }
.detail-header h2 { font-size: 15px; color: #fff; }
.detail-close { background: none; border: none; color: #888; font-size: 22px; cursor: pointer; padding: 0 4px; }
.detail-close:hover { color: #fff; }
.detail-body { padding: 16px 20px; }

/* Team card inside detail panel */
.team-card { background: #16213e; border-radius: 8px; padding: 14px; margin-bottom: 12px; }
.team-card.winner-card { border: 1px solid #4caf50; }
.team-card.loser-card { border: 1px solid #444; opacity: 0.75; }
.tc-name { font-size: 15px; font-weight: 700; color: #fff; margin-bottom: 2px; }
.tc-meta { font-size: 11px; color: #8899aa; margin-bottom: 10px; }
.tc-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.tc-stat { display: flex; flex-direction: column; }
.tc-stat-label { font-size: 9px; color: #667; text-transform: uppercase; letter-spacing: 0.5px; }
.tc-stat-value { font-size: 13px; font-weight: 600; color: #ccc; }
.tc-stat-value.good, .ps-value.good { color: #4caf50; }
.tc-stat-value.warn, .ps-value.warn { color: var(--upset); }

/* Pick summary in detail panel */
.pick-summary { background: #16213e; border-radius: 8px; padding: 14px; margin-top: 4px; }
.pick-summary h3 { font-size: 12px; color: #8899aa; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }
.ps-row { display: flex; justify-content: space-between; padding: 3px 0; font-size: 12px; }
.ps-row .ps-label { color: #8899aa; }
.ps-row .ps-value { color: #fff; font-weight: 600; }

/* Glossary Modal */
.modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: 200; }
.modal-overlay.open { display: flex; align-items: center; justify-content: center; }
.modal-backdrop { position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); }
.modal-content { position: relative; background: #1a1a2e; color: var(--panel-text); border-radius: 12px; padding: 28px 32px; max-width: 560px; width: 90%; max-height: 80vh; overflow-y: auto; box-shadow: 0 8px 32px rgba(0,0,0,0.4); }
.modal-content h2 { font-size: 18px; color: #fff; margin-bottom: 16px; }
.modal-close { position: absolute; top: 12px; right: 16px; background: none; border: none; color: #888; font-size: 22px; cursor: pointer; }
.modal-close:hover { color: #fff; }
.gloss-item { margin-bottom: 12px; }
.gloss-term { font-weight: 700; color: var(--gold); font-size: 13px; }
.gloss-def { font-size: 12px; color: #bbb; line-height: 1.5; margin-top: 2px; }
</style>
</head>
<body>

<div class="header">
  <h1><a href="../" style="color:#fff;text-decoration:none;">BernieBrackets</a></h1>
  <div class="selector-group">
    <select id="winner-selector"></select>
    <select id="bracket-selector"></select>
  </div>
  <div class="header-spacer"></div>
  <div class="header-btns">
    <button class="why-chalk-btn" onclick="document.getElementById('why-chalk-modal').classList.add('open')">Why Perfect Loses?</button>
    <button class="glossary-btn" onclick="document.getElementById('methodology-modal').classList.add('open')">Methodology</button>
    <button class="glossary-btn" onclick="document.getElementById('model-modal').classList.add('open')">Model</button>
    <button class="glossary-btn" onclick="document.getElementById('glossary-modal').classList.add('open')">Glossary</button>
  </div>
</div>

<div class="stats-bar" id="stats-bar"></div>

<div class="bracket-wrap">
  <div class="bracket-container" id="bracket-container">
    <div class="bracket-side left" id="side-left"></div>
    <div class="bracket-center" id="center"></div>
    <div class="bracket-side right" id="side-right"></div>
  </div>
</div>

<!-- Detail Panel -->
<div class="detail-overlay" id="detail-overlay">
  <div class="detail-backdrop" onclick="closeDetail()"></div>
  <div class="detail-panel">
    <div class="detail-header">
      <h2 id="detail-title">Matchup Detail</h2>
      <button class="detail-close" onclick="closeDetail()">&times;</button>
    </div>
    <div class="detail-body" id="detail-body"></div>
  </div>
</div>

<!-- Why Perfect Loses Modal -->
<div class="modal-overlay" id="why-chalk-modal">
  <div class="modal-backdrop" onclick="document.getElementById('why-chalk-modal').classList.remove('open')"></div>
  <div class="modal-content" style="max-width:680px;">
    <button class="modal-close" onclick="document.getElementById('why-chalk-modal').classList.remove('open')">&times;</button>
    <h2 style="color:#dc3545;">Why Perfect Loses</h2>
    <p style="font-size:13px;color:#bbb;margin-bottom:20px;line-height:1.6;">BERNS_CHALK always picks the most probable winner in every game. It is the most <em>accurate</em> bracket. So why doesn&rsquo;t it have the highest P(1st place)?</p>

    <div class="gloss-item">
      <span class="gloss-term">The Core Problem: You Score Relative to the Field</span>
      <div class="gloss-def">When BERNS_CHALK picks Duke as champion (say, 35% win prob) and Duke wins &mdash; so do the 55% of pool entrants who also picked Duke. You score 320 points. So do they. Your relative gain is <strong style="color:#fff;">zero</strong>. Winning a pool requires maximizing P(your score &gt; everyone else&rsquo;s), not maximizing expected correct picks. These are fundamentally different objectives.</div>
    </div>

    <div class="gloss-item">
      <span class="gloss-term">Proof: The 20% Underdog Can Win More Often</span>
      <div class="gloss-def" style="font-family:monospace;font-size:11px;line-height:1.8;color:#ccc;">
        10-person pool &bull; 1 championship game &bull; 320 pts<br>
        Team A: 80% win prob, 90% ownership (9 of 10 pick A)<br>
        Team B: 20% win prob, 10% ownership (1 of 10 picks B)<br><br>
        <strong style="color:#fff;">Pick A (BERNS_CHALK):</strong><br>
        &nbsp;&nbsp;A wins (80%): you share 320 pts with 8 others &rarr; win tiebreak 1/9<br>
        &nbsp;&nbsp;B wins (20%): you score 0, contrarian scores 320 &rarr; you lose<br>
        &nbsp;&nbsp;<strong style="color:#dc3545;">P(1st) = 0.80 &times; (1/9) + 0.20 &times; 0 = 8.9%</strong><br><br>
        <strong style="color:#fff;">Pick B (contrarian):</strong><br>
        &nbsp;&nbsp;A wins (80%): you score 0 &rarr; you lose<br>
        &nbsp;&nbsp;B wins (20%): you and 1 opponent share 320 pts &rarr; win tiebreak 1/2<br>
        &nbsp;&nbsp;<strong style="color:#4caf50;">P(1st) = 0.80 &times; 0 + 0.20 &times; (1/2) = 10.0%</strong>
      </div>
    </div>

    <div class="gloss-item">
      <span class="gloss-term">The General Rule</span>
      <div class="gloss-def">Pick the underdog when: <strong style="color:#fff;">ownership_A / ownership_B &gt; prob_A / prob_B</strong>. In the example: 90/10 = 9 &gt; 80/20 = 4 &rarr; pick B. This is exactly what <strong style="color:var(--gold);">Leverage</strong> captures: model_prob / public_ownership. When leverage &gt; 1 for the underdog, picking them increases P(1st) even though it decreases expected score.</div>
    </div>

    <div class="gloss-item">
      <span class="gloss-term">The Variance Argument</span>
      <div class="gloss-def">BERNS_CHALK is a low-variance strategy. It scores consistently near the pool average. But &ldquo;slightly above average&rdquo; rarely wins a 25-person pool. The optimizer introduces <em>good variance</em>: EMV-positive upsets that are correlated with leapfrogging the most people at once. When a 4-seed Final Four pick hits, you score 160 pts while ~75% of the field scores 0 on that slot.</div>
    </div>

    <div class="gloss-item">
      <span class="gloss-term">More Simulations Don&rsquo;t Change This</span>
      <div class="gloss-def">More Monte Carlo sims reduce measurement noise &mdash; they converge to the true P(1st). But the true P(1st) for BERNS_CHALK is structurally limited because it picks the same teams as most opponents. It wins when they win, loses when they lose. No amount of simulation changes the underlying math.</div>
    </div>

    <div class="gloss-item">
      <span class="gloss-term">The Analogy</span>
      <div class="gloss-def">BERNS_CHALK is like a stock portfolio that perfectly tracks the index. You&rsquo;ll never dramatically underperform. But you&rsquo;ll never outperform either &mdash; because everyone else is also indexed. To beat the field, you need a concentrated position that the field doesn&rsquo;t have.</div>
    </div>
  </div>
</div>

<!-- Glossary Modal -->
<div class="modal-overlay" id="glossary-modal">
  <div class="modal-backdrop" onclick="document.getElementById('glossary-modal').classList.remove('open')"></div>
  <div class="modal-content">
    <button class="modal-close" onclick="document.getElementById('glossary-modal').classList.remove('open')">&times;</button>
    <h2>Glossary</h2>
    <div class="gloss-item"><span class="gloss-term">AdjEM</span><div class="gloss-def">Adjusted Efficiency Margin. Points scored minus points allowed per 100 possessions, adjusted for opponent strength. The single best predictor of tournament success.</div></div>
    <div class="gloss-item"><span class="gloss-term">AdjO / AdjD</span><div class="gloss-def">Adjusted Offensive / Defensive Efficiency. Points scored (or allowed) per 100 possessions, adjusted for opponent strength. Lower AdjD is better.</div></div>
    <div class="gloss-item"><span class="gloss-term">KenPom Rank</span><div class="gloss-def">Overall team ranking from kenpom.com, based on AdjEM. #1 is the best team in the country.</div></div>
    <div class="gloss-item"><span class="gloss-term">Barthag</span><div class="gloss-def">From Barttorvik. Estimated probability of beating an average Division I team on a neutral court. 0.95+ is elite.</div></div>
    <div class="gloss-item"><span class="gloss-term">WAB</span><div class="gloss-def">Wins Above Bubble. How many wins above (or below) what a bubble team would achieve against the same schedule. Positive = comfortably in the tournament.</div></div>
    <div class="gloss-item"><span class="gloss-term">Top-25 Record</span><div class="gloss-def">Wins and losses against top-25 ranked opponents. Reveals how a team performs against elite competition.</div></div>
    <div class="gloss-item"><span class="gloss-term">Seed Advantage</span><div class="gloss-def">Underdog&rsquo;s seed minus favorite&rsquo;s seed (e.g., +7 for a 5-vs-12 matchup). The model&rsquo;s strongest single predictor of upset probability.</div></div>
    <div class="gloss-item"><span class="gloss-term">AdjEM Gap</span><div class="gloss-def">AdjEM difference (underdog minus favorite). Negative = underdog is less efficient. Used by the upset model alongside seed.</div></div>
    <div class="gloss-item"><span class="gloss-term">Seed &times; AdjEM Interaction</span><div class="gloss-def">Product of seed gap and AdjEM gap. Captures games where a team is higher-seeded but statistically close (or lower-seeded but overrated).</div></div>
    <div class="gloss-item"><span class="gloss-term">Barthag Gap</span><div class="gloss-def">Barthag difference (underdog minus favorite). Negative = underdog has a lower probability of beating an average D-I team.</div></div>
    <div class="gloss-item"><span class="gloss-term">WAB Gap</span><div class="gloss-def">Wins Above Bubble difference (underdog minus favorite). Negative = underdog barely qualified for the tournament.</div></div>
    <div class="gloss-item"><span class="gloss-term">Top-25 Win% Gap</span><div class="gloss-def">Favorite&rsquo;s top-25 win percentage minus underdog&rsquo;s. Positive = favorite has a stronger resume against elite competition.</div></div>
    <div class="gloss-item"><span class="gloss-term">Leverage</span><div class="gloss-def">Model probability / public ownership. Values &gt;1 mean the public is undervaluing this pick. Higher leverage = more contrarian value if the pick hits.</div></div>
    <div class="gloss-item"><span class="gloss-term">Public %</span><div class="gloss-def">Percentage of Yahoo Bracket Mayhem entrants picking this team to advance to this round. Represents what "the field" is doing.</div></div>
    <div class="gloss-item"><span class="gloss-term">P(1st)</span><div class="gloss-def">Probability this bracket finishes 1st in the pool, estimated via Monte Carlo simulation of thousands of random tournaments against opponent brackets sampled from public ownership.</div></div>
    <div class="gloss-item"><span class="gloss-term">E[Score]</span><div class="gloss-def">Expected ESPN bracket score using standard scoring: 10, 20, 40, 80, 160, 320 points per round. The championship pick alone is worth 320 points.</div></div>
    <div class="gloss-item"><span class="gloss-term">EMV</span><div class="gloss-def">Expected Marginal Value. P(upset) &times; ownership_gain &minus; P(chalk) &times; ownership_cost. Positive EMV means picking the upset increases your expected pool finish.</div></div>
    <div class="gloss-item"><span class="gloss-term">Confidence Tiers</span><div class="gloss-def">&#x1f512; Lock: &ge;75% win probability. &#x1f44d; Lean: 55-75%. &#x1f3b2; Gamble: &lt;55%.</div></div>
  </div>
</div>

<!-- Methodology Modal -->
<div class="modal-overlay" id="methodology-modal">
  <div class="modal-backdrop" onclick="document.getElementById('methodology-modal').classList.remove('open')"></div>
  <div class="modal-content" style="max-width:680px;">
    <button class="modal-close" onclick="document.getElementById('methodology-modal').classList.remove('open')">&times;</button>
    <h2>Methodology</h2>

    <div class="gloss-item">
      <span class="gloss-term">1. Data Collection</span>
      <div class="gloss-def">
        We scrape live data from five sources: <b>NCAA.com</b> for the official 68-team bracket and seedings, <b>KenPom</b> for adjusted efficiency ratings (AdjEM, AdjO, AdjD, tempo, luck, SOS), <b>Barttorvik</b> for Barthag and Wins Above Bubble (WAB), <b>LRMC</b> (Georgia Tech) for top-25 win/loss records, and <b>Yahoo Bracket Mayhem</b> for public pick percentages across all 6 rounds. All data is cached locally so re-runs don't re-scrape.
      </div>
    </div>

    <div class="gloss-item">
      <span class="gloss-term">2. Win Probability Model</span>
      <div class="gloss-def">
        A pairwise win probability matrix is built for all 68 teams. The primary engine is a <b>stacked ensemble</b> of Logistic Regression, Random Forest, and Gradient Boosted Trees trained on <b>738 NCAA tournament games (2011&ndash;2025)</b>. The model uses 16 features extracted from the team stats above: seed difference, AdjEM gap, offensive/defensive efficiency gaps, Barthag gap, WAB gap, top-25 record, tempo differential, and interaction terms. When the trained model is unavailable, we fall back to historical seed-vs-seed upset rates.
      </div>
    </div>

    <div class="gloss-item">
      <span class="gloss-term">3. Ownership &amp; Leverage Analysis</span>
      <div class="gloss-def">
        Yahoo public pick percentages tell us what the field is doing. For each team at each round, we compute <b>leverage = model probability / public ownership</b>. Leverage &gt;1 means the public is undervaluing a team relative to our model. This is the key contrarian signal: we want picks where we're right and the crowd is wrong, because those picks create separation in the pool standings.
      </div>
    </div>

    <div class="gloss-item">
      <span class="gloss-term">4. Scenario Generation</span>
      <div class="gloss-def">
        We identify the <b>top 8 champion candidates</b> ranked by pool-adjusted value (title probability divided by expected number of opponents picking the same champion). For each candidate, we generate scenarios at multiple chaos levels:
        <ul style="margin:6px 0 0 16px; line-height:1.8;">
          <li><b>Chalk</b> (low chaos) &mdash; favorites win most games, upsets are rare</li>
          <li><b>Contrarian</b> (medium chaos) &mdash; 1&ndash;2 upset-heavy regions, a Cinderella run</li>
          <li><b>Chaos</b> (high chaos) &mdash; upsets across all regions, deep runs by mid-seeds</li>
        </ul>
        The top 4 champions get all 3 levels; champions 5&ndash;8 get medium and high only. The top 2 champions also get Final Four variant scenarios with different supporting casts. This yields ~24 distinct bracket scenarios.
      </div>
    </div>

    <div class="gloss-item">
      <span class="gloss-term">5. Top-Down Bracket Construction</span>
      <div class="gloss-def">
        Each scenario is converted into a full 63-game bracket using a <b>top-down process</b>:
        <ol style="margin:6px 0 0 16px; line-height:1.8;">
          <li><b>Champion</b> is locked first (worth 320 points)</li>
          <li><b>Final Four paths</b> are locked for each region</li>
          <li><b>EMV-positive upsets</b> are added in descending order &mdash; EMV = P(upset) &times; ownership_gain &minus; P(chalk) &times; ownership_cost. Only upsets with positive expected value make the cut.</li>
          <li><b>Remaining slots</b> are filled with chalk (higher-seeded favorite)</li>
        </ol>
        This ensures the most valuable picks (champion, Final Four) are chosen for strategic reasons, not left to cascading effects from early-round picks.
      </div>
    </div>

    <div class="gloss-item">
      <span class="gloss-term">6. Monte Carlo Evaluation</span>
      <div class="gloss-def">
        Each of the ~24 brackets is evaluated by simulating <b>thousands of tournaments</b>. In each simulation:
        <ol style="margin:6px 0 0 16px; line-height:1.8;">
          <li>An <b>actual tournament outcome</b> is generated by rolling dice using the win probability matrix</li>
          <li>A pool of <b>opponent brackets</b> is generated by sampling picks from Yahoo public ownership distributions</li>
          <li>Your bracket and all opponents are <b>scored</b> using ESPN standard scoring [10, 20, 40, 80, 160, 320]</li>
          <li>Your <b>finish position</b> is recorded (1st, 2nd, etc.)</li>
        </ol>
        Across all simulations, we compute: <b>P(1st place)</b>, <b>P(top 3)</b>, <b>expected finish</b>, and <b>expected score</b>. The bracket with the highest P(1st) is tagged as &ldquo;optimal&rdquo;.
      </div>
    </div>

    <div class="gloss-item">
      <span class="gloss-term">7. Why This Works</span>
      <div class="gloss-def">
        In a small pool (10&ndash;50 people), you don't win by picking the most correct bracket &mdash; you win by picking the bracket that's most <b>different from everyone else's</b> when you happen to be right. A chalk bracket scores well on average but rarely wins the pool because 10 other people picked the same favorites. BernieBrackets finds the picks where the model disagrees with the public and the expected value of being contrarian is positive. It's not about being different for its own sake &mdash; it's about being different in spots where the math says the crowd is wrong.
      </div>
    </div>

  </div>
</div>

<!-- Model Modal -->
<div class="modal-overlay" id="model-modal">
  <div class="modal-backdrop" onclick="document.getElementById('model-modal').classList.remove('open')"></div>
  <div class="modal-content" style="max-width:720px;">
    <button class="modal-close" onclick="document.getElementById('model-modal').classList.remove('open')">&times;</button>
    <h2>Upset Prediction Model</h2>

    <div class="gloss-item">
      <span class="gloss-term">Performance</span>
      <div class="gloss-def" id="model-perf-stats" style="line-height:1.6;"></div>
    </div>
    <div id="model-auc-chart" style="margin:12px 0 20px;"></div>

    <div class="gloss-item">
      <span class="gloss-term">Match Predictor</span>
      <div class="gloss-def">Select any two tournament teams to see the model&rsquo;s predicted win probability and the per-feature breakdown driving it.</div>
    </div>

    <div style="display:flex;align-items:center;gap:10px;margin:12px 0 0;">
      <select id="model-team-a" style="flex:1;background:#16213e;color:#fff;border:1px solid #444;border-radius:6px;padding:7px 10px;font-size:13px;"></select>
      <span style="color:#666;font-size:16px;font-weight:300;flex-shrink:0;">vs.</span>
      <select id="model-team-b" style="flex:1;background:#16213e;color:#fff;border:1px solid #444;border-radius:6px;padding:7px 10px;font-size:13px;"></select>
    </div>

    <div id="model-result" style="margin-top:12px;"></div>
    <div id="model-features" style="margin-top:4px;"></div>

  </div>
</div>

<script>
const BRACKETS = __BRACKET_DATA__;
const SLOTS = __STRUCTURE_DATA__;
const TEAMS = __TEAM_DATA__;
const OWNERSHIP = __OWNERSHIP_DATA__;
const MATCHUPS = __MATCHUP_DATA__;
const MODEL_DATA = __MODEL_DATA__;

let currentPicks = null; // track current bracket's picks for detail panel

const ROUND_NAMES = {1:'R64',2:'R32',3:'S16',4:'E8',5:'Final Four',6:'Championship'};

// Build slot lookup
const slotById = {};
SLOTS.forEach(s => slotById[s.slot_id] = s);

function feedersOf(slotId) {
  return SLOTS.filter(s => s.feeds_into === slotId).sort((a,b) => a.slot_id - b.slot_id);
}

function detectLayout() {
  // ESPN layout: East top-left, South bottom-left, West top-right, Midwest bottom-right
  // Find all regions in the data
  const allRegions = [...new Set(SLOTS.filter(s => s.region && s.region !== 'FinalFour').map(s => s.region))];

  // Map to ESPN positions; normalize to uppercase for matching
  const regionSet = new Set(allRegions.map(r => r.toUpperCase()));
  const find = (name) => allRegions.find(r => r.toUpperCase() === name) || null;

  const east = find('EAST');
  const west = find('WEST');
  const south = find('SOUTH');
  const midwest = find('MIDWEST');

  // Left side: East (top), South (bottom).  Right side: West (top), Midwest (bottom).
  const layout = {
    left:  [east, south].filter(Boolean),
    right: [west, midwest].filter(Boolean),
  };

  // Fallback if region names don't match expected
  if (layout.left.length === 0 && layout.right.length === 0) {
    layout.left = allRegions.slice(0, 2);
    layout.right = allRegions.slice(2, 4);
  }
  return layout;
}

// Build winner index: champion -> [{idx, b}], each list sorted by p_first_place desc
const WINNER_INDEX = (() => {
  const map = {};
  BRACKETS.forEach((b, i) => {
    if (!map[b.champion]) map[b.champion] = [];
    map[b.champion].push({idx: i, b});
  });
  for (const w in map) map[w].sort((a, z) => z.b.p_first_place - a.b.p_first_place);
  return map;
})();

// Winners sorted by each winner's max P(1st)
const WINNERS_SORTED = Object.keys(WINNER_INDEX).sort(
  (a, b) => WINNER_INDEX[b][0].b.p_first_place - WINNER_INDEX[a][0].b.p_first_place
);

function refreshBracketSelector() {
  const winner = document.getElementById('winner-selector').value;
  let pool = winner === '__all__'
    ? BRACKETS.map((b, i) => ({idx: i, b})).sort((a, z) => z.b.p_first_place - a.b.p_first_place)
    : (WINNER_INDEX[winner] || []);

  const sel = document.getElementById('bracket-selector');
  const prev = parseInt(sel.value);
  sel.innerHTML = '';
  pool.forEach(({idx, b}) => {
    const tag = ['optimal','safe_alternate','aggressive_alternate'].includes(b.label)
      ? ` [${b.label.toUpperCase()}]` : '';
    const label = winner === '__all__'
      ? `${b.champion}: ${b.label}${tag} \u2014 ${(b.p_first_place*100).toFixed(1)}%`
      : `${b.label}${tag} \u2014 ${(b.p_first_place*100).toFixed(1)}%`;
    sel.appendChild(new Option(label, idx));
  });

  const keep = [...sel.options].find(o => parseInt(o.value) === prev);
  if (keep) { sel.value = prev; }
  else if (pool.length > 0) { closeDetail(); renderBracket(pool[0].idx); }
}

function populateSelector() {
  // Winner dropdown
  const winSel = document.getElementById('winner-selector');
  winSel.appendChild(new Option('All Winners', '__all__'));
  WINNERS_SORTED.forEach(w => {
    const max = (WINNER_INDEX[w][0].b.p_first_place * 100).toFixed(1);
    winSel.appendChild(new Option(`${w}  (${max}% max)`, w));
  });

  document.getElementById('bracket-selector').addEventListener('change', e => {
    closeDetail(); renderBracket(parseInt(e.target.value));
  });

  winSel.addEventListener('change', () => {
    refreshBracketSelector();
  });

  refreshBracketSelector();
}

function updateStats(b) {
  const bar = document.getElementById('stats-bar');
  const stats = [
    ['Champion', b.champion, true],
    ['P(1st)', (b.p_first_place*100).toFixed(1) + '%', true],
    ['P(Top 3)', (b.p_top_three*100).toFixed(1) + '%', false],
    ['E[Score]', Math.round(b.expected_score) + ' pts', false],
    ['E[Finish]', b.expected_finish.toFixed(1), false],
    ['Upsets', b.upset_count, false],
    ['Final Four', b.final_four.join(', '), false],
  ];
  bar.innerHTML = stats.map(([label, val, hl]) =>
    `<div class="stat"><span class="stat-label">${label}</span><span class="stat-value${hl?' highlight':''}">${val}</span></div>`
  ).join('');
}

// ── Detail Panel ──

function closeDetail() {
  document.getElementById('detail-overlay').classList.remove('open');
}

function pct(v) { return v != null ? (v * 100).toFixed(1) + '%' : '--'; }
function signed(v) { return v != null ? (v >= 0 ? '+' : '') + v.toFixed(1) : '--'; }

function showDetail(slotId) {
  if (!currentPicks) return;
  const pick = currentPicks[String(slotId)];
  const slot = slotById[slotId];
  if (!pick || !slot) return;

  // Determine teams
  let teamA, teamB;
  if (slot.round_num === 1) {
    teamA = slot.team_a;
    teamB = slot.team_b;
  } else {
    const feeders = feedersOf(slotId);
    teamA = feeders[0] ? currentPicks[String(feeders[0].slot_id)]?.winner : null;
    teamB = feeders[1] ? currentPicks[String(feeders[1].slot_id)]?.winner : null;
  }

  const roundName = ROUND_NAMES[pick.round_num] || ('Round ' + pick.round_num);
  document.getElementById('detail-title').textContent = roundName + ' Matchup';

  const body = document.getElementById('detail-body');
  let html = '';

  // Team cards
  [teamA, teamB].forEach(name => {
    if (!name) return;
    const t = TEAMS[name] || {};
    const o = OWNERSHIP[name] || {};
    const isWinner = name === pick.winner;
    const cardClass = isWinner ? 'winner-card' : 'loser-card';
    const roundOwn = o.round_ownership ? o.round_ownership[String(pick.round_num)] : null;
    const roundLev = o.leverage_by_round ? o.leverage_by_round[String(pick.round_num)] : null;

    html += `<div class="team-card ${cardClass}">`;
    html += `<div class="tc-name">${isWinner ? '&#x2714; ' : ''}${name}</div>`;
    html += `<div class="tc-meta">${t.seed || '?'}-seed &middot; ${t.conference || '?'} &middot; ${t.record || '?'}</div>`;
    html += `<div class="tc-grid">`;
    html += `<div class="tc-stat"><span class="tc-stat-label">KenPom</span><span class="tc-stat-value">#${t.kenpom_rank || '?'}</span></div>`;
    html += `<div class="tc-stat"><span class="tc-stat-label">AdjEM</span><span class="tc-stat-value">${signed(t.adj_em)}</span></div>`;
    html += `<div class="tc-stat"><span class="tc-stat-label">AdjO</span><span class="tc-stat-value">${t.adj_o != null ? t.adj_o.toFixed(1) : '--'}</span></div>`;
    html += `<div class="tc-stat"><span class="tc-stat-label">AdjD</span><span class="tc-stat-value">${t.adj_d != null ? t.adj_d.toFixed(1) : '--'}</span></div>`;
    if (t.barthag != null) html += `<div class="tc-stat"><span class="tc-stat-label">Barthag</span><span class="tc-stat-value">${t.barthag.toFixed(3)}</span></div>`;
    if (t.wab != null) html += `<div class="tc-stat"><span class="tc-stat-label">WAB</span><span class="tc-stat-value">${signed(t.wab)}</span></div>`;
    if (t.top25_wins != null && t.top25_losses != null) html += `<div class="tc-stat"><span class="tc-stat-label">vs Top 25</span><span class="tc-stat-value">${t.top25_wins}-${t.top25_losses}</span></div>`;
    // Public ownership for this round
    if (roundOwn != null) html += `<div class="tc-stat"><span class="tc-stat-label">Public % (${roundName})</span><span class="tc-stat-value">${pct(roundOwn)}</span></div>`;
    html += `</div></div>`;
  });

  // Pick summary
  const winnerOwn = OWNERSHIP[pick.winner] || {};
  const winRoundOwn = winnerOwn.round_ownership ? winnerOwn.round_ownership[String(pick.round_num)] : null;

  // Model win probability from matchup matrix
  const loser = (pick.winner === teamA) ? teamB : teamA;
  const winProb = (MATCHUPS[pick.winner] && MATCHUPS[pick.winner][loser]) ? MATCHUPS[pick.winner][loser] : null;

  html += `<div class="pick-summary"><h3>Pick Analysis</h3>`;
  html += `<div class="ps-row"><span class="ps-label">Winner</span><span class="ps-value">${pick.winner} ${pick.confidence}</span></div>`;
  if (winProb != null) {
    html += `<div class="ps-row"><span class="ps-label">Model win prob</span><span class="ps-value ${winProb >= 0.5 ? 'good' : 'warn'}">${(winProb * 100).toFixed(1)}%</span></div>`;
  }
  html += `<div class="ps-row"><span class="ps-label">Upset?</span><span class="ps-value">${pick.is_upset ? 'Yes' : 'No'}</span></div>`;
  html += `<div class="ps-row"><span class="ps-label">Leverage</span><span class="ps-value">${pick.leverage.toFixed(4)}</span></div>`;
  if (winRoundOwn != null) {
    html += `<div class="ps-row"><span class="ps-label">Public picking ${pick.winner} here</span><span class="ps-value">${pct(winRoundOwn)}</span></div>`;
  }
  // Title ownership if this is a late round
  if (pick.round_num >= 5 && winnerOwn.title_ownership != null) {
    html += `<div class="ps-row"><span class="ps-label">Public title %</span><span class="ps-value">${pct(winnerOwn.title_ownership)}</span></div>`;
    if (winnerOwn.title_leverage != null) {
      html += `<div class="ps-row"><span class="ps-label">Title leverage</span><span class="ps-value">${winnerOwn.title_leverage.toFixed(2)}</span></div>`;
    }
  }
  html += `</div>`;

  body.innerHTML = html;
  document.getElementById('detail-overlay').classList.add('open');
}

// ── Game Cell Builder ──

function makeGameCell(slot, picks, champPath) {
  const pick = picks[String(slot.slot_id)];
  if (!pick) return null;

  const div = document.createElement('div');
  div.className = 'game';
  if (pick.is_upset) div.classList.add('upset');
  if (champPath.has(slot.slot_id)) div.classList.add('champ-path');

  // Click handler
  div.addEventListener('click', (e) => { e.stopPropagation(); showDetail(slot.slot_id); });

  let teamA, teamB;
  if (slot.round_num === 1) {
    teamA = slot.team_a;
    teamB = slot.team_b;
  } else {
    const feeders = feedersOf(slot.slot_id);
    teamA = feeders[0] ? picks[String(feeders[0].slot_id)]?.winner : '?';
    teamB = feeders[1] ? picks[String(feeders[1].slot_id)]?.winner : '?';
  }

  [teamA, teamB].forEach(team => {
    const isWinner = team === pick.winner;
    const teamInfo = TEAMS[team] || {};
    const row = document.createElement('div');
    row.className = 'game-team ' + (isWinner ? 'winner' : 'loser');
    row.innerHTML = `<span class="seed">${teamInfo.seed || '?'}</span><span class="name" title="${team}">${team}</span>`;
    if (isWinner) {
      const confMap = {'\u{1f512} Lock':'\u{1f512}','\u{1f44d} Lean':'\u{1f44d}','\u{1f3b2} Gamble':'\u{1f3b2}'};
      row.innerHTML += `<span class="conf">${confMap[pick.confidence]||''}</span>`;
    }
    div.appendChild(row);
  });

  return div;
}

// ── Champion Path ──

function getChampPath(picks, champion) {
  const path = new Set();
  const champSlot = SLOTS.find(s => s.round_num === 6);
  if (!champSlot) return path;
  function trace(slotId) {
    const pick = picks[String(slotId)];
    if (!pick || pick.winner !== champion) return;
    const slot = slotById[slotId];
    if (!slot) return;
    if (slot.round_num === 1 && slot.team_a !== champion && slot.team_b !== champion) return;
    path.add(slotId);
    feedersOf(slotId).forEach(f => trace(f.slot_id));
  }
  trace(champSlot.slot_id);
  return path;
}

// ── Region Renderer ──

function renderRegion(container, regionName, picks, champPath) {
  const regionDiv = document.createElement('div');
  regionDiv.className = 'region';
  const label = document.createElement('div');
  label.className = 'region-label';
  label.textContent = regionName;
  regionDiv.appendChild(label);

  const roundsDiv = document.createElement('div');
  roundsDiv.className = 'rounds';

  for (let r = 1; r <= 4; r++) {
    const roundSlots = SLOTS.filter(s => s.region === regionName && s.round_num === r)
                            .sort((a,b) => a.slot_id - b.slot_id);
    if (roundSlots.length === 0) continue;
    const col = document.createElement('div');
    col.className = 'round-col';
    roundSlots.forEach(slot => {
      const cell = makeGameCell(slot, picks, champPath);
      if (cell) col.appendChild(cell);
    });
    roundsDiv.appendChild(col);
  }

  regionDiv.appendChild(roundsDiv);
  container.appendChild(regionDiv);
}

// ── Center (FF + Championship) ──

function renderCenter(container, picks, champPath, bracket) {
  container.innerHTML = '';
  const ffSlots = SLOTS.filter(s => s.round_num === 5).sort((a,b) => a.slot_id - b.slot_id);

  const ffLabel1 = document.createElement('div');
  ffLabel1.className = 'ff-label';
  ffLabel1.textContent = 'Final Four';
  container.appendChild(ffLabel1);
  if (ffSlots[0]) {
    const cell = makeGameCell(ffSlots[0], picks, champPath);
    if (cell) { cell.classList.add('center-game'); container.appendChild(cell); }
  }

  const champSlot = SLOTS.find(s => s.round_num === 6);
  const champLabel = document.createElement('div');
  champLabel.className = 'championship-label';
  champLabel.textContent = 'Championship';
  container.appendChild(champLabel);
  if (champSlot) {
    const cell = makeGameCell(champSlot, picks, champPath);
    if (cell) { cell.classList.add('center-game'); container.appendChild(cell); }
  }

  const champBox = document.createElement('div');
  champBox.className = 'champion-box';
  const champTeam = TEAMS[bracket.champion] || {};
  champBox.innerHTML = `${bracket.champion}<br><span class="champ-seed">${champTeam.seed ? '(' + champTeam.seed + ' seed)' : ''}</span>`;
  container.appendChild(champBox);

  if (ffSlots[1]) {
    const ffLabel2 = document.createElement('div');
    ffLabel2.className = 'ff-label';
    ffLabel2.textContent = 'Final Four';
    container.appendChild(ffLabel2);
    const cell = makeGameCell(ffSlots[1], picks, champPath);
    if (cell) { cell.classList.add('center-game'); container.appendChild(cell); }
  }
}

// ── Main Render ──

function renderBracket(index) {
  const bracket = BRACKETS[index];
  currentPicks = bracket.picks;
  const champPath = getChampPath(currentPicks, bracket.champion);

  updateStats(bracket);

  const layout = detectLayout();

  const leftEl = document.getElementById('side-left');
  leftEl.innerHTML = '';
  layout.left.forEach(region => renderRegion(leftEl, region, currentPicks, champPath));

  const rightEl = document.getElementById('side-right');
  rightEl.innerHTML = '';
  layout.right.forEach(region => renderRegion(rightEl, region, currentPicks, champPath));

  renderCenter(document.getElementById('center'), currentPicks, champPath, bracket);
}

// ── Model Modal ──

const FEATURE_LABELS = {
  seed_diff:          'Seed Advantage',
  adj_em_diff:        'AdjEM Gap',
  adj_o_diff:         'Offensive Efficiency',
  adj_t_diff:         'Tempo Differential',
  seed_x_adj_em:      'Seed \u00d7 AdjEM Interaction',
  top25_winpct_diff:  'Top-25 Win% Gap',
  dog_top25_winpct:   'Underdog Top-25 Win%',
  barthag_diff:       'Barthag Gap',
  wab_diff:           'WAB Gap',
  momentum_diff:      'Momentum Differential',
  dog_momentum:       'Underdog Momentum',
  dog_last10_winpct:  'Underdog Last-10 Win%',
  spread:             'Vegas Spread',
  spread_vs_expected: 'Spread vs. Expected',
};

function initModelModal() {
  renderAucChart();
  populateTeamSelectors();
}

function renderAucChart() {
  const container = document.getElementById('model-auc-chart');
  const perfEl    = document.getElementById('model-perf-stats');
  if (!MODEL_DATA || !MODEL_DATA.model_auc) {
    if (perfEl) perfEl.innerHTML = 'Model not available &mdash; run <code>python upset_model/train_sklearn.py</code> to enable.';
    if (container) container.innerHTML = '';
    return;
  }

  const n       = MODEL_DATA.training_n || 0;
  const nu      = MODEL_DATA.n_upsets   || 0;
  const years   = MODEL_DATA.years || [];
  const yearStr = years.length > 1 ? years[0] + '\u2013' + years[years.length - 1] : (years[0] || '');
  const nf      = (MODEL_DATA.feature_names || []).length;
  if (perfEl) perfEl.innerHTML =
    'Logistic Regression with isotonic calibration. Trained on <b>' + n +
    ' NCAA tournament games</b> (' + yearStr + '), ' + nu + ' upsets (' +
    Math.round(100 * nu / n) + '%). ' + nf +
    ' features selected via L1 (Lasso) screening from 14 candidates. ' +
    'Cross-validated via Leave-One-Year-Out (LOGO) methodology.';

  const bars = [
    { label: 'Seed Only',               auc: MODEL_DATA.baseline_auc,    color: '#4a5568' },
    MODEL_DATA.seed_kenpom_auc != null
      ? { label: 'Seed + KenPom AdjEM', auc: MODEL_DATA.seed_kenpom_auc, color: '#2d6a9f' }
      : null,
    { label: 'Full Model (' + nf + ' features)', auc: MODEL_DATA.model_auc, color: 'var(--accent)' },
  ].filter(Boolean);

  const baseline = bars[0].auc;
  const maxAuc   = Math.max(...bars.map(b => b.auc));
  const minAuc   = 0.5;
  const range    = maxAuc - minAuc;

  let html = '<div style="font-size:11px;color:#8899aa;margin-bottom:8px;text-transform:uppercase;letter-spacing:0.5px;">AUC \u2014 Area Under ROC Curve (Leave-One-Year-Out CV)</div>';
  for (const bar of bars) {
    const pct  = range > 0 ? ((bar.auc - minAuc) / range * 78).toFixed(1) : '40';
    const lift = bar.auc > baseline
      ? '+' + ((bar.auc / baseline - 1) * 100).toFixed(1) + '% lift'
      : '';
    html +=
      '<div style="display:flex;align-items:center;gap:10px;margin-bottom:9px;">' +
        '<div style="width:190px;font-size:12px;color:#ccc;text-align:right;flex-shrink:0;">' + bar.label + '</div>' +
        '<div style="flex:1;background:#0d1b2a;border-radius:4px;height:20px;overflow:hidden;">' +
          '<div style="width:' + pct + '%;height:100%;background:' + bar.color + ';border-radius:4px;"></div>' +
        '</div>' +
        '<div style="width:46px;font-size:13px;font-weight:700;color:#fff;flex-shrink:0;">' + bar.auc.toFixed(3) + '</div>' +
        '<div style="width:90px;font-size:11px;color:' + (lift ? '#4ade80' : '#666') + ';flex-shrink:0;">' + (lift || '(baseline)') + '</div>' +
      '</div>';
  }
  if (MODEL_DATA.brier != null) {
    html += '<div style="font-size:11px;color:#8899aa;margin-top:2px;">Brier score: ' + MODEL_DATA.brier.toFixed(4) + ' (calibration quality; lower is better)</div>';
  }
  container.innerHTML = html;
}

function populateTeamSelectors() {
  const selA = document.getElementById('model-team-a');
  const selB = document.getElementById('model-team-b');
  if (!selA || !selB) return;

  const sorted = Object.entries(TEAMS).sort((a, b) =>
    a[1].seed !== b[1].seed ? a[1].seed - b[1].seed : a[0].localeCompare(b[0])
  );

  selA.innerHTML = '<option value="">— Pick Team —</option>';
  selB.innerHTML = '<option value="">— Pick Team —</option>';
  sorted.forEach(([name, d]) => {
    const txt = '(' + d.seed + ') ' + name;
    selA.appendChild(new Option(txt, name));
    selB.appendChild(new Option(txt, name));
  });

  if (sorted.length >= 17) {
    selA.value = sorted[0][0];
    selB.value = sorted[16][0];
  }
  selA.addEventListener('change', updateModelPrediction);
  selB.addEventListener('change', updateModelPrediction);
  updateModelPrediction();
}

function safeTop25Pct(t) {
  const w = t.top25_wins || 0, l = t.top25_losses || 0, g = w + l;
  return g >= 4 ? w / g : 0.0;
}

function computeModelPrediction(aName, bName) {
  const a = TEAMS[aName], b = TEAMS[bName];
  if (!a || !b || !MODEL_DATA || !(MODEL_DATA.coefficients || []).length) return null;

  const favIsA = a.seed <= b.seed;
  const fav = favIsA ? a : b, dog = favIsA ? b : a;
  // All differentials are computed as (underdog - favorite), matching features.py.
  // Exception: top25_winpct_diff = favorite - underdog (see features.py line ~107).
  const sd      = dog.seed    - fav.seed;               // +15 for 1v16
  const aemDiff = (dog.adj_em || 0) - (fav.adj_em || 0); // negative for strong fav

  const rawFeatures = {
    seed_diff:          sd,
    adj_em_diff:        aemDiff,
    adj_o_diff:         (dog.adj_o || 0) - (fav.adj_o || 0),
    adj_t_diff:         (dog.adj_t || 0) - (fav.adj_t || 0),
    seed_x_adj_em:      sd * aemDiff,
    top25_winpct_diff:  safeTop25Pct(fav) - safeTop25Pct(dog),  // fav - dog (exception)
    dog_top25_winpct:   safeTop25Pct(dog),
    barthag_diff:       (dog.barthag || 0) - (fav.barthag || 0),
    wab_diff:           (dog.wab || 0) - (fav.wab || 0),
    momentum_diff:      0,
    dog_momentum:       0,
    dog_last10_winpct:  0.5,
    spread:             0,
    spread_vs_expected: 0,
  };

  const names = MODEL_DATA.feature_names;
  const coefs = MODEL_DATA.coefficients;
  const means = MODEL_DATA.scaler_mean;
  const stds  = MODEL_DATA.scaler_std;

  let logOdds = MODEL_DATA.intercept || 0;
  const contributions = names.map((name, i) => {
    const raw     = rawFeatures[name] !== undefined ? rawFeatures[name] : 0;
    const scaled  = (stds[i] > 0) ? (raw - means[i]) / stds[i] : 0;
    const contrib = coefs[i] * scaled;
    logOdds += contrib;
    return { name, raw, scaled, contrib };
  });

  const pUpset  = Math.max(0.01, Math.min(0.99, 1 / (1 + Math.exp(-logOdds))));
  const pAWins  = favIsA ? 1 - pUpset : pUpset;
  return { pAWins, pUpset, logOdds, contributions, favIsA,
           favName: favIsA ? aName : bName, dogName: favIsA ? bName : aName };
}

function updateModelPrediction() {
  const aName = (document.getElementById('model-team-a') || {}).value;
  const bName = (document.getElementById('model-team-b') || {}).value;
  const resultEl   = document.getElementById('model-result');
  const featuresEl = document.getElementById('model-features');
  if (!resultEl || !featuresEl) return;

  if (!aName || !bName || aName === bName) {
    resultEl.innerHTML   = '<div style="color:#888;font-size:12px;text-align:center;padding:16px;">Select two different teams above.</div>';
    featuresEl.innerHTML = '';
    return;
  }

  const r = computeModelPrediction(aName, bName);
  if (!r) {
    resultEl.innerHTML   = '<div style="color:#888;font-size:12px;padding:12px;">Model not available &mdash; run <code>python upset_model/train_sklearn.py</code> to enable.</div>';
    featuresEl.innerHTML = '';
    return;
  }

  const aData = TEAMS[aName], bData = TEAMS[bName];
  // Use calibrated matchup probability when available (matches bracket "Model win prob")
  const matchupProb = (MATCHUPS[aName] && MATCHUPS[aName][bName] != null)
    ? MATCHUPS[aName][bName]
    : (MATCHUPS[bName] && MATCHUPS[bName][aName] != null)
      ? 1 - MATCHUPS[bName][aName]
      : null;
  const pAWins   = matchupProb != null ? matchupProb : r.pAWins;
  const calibrated = matchupProb != null;
  const pctA  = (pAWins * 100).toFixed(1);
  const pctB  = (100 - pAWins * 100).toFixed(1);
  const colA  = pAWins >= 0.5 ? '#4ade80' : '#f87171';
  const colB  = pAWins <  0.5 ? '#4ade80' : '#f87171';

  resultEl.innerHTML =
    '<div style="display:flex;align-items:center;justify-content:center;background:#16213e;border-radius:10px;padding:14px 20px;gap:0;">' +
      '<div style="flex:1;text-align:right;">' +
        '<div style="font-size:12px;color:#bbb;margin-bottom:3px;">(' + aData.seed + ') ' + aName + '</div>' +
        '<div style="font-size:38px;font-weight:800;color:' + colA + ';line-height:1;">' + pctA + '%</div>' +
        '<div style="font-size:11px;color:#8899aa;margin-top:3px;">' + (aData.conference || '') + ' &middot; ' + aData.record + '</div>' +
      '</div>' +
      '<div style="padding:0 22px;color:#555;font-size:18px;">vs</div>' +
      '<div style="flex:1;text-align:left;">' +
        '<div style="font-size:12px;color:#bbb;margin-bottom:3px;">(' + bData.seed + ') ' + bName + '</div>' +
        '<div style="font-size:38px;font-weight:800;color:' + colB + ';line-height:1;">' + pctB + '%</div>' +
        '<div style="font-size:11px;color:#8899aa;margin-top:3px;">' + (bData.conference || '') + ' &middot; ' + bData.record + '</div>' +
      '</div>' +
    '</div>' +
    '<div style="font-size:10px;color:#556677;text-align:center;margin-top:6px;">' +
      (calibrated ? '\u2020 Calibrated ensemble model' : '\u2020 Logistic regression (uncalibrated)') +
    '</div>';

  renderFeatureContribs(r, aName, bName, featuresEl);
}

function renderFeatureContribs(r, aName, bName, container) {
  const sign     = r.favIsA ? -1 : 1; // flip if A is favorite (upset goes against A)
  const adjusted = r.contributions.map(c => ({ ...c, aContrib: c.contrib * sign }));
  const maxAbs   = Math.max(...adjusted.map(c => Math.abs(c.contrib)), 0.01);

  let html =
    '<div style="font-size:11px;color:#8899aa;text-transform:uppercase;letter-spacing:0.5px;margin:14px 0 4px;">' +
      'Feature Contributions &mdash; pull toward <b style="color:#fff;">' + aName + '</b> winning' +
    '</div>' +
    '<div style="font-size:11px;color:#8899aa;margin-bottom:10px;">' +
      (r.favIsA
        ? aName + ' is the <b style="color:#ccc;">favorite</b>. Green bars push toward ' + aName + ' winning; red bars push toward ' + bName + ' winning.'
        : aName + ' is the <b style="color:#ccc;">underdog</b>. Green bars push toward ' + aName + ' winning; red bars push toward ' + bName + ' winning.') +
    '</div>';

  const zeroRaw = adjusted.filter(c => c.raw === 0);
  const nonZero = adjusted.filter(c => c.raw !== 0);
  const sorted  = [...nonZero].sort((a, b) => Math.abs(b.contrib) - Math.abs(a.contrib));

  html += '<div>';
  for (const f of sorted) {
    const barPct  = (Math.abs(f.contrib) / maxAbs * 44).toFixed(1);
    const isGreen = f.aContrib >= 0;
    const barCol  = isGreen ? '#4ade80' : '#f87171';
    const label   = FEATURE_LABELS[f.name] || f.name;
    const rawStr  = typeof f.raw === 'number'
      ? (Math.abs(f.raw) < 0.005 ? '0.00' : (f.raw >= 0 ? '+' + f.raw.toFixed(2) : f.raw.toFixed(2)))
      : '\u2014';
    const cStr = (f.aContrib >= 0 ? '+' : '') + f.aContrib.toFixed(3);

    html +=
      '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">' +
        '<div style="width:175px;font-size:11px;color:#ccc;text-align:right;flex-shrink:0;">' + label + '</div>' +
        '<div style="width:48px;font-size:10px;color:#8899aa;text-align:right;flex-shrink:0;">' + rawStr + '</div>' +
        '<div style="flex:1;position:relative;height:16px;">' +
          '<div style="position:absolute;left:50%;top:0;width:1px;height:100%;background:#2a3a4a;"></div>' +
          (isGreen
            ? '<div style="position:absolute;left:50%;top:2px;width:' + barPct + '%;height:12px;background:' + barCol + ';border-radius:0 3px 3px 0;opacity:0.8;"></div>'
            : '<div style="position:absolute;right:50%;top:2px;width:' + barPct + '%;height:12px;background:' + barCol + ';border-radius:3px 0 0 3px;opacity:0.8;"></div>') +
        '</div>' +
        '<div style="width:55px;font-size:10px;color:' + barCol + ';flex-shrink:0;">' + cStr + '</div>' +
      '</div>';
  }
  html += '</div>';

  if (zeroRaw.length > 0) {
    const zeroNames = zeroRaw.map(c => FEATURE_LABELS[c.name] || c.name).join(', ');
    html += '<div style="font-size:10px;color:#556677;margin-top:6px;">' +
      '\u2020 Not shown (zero input): ' + zeroNames + '. Their effect is included in Log-odds below.' +
    '</div>';
  }

  html +=
    '<div style="font-size:11px;color:#8899aa;border-top:1px solid #1e2d3d;padding-top:8px;margin-top:8px;">' +
      'Log-odds = ' + r.logOdds.toFixed(3) +
      ' &rarr; P(upset) = ' + (r.pUpset * 100).toFixed(1) + '%' +
      ' &rarr; P(' + aName + ' wins) = <b style="color:#fff;">' + (r.pAWins * 100).toFixed(1) + '%</b>' +
    '</div>';

  container.innerHTML = html;
}

// ── Init ──
populateSelector();
renderBracket(0);
initModelModal();
</script>
</body>
</html>
"""


# ============================================================================
# MAIN OUTPUT ORCHESTRATOR
# ============================================================================

def generate_all_output(brackets: list[CompleteBracket], teams: list[Team],
                        ownership_profiles: list[OwnershipProfile],
                        matchup_matrix: dict[str, dict[str, float]],
                        bracket_structure: BracketStructure, config) -> None:
    """Run the full output pipeline. Generates 5 output files."""
    logger.info("=== Generating output files ===")

    ensure_dir(config.output_dir)

    optimal = next((b for b in brackets if b.label == "optimal"), brackets[0])

    # 1. analysis.md (comprehensive, uses all brackets)
    analysis = generate_analysis_report(brackets, teams, ownership_profiles, matchup_matrix)
    analysis_file = f"{config.output_dir}/analysis.md"
    with open(analysis_file, 'w', encoding='utf-8') as f:
        f.write(analysis)
    logger.info(f"Saved analysis to {analysis_file}")

    # 2. bracket.txt (ASCII, optimal only)
    ascii_bracket = generate_ascii_bracket(optimal, bracket_structure)
    bracket_file = f"{config.output_dir}/bracket.txt"
    with open(bracket_file, 'w', encoding='utf-8') as f:
        f.write(ascii_bracket)
    logger.info(f"Saved ASCII bracket to {bracket_file}")

    # 3. summary.json (enhanced with aggregate stats)
    summary = generate_summary_json(brackets)
    summary_file = f"{config.output_dir}/summary.json"
    save_json(summary, summary_file)
    logger.info(f"Saved summary to {summary_file}")

    # 4. all_brackets.json (every bracket with full picks)
    all_brackets_file = f"{config.output_dir}/all_brackets.json"
    save_json([b.to_dict() for b in brackets], all_brackets_file)
    logger.info(f"Saved all {len(brackets)} brackets to {all_brackets_file}")

    # 5. index.html (interactive viewer)
    html = generate_bracket_html(brackets, bracket_structure, teams, ownership_profiles, matchup_matrix)
    html_file = f"{config.output_dir}/index.html"
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html)
    logger.info(f"Saved interactive bracket viewer to {html_file}")

    logger.info(f"=== Output generation complete ({len(brackets)} brackets) ===")
