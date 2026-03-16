# BernieBrackets

March Madness bracket optimizer for small pools (10-50 people). Maximizes your probability of finishing 1st by combining ML upset prediction, contrarian ownership analysis, and Monte Carlo simulation.

The core insight: in a small pool, you don't win by picking the most correct bracket -- you win by picking the bracket that's most *different from everyone else's* when you happen to be right. BernieBrackets finds those high-leverage picks.

## Quickstart

```bash
# Set up conda environment
conda create -n bracket python=3.11
conda activate bracket
pip install -r requirements.txt
pip install scikit-learn joblib numpy pandas

# For Torvik data enrichment (bypasses Cloudflare)
conda install -c conda-forge nodejs playwright
playwright install chromium

# Run the full pipeline
python main.py full --sims 10000 --pool-size 25
```

Results are written to `results/<timestamp>/`.

## How It Works

### Pipeline Stages

The `full` command runs three stages in sequence:

**1. Collect** (`python main.py collect`)

Scrapes live data from multiple sources and assembles the tournament field:

| Source | Data | Method |
|--------|------|--------|
| **ncaa.com** | 68-team bracket with seeds, regions, play-in games | urllib + BeautifulSoup |
| **kenpom.com** | AdjEM, AdjO, AdjD, AdjT, Luck for all 363 D1 teams | urllib + BeautifulSoup |
| **barttorvik.com** | Barthag (win probability), WAB (wins above bubble) | Node.js Playwright (Cloudflare bypass) |
| **LRMC (Georgia Tech)** | Top-25 W-L record per team | urllib + BeautifulSoup |
| **Yahoo Bracket Mayhem** | Public pick percentages for all 6 rounds | urllib |

All scraped data is cached to `data/` so re-runs don't re-scrape unless forced.

**2. Analyze** (`python main.py analyze`)

- **Sharp** -- Builds a pairwise win probability matrix for all 68 teams using the trained upset model (see `upset_model/README.md`). Falls back to seed-based historical rates if the model isn't available.
- **Contrarian** -- Computes leverage scores: `model_probability / public_ownership`. A leverage > 1 means the public is undervaluing a team.
- **Optimizer** -- Constructs brackets top-down (champion first, then Final Four paths, then EMV-positive upsets, then chalk). Evaluates each bracket via Monte Carlo simulation against a pool of opponents sampled from Yahoo ownership data. Selects the bracket that maximizes P(1st place).

**3. Bracket** (`python main.py bracket`)

Generates human-readable output: `analysis.md`, `bracket.txt`, `summary.json`.

### Key Concepts

- **EMV (Expected Marginal Value)**: `P(upset) * ownership_gain - P(chalk) * ownership_cost`. Positive EMV = picking the upset increases your expected finish.
- **Leverage**: `model_probability / public_ownership`. The public picks Duke to the Final Four 40% of the time but the model says 35% -- that's leverage < 1, avoid. The public picks a 7-seed at 8% but the model says 15% -- leverage ~2, pick it.
- **Top-down construction**: Champion is picked first (highest pool-value), then Final Four paths are locked, then EMV-positive upsets are added in descending order, then remaining slots are filled with chalk.
- **Scoring**: ESPN standard `[10, 20, 40, 80, 160, 320]` per round. The championship pick alone is worth 320 points -- 32x a Round 1 pick.

## CLI Reference

```bash
# Full pipeline (most common)
python main.py full --sims 10000 --pool-size 25

# Individual stages
python main.py collect
python main.py analyze
python main.py bracket

# Options (available on all commands)
--pool-size N          # Number of people in your pool (default: 25)
--sims N               # Monte Carlo simulations (default: 10000)
--risk PROFILE         # conservative | balanced | aggressive | auto (default: auto)
--seed N               # Random seed for reproducibility
--verbose / -v         # Debug logging

# Collect-specific options
--no-yahoo             # Skip Yahoo scraping, use seed-based ownership estimates
--no-strict-yahoo      # Don't fail if Yahoo is unavailable (testing only)
--force-yahoo-refresh  # Bypass Yahoo cache
--kenpom-file PATH     # Use local KenPom HTML instead of scraping
--year YYYY            # Tournament year (default: 2026)
```

## Configuration

`config.json` sets defaults. CLI flags override.

```json
{
  "pool_size": 25,
  "scoring": [10, 20, 40, 80, 160, 320],
  "sim_count": 10000,
  "risk_profile": "auto",
  "random_seed": null
}
```

## Project Structure

```
berniebrackets/
  main.py                 # CLI entry point, pipeline orchestration
  config.json             # Default configuration
  requirements.txt        # Python dependencies

  src/
    scout.py              # KenPom + Yahoo scraping
    sharp.py              # Win probability matrix (uses upset model)
    contrarian.py         # Ownership analysis, leverage scores
    optimizer.py          # Bracket construction + Monte Carlo simulation
    analyst.py            # Output generation (markdown, text, JSON)
    enrich.py             # Live Torvik + LRMC scraping for current year
    load_real_bracket.py  # Merge NCAA bracket with KenPom stats
    name_matching.py      # Team name normalization across data sources
    models.py             # Dataclasses (Team, Bracket, Config, etc.)
    constants.py          # Seed matchup rates, URLs, scoring tables
    config.py             # Config loading (JSON + CLI merge)
    utils.py              # JSON I/O, logging setup

  upset_model/            # Standalone ML model (see upset_model/README.md)
    predict.py            # Public prediction API (UpsetPredictor class)
    features.py           # Feature extraction (14 candidate features)
    train_sklearn.py      # Model training pipeline
    scrape_*.py           # Historical data scrapers

  scripts/
    fetch_real_bracket.py   # Fetch NCAA bracket from ncaa.com
    parse_bracket_html.py   # Parse saved NCAA bracket HTML
    fetch_kenpom_2026.py    # Fetch current-year KenPom data

  data/                   # Intermediate data (gitignored, auto-populated)
  results/                # Output per run (results/<timestamp>/)
```

## Data Flow

```
ncaa.com ------> real_bracket_2026.json ---+
kenpom.com ----> teams_kenpom_temp.json ---+--> teams.json (68 teams, enriched)
barttorvik.com > torvik_2026_live.json ----+          |
lrmc.gatech.edu> lrmc_2026_live.json -----+          |
                                                      v
yahoo ---------> public_picks.json       matchup_probabilities.json
                                                      |
                                          ownership.json (leverage scores)
                                                      |
                                          optimal_brackets.json
                                                      |
                                          results/<timestamp>/
                                            analysis.md
                                            bracket.txt
                                            summary.json
```

## Dependencies

**Core pipeline** (stdlib + beautifulsoup4):
```
beautifulsoup4>=4.12.0
pytest>=7.0.0
```

**Upset model** (training only):
```
scikit-learn>=1.3.0
numpy>=1.24.0
pandas>=2.0.0
joblib>=1.3.0
```

**Torvik enrichment** (live data collection):
```
nodejs          (conda install -c conda-forge nodejs)
playwright      (conda install -c conda-forge playwright)
```

The pre-trained model (`data/upset_model/sklearn_model.joblib`) is included, so you don't need the training dependencies just to run the optimizer.
