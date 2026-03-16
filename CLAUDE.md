# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

March Madness bracket optimizer for small pools (10-50 people). Maximizes P(1st place) using ML upset prediction + contrarian ownership analysis + Monte Carlo simulation.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run full pipeline (collect data → analyze → generate bracket)
python main.py full --sims 500 --pool-size 25

# Run individual stages
python main.py collect          # Scrape KenPom, Yahoo picks, NCAA bracket
python main.py analyze          # Run model + optimization
python main.py bracket          # Generate output from existing data

# Useful CLI flags
python main.py full --seed 42 --risk aggressive --verbose
python main.py full --no-yahoo --no-strict-yahoo  # Skip Yahoo scraping (testing)

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

1. **Scout** (`src/scout.py`) — Scrapes KenPom efficiency ratings, Yahoo Fantasy public pick distributions (all 6 rounds), and NCAA bracket structure. Produces `data/teams.json`, `data/bracket_structure.json`, `data/public_picks.json`.

2. **Sharp** (`src/sharp.py`) — Converts team stats into pairwise win probabilities. Uses the sklearn upset model (`upset_model/predict.py`) when available, falls back to seed-based historical rates from `constants.py`. Produces a matchup probability matrix.

3. **Contrarian** (`src/contrarian.py`) — Builds ownership profiles from Yahoo pick data (or seed-based estimates). Calculates leverage = model probability / public ownership. Higher leverage = more contrarian value.

4. **Optimizer** (`src/optimizer.py`) — The core engine. Returns all ~24 evaluated brackets:
   - Evaluate top 8 champion candidates (pool-value = title_prob / ownership)
   - Generate ~24 scenarios (each champion at appropriate chaos levels + FF variants)
   - Build bracket top-down: champion → FF paths → EMV upsets → fill chalk
   - Monte Carlo simulate each bracket against opponent pools sampled from Yahoo ownership
   - Tag top 3 diverse brackets (optimal, safe, aggressive) but return all ~24

5. **Analyst** (`src/analyst.py`) — Generates 5 output files into `results/<timestamp>/`:
   - `analysis.md` — Comprehensive report with cross-bracket stats (champion distribution, FF frequency, upset consensus, all-brackets comparison table, model vs public)
   - `bracket.txt` — ASCII bracket visualization (optimal only)
   - `summary.json` — Machine-readable summary with aggregate stats
   - `all_brackets.json` — Every evaluated bracket with full picks and stats
   - `bracket.html` — Interactive bracket viewer with dropdown to browse all ~24 brackets

### Upset Model (`upset_model/`)

Standalone sklearn ensemble (Logistic Regression + Random Forest + GBM) trained on 738 NCAA tournament games (2011-2025). 16 features extracted in `features.py` (shared between training and prediction). Model saved as `.joblib` file. The predictor is lazy-loaded as a global singleton in `sharp.py`.

### Key Data Models (`src/models.py`)

All dataclasses have `to_dict()`/`from_dict()` for JSON serialization. Key types:
- `Team` — stats and seeding
- `BracketStructure` / `BracketSlot` — 67-slot tournament structure
- `CompleteBracket` / `BracketPick` — a filled-out bracket
- `OwnershipProfile` — public pick % and leverage by round
- `Scenario` — narrative driving bracket construction (chalk/contrarian/chaos)
- `ChampionCandidate`, `UpsetCandidate`, `PathInfo` — optimizer intermediates
- `Config` — all settings (priority: CLI > config.json > defaults)

### Key Concepts

- **EMV (Expected Marginal Value)**: P(upset) × ownership_gain − P(chalk) × ownership_cost. Positive EMV = picking upset increases P(1st).
- **Leverage**: model_probability / public_ownership. >1 means public is undervaluing.
- **Top-down construction**: Champion picked first, then Final Four paths locked, then EMV-positive upsets added, then remaining slots filled with chalk.
- **Scoring**: ESPN standard `[10, 20, 40, 80, 160, 320]` per round. Championship pick worth 32x a Round 1 pick.

## Configuration

`config.json` holds defaults. CLI flags override. Key settings: `pool_size`, `sim_count`, `risk_profile` (auto/conservative/balanced/aggressive), `scoring`, `random_seed`.

## Data Flow

`data/` is for inputs only — cached scraped data and the trained model (gitignored). All optimizer output goes to `results/<timestamp>/`. The `full` command clears stale `data/*.json` between runs but preserves `real_bracket_2026.json` and raw HTML files. In the `full` pipeline, brackets flow in-memory from analyze → bracket stage; `data/all_brackets.json` is only written as a convenience cache for the standalone `analyze` + `bracket` two-step workflow.

## Dependencies

Minimal: `beautifulsoup4` for HTML scraping, `pytest` for tests. The upset model additionally uses `scikit-learn`, `joblib`, `numpy`. Core pipeline uses only stdlib (`urllib`, `json`, `random`, `dataclasses`, `argparse`, `logging`).
