# Upset Prediction Model

Logistic regression model that predicts the probability of an upset in NCAA tournament games. Trained on 738 real tournament games from 2011-2025 (excluding 2012 and 2020 -- no tournaments held). Evaluated via Leave-One-Year-Out cross-validation.

## Current Model Performance

```
AUC:   0.7515  (+13.1% over seed-only baseline of 0.6646)
Brier: 0.1723
Type:  Logistic Regression (C=1.0) with isotonic calibration
Data:  738 games, 216 upsets (29.3%), 13 tournament years
```

## Features

The model extracts 14 candidate features from team stats, then L1 (Lasso) screening selects the 8 that survive regularization. The selected features and their data sources:

| # | Feature | Source | Description |
|---|---------|--------|-------------|
| 1 | `seed_diff` | NCAA bracket | Seed gap (e.g., 1v16 = 15) |
| 2 | `adj_o_diff` | KenPom | Offensive efficiency differential |
| 3 | `adj_t_diff` | KenPom | Tempo differential |
| 4 | `seed_x_adj_em` | KenPom | Seed x efficiency interaction |
| 5 | `top25_winpct_diff` | LRMC | Top-25 win percentage differential (fav - dog) |
| 6 | `dog_top25_winpct` | LRMC | Underdog's win% vs top-25 teams (battle-tested signal) |
| 7 | `barthag_diff` | Torvik | Win probability differential (partially independent of AdjEM) |
| 8 | `wab_diff` | Torvik | Wins-above-bubble differential (resume strength) |

Features eliminated by L1: `adj_em_diff` (subsumed by barthag_diff), `momentum_diff`, `dog_momentum`, `dog_last10_winpct`, `spread`, `spread_vs_expected` (no data for these in training set).

## Architecture

```
features.py          extract_features() --> 14-element vector
                           |
train_sklearn.py     L1 screening --> 8 features selected
                     StandardScaler --> LogisticRegression(C=1.0)
                     CalibratedClassifierCV(method='isotonic')
                           |
                     sklearn_model.joblib
                           |
predict.py           UpsetPredictor.predict() --> P(upset) in [0.01, 0.99]
```

The saved `.joblib` package contains the scaler, calibrated logistic model, and feature selection indices. At prediction time, all 14 features are extracted, then the saved indices select the 8 active features before scaling and prediction.

## Usage

### Predicting (inference)

```python
from upset_model.predict import UpsetPredictor

predictor = UpsetPredictor()

# From raw dicts
p_upset = predictor.predict(
    team_a={'seed': 1, 'adj_em': 30, 'adj_o': 120, 'adj_d': 90, 'adj_t': 68},
    team_b={'seed': 9, 'adj_em': 15, 'adj_o': 110, 'adj_d': 95, 'adj_t': 65},
    round_num=1,
    team_a_torvik={'barthag': 0.97, 'wab': 10.0},
    team_b_torvik={'barthag': 0.85, 'wab': 1.5},
    team_a_lrmc={'top25_wins': 8, 'top25_losses': 2, 'top25_games': 10},
    team_b_lrmc={'top25_wins': 2, 'top25_losses': 3, 'top25_games': 5},
)

# From Team objects (used by the bracket optimizer pipeline)
p_upset = predictor.predict_from_teams(favorite, underdog, round_num=1)
```

`predict()` returns P(team_b wins) -- i.e., the upset probability. Team A is always the favorite (lower seed). Missing data (no Torvik, no LRMC) degrades gracefully to neutral defaults.

### Training

```bash
conda activate bracket
python upset_model/train_sklearn.py
```

This runs the full training pipeline:

1. Loads game data from `data/upset_model/*.json`
2. Joins team stats from KenPom, LRMC, and Torvik by year + normalized name
3. Extracts features via `features.py`
4. Runs L1 screening (LassoCV) to select features
5. Trains L2 logistic regression on selected features
6. Wraps with isotonic calibration
7. Evaluates via Leave-One-Year-Out CV (13 folds)
8. Saves model to `data/upset_model/sklearn_model.joblib`

Output includes per-year AUC, overall AUC, Brier score, feature importances, and calibration diagnostics.

## Data Sources

Training data lives in `data/upset_model/`. Each file is produced by its corresponding scraper:

| File | Scraper | Records | Content |
|------|---------|---------|---------|
| `ncaa_tournament_real.json` | `scrape_ncaa_real.py` | 798 games | Real tournament results (teams, seeds, scores, winner) |
| `kenpom_historical.json` | `scrape_kenpom_real.py` | 4,604 teams | AdjEM, AdjO, AdjD, AdjT, Luck per team-year |
| `lrmc_historical.json` | `scrape_lrmc.py` | 4,242 teams | LRMC rank, top-25 W-L record per team-year |
| `torvik_historical.json` | `scrape_torvik.py` | 4,594 teams | Barthag, WAB per team-year |
| `sklearn_model.joblib` | `train_sklearn.py` | -- | Trained model package |

### Scraper Notes

- **KenPom + LRMC historical**: Scraped from Wayback Machine snapshots (March dates for each year). Uses urllib + BeautifulSoup.
- **Torvik historical**: Scraped from barttorvik.com using Node.js Playwright with headed Chromium. Cloudflare blocks headless browsers and curl; headed Chromium with `--disable-blink-features=AutomationControlled` and a custom User-Agent bypasses it.
- **NCAA games**: Scraped from `data.ncaa.com/casablanca/scoreboard/` JSON API, scanning March-April dates for each year.

### Running the Scrapers

The scrapers only need to be run to rebuild training data (e.g., after a new tournament year). The model ships pre-trained.

```bash
# Requires conda environment with nodejs + playwright
conda activate bracket

python upset_model/scrape_ncaa_real.py      # NCAA game results
python upset_model/scrape_kenpom_real.py     # KenPom historical (Wayback)
python upset_model/scrape_lrmc.py            # LRMC historical (Wayback)
python upset_model/scrape_torvik.py          # Torvik historical (Playwright)

# Then retrain
python upset_model/train_sklearn.py
```

## Name Matching

Team names differ across sources (KenPom: "Connecticut", Torvik: "UConn", LRMC: "NC_State", NCAA: "North Carolina St."). All normalization is centralized in `src/name_matching.py`:

- `normalize_team_name()` -- 63+ aliases, canonical form
- `normalize_torvik_name()` -- 16 Torvik-specific aliases
- `normalize_lrmc_name()` -- 70+ LRMC underscore/abbreviation aliases

Both training (`train_sklearn.py`) and live prediction (`src/enrich.py`) import from the same shared module to ensure consistency.

## File Reference

| File | Purpose |
|------|---------|
| `predict.py` | `UpsetPredictor` class -- public API for predictions |
| `features.py` | `extract_features()` -- feature computation (single source of truth) |
| `train_sklearn.py` | Full training pipeline with LOO-CV evaluation |
| `scrape_ncaa_real.py` | NCAA tournament game scraper (2011-2025) |
| `scrape_kenpom_real.py` | KenPom historical scraper via Wayback Machine |
| `scrape_lrmc.py` | LRMC historical scraper via Wayback Machine |
| `scrape_torvik.py` | Torvik historical scraper via Node.js Playwright |
