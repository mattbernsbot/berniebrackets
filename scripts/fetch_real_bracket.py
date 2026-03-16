#!/usr/bin/env python3
"""
Fetch and parse the REAL 2026 NCAA tournament bracket from ncaa.com
NO SYNTHETIC DATA - extracts all 68 teams with their seeds and regions.
"""

import json
import re
import sys
import urllib.request
from pathlib import Path
from bs4 import BeautifulSoup

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

NCAA_BRACKET_URL = "https://www.ncaa.com/brackets/basketball-men/d1/2026"

def fetch_url(url: str, timeout: int = 30) -> str:
    """Fetch URL content with proper headers."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Encoding': 'identity',
        'Accept-Language': 'en-US,en;q=0.9',
    }

    print(f"Fetching {url}...")
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        text = response.read().decode('utf-8')
    print(f"✓ Received {len(text)} bytes")
    return text


def parse_bracket_wrapper_text(text: str) -> dict:
    """Parse the bracket-wrapper div text content.
    
    The structure is: REGION followed by seed-team pairs like "1Duke16Siena8Ohio St.9TCU"
    Each region has 16 teams (seeds 1-16).
    """
    
    # Find all region sections
    regions = {}
    region_pattern = r'(EAST|WEST|SOUTH|MIDWEST)\s*(.*?)(?=(?:EAST|WEST|SOUTH|MIDWEST)|$)'
    
    matches = re.findall(region_pattern, text, re.DOTALL | re.IGNORECASE)
    
    for region_name, region_text in matches:
        region_name = region_name.upper()
        print(f"\n=== Parsing {region_name} ===")
        
        # Clean the region text
        region_text = re.sub(r'\s+', ' ', region_text).strip()
        
        teams = []
        
        # Pattern: seed(1-16) followed by team name
        # Team name continues until next digit that's a valid seed (1-16)
        # Use lookahead to find boundaries
        
        # Build pattern that captures seed and team name
        # Seeds appear in matchup order: 1,16,8,9,5,12,4,13,6,11,3,14,7,10,2,15
        seed_order = [1, 16, 8, 9, 5, 12, 4, 13, 6, 11, 3, 14, 7, 10, 2, 15]
        
        # Extract all seed-team pairs
        # Pattern: number (1-16) followed by letters/spaces until next number
        pattern = r'(\d+)([A-Za-z][A-Za-z\s.&\'-]*?)(?=\d+|$)'
        pairs = re.findall(pattern, region_text)
        
        position = 1
        for seed_str, team_name in pairs:
            seed = int(seed_str)
            if 1 <= seed <= 16:
                team_name = team_name.strip()
                if team_name:
                    teams.append({
                        "seed": seed,
                        "team": team_name,
                        "position": position
                    })
                    print(f"  ({seed}) {team_name}")
                    position += 1
        
        if len(teams) >= 16:
            regions[region_name] = teams[:16]  # Take first 16
        else:
            print(f"⚠ WARNING: Only found {len(teams)} teams in {region_name}, expected 16")
            regions[region_name] = teams
    
    return regions


def parse_bracket_with_classes(soup: BeautifulSoup) -> dict:
    """Parse bracket using HTML structure and CSS classes."""
    
    regions = {}
    
    # Look for region containers
    region_containers = soup.find_all('div', class_=re.compile(r'region', re.I))
    
    for container in region_containers:
        # Try to find region name
        region_header = container.find(['h2', 'h3', 'div'], class_=re.compile(r'region.*title|header', re.I))
        if region_header:
            region_name = region_header.get_text(strip=True).upper()
            if region_name in ['EAST', 'WEST', 'SOUTH', 'MIDWEST']:
                print(f"\n=== Parsing {region_name} (HTML structure) ===")
                
                # Find all team/matchup elements
                teams = []
                
                # Look for team/seed containers
                team_elements = container.find_all(['div', 'span'], class_=re.compile(r'team|seed|matchup', re.I))
                
                for elem in team_elements:
                    text = elem.get_text(strip=True)
                    # Try to extract seed and team
                    match = re.match(r'(\d+)\s*(.+)', text)
                    if match:
                        seed = int(match.group(1))
                        team = match.group(2).strip()
                        if 1 <= seed <= 16 and team:
                            teams.append({
                                "seed": seed,
                                "team": team,
                                "position": len(teams) + 1
                            })
                            print(f"  ({seed}) {team}")
                
                if teams:
                    regions[region_name] = teams
    
    return regions


def parse_embedded_json(html: str) -> dict:
    """Look for embedded JSON data (e.g., __INITIAL_STATE__, __NEXT_DATA__)."""
    
    # Common patterns for embedded data
    patterns = [
        r'__INITIAL_STATE__\s*=\s*({.*?});',
        r'__NEXT_DATA__\s*=\s*({.*?});',
        r'window\.__data\s*=\s*({.*?});',
        r'bracketData\s*=\s*({.*?});',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, html, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                print(f"✓ Found embedded JSON with pattern: {pattern[:30]}...")
                return data
            except json.JSONDecodeError:
                continue
    
    return {}


def extract_teams_from_json(data: dict, path: list = None, depth: int = 0) -> dict:
    """Recursively search JSON for bracket data."""
    
    if path is None:
        path = []
    
    if depth > 10:  # Prevent infinite recursion
        return {}
    
    regions = {}
    
    # Check if current level has region data
    if isinstance(data, dict):
        # Look for region keys
        for region_name in ['EAST', 'WEST', 'SOUTH', 'MIDWEST', 'east', 'west', 'south', 'midwest']:
            if region_name.upper() in [k.upper() for k in data.keys()]:
                # Found a region
                region_data = data.get(region_name) or data.get(region_name.upper()) or data.get(region_name.lower())
                if isinstance(region_data, list):
                    teams = []
                    for item in region_data:
                        if isinstance(item, dict):
                            seed = item.get('seed') or item.get('Seed')
                            team = item.get('team') or item.get('Team') or item.get('name') or item.get('Name')
                            if seed and team:
                                teams.append({
                                    "seed": int(seed),
                                    "team": str(team),
                                    "position": len(teams) + 1
                                })
                    if teams:
                        regions[region_name.upper()] = teams
        
        # Recursively search nested dicts
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                nested_regions = extract_teams_from_json(value, path + [key], depth + 1)
                if nested_regions and not regions:
                    regions = nested_regions
    
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, (dict, list)):
                nested_regions = extract_teams_from_json(item, path, depth + 1)
                if nested_regions and not regions:
                    regions = nested_regions
    
    return regions


def find_play_in_games(html: str, soup: BeautifulSoup) -> list:
    """Find First Four / play-in games."""
    
    play_in = []
    
    # Look for "First Four" or "Play-In" section
    first_four_pattern = r'(?:First Four|Play-?In|FIRST FOUR|PLAY-?IN)(.*?)(?:EAST|WEST|SOUTH|MIDWEST|$)'
    match = re.search(first_four_pattern, html, re.DOTALL | re.IGNORECASE)
    
    if match:
        section_text = match.group(1)
        # Extract team pairs
        teams = re.findall(r'(\d+)\s*([A-Za-z][A-Za-z\s.&\'-]+?)(?=\d+|vs|$)', section_text)
        
        # Group into pairs
        for i in range(0, len(teams) - 1, 2):
            seed_a, team_a = teams[i]
            seed_b, team_b = teams[i + 1] if i + 1 < len(teams) else (seed_a, "TBD")
            
            play_in.append({
                "seed": int(seed_a),
                "team_a": team_a.strip(),
                "team_b": team_b.strip(),
                "region": "TBD"  # Will be determined by where winner goes
            })
    
    return play_in


def main():
    # Fetch the bracket page
    html = fetch_url(NCAA_BRACKET_URL)
    
    # Save raw HTML for inspection
    debug_file = project_root / "data" / "ncaa_bracket_2026_raw.html"
    debug_file.parent.mkdir(exist_ok=True)
    debug_file.write_text(html, encoding='utf-8')
    print(f"\n✓ Saved raw HTML to {debug_file}")
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Method 1: Try embedded JSON
    print("\n=== Method 1: Searching for embedded JSON ===")
    json_data = parse_embedded_json(html)
    regions = {}
    
    if json_data:
        regions = extract_teams_from_json(json_data)
        if regions:
            print(f"✓ Extracted {len(regions)} regions from JSON")
    
    # Method 2: Parse bracket-wrapper div text
    if not regions or sum(len(teams) for teams in regions.values()) < 64:
        print("\n=== Method 2: Parsing bracket-wrapper text ===")
        bracket_wrapper = soup.find('div', class_='bracket-wrapper')
        if bracket_wrapper:
            wrapper_text = bracket_wrapper.get_text()
            regions_text = parse_bracket_wrapper_text(wrapper_text)
            if regions_text and sum(len(teams) for teams in regions_text.values()) > sum(len(teams) for teams in regions.values()):
                regions = regions_text
    
    # Method 3: Parse with HTML structure
    if not regions or sum(len(teams) for teams in regions.values()) < 64:
        print("\n=== Method 3: Parsing HTML structure ===")
        regions_html = parse_bracket_with_classes(soup)
        if regions_html and sum(len(teams) for teams in regions_html.values()) > sum(len(teams) for teams in regions.values()):
            regions = regions_html
    
    # Find play-in games
    play_in = find_play_in_games(html, soup)
    
    # Verify team count
    total_teams = sum(len(teams) for teams in regions.values())
    print(f"\n=== RESULTS ===")
    print(f"Total teams extracted: {total_teams}")
    
    for region, teams in regions.items():
        print(f"{region}: {len(teams)} teams")
    
    if play_in:
        print(f"Play-in games: {len(play_in)}")
    
    # Build output structure
    output = {
        "source": "ncaa.com",
        "url": NCAA_BRACKET_URL,
        "year": 2026,
        "regions": regions,
        "play_in": play_in
    }
    
    # Save to JSON
    output_file = project_root / "data" / "real_bracket_2026.json"
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n✓ Saved bracket to {output_file}")
    
    # Validation
    if total_teams < 64:
        print(f"\n⚠ WARNING: Only extracted {total_teams}/64 teams")
        print("Manual inspection of HTML required.")
        return 1
    
    print(f"\n✅ SUCCESS: Extracted all {total_teams} teams from real bracket")
    return 0


if __name__ == "__main__":
    sys.exit(main())
