#!/usr/bin/env python3
"""
Scrape REAL NCAA tournament data from the official NCAA API.
NO FAKE DATA ALLOWED.
"""
import urllib.request
import json
import time
import html
from datetime import datetime
from pathlib import Path

def fetch_scoreboard(year, month, day):
    """Fetch scoreboard for a specific date from NCAA API."""
    url = f"https://data.ncaa.com/casablanca/scoreboard/basketball-men/d1/{year}/{month:02d}/{day:02d}/scoreboard.json"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read())
            return data
    except Exception as e:
        # Silently skip missing dates (not all days have games)
        return None

def parse_game(game_data, year):
    """Parse a tournament game from NCAA JSON format."""
    try:
        game = game_data.get('game', {})
        
        # Only process tournament games (have bracketRound)
        bracket_round_raw = game.get('bracketRound', '')
        if not bracket_round_raw:
            return None
        
        # Decode HTML entities (e.g., "FINAL FOUR&#174;" -> "FINAL FOUR®")
        bracket_round = html.unescape(bracket_round_raw)
        
        home = game.get('home', {})
        away = game.get('away', {})
        
        # Must have seeds to be a tournament game
        if 'seed' not in home or 'seed' not in away:
            return None
        
        # Parse seeds (can be strings like "1" or "16")
        try:
            seed_home = int(home['seed'])
            seed_away = int(away['seed'])
        except (ValueError, TypeError):
            return None
        
        # Parse scores
        try:
            score_home = int(home.get('score', 0))
            score_away = int(away.get('score', 0))
        except (ValueError, TypeError):
            return None
        
        # Determine winner
        home_won = home.get('winner', False)
        away_won = away.get('winner', False)
        
        if not home_won and not away_won:
            # Game might not be final
            return None
        
        # Get team names
        team_home = home.get('names', {}).get('short', 'Unknown')
        team_away = away.get('names', {}).get('short', 'Unknown')
        
        # Map bracket round to round number (case-insensitive, partial match)
        round_name_lower = bracket_round.lower()
        round_num = -1
        round_name_clean = bracket_round
        
        if 'first four' in round_name_lower:
            round_num = 0
            round_name_clean = 'First Four'
        elif 'first round' in round_name_lower or 'round of 64' in round_name_lower:
            round_num = 1
            round_name_clean = 'First Round'
        elif 'second round' in round_name_lower or 'round of 32' in round_name_lower:
            round_num = 2
            round_name_clean = 'Second Round'
        elif 'sweet' in round_name_lower or 'regional semifinal' in round_name_lower:
            round_num = 3
            round_name_clean = 'Sweet 16'
        elif 'elite' in round_name_lower or 'regional final' in round_name_lower:
            round_num = 4
            round_name_clean = 'Elite Eight'
        elif 'final four' in round_name_lower or 'national semifinal' in round_name_lower:
            round_num = 5
            round_name_clean = 'Final Four'
        elif 'championship' in round_name_lower or 'national final' in round_name_lower:
            round_num = 6
            round_name_clean = 'Championship'
        
        if round_num == -1:
            print(f"  WARNING: Unknown bracket round: '{bracket_round}'")
            return None
        
        # Determine upset: higher seed number (worse team) beats lower seed number (better team)
        is_upset = False
        if home_won and seed_home > seed_away:
            is_upset = True
        elif away_won and seed_away > seed_home:
            is_upset = True
        
        # Store as away (team_a) vs home (team_b) for consistency
        return {
            'year': year,
            'round_name': round_name_clean,
            'round_num': round_num,
            'seed_a': seed_away,
            'team_a': team_away,
            'score_a': score_away,
            'seed_b': seed_home,
            'team_b': team_home,
            'score_b': score_home,
            'winner': 'a' if away_won else 'b',
            'is_upset': is_upset
        }
    except Exception as e:
        print(f"  ERROR parsing game: {e}")
        return None

def scrape_tournament_year(year):
    """Scrape all tournament games for a given year."""
    print(f"\nScraping {year} tournament...")
    games = []
    
    # Scan March 14 - April 10
    for month in [3, 4]:
        start_day = 14 if month == 3 else 1
        end_day = 31 if month == 3 else 10
        
        for day in range(start_day, end_day + 1):
            # Check if valid date
            try:
                datetime(year, month, day)
            except ValueError:
                continue
            
            data = fetch_scoreboard(year, month, day)
            time.sleep(0.3)  # Rate limiting
            
            if not data:
                continue
            
            # Parse games from this date
            games_list = data.get('games', [])
            for game_data in games_list:
                parsed = parse_game(game_data, year)
                if parsed:
                    games.append(parsed)
                    upset_mark = " [UPSET]" if parsed['is_upset'] else ""
                    print(f"  {parsed['team_a']} ({parsed['seed_a']}) vs {parsed['team_b']} ({parsed['seed_b']}) - {parsed['round_name']}{upset_mark}")
    
    print(f"  ✓ Found {len(games)} tournament games from {year}")
    return games

def main():
    """Scrape all tournament data from 2010-2025, skipping 2020."""
    all_games = []
    
    years = list(range(2010, 2026))
    years.remove(2020)  # No tournament in 2020 (COVID)
    
    for year in years:
        games = scrape_tournament_year(year)
        all_games.extend(games)
    
    print(f"\n{'='*60}")
    print(f"SCRAPING COMPLETE")
    print(f"{'='*60}")
    print(f"Total real games scraped: {len(all_games)}")
    print(f"Years covered: {sorted(set(g['year'] for g in all_games))}")
    print(f"Upsets found: {sum(1 for g in all_games if g['is_upset'])}")
    
    # Save to file
    output_dir = Path(__file__).resolve().parent.parent / "data" / "upset_model"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / 'ncaa_tournament_real.json'
    with open(output_path, 'w') as f:
        json.dump(all_games, f, indent=2)
    
    print(f"\n✓ Saved to: {output_path}")
    
    # Print sample
    if all_games:
        print(f"\nSample games:")
        for i in [0, len(all_games)//2, -1]:
            print(json.dumps(all_games[i], indent=2))
            if i < len(all_games) - 1:
                print("...")

if __name__ == '__main__':
    main()
