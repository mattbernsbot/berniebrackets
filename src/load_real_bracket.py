"""
Load real NCAA bracket and match with KenPom stats.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional
from src.models import Team, BracketStructure, BracketSlot
from src.constants import BRACKET_SEED_ORDER
from src.name_matching import normalize_team_name, match_team_name as _match_name


def match_team_name(bracket_name: str, kenpom_teams: List[Dict]) -> Optional[Dict]:
    """Find best match for a team in KenPom data."""
    team_names = [t['name'] for t in kenpom_teams]
    matched = _match_name(bracket_name, team_names, source="generic")
    if matched:
        for t in kenpom_teams:
            if t['name'] == matched:
                return t
    return None


def load_real_bracket(
    bracket_file: str,
    kenpom_file: str,
    first_four_winners: Optional[List[str]] = None
) -> tuple[List[Team], BracketStructure]:
    """Load real bracket and match with KenPom data.
    
    Args:
        bracket_file: Path to real_bracket_2026.json
        kenpom_file: Path to teams.json (KenPom data)
    
    Returns:
        Tuple of (team list, bracket structure)
    """
    
    # Load real bracket
    with open(bracket_file) as f:
        bracket_data = json.load(f)
    
    # Load KenPom data
    with open(kenpom_file) as f:
        kenpom_teams = json.load(f)
    
    print(f"Loaded {len(kenpom_teams)} teams from KenPom")
    print(f"Real bracket has {sum(len(t) for t in bracket_data['regions'].values())} teams")

    # Resolve First Four: build set of play-in losers to exclude
    play_in_losers = set()
    winners = set(first_four_winners or [])
    for game in bracket_data.get('play_in', []):
        team_a, team_b = game['team_a'], game['team_b']
        if team_a in winners:
            play_in_losers.add(team_b)
        elif team_b in winners:
            play_in_losers.add(team_a)
        else:
            # Game not yet played — default to team_a
            play_in_losers.add(team_b)
    if play_in_losers:
        print(f"First Four losers excluded: {play_in_losers}")

    # Create team objects
    teams = []
    team_by_name = {}
    unmatched = []

    for region_name, region_teams in bracket_data['regions'].items():
        print(f"\n{region_name}:")
        
        for team_data in region_teams:
            bracket_name = team_data['team']
            seed = team_data['seed']
            is_play_in = team_data.get('play_in', False)

            if bracket_name in play_in_losers:
                continue

            # Match with KenPom
            kenpom_match = match_team_name(bracket_name, kenpom_teams)
            
            if kenpom_match:
                team = Team(
                    name=bracket_name,  # Use bracket name
                    seed=seed,
                    region=region_name,
                    kenpom_rank=kenpom_match.get('kenpom_rank', 0),
                    adj_em=kenpom_match.get('adj_em', 0.0),
                    adj_o=kenpom_match.get('adj_o', 0.0),
                    adj_d=kenpom_match.get('adj_d', 0.0),
                    adj_t=kenpom_match.get('adj_t', 0.0),
                    luck=kenpom_match.get('luck', 0.0),
                    sos=kenpom_match.get('sos', 0.0),
                    wins=kenpom_match.get('wins', 0),
                    losses=kenpom_match.get('losses', 0),
                    conference=kenpom_match.get('conference', ''),
                    bracket_position=len(teams) + 1
                )
                print(f"  ({seed:2d}) {bracket_name:25s} = {kenpom_match['name']:25s} AdjEM:{team.adj_em:6.2f}")
            else:
                # No KenPom match - use seed-based estimate
                estimated_em = 25.0 - (seed * 1.5)  # Rough estimate
                team = Team(
                    name=bracket_name,
                    seed=seed,
                    region=region_name,
                    kenpom_rank=seed * 20,  # Rough estimate
                    adj_em=estimated_em,
                    adj_o=110.0,
                    adj_d=110.0 - estimated_em,
                    adj_t=68.0,
                    sos=0.0,
                    wins=20,
                    losses=10,
                    conference='',
                    bracket_position=len(teams) + 1
                )
                print(f"  ({seed:2d}) {bracket_name:25s} ⚠ NO KENPOM MATCH (estimated AdjEM:{estimated_em:.2f})")
                unmatched.append(bracket_name)
            
            teams.append(team)
            team_by_name[bracket_name] = team
    
    if unmatched:
        print(f"\n⚠ WARNING: {len(unmatched)} teams not matched to KenPom:")
        for name in unmatched:
            print(f"  - {name}")
    
    # Build bracket structure
    slots = []
    slot_id = 1
    
    # Round 1 - 32 games (8 per region)
    region_names = ["East", "West", "South", "Midwest"]
    for region_idx, region in enumerate(region_names):
        for seed_pair in BRACKET_SEED_ORDER:
            # Find teams in this matchup
            team_a = None
            team_b = None
            
            for t in teams:
                if t.region == region.upper() and t.seed == seed_pair[0]:
                    team_a = t.name
                if t.region == region.upper() and t.seed == seed_pair[1]:
                    team_b = t.name
            
            slot = BracketSlot(
                slot_id=slot_id,
                round_num=1,
                region=region,
                seed_a=seed_pair[0],
                seed_b=seed_pair[1],
                team_a=team_a,
                team_b=team_b,
                feeds_into=33 + region_idx * 4 + (slot_id - 1 - region_idx * 8) // 2
            )
            slots.append(slot)
            slot_id += 1
    
    # Rounds 2-6 (simplified - empty for now)
    for region_idx, region in enumerate(region_names):
        for i in range(4):
            slots.append(BracketSlot(slot_id=slot_id, round_num=2, region=region,
                seed_a=0, seed_b=0, feeds_into=49 + region_idx * 2 + i // 2))
            slot_id += 1
    
    for region_idx, region in enumerate(region_names):
        for i in range(2):
            slots.append(BracketSlot(slot_id=slot_id, round_num=3, region=region,
                seed_a=0, seed_b=0, feeds_into=57 + region_idx))
            slot_id += 1
    
    for region_idx, region in enumerate(region_names):
        slots.append(BracketSlot(slot_id=slot_id, round_num=4, region=region,
            seed_a=0, seed_b=0, feeds_into=61 if region_idx % 2 == 0 else 62))  # East+South vs West+Midwest
        slot_id += 1
    
    for i in range(2):
        slots.append(BracketSlot(slot_id=slot_id, round_num=5, region="FinalFour",
            seed_a=0, seed_b=0, feeds_into=63))
        slot_id += 1
    
    slots.append(BracketSlot(slot_id=63, round_num=6, region="FinalFour",
        seed_a=0, seed_b=0, feeds_into=0))
    
    # Build regions dict for BracketStructure
    regions_dict = {region.upper(): [] for region in region_names}
    for team in teams:
        if team.region in regions_dict:
            regions_dict[team.region].append(team.name)
    
    bracket = BracketStructure(
        slots=slots,
        regions=regions_dict,
        play_in_games=[]
    )
    
    print(f"\n✅ Loaded {len(teams)} teams from real bracket")
    print(f"   Matched: {len(teams) - len(unmatched)}")
    print(f"   Unmatched: {len(unmatched)}")
    
    return teams, bracket
