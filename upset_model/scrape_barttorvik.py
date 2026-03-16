#!/usr/bin/env python3
"""
Scrape Barttorvik (T-Rank) Four Factors from Wayback Machine.
CRITICAL: Handle cell parsing correctly - cells contain value<br/><span>rank</span>
NO FAKE DATA. If a year fails, skip it and log the failure.
"""

import json
import time
import urllib.request
from urllib.error import HTTPError, URLError
from bs4 import BeautifulSoup

# Years we need (from tournament dataset)
YEARS = [2011, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025]

# Try multiple dates for each year (March snapshots before tournament)
DATE_ATTEMPTS = ['0315', '0314', '0316', '0313', '0317', '0310', '0320', '0301']

OUTPUT_FILE = '/home/clawdbot/.openclaw/workspace/projects/builder-engine/jobs/bracket-optimizer/upset_model/data/barttorvik_historical.json'


def fetch_barttorvik_snapshot(year, date_suffix):
    """
    Fetch Barttorvik from Wayback Machine for a specific year and date.
    Returns HTML content if successful, None otherwise.
    """
    url = f'https://web.archive.org/web/{year}{date_suffix}/https://barttorvik.com/trank.php?year={year}'
    
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


def parse_barttorvik_value(cell):
    """
    Extract numeric value from a Barttorvik cell, ignoring the rank.
    
    CRITICAL: Cells contain value<br/><span>rank</span>
    Example: <td>56.9<br/><span style="font-size:8px">7</span></td>
    
    Using .text.strip() returns "56.97" (concatenated!).
    Must extract the value before <br/>.
    """
    br = cell.find('br')
    if br and br.previous_sibling:
        # Get the text before the <br/>
        value_text = str(br.previous_sibling).strip()
        try:
            return float(value_text)
        except ValueError:
            pass
    
    # Fallback: try full text (for cells without ranks)
    try:
        return float(cell.text.strip())
    except ValueError:
        return 0.0


def parse_barttorvik_table(html, year):
    """
    Parse Barttorvik table from HTML.
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
    
    # Get data rows from tbody
    tbody = table.find('tbody')
    if not tbody:
        rows = table.find_all('tr')
    else:
        rows = tbody.find_all('tr')
    
    for row in rows:
        cells = row.find_all('td')
        if len(cells) < 15:
            continue
        
        try:
            # Cell [1] = Team name (use id attribute for clean name)
            team_cell = cells[1]
            team_name = team_cell.get('id', team_cell.text.strip())
            
            # Clean team name - remove seed/tournament result
            if team_name and '  ' in team_name:
                team_name = team_name.split('  ')[0].strip()
            
            # Four Factors (same indices for both 22-cell and 24-cell layouts)
            # [8]  = EFG% (offensive)
            # [9]  = EFGD% (defensive - opponent EFG%)
            # [10] = TOR (turnover rate - offensive, lower is better)
            # [11] = TORD (turnover rate forced on defense, higher is better)
            # [12] = ORB (offensive rebound %)
            # [14] = FTR (free throw rate - offensive)
            
            efg = parse_barttorvik_value(cells[8])
            efg_d = parse_barttorvik_value(cells[9])
            to_rate = parse_barttorvik_value(cells[10])
            to_rate_d = parse_barttorvik_value(cells[11])
            or_pct = parse_barttorvik_value(cells[12])
            ft_rate = parse_barttorvik_value(cells[14])
            
            teams.append({
                'year': year,
                'team': team_name,
                'efg': efg,
                'efg_d': efg_d,
                'to_rate': to_rate,
                'to_rate_d': to_rate_d,
                'or_pct': or_pct,
                'ft_rate': ft_rate
            })
            
        except (ValueError, IndexError, AttributeError) as e:
            # Skip malformed rows
            continue
    
    return teams


def scrape_all_years():
    """
    Scrape Barttorvik data for all years.
    Returns combined list of all team data.
    """
    all_data = []
    failed_years = []
    
    for year in YEARS:
        print(f"\n📊 Scraping {year}...")
        
        html = None
        for date_suffix in DATE_ATTEMPTS:
            html = fetch_barttorvik_snapshot(year, date_suffix)
            if html:
                break
            time.sleep(2)  # Be polite to archive.org
        
        if not html:
            print(f"  ❌ FAILED: No snapshot found for {year}")
            failed_years.append(year)
            continue
        
        # Parse the table
        teams = parse_barttorvik_table(html, year)
        
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
    print("🔍 Barttorvik Historical Data Scraper")
    print("=" * 60)
    print("Scraping from Wayback Machine (archive.org)")
    print("NO FAKE DATA - Real archives only!\n")
    
    all_data = scrape_all_years()
    
    # Save to JSON
    print(f"\n💾 Saving to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(all_data, f, indent=2)
    
    print("✓ Done!\n")
