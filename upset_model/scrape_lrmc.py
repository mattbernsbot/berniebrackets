#!/usr/bin/env python3
"""
Scrape LRMC (Logistic Regression Markov Chain) rankings from Wayback Machine.
Extract vs Top 25 win percentage for each team.
NO FAKE DATA. If a year fails, skip it and log the failure.
"""

import json
import time
import urllib.request
from pathlib import Path
from urllib.error import HTTPError, URLError
from bs4 import BeautifulSoup

# Years we need (from tournament dataset)
YEARS = [2011, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025]

# Try multiple dates for each year (March snapshots before tournament)
DATE_ATTEMPTS = ['0315', '0314', '0316', '0313', '0317', '0310', '0320', '0301']

_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "upset_model"
OUTPUT_FILE = str(_OUTPUT_DIR / "lrmc_historical.json")


def fetch_lrmc_snapshot(year, date_suffix):
    """
    Fetch LRMC from Wayback Machine for a specific year and date.
    Returns HTML content if successful, None otherwise.
    """
    url = f'https://web.archive.org/web/{year}{date_suffix}/https://www2.isye.gatech.edu/~jsokol/lrmc/'
    
    try:
        print(f"  Trying {year}{date_suffix}...", end=' ')
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        
        with urllib.request.urlopen(req, timeout=30) as response:
            html = response.read()
            print("✓ Success")
            return html
    except HTTPError as e:
        print(f"✗ HTTP {e.code}")
        return None
    except URLError as e:
        print(f"✗ URL Error: {e.reason}")
        return None
    except Exception as e:
        print(f"✗ Error: {e}")
        return None


def parse_top25_record(cell_text):
    """Parse vs.1-25 W-L record. Returns (wins, losses) or (0, 0) if missing."""
    text = cell_text.strip()
    if text == '---' or not text:
        return (0, 0)
    
    # Take the part before '(' → "4-2"
    wl = text.split('(')[0].strip()
    parts = wl.split('-')
    
    try:
        return (int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return (0, 0)


def parse_lrmc_table(html, year):
    """
    Parse LRMC table from HTML.
    Returns list of team dicts.
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find all tables - we want the second one (index 1)
    tables = soup.find_all('table')
    if len(tables) < 2:
        print(f"    ⚠ Not enough tables found for {year}")
        return []
    
    table = tables[1]
    teams = []
    
    # Skip header rows (first 3 rows: group headers, sub-headers, spacer)
    rows = table.find_all('tr')[3:]
    
    for row in rows:
        cells = row.find_all('td')
        if len(cells) < 17:
            continue
        
        try:
            # Cell [1] = LRMC Rank
            lrmc_rank = int(cells[1].text.strip())
            
            # Cell [2] = Team name
            team_name = cells[2].text.strip()
            
            # Cell [16] = vs.1-25 W-L Record
            wins, losses = parse_top25_record(cells[16].text)
            
            teams.append({
                'year': year,
                'team': team_name,
                'lrmc_rank': lrmc_rank,
                'top25_wins': wins,
                'top25_losses': losses,
                'top25_games': wins + losses
            })
            
        except (ValueError, IndexError, AttributeError) as e:
            # Skip malformed rows
            continue
    
    return teams


def scrape_all_years():
    """
    Scrape LRMC data for all years.
    Returns combined list of all team data.
    """
    all_data = []
    failed_years = []
    
    for year in YEARS:
        print(f"\n📊 Scraping {year}...")
        
        html = None
        for date_suffix in DATE_ATTEMPTS:
            html = fetch_lrmc_snapshot(year, date_suffix)
            if html:
                break
            time.sleep(2)  # Be polite to archive.org
        
        if not html:
            print(f"  ❌ FAILED: No snapshot found for {year}")
            failed_years.append(year)
            continue
        
        # Parse the table
        teams = parse_lrmc_table(html, year)
        
        if not teams:
            print(f"  ❌ FAILED: Could not parse data for {year}")
            failed_years.append(year)
            continue
        
        print(f"  ✓ Parsed {len(teams)} teams")
        all_data.extend(teams)
        
        # Be polite - wait before next request
        if year != YEARS[-1]:
            time.sleep(2)
    
    print(f"\n{'='*60}")
    print(f"SCRAPING COMPLETE")
    print(f"  Successful: {len(YEARS) - len(failed_years)}/{len(YEARS)} years")
    print(f"  Total teams: {len(all_data)}")
    
    if failed_years:
        print(f"  ⚠ Failed years: {failed_years}")
    
    return all_data


if __name__ == '__main__':
    print("🔍 LRMC Historical Data Scraper")
    print("=" * 60)
    print("Scraping from Wayback Machine (archive.org)")
    print("NO FAKE DATA - Real archives only!\n")
    
    all_data = scrape_all_years()
    
    # Save to JSON
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\n💾 Saving to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(all_data, f, indent=2)
    
    print("✓ Done!\n")
