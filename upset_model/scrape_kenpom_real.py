#!/usr/bin/env python3
"""
Scrape REAL KenPom historical data from the Wayback Machine.
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
OUTPUT_FILE = str(_OUTPUT_DIR / "kenpom_historical.json")

def fetch_kenpom_snapshot(year, date_suffix):
    """
    Fetch KenPom from Wayback Machine for a specific year and date.
    Returns HTML content if successful, None otherwise.
    """
    url = f'https://web.archive.org/web/{year}{date_suffix}/https://kenpom.com/'
    
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

def parse_kenpom_table(html, year):
    """
    Parse KenPom ratings table from HTML.
    Returns list of team dicts.
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find the ratings table
    table = soup.find('table', {'id': 'ratings-table'})
    if not table:
        print(f"    ⚠ No ratings-table found for {year}")
        return []
    
    teams = []
    rows = table.find('tbody').find_all('tr') if table.find('tbody') else table.find_all('tr')
    
    for row in rows:
        cells = row.find_all('td')
        if len(cells) < 10:
            continue
        
        try:
            # Extract data from cells
            rank = int(cells[0].text.strip())
            team_cell = cells[1]
            team_name = team_cell.text.strip()
            
            # Remove any ranking numbers in parentheses from team name
            if '(' in team_name:
                team_name = team_name.split('(')[0].strip()
            
            # Remove seed numbers (e.g., "Ohio St. 1" -> "Ohio St.")
            # Seed numbers appear as space + digit at end of name
            parts = team_name.rsplit(' ', 1)
            if len(parts) == 2 and parts[1].isdigit():
                team_name = parts[0]
            
            conference = cells[2].text.strip()
            record = cells[3].text.strip()
            
            # AdjEM (Adjusted Efficiency Margin)
            adj_em = float(cells[4].text.strip())
            
            # AdjO (Adjusted Offense)
            adj_o = float(cells[5].text.strip())
            
            # AdjD (Adjusted Defense) 
            adj_d = float(cells[7].text.strip())
            
            # AdjT (Adjusted Tempo)
            adj_t = float(cells[9].text.strip())
            
            # Luck (cell 11)
            luck = float(cells[11].text.strip())
            
            teams.append({
                'year': year,
                'team': team_name,
                'rank': rank,
                'conference': conference,
                'record': record,
                'adj_em': adj_em,
                'adj_o': adj_o,
                'adj_d': adj_d,
                'adj_t': adj_t,
                'luck': luck
            })
            
        except (ValueError, IndexError, AttributeError) as e:
            # Skip malformed rows
            continue
    
    return teams

def scrape_all_years():
    """
    Scrape KenPom data for all years.
    Returns combined list of all team data.
    """
    all_data = []
    failed_years = []
    
    for year in YEARS:
        print(f"\n📊 Scraping {year}...")
        
        html = None
        for date_suffix in DATE_ATTEMPTS:
            html = fetch_kenpom_snapshot(year, date_suffix)
            if html:
                break
            time.sleep(2)  # Be polite to archive.org
        
        if not html:
            print(f"  ❌ FAILED: No snapshot found for {year}")
            failed_years.append(year)
            continue
        
        # Parse the table
        teams = parse_kenpom_table(html, year)
        
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
    print("🔍 KenPom Historical Data Scraper")
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
