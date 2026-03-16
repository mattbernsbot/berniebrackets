#!/usr/bin/env python3
"""
Scrape KenPom historical ratings for NCAA teams.
"""
import urllib.request
import time
import json
from html.parser import HTMLParser

class KenPomParser(HTMLParser):
    """Parse KenPom table to extract team ratings."""
    
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_row = False
        self.in_cell = False
        self.current_row = []
        self.rows = []
        self.cell_data = []
        
    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            # Check if this is the ratings table
            for attr, value in attrs:
                if attr == 'id' and value == 'ratings-table':
                    self.in_table = True
        elif tag == 'tbody' and self.in_table:
            pass  # Inside table body
        elif tag == 'tr' and self.in_table:
            self.in_row = True
            self.current_row = []
        elif tag == 'td' and self.in_row:
            self.in_cell = True
            self.cell_data = []
    
    def handle_endtag(self, tag):
        if tag == 'table':
            self.in_table = False
        elif tag == 'tr' and self.in_row:
            if self.current_row:
                self.rows.append(self.current_row)
            self.in_row = False
        elif tag == 'td' and self.in_cell:
            self.current_row.append(''.join(self.cell_data).strip())
            self.in_cell = False
            self.cell_data = []
    
    def handle_data(self, data):
        if self.in_cell:
            self.cell_data.append(data)

def scrape_kenpom_year(year):
    """Scrape KenPom ratings for a specific year."""
    url = f"https://kenpom.com/index.php?y={year}"
    print(f"\nScraping KenPom {year}: {url}")
    
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0')
        
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode('utf-8')
        
        # Parse HTML table
        parser = KenPomParser()
        parser.feed(html)
        
        teams = {}
        for row in parser.rows:
            if len(row) < 8:
                continue
            
            try:
                # Expected columns: Rank, Team, Conf, W-L, AdjEM, AdjO, AdjD, AdjT
                rank = row[0]
                team_name = row[1]
                adj_em = float(row[4])
                adj_o = float(row[5])
                adj_d = float(row[6])
                adj_t = float(row[7])
                
                teams[team_name] = {
                    'rank': rank,
                    'adj_em': adj_em,
                    'adj_o': adj_o,
                    'adj_d': adj_d,
                    'adj_t': adj_t
                }
            except (ValueError, IndexError):
                continue
        
        print(f"  ✓ Found {len(teams)} teams")
        return teams
        
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return None

def main():
    """Scrape KenPom data for all tournament years."""
    # Years we have tournament data for
    years = [2011, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025]
    
    all_stats = {}
    
    for year in years:
        stats = scrape_kenpom_year(year)
        if stats:
            all_stats[str(year)] = stats
        time.sleep(1.0)  # Be nice to KenPom servers
    
    print(f"\n{'='*60}")
    print(f"KenPom scraping complete: {len(all_stats)} years")
    print(f"{'='*60}")
    
    # Save to file
    output_path = 'data/kenpom_historical.json'
    with open(output_path, 'w') as f:
        json.dump(all_stats, f, indent=2)
    
    print(f"✓ Saved to: {output_path}")
    
    # Sample
    if all_stats:
        first_year = min(all_stats.keys())
        sample_teams = list(all_stats[first_year].items())[:3]
        print(f"\nSample from {first_year}:")
        for team, stats in sample_teams:
            print(f"  {team}: AdjEM={stats['adj_em']:.2f}")

if __name__ == '__main__':
    main()
