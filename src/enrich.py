"""Enrich Team objects with Torvik and LRMC data for the current year.

Scrapes barttorvik.com (Barthag, WAB) and LRMC (top-25 W-L record),
then matches and populates fields on Team objects so the upset model
has all 8 features at inference time.
"""

import json
import logging
import os
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError

from bs4 import BeautifulSoup

from src.name_matching import normalize_team_name, normalize_torvik_name, normalize_lrmc_name, match_team_name

logger = logging.getLogger("bracket_optimizer")


# ---------------------------------------------------------------------------
# Torvik scraping (requires Node.js + Playwright via conda)
# ---------------------------------------------------------------------------

_NODE_SCRIPT_TORVIK = r"""
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({
    headless: false,
    args: ['--disable-blink-features=AutomationControlled']
  });
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
  });
  const page = await context.newPage();

  process.stderr.write('Scraping Torvik YEAR_PLACEHOLDER...\n');
  await page.goto('https://barttorvik.com/trank.php?year=YEAR_PLACEHOLDER', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(3000);

  const teams = await page.evaluate(() => {
    const table = document.querySelector('table');
    if (!table) return [];

    const rows = table.querySelectorAll('tbody tr');
    const results = [];

    const cleanText = (cell) => {
      const clone = cell.cloneNode(true);
      clone.querySelectorAll('.lowrow, sub, sup, .steep-sub, .steep-sup, small, br').forEach(el => el.remove());
      return clone.textContent.trim();
    };

    for (const row of rows) {
      const cells = row.querySelectorAll('td');
      if (cells.length < 10) continue;

      const barthag = cleanText(cells[7]);
      const wab = cleanText(cells[cells.length - 1]);

      const link = cells[1].querySelector('a');
      let team = '';
      if (link) {
        for (const node of link.childNodes) {
          if (node.nodeType === 3) team += node.textContent;
        }
        team = team.trim();
      }

      if (team && barthag) {
        results.push({
          team: team,
          barthag: parseFloat(barthag),
          wab: parseFloat(wab)
        });
      }
    }
    return results;
  });

  process.stderr.write(`  ${teams.length} teams scraped\n`);
  process.stdout.write(JSON.stringify(teams, null, 2));
  await browser.close();
})();
"""


def scrape_torvik_live(year: int = 2026) -> dict[str, dict]:
    """Scrape barttorvik.com for current year Barthag + WAB.

    Returns {normalized_name: {'barthag': float, 'wab': float}}.
    Empty dict on failure.
    """
    import shutil

    node_bin = shutil.which('node')
    if not node_bin:
        logger.warning("Node.js not found — skipping Torvik enrichment")
        return {}

    script = _NODE_SCRIPT_TORVIK.replace('YEAR_PLACEHOLDER', str(year))

    with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
        f.write(script)
        script_path = f.name

    try:
        conda_prefix = os.environ.get('CONDA_PREFIX', '')
        node_path = os.path.join(conda_prefix, 'lib', 'node_modules') if conda_prefix else ''

        env = os.environ.copy()
        if node_path:
            env['NODE_PATH'] = node_path

        logger.info(f"Scraping Torvik {year} data via Playwright...")
        result = subprocess.run(
            ['node', script_path],
            capture_output=True, text=True, env=env, timeout=120
        )

        if result.stderr:
            logger.info(result.stderr.strip())

        if result.returncode != 0:
            logger.warning(f"Torvik scraper failed (exit {result.returncode})")
            return {}

        data = json.loads(result.stdout)
        out = {}
        for entry in data:
            norm = normalize_torvik_name(entry['team'])
            out[norm] = {
                'barthag': entry['barthag'],
                'wab': entry['wab']
            }

        logger.info(f"Torvik: {len(out)} teams scraped for {year}")
        return out

    except subprocess.TimeoutExpired:
        logger.warning("Torvik scraper timed out (120s)")
        return {}
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Torvik parse error: {e}")
        return {}
    finally:
        os.unlink(script_path)


# ---------------------------------------------------------------------------
# LRMC scraping
# ---------------------------------------------------------------------------

def _fetch_lrmc_html(year: int) -> Optional[str]:
    """Fetch LRMC HTML, trying live site first then Wayback Machine."""
    headers = {'User-Agent': 'Mozilla/5.0'}

    # Try live site
    live_url = 'https://www2.isye.gatech.edu/~jsokol/lrmc/'
    try:
        logger.info(f"Trying LRMC live site: {live_url}")
        req = urllib.request.Request(live_url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            html = response.read()
            logger.info("LRMC live site responded")
            return html
    except (HTTPError, URLError, Exception) as e:
        logger.info(f"LRMC live site failed: {e}")

    # Fallback: Wayback Machine
    date_attempts = ['0316', '0315', '0314', '0317', '0313', '0310', '0320']
    for date_suffix in date_attempts:
        wayback_url = f'https://web.archive.org/web/{year}{date_suffix}/https://www2.isye.gatech.edu/~jsokol/lrmc/'
        try:
            logger.info(f"Trying Wayback: {year}{date_suffix}...")
            req = urllib.request.Request(wayback_url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as response:
                html = response.read()
                logger.info(f"LRMC Wayback {year}{date_suffix} success")
                return html
        except (HTTPError, URLError, Exception):
            pass
        time.sleep(1)

    return None


def _parse_top25_record(cell_text: str) -> tuple[int, int]:
    """Parse vs.1-25 W-L record. Returns (wins, losses)."""
    text = cell_text.strip()
    if text == '---' or not text:
        return (0, 0)
    wl = text.split('(')[0].strip()
    parts = wl.split('-')
    try:
        return (int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return (0, 0)


def scrape_lrmc_live(year: int = 2026) -> dict[str, dict]:
    """Scrape LRMC for current year top-25 W-L record.

    Returns {normalized_name: {'top25_wins': int, 'top25_losses': int, 'top25_games': int}}.
    Empty dict on failure.
    """
    html = _fetch_lrmc_html(year)
    if not html:
        logger.warning("Could not fetch LRMC data from any source")
        return {}

    soup = BeautifulSoup(html, 'html.parser')
    tables = soup.find_all('table')

    if len(tables) >= 2:
        # Wayback Machine format: 2 tables, table[1] has 17 cells
        return _parse_lrmc_wayback(tables[1], year)
    elif len(tables) == 1:
        # Live site format: 1 table, 31 cells per row
        return _parse_lrmc_live(tables[0], year)
    else:
        logger.warning("LRMC: no tables found")
        return {}


def _parse_lrmc_wayback(table, year: int) -> dict[str, dict]:
    """Parse Wayback Machine LRMC format (table[1], 17+ cells, col[16] = vs top-25)."""
    rows = table.find_all('tr')[3:]  # Skip header rows
    out = {}
    for row in rows:
        cells = row.find_all('td')
        if len(cells) < 17:
            continue
        try:
            team_name = cells[2].text.strip()
            wins, losses = _parse_top25_record(cells[16].text)
            norm = normalize_lrmc_name(team_name)
            out[norm] = {
                'top25_wins': wins,
                'top25_losses': losses,
                'top25_games': wins + losses
            }
        except (ValueError, IndexError, AttributeError):
            continue
    logger.info(f"LRMC (wayback): {len(out)} teams parsed for {year}")
    return out


def _parse_lrmc_live(table, year: int) -> dict[str, dict]:
    """Parse live LRMC site format (1 table, 31 cells, col[24] = vs.1-25 W-L)."""
    rows = table.find_all('tr')
    out = {}
    for row in rows:
        cells = row.find_all(['td', 'th'])
        if len(cells) < 25:
            continue
        try:
            rank_text = cells[1].text.strip()
            if not rank_text.isdigit():
                continue  # Skip header rows
            team_name = cells[2].text.strip()
            # Col 24 = vs.1-25 W-L record, format: "11-3(11-3-0)" or "11-3"
            wins, losses = _parse_top25_record(cells[24].text)
            norm = normalize_lrmc_name(team_name)
            out[norm] = {
                'top25_wins': wins,
                'top25_losses': losses,
                'top25_games': wins + losses
            }
        except (ValueError, IndexError, AttributeError):
            continue
    logger.info(f"LRMC (live): {len(out)} teams parsed for {year}")
    return out


# ---------------------------------------------------------------------------
# Team enrichment (main entry point)
# ---------------------------------------------------------------------------

def enrich_teams(teams: list, data_dir: str = "data") -> list:
    """Enrich Team objects with Torvik and LRMC data.

    Checks for cached data first. If not cached, scrapes live.
    Gracefully degrades if scraping fails (teams keep existing data).
    """
    torvik_cache = os.path.join(data_dir, "torvik_2026_live.json")
    lrmc_cache = os.path.join(data_dir, "lrmc_2026_live.json")

    # Load or scrape Torvik data
    torvik_data = _load_or_scrape(torvik_cache, scrape_torvik_live, "Torvik")

    # Load or scrape LRMC data
    lrmc_data = _load_or_scrape(lrmc_cache, scrape_lrmc_live, "LRMC")

    # Build list of team names for matching
    team_names = [t.name for t in teams]

    # Enrich teams
    torvik_matched = 0
    lrmc_matched = 0

    for team in teams:
        # Torvik enrichment
        if torvik_data:
            matched_name = match_team_name(team.name, list(torvik_data.keys()), source="generic")
            if matched_name and matched_name in torvik_data:
                entry = torvik_data[matched_name]
                team.barthag = entry['barthag']
                team.wab = entry['wab']
                torvik_matched += 1
            else:
                # Try direct normalized lookup
                norm = normalize_team_name(team.name)
                if norm in torvik_data:
                    entry = torvik_data[norm]
                    team.barthag = entry['barthag']
                    team.wab = entry['wab']
                    torvik_matched += 1

        # LRMC enrichment
        if lrmc_data:
            matched_name = match_team_name(team.name, list(lrmc_data.keys()), source="generic")
            if matched_name and matched_name in lrmc_data:
                entry = lrmc_data[matched_name]
                team.top25_wins = entry['top25_wins']
                team.top25_losses = entry['top25_losses']
                team.top25_games = entry['top25_games']
                lrmc_matched += 1
            else:
                norm = normalize_team_name(team.name)
                if norm in lrmc_data:
                    entry = lrmc_data[norm]
                    team.top25_wins = entry['top25_wins']
                    team.top25_losses = entry['top25_losses']
                    team.top25_games = entry['top25_games']
                    lrmc_matched += 1

    logger.info(f"Enrichment: Torvik {torvik_matched}/{len(teams)}, LRMC {lrmc_matched}/{len(teams)}")

    if torvik_data and torvik_matched < len(teams) * 0.8:
        unmatched = [t.name for t in teams if t.barthag is None]
        logger.warning(f"Torvik unmatched ({len(unmatched)}): {unmatched[:10]}")

    if lrmc_data and lrmc_matched < len(teams) * 0.8:
        unmatched = [t.name for t in teams if t.top25_games is None]
        logger.warning(f"LRMC unmatched ({len(unmatched)}): {unmatched[:10]}")

    return teams


def _load_or_scrape(cache_path: str, scrape_fn, label: str) -> dict:
    """Load cached data or scrape fresh."""
    if os.path.exists(cache_path):
        try:
            with open(cache_path) as f:
                data = json.load(f)
            if data:
                logger.info(f"{label}: loaded {len(data)} teams from cache ({cache_path})")
                return data
        except (json.JSONDecodeError, IOError):
            pass

    logger.info(f"{label}: no cache found, scraping live...")
    data = scrape_fn()

    if data:
        try:
            with open(cache_path, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"{label}: cached {len(data)} teams to {cache_path}")
        except IOError as e:
            logger.warning(f"{label}: could not write cache: {e}")

    return data
