#!/usr/bin/env python3
"""Scrape real NCAA tournament data from Sports Reference.

This script fetches:
1. Tournament game results (seeds, scores, winners)
2. Advanced team statistics (SRS, SOS, ORtg, DRtg, pace)

Output:
- upset_model/data/real_tournament_games.json
- upset_model/data/real_team_stats.json
"""

import json
import time
import re
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from bs4 import BeautifulSoup


def fetch_url(url: str, max_retries: int = 3) -> str:
    """Fetch URL with proper headers and exponential backoff."""
    for attempt in range(max_retries):
        try:
            req = Request(url)
            req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            req.add_header('Accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8')
            req.add_header('Accept-Language', 'en-US,en;q=0.5')
            req.add_header('Accept-Encoding', 'identity')
            req.add_header('Connection', 'keep-alive')
            
            with urlopen(req, timeout=30) as response:
                return response.read().decode('utf-8')
                
        except HTTPError as e:
            if e.code == 429:
                wait_time = (2 ** attempt) * 5  # 5s, 10s, 20s
                print(f"  Rate limited, waiting {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(2)
    
    raise Exception("Max retries exceeded")


def scrape_tournament_year(year: int) -> list:
    """Scrape tournament games for a given year."""
    url = f'https://www.sports-reference.com/cbb/postseason/men/{year}-ncaa.html'
    
    print(f"Fetching {year} tournament data...")
    try:
        html = fetch_url(url)
        soup = BeautifulSoup(html, 'html.parser')
        
        games = []
        round_num = 0
        
        # Find all round divs
        for round_div in soup.find_all('div', class_='round'):
            round_num += 1
            
            # Find all game containers (div with no class, directly inside round)
            for game_div in round_div.find_all('div', recursive=False):
                # Each game has 2 team divs
                team_divs = game_div.find_all('div', recursive=False)
                
                if len(team_divs) != 2:
                    continue
                
                teams = []
                for team_div in team_divs:
                    # Check if this is the winner
                    is_winner = 'winner' in team_div.get('class', [])
                    
                    # Extract seed (first span)
                    seed_span = team_div.find('span')
                    seed = None
                    if seed_span:
                        try:
                            seed = int(seed_span.get_text().strip())
                        except ValueError:
                            pass
                    
                    # Extract team name (first <a> with /cbb/schools/ in href)
                    team_name = None
                    score = None
                    
                    links = team_div.find_all('a')
                    for i, link in enumerate(links):
                        href = link.get('href', '')
                        if i == 0 and '/cbb/schools/' in href:
                            team_name = link.get_text().strip()
                        elif i == 1:
                            # Second link is score (boxscore)
                            try:
                                score = int(link.get_text().strip())
                            except ValueError:
                                pass
                    
                    teams.append({
                        'seed': seed,
                        'team': team_name,
                        'score': score,
                        'is_winner': is_winner
                    })
                
                # Create game record
                if len(teams) == 2 and teams[0]['team'] and teams[1]['team']:
                    # Determine winner
                    if teams[0]['is_winner']:
                        winner_idx = 0
                    elif teams[1]['is_winner']:
                        winner_idx = 1
                    else:
                        # Fallback: higher score wins
                        if (teams[0]['score'] or 0) > (teams[1]['score'] or 0):
                            winner_idx = 0
                        else:
                            winner_idx = 1
                    
                    game = {
                        'year': year,
                        'round_num': round_num,
                        'seed_a': teams[0]['seed'],
                        'seed_b': teams[1]['seed'],
                        'team_a': teams[0]['team'],
                        'team_b': teams[1]['team'],
                        'score_a': teams[0]['score'],
                        'score_b': teams[1]['score'],
                        'winner': winner_idx
                    }
                    
                    # Check if it's an upset (higher seed wins)
                    if game['seed_a'] and game['seed_b']:
                        if winner_idx == 0:
                            game['is_upset'] = game['seed_a'] > game['seed_b']
                        else:
                            game['is_upset'] = game['seed_b'] > game['seed_a']
                    else:
                        game['is_upset'] = False
                    
                    games.append(game)
        
        print(f"  Found {len(games)} games")
        return games
        
    except Exception as e:
        print(f"  ERROR: {e}")
        return []


def scrape_team_stats(year: int) -> list:
    """Scrape advanced team statistics for a given year."""
    url = f'https://www.sports-reference.com/cbb/seasons/{year}-advanced-school-stats.html'
    
    print(f"Fetching {year} advanced stats...")
    try:
        html = fetch_url(url)
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find the advanced stats table
        table = soup.find('table', id='advanced-school-stats')
        if not table:
            print(f"  WARNING: Could not find advanced-school-stats table")
            return []
        
        teams = []
        tbody = table.find('tbody')
        if not tbody:
            return []
        
        for row in tbody.find_all('tr'):
            # Skip header rows
            if row.get('class') and 'thead' in row.get('class'):
                continue
            
            team_data = {'year': year}
            
            # Extract data from cells
            for cell in row.find_all(['th', 'td']):
                data_stat = cell.get('data-stat')
                if not data_stat:
                    continue
                
                value = cell.get_text().strip()
                
                # Store relevant stats
                if data_stat == 'school_name':
                    team_data['team'] = value
                elif data_stat in ['srs', 'sos', 'off_rtg', 'def_rtg', 'pace']:
                    try:
                        team_data[data_stat] = float(value)
                    except ValueError:
                        team_data[data_stat] = None
            
            if 'team' in team_data:
                teams.append(team_data)
        
        print(f"  Found {len(teams)} teams")
        return teams
        
    except Exception as e:
        print(f"  ERROR: {e}")
        return []


def main():
    """Scrape all tournament data."""
    all_games = []
    all_stats = []
    
    # Scrape tournaments with aggressive delays
    print("=" * 60)
    print("SCRAPING TOURNAMENT GAMES")
    print("=" * 60)
    print("Using 5-second delays to avoid rate limiting...")
    print()
    
    for year in range(2002, 2026):
        if year == 2020:
            print(f"Skipping {year} (no tournament - COVID-19)")
            continue
            
        games = scrape_tournament_year(year)
        all_games.extend(games)
        
        time.sleep(5)  # Aggressive delay
    
    # Scrape team stats with even longer delays
    print("\n" + "=" * 60)
    print("SCRAPING TEAM STATISTICS")
    print("=" * 60)
    print("Using 5-second delays to avoid rate limiting...")
    print()
    
    for year in range(2002, 2026):
        if year == 2020:
            print(f"Skipping {year} (no tournament - COVID-19)")
            continue
            
        stats = scrape_team_stats(year)
        all_stats.extend(stats)
        
        time.sleep(5)  # Aggressive delay
    
    # Save data
    print("\n" + "=" * 60)
    print("SAVING DATA")
    print("=" * 60)
    
    data_dir = Path(__file__).parent / 'data'
    data_dir.mkdir(exist_ok=True)
    
    games_path = data_dir / 'real_tournament_games.json'
    with open(games_path, 'w') as f:
        json.dump(all_games, f, indent=2)
    print(f"Saved {len(all_games)} games to {games_path}")
    
    stats_path = data_dir / 'real_team_stats.json'
    with open(stats_path, 'w') as f:
        json.dump(all_stats, f, indent=2)
    print(f"Saved {len(all_stats)} team-years to {stats_path}")
    
    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    if all_games:
        years = sorted(set(g['year'] for g in all_games))
        print(f"Years scraped: {years[0]}-{years[-1]} (excluding 2020)")
        print(f"Total games: {len(all_games)}")
        
        upsets = [g for g in all_games if g.get('is_upset')]
        print(f"Total upsets: {len(upsets)} ({len(upsets)/len(all_games)*100:.1f}%)")
        
        by_round = {}
        for game in all_games:
            round_num = game.get('round_num', 0)
            by_round[round_num] = by_round.get(round_num, 0) + 1
        
        print(f"\nGames by round:")
        for round_num in sorted(by_round.keys()):
            print(f"  Round {round_num}: {by_round[round_num]}")
    else:
        print("WARNING: No games scraped!")
    
    print(f"\nTeam-years with stats: {len(all_stats)}")


if __name__ == '__main__':
    main()
