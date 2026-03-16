# BernieBrackets 🏀

March Madness bracket optimizer for winning small pools (10-50 people). Uses machine learning upset prediction + contrarian ownership analysis to maximize P(1st place).

## How It Works

1. **Upset Model** — 16-feature sklearn ensemble (Logistic Regression + Random Forest + GBM) trained on 738 real NCAA tournament games (2011-2025). LOO-CV AUC = 0.6976.
2. **Public Ownership** — Scrapes Yahoo Fantasy pick distribution for all 6 rounds (R1-Championship). Real per-team, per-round data — not estimated.
3. **KenPom Stats** — Live scraping of current season efficiency ratings (AdjEM, AdjO, AdjD, AdjT, Luck).
4. **Contrarian EMV** — Expected Marginal Value = P(upset) × gain − P(chalk) × cost. Picks upsets where the model disagrees with the public.
5. **Monte Carlo Simulation** — Simulates 500+ tournament outcomes against 24 opponent brackets sampled from Yahoo ownership distributions.
6. **Top-Down Construction** — Champion → Final Four paths → EMV upsets → fill chalk → validate coherence.

## Quick Start

```bash
pip install -r requirements.txt
python main.py full --sims 500 --pool-size 25
```

Results land in `results/<timestamp>/`.

## Project Structure

```
main.py                 # CLI entry point (collect → analyze → bracket)
src/
  scout.py              # Data collection (KenPom, Yahoo picks, NCAA bracket)
  sharp.py              # Matchup probability engine (wraps upset model)
  contrarian.py         # Ownership profiles + EMV calculations
  optimizer.py          # Scenario generation, bracket construction, Monte Carlo
  analyst.py            # Output generation (analysis.md, bracket.txt, summary.json)
  models.py             # Data models (Team, Matchup, CompleteBracket, etc.)
  load_real_bracket.py  # NCAA bracket → Team objects with KenPom stats
  constants.py          # Scoring, seed curves, configuration
  config.py             # Config loading
  utils.py              # JSON I/O helpers
upset_model/
  features.py           # 16-feature extraction (shared by training + prediction)
  predict.py            # UpsetPredictor API (loads sklearn_model.joblib)
  train_sklearn.py      # Model training with LOO-CV evaluation
  scrape_ncaa_real.py   # NCAA tournament game scraper (2011-2025)
  scrape_kenpom_real.py # Historical KenPom scraper (Wayback Machine)
  scrape_lrmc.py        # LRMC ranking scraper (Georgia Tech)
tests/                  # Test suite
results/                # Timestamped output from each pipeline run
```

## The 16 Features

| # | Feature | Description |
|---|---------|-------------|
| 1 | seed_diff | Seed gap (e.g., 1v16 = 15) |
| 2 | round_num | Tournament round (1-6) |
| 3 | adj_em_diff | KenPom net efficiency differential |
| 4 | adj_o_diff | Offensive efficiency differential |
| 5 | adj_d_diff | Defensive efficiency differential |
| 6 | adj_t_diff | Tempo differential |
| 7 | seed_x_adj_em | Seed × efficiency interaction |
| 8 | round_x_seed | Round × seed interaction |
| 9 | round_x_adj_em | Round × efficiency interaction |
| 10 | luck_diff | KenPom luck differential |
| 11 | favorite_luck | Favorite's luck (lucky favorites are vulnerable) |
| 12 | tempo_mismatch | Absolute tempo difference |
| 13 | slow_dog_vs_fast_fav | Binary: slow underdog vs fast favorite |
| 14 | top25_winpct_diff | LRMC vs-top-25 win% differential |
| 15 | dog_top25_winpct | Underdog's record vs top-25 teams |
| 16 | luck_x_seed_diff | Luck × seed interaction |

## Data Sources

- **NCAA.com API** — Real tournament game results
- **KenPom** — Efficiency ratings (live + historical via Wayback Machine)
- **LRMC** — Georgia Tech logistic regression Markov chain rankings
- **Yahoo Fantasy** — Public pick distribution (all 6 rounds)

## Model Performance

```
Seed only (1 feat):        AUC = 0.6222
Seed + KP NetRtg (2 feat): AUC = 0.6330
Full model (16 feat):      AUC = 0.6976  (+12% over seed-only)
```

Training data: 738 games, 216 upsets (29.3%), 13 years. LOO-CV by year ensures no data leakage.
