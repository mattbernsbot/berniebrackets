# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

March Madness bracket optimizer for small pools (10-50 people). Maximizes P(1st place) using ML upset prediction + contrarian ownership analysis + Monte Carlo simulation.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt
pip install scikit-learn joblib numpy pandas  # for upset model + optimizer

# For Torvik enrichment (bypasses Cloudflare)
conda install -c conda-forge nodejs playwright
playwright install chromium

# Run full pipeline (collect data → analyze → generate bracket)
python main.py full --sims 10000 --pool-size 25

# Run individual stages
python main.py collect          # Scrape KenPom, Yahoo picks, NCAA bracket, Torvik, LRMC
python main.py analyze          # Run model + optimization
python main.py bracket          # Generate output from existing data

# Useful CLI flags
python main.py full --seed 42 --risk aggressive --verbose
python main.py full --no-yahoo --no-strict-yahoo  # Skip Yahoo scraping (testing)
python main.py full --first-four "Texas,Howard"    # Specify First Four winners
python main.py full --update-github-pages          # Copy index.html to docs/

# Run tests
pytest
pytest tests/test_optimizer.py              # Single test file
pytest tests/test_optimizer.py -k "test_name" -v  # Single test, verbose

# Train the upset model (requires scraped historical data)
python upset_model/train_sklearn.py
```

## Architecture

The pipeline runs in three stages: **collect → analyze → bracket**.

### Pipeline Flow (main.py)

1. **Collect** (`cmd_collect`) — Multi-source data collection:
   - Fetches the real NCAA bracket from ncaa.com via `scripts/fetch_real_bracket.py` + `scripts/parse_bracket_html.py`
   - Scrapes KenPom efficiency ratings for all D1 teams (`src/scout.py:scrape_kenpom`)
   - Scrapes Yahoo Bracket Mayhem public pick distributions for all 6 rounds (`src/scout.py:scrape_yahoo_picks`)
   - Enriches teams with Torvik (Barthag, WAB) and LRMC (top-25 W-L) data (`src/enrich.py`)
   - Merges NCAA bracket with KenPom stats via fuzzy name matching (`src/load_real_bracket.py`, `src/name_matching.py`)
   - Produces `data/teams.json`, `data/bracket_structure.json`, `data/public_picks.json`
   - Falls back to KenPom-generated bracket if ncaa.com bracket unavailable

2. **Analyze** (`cmd_analyze`) — Model + optimization:
   - **Sharp** (`src/sharp.py`) — Builds pairwise win probability matrix for all 68 teams. Uses the trained sklearn upset model (`upset_model/predict.py`) when available, falls back to seed-based historical rates. Produces `data/matchup_probabilities.json`.
   - **Contrarian** (`src/contrarian.py`) — Builds ownership profiles from Yahoo pick data (or seed-based estimates). Calculates pool-size-aware leverage = `model_prob / ((pool_size - 1) * ownership + 1)`. Produces `data/ownership.json`.
   - **Optimizer** (`src/optimizer.py`) — The core engine:
     - **Component 1** (Champion Evaluator): Quick Monte Carlo to estimate title probabilities, then evaluates up to 24 champion candidates (seeds 1-6) ranked by pool-adjusted value
     - **Component 2** (Scenario Generator): Generates ~600 scenarios across champions × 3 chaos levels × multiple FF compositions × cinderella variants × chaos-region permutations
     - **Component 3** (Bracket Constructor): Builds each bracket top-down: champion → FF paths → cinderella → EMV upsets → chalk fill. Two-gate upset system: EMV floor + target count
     - **Component 3.5**: Injects 3 deterministic reference brackets (CHALK, KP_CHALK, BERNS_CHALK) for comparison
     - Deduplicates identical brackets before Monte Carlo evaluation
     - **Component 5** (Shared-Sim MC): Evaluates all unique brackets via Monte Carlo simulation against opponent pools sampled from Yahoo ownership. Uses shared tournament sims + numpy vectorized scoring
     - **Component 7** (Output Selection): Tags top 3 diverse brackets: `optimal`, `safe_alternate`, `aggressive_alternate`. Returns ALL evaluated brackets sorted by P(1st)
   - Saves all brackets to `data/all_brackets.json` (convenience cache for standalone `analyze` + `bracket` workflow)

3. **Bracket** (`cmd_bracket`) — Output generation via `src/analyst.py`. Generates 5 files into `results/<timestamp>/`:
   - `analysis.md` — Comprehensive report with cross-bracket stats (champion distribution, FF frequency, upset consensus, all-brackets comparison table, model vs public)
   - `bracket.txt` — ASCII bracket visualization (optimal only)
   - `summary.json` — Machine-readable summary with aggregate stats
   - `all_brackets.json` — Every evaluated bracket with full picks and stats
   - `index.html` — Interactive HTML bracket viewer with dropdown to browse all brackets, team detail panels, matchup data, glossary

### Upset Model (`upset_model/`)

Calibrated logistic regression trained on 798 NCAA tournament games (2011-2025, excluding 2012/2020). 14 candidate features extracted in `features.py` (shared between training and prediction); L1 screening selects 8 active features. Data from KenPom, Torvik, and LRMC. Model saved as `.joblib` file. The predictor is lazy-loaded as a global singleton in `sharp.py`. See `upset_model/README.md` for full details.

### Key Modules

| Module | Purpose |
|--------|---------|
| `src/scout.py` | KenPom + Yahoo scraping |
| `src/sharp.py` | Win probability matrix (ensemble model + fallback) |
| `src/contrarian.py` | Ownership analysis, leverage scores |
| `src/optimizer.py` | Scenario generation, bracket construction, Monte Carlo evaluation |
| `src/analyst.py` | Output generation (markdown, ASCII, JSON, HTML) |
| `src/enrich.py` | Live Torvik + LRMC scraping for current year |
| `src/load_real_bracket.py` | Merge NCAA bracket with KenPom stats |
| `src/name_matching.py` | Team name normalization across data sources (63+ aliases) |
| `src/models.py` | Dataclasses (Team, Bracket, Config, CompleteBracket, etc.) |
| `src/constants.py` | Seed matchup rates, ownership curves, scoring tables |
| `src/config.py` | Config loading (JSON + CLI merge), auto risk profile |
| `src/utils.py` | JSON I/O, HTTP fetch, logging setup |

### Key Data Models (`src/models.py`)

All dataclasses have `to_dict()`/`from_dict()` for JSON serialization. Key types:
- `Team` — stats, seeding, and enrichment fields (barthag, wab, top25 record)
- `BracketStructure` / `BracketSlot` — 63-slot tournament structure (+ play-ins)
- `CompleteBracket` / `BracketPick` — a filled-out bracket with evaluation metrics
- `OwnershipProfile` — public pick % and pool-size-aware leverage by round
- `Scenario` — narrative driving bracket construction (chalk/contrarian/chaos)
- `ChampionCandidate`, `UpsetCandidate`, `PathInfo` — optimizer intermediates
- `EvaluatedBracket` — bracket with Monte Carlo evaluation metadata
- `Config` — all settings (priority: CLI > config.json > defaults)

### Key Concepts

- **EMV (Expected Marginal Value)**: `P(upset) × ownership_gain − P(chalk) × ownership_cost`. Positive EMV = picking upset increases P(1st). Two-gate system: EMV floor threshold + target upset count per chaos level.
- **Pool-Size-Aware Leverage**: `model_prob / ((pool_size - 1) * ownership + 1)`. Accounts for expected number of opponents with the same pick. Same pick has different value in 10-person vs 50-person pools.
- **Top-down construction**: Champion picked first (highest pool-value), then FF paths locked, then cinderella path, then EMV-positive upsets added, then remaining slots filled with chalk.
- **Scoring**: ESPN standard `[10, 20, 40, 80, 160, 320]` per round. Championship pick worth 32x a Round 1 pick.
- **Reference brackets**: CHALK (pure seed order), KP_CHALK (pure KenPom AdjEM), BERNS_CHALK (model probability) — injected for comparison baseline.

## Configuration

`config.json` holds defaults. CLI flags override. Key settings: `pool_size`, `sim_count`, `risk_profile` (auto/conservative/balanced/aggressive), `scoring`, `random_seed`.

Auto risk profile: pool ≤10 → conservative, 11-50 → balanced, 51+ → aggressive.

## Data Flow

`data/` is for inputs only — cached scraped data and the trained model (gitignored). All optimizer output goes to `results/<timestamp>/`. The `full` command clears stale `data/*.json` between runs but preserves `real_bracket_2026.json`, raw HTML, and cached Torvik/LRMC/KenPom data. In the `full` pipeline, brackets flow in-memory from analyze → bracket stage; `data/all_brackets.json` is only written as a convenience cache for the standalone `analyze` + `bracket` two-step workflow.

GitHub Pages: `--update-github-pages` copies `index.html` to `docs/index.html`.

## Dependencies

**Core pipeline**: `beautifulsoup4` for HTML scraping, `numpy` for vectorized Monte Carlo scoring, `pytest` for tests.

**Upset model** (prediction): `scikit-learn`, `joblib`, `numpy`. These are needed at runtime when the trained model is available.

**Upset model** (training only): additionally `pandas`.

**Torvik enrichment**: `nodejs` + `playwright` via conda (Cloudflare bypass).

All other functionality uses Python stdlib (`urllib`, `json`, `random`, `dataclasses`, `argparse`, `logging`, `statistics`, `concurrent.futures`).
