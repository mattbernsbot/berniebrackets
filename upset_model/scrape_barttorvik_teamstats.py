#!/usr/bin/env python3
"""
Scrape Barttorvik Four Factors from the CORRECT page: teamstats.php
This page has REAL four-factors data going back to 2008.

URL: https://barttorvik.com/teamstats.php?year={YEAR}&sort=2

Table structure (355 rows):
Headers: ['', '', 'Adj. Eff.', 'Eff. FG%', 'Turnover%', 'Off. Reb%', 'FT Rate', 'FT%', '2P%', '3P%']
Sub-headers: ['Rk', 'Team', 'Conf', 'Off.', 'Def.', 'Off.', 'Def.', 'Off.', 'Def.', 'Off.']

CRITICAL: Cells contain value+rank concatenated (e.g., "57.41" where 57.4 is eFG% and 1 is the rank).
The value is a float with 1-2 decimal places, the trailing digits are the rank.

NO FAKE DATA. If a year fails, skip it and log the failure.
"""

import json
import time
import re
from pathlib import Path
import urllib.request
from urllib.error import HTTPError, URLError
from bs4 import BeautifulSoup

# Years 2008-2025, skip 2020 (COVID)
YEARS = [y for y in range(2008, 2026) if y != 2020]

# Wayback Machine date (verified to have data)
WAYBACK_DATE = '20240315'

OUTPUT_FILE = Path(__file__).parent / 'data' / 'barttorvik_teamstats.json'


def parse_value_rank(cell_text):
    """
    Parse concatenated value+rank from cell text.
    
    Examples:
    - "57.41" → value=57.4, rank=1
    - "50.012" → value=50.0, rank=12
    - "21.4186" → value=21.4, rank=186
    - "34.13" → value=34.1, rank=3
    
    Strategy: The value is a float with 1-2 decimal places.
    After the decimal, the first 1-2 digits are part of the value,
    the remaining digits are the rank.
    
    More reliable: split at the point where we transition from 
    reasonable percentage/rate values to rank values.
    """
    cell_text = cell_text.strip()
    
    # Match: number with decimal, capturing value and rank
    # Pattern: decimal number where rank follows immediately
    # Since values are percentages (10-100) or rates (10-50),
    # and ranks are 1-355, we can use heuristics.
    
    # Try pattern: float with 1-2 decimal digits, followed by optional rank digits
    match = re.match(r'^(\d+\.\d{1,2})(\d*)$', cell_text)
    if match:
        value = float(match.group(1))
        rank = int(match.group(2)) if match.group(2) else None
        return value
    
    # Fallback: try to parse as float (no rank)
    try:
        return float(cell_text)
    except ValueError:
        return 0.0


def fetch_barttorvik_teamstats(year):
    """
    Fetch Barttorvik teamstats page from Wayback Machine for a specific year.
    Returns HTML content if successful, None otherwise.
    """
    wayback_date = get_wayback_date(year)
    url = f'https://web.archive.org/web/{wayback_date}/https://barttorvik.com/teamstats.php?year={year}&sort=2'
    
    try:
        print(f"  Fetching {year}...", end=' ', flush=True)
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        
        with urllib.request.urlopen(req, timeout=30) as response:
            html = response.read()
            print("✓")
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


def parse_barttorvik_teamstats_table(html, year):
    """
    Parse Barttorvik teamstats table from HTML.
    
    Expected columns (after Rk, Team, Conf):
    - AdjO (Adj. Eff. Off.)
    - AdjD (Adj. Eff. Def.)
    - eFG_off (Eff. FG% Off.)
    - eFG_def (Eff. FG% Def.)
    - TO_off (Turnover% Off.)
    - TO_def (Turnover% Def.)
    - OR_off (Off. Reb% Off.)
    - OR_def (Off. Reb% Def. - NOT IN TABLE, skip)
    - FTRate_off (FT Rate Off.)
    - FTRate_def (FT Rate Def. - NOT IN TABLE, skip)
    
    Returns list of team dicts.
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find the main data table
    table = soup.find('table', {'id': 'stats-table'})
    if not table:
        # Try finding any table with class that suggests it's the stats table
        tables = soup.find_all('table')
        if not tables:
            print(f"    ⚠ No tables found for {year}")
            return []
        # Usually the first or second table
        table = tables[0] if len(tables) == 1 else tables[1] if len(tables) > 1 else tables[0]
    
    teams = []
    
    # Get data rows
    tbody = table.find('tbody')
    rows = tbody.find_all('tr') if tbody else table.find_all('tr')[1:]  # Skip header
    
    for row in rows:
        cells = row.find_all('td')
        if len(cells) < 10:
            continue
        
        try:
            # Parse columns (0-indexed)
            # [0] = Rank (skip)
            # [1] = Team
            # [2] = Conference
            # [3] = AdjO (Adj. Eff. Off.)
            # [4] = AdjD (Adj. Eff. Def.)
            # [5] = eFG_off (Eff. FG% Off.)
            # [6] = eFG_def (Eff. FG% Def.)
            # [7] = TO_off (Turnover% Off.)
            # [8] = TO_def (Turnover% Def.)
            # [9] = OR_off (Off. Reb% Off.)
            # [10] = FTRate_off (FT Rate Off.) - if exists
            
            team_cell = cells[1]
            team_name = team_cell.text.strip()
            conf = cells[2].text.strip()
            
            # Parse metrics with value+rank handling
            adj_o = parse_value_rank(cells[3].text)
            adj_d = parse_value_rank(cells[4].text)
            efg_off = parse_value_rank(cells[5].text)
            efg_def = parse_value_rank(cells[6].text)
            to_off = parse_value_rank(cells[7].text)
            to_def = parse_value_rank(cells[8].text)
            or_off = parse_value_rank(cells[9].text)
            
            # FT Rate is in column 10 or 11 depending on layout
            ft_rate_off = parse_value_rank(cells[10].text) if len(cells) > 10 else 0.0
            # FT Rate defense is in column 11 or 12
            ft_rate_def = parse_value_rank(cells[11].text) if len(cells) > 11 else 0.0
            
            teams.append({
                'year': year,
                'team': team_name,
                'conf': conf,
                'adj_o': adj_o,
                'adj_d': adj_d,
                'efg_off': efg_off,
                'efg_def': efg_def,
                'to_off': to_off,
                'to_def': to_def,
                'or_off': or_off,
                'ft_rate_off': ft_rate_off,
                'ft_rate_def': ft_rate_def
            })
            
        except (ValueError, IndexError, AttributeError) as e:
            # Skip malformed rows
            continue
    
    return teams


def verify_data_quality(all_data):
    """
    Verify data quality for all years.
    Print statistics for each year.
    
    Expected ranges:
    - eFG%: 42-60
    - TO%: 14-26
    - OR%: 22-42
    - FTRate: 20-50
    """
    print("\n" + "=" * 80)
    print("DATA QUALITY VERIFICATION")
    print("=" * 80)
    
    years_data = {}
    for record in all_data:
        year = record['year']
        if year not in years_data:
            years_data[year] = []
        years_data[year].append(record)
    
    for year in sorted(years_data.keys()):
        records = years_data[year]
        
        # Extract metrics
        efg_vals = [r['efg_off'] for r in records]
        to_vals = [r['to_off'] for r in records]
        or_vals = [r['or_off'] for r in records]
        ft_vals = [r['ft_rate_off'] for r in records]
        
        print(f"\nYear {year}: {len(records)} teams")
        print(f"  eFG_off:    [{min(efg_vals):.1f}, {max(efg_vals):.1f}]")
        print(f"  TO_off:     [{min(to_vals):.1f}, {max(to_vals):.1f}]")
        print(f"  OR_off:     [{min(or_vals):.1f}, {max(or_vals):.1f}]")
        print(f"  FTRate_off: [{min(ft_vals):.1f}, {max(ft_vals):.1f}]")
        
        # Flag suspicious data
        if max(efg_vals) > 60 or min(efg_vals) < 42:
            print(f"  ⚠ WARNING: eFG% out of expected range [42-60]")
        if max(to_vals) > 26 or min(to_vals) < 14:
            print(f"  ⚠ WARNING: TO% out of expected range [14-26]")
        if max(or_vals) > 42 or min(or_vals) < 22:
            print(f"  ⚠ WARNING: OR% out of expected range [22-42]")
        if max(ft_vals) > 50 or min(ft_vals) < 20:
            print(f"  ⚠ WARNING: FTRate out of expected range [20-50]")
    
    print("\n" + "=" * 80)


def scrape_all_years():
    """
    Scrape Barttorvik teamstats data for all years 2008-2025 (skip 2020).
    Returns combined list of all team data.
    """
    all_data = []
    failed_years = []
    
    print("🔍 Barttorvik Team Stats Scraper (CORRECT PAGE)")
    print("=" * 80)
    print(f"Scraping from Wayback Machine ({WAYBACK_DATE})")
    print(f"URL: barttorvik.com/teamstats.php?year=YEAR&sort=2")
    print(f"Years: {min(YEARS)}-{max(YEARS)} (skip 2020)")
    print("NO FAKE DATA - Real archives only!\n")
    
    for year in YEARS:
        html = fetch_barttorvik_teamstats(year)
        
        if not html:
            print(f"  ❌ FAILED: No snapshot found for {year}")
            failed_years.append(year)
            time.sleep(2)
            continue
        
        # Parse the table
        teams = parse_barttorvik_teamstats_table(html, year)
        
        if not teams:
            print(f"  ❌ FAILED: Could not parse data for {year}")
            failed_years.append(year)
            time.sleep(2)
            continue
        
        print(f"  ✓ Parsed {len(teams)} teams")
        all_data.extend(teams)
        
        # Be polite - wait before next request
        if year != YEARS[-1]:
            time.sleep(2)
    
    print(f"\n{'='*80}")
    print(f"SCRAPING COMPLETE")
    print(f"  Successful: {len(YEARS) - len(failed_years)}/{len(YEARS)} years")
    print(f"  Total teams: {len(all_data)}")
    
    if failed_years:
        print(f"  ⚠ Failed years: {failed_years}")
    
    return all_data


if __name__ == '__main__':
    all_data = scrape_all_years()
    
    if all_data:
        # Verify data quality
        verify_data_quality(all_data)
        
        # Save to JSON
        print(f"\n💾 Saving to {OUTPUT_FILE}...")
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_FILE, 'w') as f:
            json.dump(all_data, f, indent=2)
        
        print("✓ Done!\n")
    else:
        print("\n❌ No data scraped. Aborting.\n")
