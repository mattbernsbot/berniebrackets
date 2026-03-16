#!/usr/bin/env python3
"""
Parse the NCAA bracket HTML using BeautifulSoup to extract all teams.
This parser reads the saved HTML file and extracts teams from game-pod divs.
"""

import json
import sys
from pathlib import Path
from bs4 import BeautifulSoup
from collections import defaultdict

project_root = Path(__file__).parent.parent

def parse_game_pod(pod):
    """Extract teams from a single game-pod div."""
    teams = []
    
    # Find all team divs
    team_divs = pod.find_all('div', class_=lambda c: c and 'team' in c and 'empty' not in c)
    
    for team_div in team_divs:
        # Get seed
        seed_span = team_div.find('span', class_='overline')
        if not seed_span:
            continue
        
        seed_text = seed_span.get_text(strip=True)
        if not seed_text or not seed_text.isdigit():
            continue
        
        seed = int(seed_text)
        
        # Get team name (first body paragraph)
        team_p = team_div.find('p', class_='body')
        if not team_p:
            continue
        
        team_name = team_p.get_text(strip=True)
        if not team_name:
            continue
        
        teams.append({'seed': seed, 'team': team_name})
    
    return teams


def parse_bracket_html(html_path: Path) -> dict:
    """Parse the NCAA bracket HTML file."""
    
    print(f"Loading HTML from {html_path}")
    html = html_path.read_text(encoding='utf-8')
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find all region containers
    regions = {}
    region_divs = soup.find_all('div', class_='region')
    
    print(f"\nFound {len(region_divs)} region divs")
    
    for region_div in region_divs:
        # Get region name from subtitle
        region_name_span = region_div.find('span', class_='subtitle')
        if not region_name_span:
            continue
        
        region_name = region_name_span.get_text(strip=True)
        
        # Skip if not a main region
        if region_name not in ['EAST', 'WEST', 'SOUTH', 'MIDWEST']:
            continue
        
        print(f"\n=== {region_name} ===")
        
        # Find all Round 1 game pods in this region
        round1_div = region_div.find('div', class_='region-round round-1')
        if not round1_div:
            print(f"  No round-1 div found")
            continue
        
        # Find all game pods
        game_pods = round1_div.find_all('a', class_='game-pod')
        print(f"  Found {len(game_pods)} game pods")
        
        region_teams = []
        
        for pod in game_pods:
            teams = parse_game_pod(pod)
            for team_data in teams:
                team_data['position'] = len(region_teams) + 1
                region_teams.append(team_data)
                print(f"  ({team_data['seed']}) {team_data['team']}")
        
        if region_teams:
            regions[region_name] = region_teams
    
    # Find First Four games
    print(f"\n=== FIRST FOUR ===")
    first_four_div = soup.find('div', class_='first-four')
    play_in = []
    
    if first_four_div:
        ff_pods = first_four_div.find_all('a', class_='game-pod')
        print(f"  Found {len(ff_pods)} First Four games")
        
        for idx, pod in enumerate(ff_pods):
            teams = parse_game_pod(pod)
            
            # Get region indicator (e.g., "MW", "W", "S")
            region_span = pod.find_next_sibling('span', class_='subtitle')
            region_code = region_span.get_text(strip=True) if region_span else "TBD"
            
            # Map region code to full name
            region_map = {'E': 'EAST', 'W': 'WEST', 'S': 'SOUTH', 'MW': 'MIDWEST'}
            full_region = region_map.get(region_code.strip(), "TBD")
            
            if len(teams) == 2:
                play_in_game = {
                    "seed": teams[0]['seed'],
                    "team_a": teams[0]['team'],
                    "team_b": teams[1]['team'],
                    "region": full_region
                }
                play_in.append(play_in_game)
                print(f"  ({teams[0]['seed']}) {teams[0]['team']} vs {teams[1]['team']} → {full_region}")
    
    return {
        "regions": regions,
        "play_in": play_in
    }


def main():
    html_file = project_root / "data" / "ncaa_bracket_2026_raw.html"
    
    if not html_file.exists():
        print(f"ERROR: {html_file} not found")
        return 1
    
    bracket_data = parse_bracket_html(html_file)
    
    # Add play-in teams to their regions
    # Each play-in game has 2 teams - we add both to the region count
    for game in bracket_data['play_in']:
        region = game['region']
        if region in bracket_data['regions']:
            # Add both teams from play-in to the region
            seed = game['seed']
            # Find max position in region
            max_pos = max((t['position'] for t in bracket_data['regions'][region]), default=0)
            
            bracket_data['regions'][region].append({
                'seed': seed,
                'team': game['team_a'],
                'position': max_pos + 1,
                'play_in': True
            })
            bracket_data['regions'][region].append({
                'seed': seed,
                'team': game['team_b'],
                'position': max_pos + 2,
                'play_in': True
            })
    
    # Count teams
    total_teams = sum(len(teams) for teams in bracket_data['regions'].values())
    
    print(f"\n=== RESULTS ===")
    print(f"Total teams: {total_teams} (including {len(bracket_data['play_in']) * 2} play-in teams)")
    for region, teams in bracket_data['regions'].items():
        main_count = len([t for t in teams if not t.get('play_in')])
        play_in_count = len([t for t in teams if t.get('play_in')])
        print(f"  {region}: {len(teams)} teams ({main_count} main + {play_in_count} play-in)")
    print(f"  Play-in games: {len(bracket_data['play_in'])}")
    
    # Build output
    output = {
        "source": "ncaa.com",
        "url": "https://www.ncaa.com/brackets/basketball-men/d1/2026",
        "year": 2026,
        "regions": bracket_data['regions'],
        "play_in": bracket_data['play_in']
    }
    
    # Save
    output_file = project_root / "data" / "real_bracket_2026.json"
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n✓ Saved to {output_file}")
    
    if total_teams < 64:
        print(f"\n⚠ WARNING: Only {total_teams}/64 teams extracted")
        return 1
    
    print(f"\n✅ SUCCESS: Extracted {total_teams} teams")
    return 0


if __name__ == "__main__":
    sys.exit(main())
