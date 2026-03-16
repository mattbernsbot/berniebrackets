#!/usr/bin/env python3
"""Scrape ESPN Tournament Challenge pick percentages using Playwright.

Run this once pick data is populated (usually Monday-Wednesday before tourney).
Saves to data/espn_picks_2026.json

Usage: python3 scripts/scrape_espn_picks.py
"""

import json
import os
import sys

def scrape_picks():
    from playwright.sync_api import sync_playwright
    
    captured = {}
    
    def handle_response(response):
        url = response.url
        if 'propositions' in url and response.status == 200:
            try:
                data = response.json()
                if isinstance(data, list) and len(data) > 1:
                    captured['propositions'] = data
                    print(f"  Captured {len(data)} propositions")
            except:
                pass
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.on('response', handle_response)
        
        print("Loading ESPN Who Picked Whom...")
        page.goto(
            'https://fantasy.espn.com/tournament-challenge-bracket/2026/en/whopickedwhom',
            timeout=30000
        )
        page.wait_for_timeout(10000)
        
        # Try clicking through rounds if needed
        for round_name in ['Round of 64', 'Round of 32', 'Sweet 16', 'Elite 8', 'Final Four', 'Championship']:
            try:
                btn = page.query_selector(f'text="{round_name}"')
                if btn:
                    btn.click()
                    page.wait_for_timeout(3000)
            except:
                pass
        
        browser.close()
    
    if 'propositions' not in captured:
        print("\n⚠ No pick data found yet. ESPN may not have enough brackets submitted.")
        print("  Try again later (usually Monday-Wednesday).")
        return None
    
    # Parse into clean format
    picks = []
    for prop in captured['propositions']:
        outcomes = prop.get('outcomes', [])
        if len(outcomes) != 2:
            continue
        
        game = {
            'id': prop.get('id', ''),
            'round': prop.get('displayOrder', 0),
            'team_a': {
                'name': outcomes[0].get('name', ''),
                'seed': outcomes[0].get('seed', 0),
                'pick_pct': outcomes[0].get('pickPercent', 0),
            },
            'team_b': {
                'name': outcomes[1].get('name', ''),
                'seed': outcomes[1].get('seed', 0),
                'pick_pct': outcomes[1].get('pickPercent', 0),
            }
        }
        picks.append(game)
    
    # Save
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, 'espn_picks_2026.json')
    
    with open(output_path, 'w') as f:
        json.dump(picks, f, indent=2)
    
    print(f"\n✅ Saved {len(picks)} matchup pick percentages to {output_path}")
    
    # Print summary
    print("\nSample matchups:")
    for g in picks[:10]:
        a = g['team_a']
        b = g['team_b']
        print(f"  ({a['seed']}) {a['name']}: {a['pick_pct']}% vs ({b['seed']}) {b['name']}: {b['pick_pct']}%")
    
    return picks

if __name__ == '__main__':
    scrape_picks()
