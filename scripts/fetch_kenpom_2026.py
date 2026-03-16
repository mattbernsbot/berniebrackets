#!/usr/bin/env python3
"""
Fetch live 2026 KenPom ratings.
"""

import json
import sys
from pathlib import Path
import requests
from bs4 import BeautifulSoup
import re

project_root = Path(__file__).parent.parent

KENPOM_URL = "https://kenpom.com"

def fetch_kenpom() -> list:
    """Scrape KenPom ratings."""
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Encoding': 'identity',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    print(f"Fetching {KENPOM_URL}...")
    response = requests.get(KENPOM_URL, headers=headers, timeout=30)
    response.raise_for_status()
    print(f"✓ Received {len(response.text)} bytes")
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Find ratings table
    table = soup.find('table', {'id': 'ratings-table'})
    if not table:
        # Try finding first table on page
        table = soup.find('table')
    
    if not table:
        print("ERROR: No table found")
        return []
    
    teams = []
    rows = table.find_all('tr')[1:]  # Skip header
    
    print(f"\nParsing {len(rows)} rows...")
    
    for idx, row in enumerate(rows, 1):
        cells = row.find_all('td')
        if len(cells) < 10:
            continue
        
        try:
            # Rank
            rank_text = cells[0].get_text(strip=True)
            rank = int(rank_text) if rank_text.isdigit() else idx
            
            # Team name
            team_link = cells[1].find('a')
            team_name = team_link.get_text(strip=True) if team_link else cells[1].get_text(strip=True)
            
            # Conference
            conference = cells[2].get_text(strip=True)
            
            # W-L
            wl_text = cells[3].get_text(strip=True)
            wl_match = re.match(r'(\d+)-(\d+)', wl_text)
            wins = int(wl_match.group(1)) if wl_match else 0
            losses = int(wl_match.group(2)) if wl_match else 0
            
            # Stats
            def parse_float(idx):
                try:
                    return float(cells[idx].get_text(strip=True))
                except (ValueError, IndexError):
                    return 0.0
            
            adj_em = parse_float(4)
            adj_o = parse_float(5)
            adj_d = parse_float(6)
            adj_t = parse_float(7)
            sos = parse_float(9)
            
            team_data = {
                "rank": rank,
                "team": team_name,
                "conference": conference,
                "wins": wins,
                "losses": losses,
                "adj_em": adj_em,
                "adj_o": adj_o,
                "adj_d": adj_d,
                "adj_t": adj_t,
                "sos": sos
            }
            
            teams.append(team_data)
            
            if idx <= 70:  # Print top 70
                print(f"  {rank:3d}. {team_name:25s} {adj_em:6.2f} AdjEM")
        
        except Exception as e:
            print(f"  Error parsing row {idx}: {e}")
            continue
    
    print(f"\n✓ Parsed {len(teams)} teams")
    return teams


def main():
    teams = fetch_kenpom()
    
    if len(teams) < 300:
        print(f"\n⚠ WARNING: Only got {len(teams)} teams, expected 360+")
    
    # Save to JSON
    output_file = project_root / "data" / "kenpom_2026_live.json"
    with open(output_file, 'w') as f:
        json.dump(teams, f, indent=2)
    
    print(f"\n✓ Saved to {output_file}")
    print(f"✅ SUCCESS: Fetched {len(teams)} teams from KenPom")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
