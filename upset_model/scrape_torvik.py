#!/usr/bin/env python3
"""
Scrape Bart Torvik T-Rank data for all tournament years.
Extracts Barthag (win probability) and WAB (wins above bubble) per team.

Requires: Node.js + Playwright (conda-forge) — headless Chrome is blocked by Cloudflare,
so we use headed Chromium via Node.js Playwright with anti-detection flags.

Usage:
    python scrape_torvik.py
"""

import json
import subprocess
import tempfile
from pathlib import Path

YEARS = [2011, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025]

_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "upset_model"
OUTPUT_FILE = str(_OUTPUT_DIR / "torvik_historical.json")

# Node.js script that uses Playwright to scrape Torvik
# Torvik blocks headless browsers and curl; headed Chromium with anti-detection works.
_NODE_SCRIPT = r"""
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

  const years = YEARS_PLACEHOLDER;
  const allData = [];

  for (const year of years) {
    process.stderr.write(`Scraping ${year}...\n`);
    await page.goto(`https://barttorvik.com/trank.php?year=${year}`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(3000);

    const teams = await page.evaluate((yr) => {
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

        const conf = cleanText(cells[2]);
        const barthag = cleanText(cells[7]);
        const wab = cleanText(cells[cells.length - 1]);

        // Extract team name from link text node (before seed info spans)
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
            year: yr,
            team: team,
            conference: conf,
            barthag: parseFloat(barthag),
            wab: parseFloat(wab)
          });
        }
      }
      return results;
    }, year);

    process.stderr.write(`  ${year}: ${teams.length} teams\n`);
    allData.push(...teams);

    if (year !== years[years.length - 1]) {
      await page.waitForTimeout(1500);
    }
  }

  process.stdout.write(JSON.stringify(allData, null, 2));
  process.stderr.write(`\nTotal: ${allData.length} team-seasons\n`);

  await browser.close();
})();
"""


def scrape_all_years():
    """Run Node.js Playwright scraper and return parsed data."""
    script = _NODE_SCRIPT.replace('YEARS_PLACEHOLDER', json.dumps(YEARS))

    with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
        f.write(script)
        script_path = f.name

    # Find Playwright node_modules
    import shutil
    node_bin = shutil.which('node')
    if not node_bin:
        raise RuntimeError("Node.js not found. Install via conda: conda install nodejs")

    # Detect NODE_PATH for conda playwright
    import os
    conda_prefix = os.environ.get('CONDA_PREFIX', '')
    node_path = os.path.join(conda_prefix, 'lib', 'node_modules') if conda_prefix else ''

    env = os.environ.copy()
    if node_path:
        env['NODE_PATH'] = node_path

    print(f"Running Playwright scraper for {len(YEARS)} years...")
    result = subprocess.run(
        ['node', script_path],
        capture_output=True, text=True, env=env, timeout=600
    )

    if result.returncode != 0:
        print(f"STDERR:\n{result.stderr}")
        raise RuntimeError(f"Scraper failed with exit code {result.returncode}")

    # Print progress from stderr
    if result.stderr:
        print(result.stderr)

    data = json.loads(result.stdout)
    return data


if __name__ == '__main__':
    print("T-Rank Historical Data Scraper (Bart Torvik)")
    print("=" * 60)

    data = scrape_all_years()

    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\nSaving to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"Done! {len(data)} team-seasons saved.")
