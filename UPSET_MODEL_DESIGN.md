# Upset Prediction Model — Implementation Design Document

> **Supersedes:** `UPSET_MODEL_SCOPE.md` (initial scoping)
> **Module location:** `projects/builder-engine/jobs/bracket-optimizer/upset_model/`
> **Constraint:** Python 3.10+ stdlib only. No sklearn, pandas, numpy, xgboost.
> **Allowed:** `math`, `statistics`, `random`, `json`, `csv`, `collections`, `itertools`, `functools`, `logging`, `os`, `pathlib`
> **External:** `beautifulsoup4` (scraping only, not used at prediction time)
> **Target hardware:** 3.7 GB RAM VPS (Ubuntu, x64)

---

## Table of Contents

1. [Module Architecture](#1-module-architecture)
2. [Feature Set (28 Candidates)](#2-feature-set-28-candidates)
3. [Stepwise Feature Selection](#3-stepwise-feature-selection)
4. [Logistic Regression (from scratch)](#4-logistic-regression-from-scratch)
5. [Random Forest (from scratch)](#5-random-forest-from-scratch)
6. [Model Comparison](#6-model-comparison)
7. [Training Pipeline](#7-training-pipeline)
8. [Prediction API](#8-prediction-api)
9. [Integration with Bracket Optimizer](#9-integration-with-bracket-optimizer)
10. [Timeline and Coding Sessions](#10-timeline-and-coding-sessions)

---

## 1. Module Architecture

### 1.1 Directory Layout

```
upset_model/
├── __init__.py              # Public API: UpsetPredictor, train_pipeline()
├── data/                    # Training data (CSVs, JSONs) — gitignored except schemas
│   ├── README.md            # Documents data file formats and provenance
│   ├── kaggle/              # Raw Kaggle March Mania CSVs (manual download)
│   ├── ratings/             # Scraped Sports Reference ratings (one JSON per year)
│   └── training/            # Processed training data ready for model
│       ├── games.json       # All tournament games 2002-2025 with features
│       └── feature_matrix.json  # Standardized feature vectors + labels
├── features.py              # Feature extraction: raw team stats → model features
├── logistic.py              # Logistic regression: gradient descent, predict, std errors
├── random_forest.py         # Random forest: CART trees, bootstrap, OOB estimation
├── selection.py             # Stepwise selection: forward, backward, VIF screening
├── train.py                 # Training pipeline: orchestrates data→features→select→train→eval
├── predict.py               # UpsetPredictor class (the public interface)
├── evaluate.py              # Brier score, log loss, AUC, calibration curves
├── scrape.py                # Sports Reference scraper (beautifulsoup4)
├── data_prep.py             # Kaggle CSV parsing, data joining, cleaning
├── models/                  # Stored model artifacts (JSON)
│   ├── logistic_model.json  # Coefficients, means, stds, feature names
│   ├── forest_model.json    # Tree structures, feature names, hyperparams
│   └── active_model.json    # Symlink/copy of whichever model won comparison
└── tests/
    ├── __init__.py
    ├── test_logistic.py     # Unit tests for logistic regression
    ├── test_forest.py       # Unit tests for random forest
    ├── test_features.py     # Unit tests for feature extraction
    └── test_pipeline.py     # Integration tests for full pipeline
```

### 1.2 Dependency Graph

```
predict.py  ←  bracket optimizer calls this (the ONLY public interface)
    ↑
    │ loads
    ↓
models/active_model.json

train.py  ←  run offline to produce model artifacts
    ├── data_prep.py  →  scrape.py (one-time data acquisition)
    ├── features.py   (compute feature vectors from raw data)
    ├── selection.py  (stepwise feature selection)
    │   └── logistic.py (used internally for AIC/BIC computation)
    ├── logistic.py   (train logistic model)
    ├── random_forest.py  (train forest model)
    └── evaluate.py   (compare models, pick winner)
```

**Key isolation principle:** `predict.py` imports NOTHING from the bracket optimizer. The bracket optimizer imports ONLY `predict.py`. The module is a black box: team stats go in, probability comes out.

### 1.3 Data Flow Summary

```
[Kaggle CSVs] + [Sports Ref HTML] 
        ↓ data_prep.py + scrape.py
[data/training/games.json]           — raw game records with team stats
        ↓ features.py
[data/training/feature_matrix.json]  — standardized feature vectors + labels
        ↓ selection.py
[optimal feature subset]             — 10-15 features surviving stepwise
        ↓ logistic.py + random_forest.py
[models/logistic_model.json]         — trained logistic coefficients
[models/forest_model.json]           — trained forest trees
        ↓ evaluate.py
[models/active_model.json]           — best model selected
        ↓ predict.py
P(upset) float                       — what the bracket optimizer consumes
```

---

## 2. Feature Set (28 Candidates)

Every feature is computed as a **differential** (underdog minus favorite, or a transformation thereof). The model predicts `P(lower_seed_wins)` — i.e., upset probability. For same-seed matchups in later rounds, the "underdog" is the team with the lower NRtg/AdjEM.

### 2.1 CRITICAL: Round-Aware Design

This model covers **all 6 rounds** (R1 through Championship), not just R1. Round context is essential because:

- **R1:** Structured seed matchups (1v16, 2v15...). Seed gap is maximally predictive.
- **R2:** Matchups are R1 results — seed gap often smaller (1v8/9, 4v5/12). Team quality dominates.
- **S16/E8:** Surviving teams are strong. Quality gap compresses. Variance/style features matter more.
- **F4/Championship:** Near-elite teams only. Historical seed advantage shrinks dramatically.

The feature set includes explicit round features and round × quality interactions to capture this.

### 2.2 Complete Feature Catalog

#### Category A: Seed Context (5 features)

| # | Name | Formula | Description | Expected Power | Source |
|---|------|---------|-------------|----------------|--------|
| 1 | `seed_diff` | `dog_seed - fav_seed` | Raw seed gap. Always ≥ 0. A 12v5=7, 9v8=1. | **High** (R1), Medium (later) | Kaggle seeds |
| 2 | `log_seed_ratio` | `log(dog_seed / fav_seed)` | Compresses extreme matchups. 16v1=2.77, 9v8=0.12. Captures nonlinearity: 16v1 is much harder than 12v5 even though seed_diff differs by only 4. | **High** | Kaggle seeds |
| 3 | `historical_upset_rate` | Lookup from `HISTORICAL_SEED_WIN_RATES[(fav, dog)]`, returning `1 - rate` | Historical base rate for this exact seed matchup. E.g., 5v12 → 0.351. Encodes 40 years of NCAA tournament structure. For matchups not in the table (unusual later-round pairings), use `0.5 - 0.02 * seed_diff` as fallback. | **High** | Constants / historical data |
| 4 | `is_chalk_matchup` | `1.0 if seed_diff <= 1 else 0.0` | Binary: matchup between adjacent seeds (8v9, 4v5, etc.). These are near coin-flips regardless of quality. | Low | Computed |
| 5 | `dog_seed_bucket` | `1.0 if dog_seed >= 11 else 0.0` | Binary: is the underdog a double-digit seed? These teams have different upset dynamics (conference tournament winners, first NCAA appearance, high variance). | Low | Computed |

#### Category B: Team Quality Differentials (7 features)

| # | Name | Formula | Description | Expected Power | Source |
|---|------|---------|-------------|----------------|--------|
| 6 | `adj_em_diff` | `dog_AdjEM - fav_AdjEM` | Net efficiency margin gap (KenPom proxy via SRS/NRtg). **The single most important quality feature.** Typically negative (underdogs are weaker). When close to 0, the underdog is "better than their seed." | **High** | Sports Ref NRtg / KenPom |
| 7 | `adj_o_diff` | `dog_AdjO - fav_AdjO` | Offensive efficiency gap. Underdogs with elite offense can score in bunches and create variance. | Medium | Sports Ref ORtg / KenPom |
| 8 | `adj_d_diff` | `fav_AdjD - dog_AdjD` | Defensive efficiency gap. **Note sign flip:** lower AdjD = better defense. Computed so positive = underdog has better defense. Underdogs with elite defense compress game pace and reduce possessions, creating low-scoring upsets. | Medium | Sports Ref DRtg / KenPom |
| 9 | `sos_diff` | `dog_SOS - fav_SOS` | Strength of schedule differential. Underdogs from tougher conferences may be underseeded. Positive = underdog played a harder schedule. | Medium | Sports Ref SOS |
| 10 | `win_pct_diff` | `dog_win% - fav_win%` | Win percentage gap. Partially redundant with adj_em_diff but captures "clutch" factor — teams that find ways to win close games. | Low-Medium | Kaggle results |
| 11 | `kenpom_rank_diff` | `fav_rank - dog_rank` | Ordinal rank gap. Positive = underdog is ranked closer to #1 than their seed suggests. A 12-seed ranked #30 vs a 5-seed ranked #28 → diff = -2 (tiny gap). Uses KenPom rank when available, else estimated from AdjEM. | Medium | KenPom / estimated |
| 12 | `srs_diff` | `dog_SRS - fav_SRS` | Simple Rating System differential (MOV + SOS combined). Available from Sports Ref for all years. Serves as a secondary quality metric to adj_em_diff. | Medium | Sports Ref SRS |

#### Category C: Variance & Style Indicators (6 features)

| # | Name | Formula | Description | Expected Power | Source |
|---|------|---------|-------------|----------------|--------|
| 13 | `tempo_diff` | `dog_AdjT - fav_AdjT` | Tempo differential. Large absolute values indicate style clash. Negative = underdog plays slower (often beneficial for underdogs — fewer possessions = fewer chances for the better team to assert dominance). | Medium | KenPom / Sports Ref |
| 14 | `tempo_mismatch_magnitude` | `abs(dog_AdjT - fav_AdjT)` | Absolute tempo difference regardless of direction. Large values = stylistic mismatch = higher variance = more upset potential. A 58-tempo defense-first team vs 74-tempo run-and-gun team → magnitude 16. | Medium | Computed |
| 15 | `dog_three_point_rate` | `dog_3PA / dog_FGA` (three-point attempt rate) | High 3PT attempt rate = high variance. A team that lives and dies by the 3 can beat anyone on a hot shooting night. Increases upset probability. | Medium | Kaggle detailed results / Sports Ref |
| 16 | `three_pct_diff` | `dog_3P% - fav_3P%` | Three-point accuracy gap. When the underdog shoots 3s better, they have a path to winning through shooting variance. | Low-Medium | Kaggle / Sports Ref |
| 17 | `turnover_rate_diff` | `fav_TO% - dog_TO%` | Turnover rate differential. **Sign: positive = favorite turns it over more.** Favorites that are turnover-prone give underdogs extra possessions → more variance → more upset potential. | Low-Medium | Kaggle detailed / Sports Ref |
| 18 | `off_reb_pct_diff` | `dog_ORB% - fav_ORB%` | Offensive rebounding rate gap. Underdogs who crash the boards get second chances, extending possessions and creating variance. | Low | Kaggle detailed / Sports Ref |

#### Category D: Situational & Experience (5 features)

| # | Name | Formula | Description | Expected Power | Source |
|---|------|---------|-------------|----------------|--------|
| 19 | `is_auto_bid` | `1.0 if dog won conference tournament, else 0.0` | Conference tournament champion. These teams are peaking — they won 3-4 games in 3-4 days to earn their bid. Battle-tested and confident. | Low-Medium | Kaggle / manual |
| 20 | `dog_tournament_experience` | `min(dog_sweet16_appearances_last_3yr / 3.0, 1.0)` | Recent deep tournament runs. Teams that have "been there before" handle tournament pressure better. Capped at 1.0. | Low-Medium | Historical records |
| 21 | `experience_diff` | `dog_tournament_experience - fav_tournament_experience` | Relative experience. When a 12-seed has more recent tournament experience than a 5-seed, it signals an undervalued program. Usually negative (favorites have more experience), so positive values are strong upset signals. | Low | Computed |
| 22 | `conference_strength_diff` | `mean_conf_NRtg(dog_conference) - mean_conf_NRtg(fav_conference)` | Conference-level quality gap. A mid-major underdog from a weak conference vs a power conference favorite → large negative value. Controls for schedule quality beyond SOS. | Low | Sports Ref conference ratings |
| 23 | `dog_last_10_win_pct` | `dog wins in last 10 games / 10` | Late-season form. Teams on a hot streak coming into the tournament. If unavailable, default to season win%. | Low | Kaggle / Sports Ref |

#### Category E: Interaction & Round Features (5 features)

| # | Name | Formula | Description | Expected Power | Source |
|---|------|---------|-------------|----------------|--------|
| 24 | `round_num` | `1, 2, 3, 4, 5, 6` | Tournament round. Base upset rate differs by round. R1 ≈ 25%, R2 ≈ 30%, S16 ≈ 33%, E8+ ≈ 35%+. Later rounds have more parity because weak teams are eliminated. | **High** | Game metadata |
| 25 | `seed_x_adj_em` | `seed_diff × adj_em_diff` | **The key interaction.** Captures "better than their seed" — when seed gap is large but quality gap is small (or inverted), the underdog is mis-seeded. Large seed_diff × small adj_em_diff = classic upset setup. Both terms are typically same-signed (positive seed_diff, negative adj_em_diff), so this product is typically negative. More negative = more expected (correctly seeded). Close to zero or positive = upset candidate. | **High** | Computed |
| 26 | `round_x_seed_diff` | `round_num × seed_diff` | **Round-seed interaction.** Seed gap means different things in different rounds. In R1, seed_diff=7 means 5v12 (structured matchup, 35% upset rate). In E8, seed_diff=7 is extremely rare and means something very different. This lets the model learn that seed_diff matters less in later rounds. | **High** | Computed |
| 27 | `round_x_adj_em_diff` | `round_num × adj_em_diff` | **Round-quality interaction.** Quality gap compresses in later rounds because weak teams are eliminated. A 5-point AdjEM gap in R1 is normal; in the F4 it's huge. This interaction lets the coefficient on quality vary by round. | **High** | Computed |
| 28 | `dog_quality_vs_seed` | `dog_AdjEM - expected_AdjEM_for_seed(dog_seed)` | How much better is the underdog than a typical team at their seed? Uses `SEED_DEFAULT_ADJEM` lookup. A 12-seed with AdjEM +14 when the typical 12-seed has +6 → quality_vs_seed = +8. Strong positive signal for upset. | **High** | Computed from constants |

### 2.3 Feature Availability Matrix

| Feature | Kaggle Basic (1985+) | Kaggle Detailed (2003+) | Sports Ref (2002+) | KenPom (current year) |
|---------|---------------------|------------------------|--------------------|-----------------------|
| seed_diff, log_seed_ratio, historical_upset_rate, is_chalk, dog_seed_bucket | ✅ | ✅ | ✅ | ✅ |
| adj_em_diff, adj_o_diff, adj_d_diff, srs_diff | ❌ Compute basic SRS from scores | ❌ Compute from box scores | ✅ NRtg/ORtg/DRtg/SRS | ✅ AdjEM/AdjO/AdjD |
| sos_diff | ❌ Compute from results | ❌ Compute from results | ✅ | ✅ |
| win_pct_diff | ✅ | ✅ | ✅ | ✅ |
| kenpom_rank_diff | ❌ | ❌ | ❌ Estimate from SRS | ✅ |
| tempo_diff, tempo_mismatch | ❌ | ❌ Estimate from possessions | ✅ Pace | ✅ AdjT |
| 3PT rate, 3P%, TO%, ORB% | ❌ | ✅ Box score data | ✅ School stats | ✅ |
| Auto-bid, experience, conference_strength | Partial | Partial | ✅ | ✅ |
| round_num, interactions | ✅ | ✅ | ✅ | ✅ |

**Training data strategy:**
- **Primary training set (2003–2025, ~1,400 games):** Use Sports Reference ratings + Kaggle detailed results. All 28 features available.
- **Extended training set (1985–2002, ~1,100 games):** Seed-based features + computed SRS from Kaggle basic results. ~15 of 28 features available. Use only if the model benefits from the extra data (test this during validation).

### 2.4 Feature Computation Pseudocode

```python
def extract_features(fav: dict, dog: dict, round_num: int) -> dict[str, float]:
    """Extract all 28 candidate features from team stat dicts.
    
    Args:
        fav: Favorite team stats dict. Keys: seed, adj_em, adj_o, adj_d, adj_t,
             sos, srs, wins, losses, conference, kenpom_rank, three_pt_rate,
             three_pct, turnover_rate, off_reb_pct, is_auto_bid,
             tournament_appearances, last_10_wins, conf_avg_nrtg.
        dog: Underdog team stats dict (same keys).
        round_num: Tournament round (1-6).
    
    Returns:
        Dict of feature_name → float value (28 entries).
    """
    seed_diff = dog["seed"] - fav["seed"]
    adj_em_diff = dog["adj_em"] - fav["adj_em"]
    
    features = {
        # Category A: Seed Context
        "seed_diff": seed_diff,
        "log_seed_ratio": math.log(max(dog["seed"], 1) / max(fav["seed"], 1)),
        "historical_upset_rate": lookup_historical_rate(fav["seed"], dog["seed"]),
        "is_chalk_matchup": 1.0 if seed_diff <= 1 else 0.0,
        "dog_seed_bucket": 1.0 if dog["seed"] >= 11 else 0.0,
        
        # Category B: Quality Differentials
        "adj_em_diff": adj_em_diff,
        "adj_o_diff": dog["adj_o"] - fav["adj_o"],
        "adj_d_diff": fav["adj_d"] - dog["adj_d"],  # flipped: positive = dog better D
        "sos_diff": dog["sos"] - fav["sos"],
        "win_pct_diff": (dog["wins"] / max(dog["wins"] + dog["losses"], 1))
                      - (fav["wins"] / max(fav["wins"] + fav["losses"], 1)),
        "kenpom_rank_diff": fav["kenpom_rank"] - dog["kenpom_rank"],  # positive = dog ranked higher
        "srs_diff": dog["srs"] - fav["srs"],
        
        # Category C: Variance & Style
        "tempo_diff": dog["adj_t"] - fav["adj_t"],
        "tempo_mismatch_magnitude": abs(dog["adj_t"] - fav["adj_t"]),
        "dog_three_point_rate": dog.get("three_pt_rate", 0.33),
        "three_pct_diff": dog.get("three_pct", 0.33) - fav.get("three_pct", 0.33),
        "turnover_rate_diff": fav.get("turnover_rate", 0.18) - dog.get("turnover_rate", 0.18),
        "off_reb_pct_diff": dog.get("off_reb_pct", 0.30) - fav.get("off_reb_pct", 0.30),
        
        # Category D: Situational
        "is_auto_bid": 1.0 if dog.get("is_auto_bid", False) else 0.0,
        "dog_tournament_experience": min(dog.get("tournament_appearances", 0) / 3.0, 1.0),
        "experience_diff": (min(dog.get("tournament_appearances", 0) / 3.0, 1.0)
                          - min(fav.get("tournament_appearances", 0) / 3.0, 1.0)),
        "conference_strength_diff": dog.get("conf_avg_nrtg", 0.0) - fav.get("conf_avg_nrtg", 0.0),
        "dog_last_10_win_pct": dog.get("last_10_wins", 7) / 10.0,
        
        # Category E: Round & Interactions
        "round_num": float(round_num),
        "seed_x_adj_em": seed_diff * adj_em_diff,
        "round_x_seed_diff": round_num * seed_diff,
        "round_x_adj_em_diff": round_num * adj_em_diff,
        "dog_quality_vs_seed": dog["adj_em"] - SEED_DEFAULT_ADJEM.get(dog["seed"], 0.0),
    }
    
    return features
```

### 2.5 Expected Feature Importance (Prior Beliefs)

Based on the NCAA tournament prediction literature and the initial scope analysis:

| Tier | Features | Rationale |
|------|----------|-----------|
| **Tier 1 — Almost certainly retained** | `adj_em_diff`, `seed_diff`, `seed_x_adj_em`, `round_num`, `historical_upset_rate` | The core signal. Quality gap, seed gap, their interaction, and round context explain ~80% of variance in tournament outcomes. |
| **Tier 2 — Likely retained** | `log_seed_ratio`, `round_x_seed_diff`, `round_x_adj_em_diff`, `dog_quality_vs_seed`, `sos_diff` | Important nuance. Log ratio captures nonlinearity. Round interactions capture how predictors change across rounds. Quality-vs-seed detects mis-seeded teams. |
| **Tier 3 — Maybe retained** | `adj_o_diff`, `adj_d_diff`, `tempo_mismatch_magnitude`, `win_pct_diff`, `srs_diff` | Secondary quality/style signals. May be too correlated with adj_em_diff to add independent value. Stepwise will decide. |
| **Tier 4 — Probably eliminated** | `is_chalk_matchup`, `dog_seed_bucket`, `three_pct_diff`, `turnover_rate_diff`, `off_reb_pct_diff`, `is_auto_bid`, `experience_diff`, `conference_strength_diff`, `dog_last_10_win_pct`, `dog_tournament_experience`, `dog_three_point_rate`, `tempo_diff`, `kenpom_rank_diff` | Weak or redundant. Many are correlated with Tier 1/2 features. Some lack enough training data to detect small effects. Stepwise will confirm. |

**Expected outcome:** Stepwise selection retains 10–15 features from the 28 candidates. The model should be more parsimonious than 28 features but richer than the original scope's 10.

---

## 3. Stepwise Feature Selection

### 3.1 Overview

Stepwise selection systematically adds and removes features to find the subset that maximizes model fit per parameter. We use **bidirectional stepwise** — a combination of forward selection and backward elimination — with AIC (Akaike Information Criterion) as the objective.

### 3.2 Pre-Screening: Multicollinearity Check

Before stepwise, screen for highly correlated feature pairs to prevent numerical instability.

**Algorithm: Correlation Matrix Pre-Screen**

```python
def compute_correlation_matrix(X: list[list[float]], feature_names: list[str]) -> dict:
    """Compute Pearson correlation between all feature pairs.
    
    Args:
        X: Feature matrix, shape [n_samples][n_features].
        feature_names: Names for each feature column.
    
    Returns:
        Dict with 'matrix' (2D list), 'high_pairs' (pairs with |r| > 0.80).
    """
    # For each pair (i, j):
    #   r = Σ((xi - x̄)(xj - x̄)) / sqrt(Σ(xi - x̄)² × Σ(xj - x̄)²)
    # Using statistics.correlation() from Python 3.10+ stdlib
    
    # Flag pairs with |r| > 0.80 for review
    # Do NOT auto-remove — just flag for the stepwise algorithm to handle
```

**Expected high-correlation pairs:**
- `adj_em_diff` ↔ `srs_diff` (r ≈ 0.95) — SRS is essentially AdjEM with a different name
- `adj_em_diff` ↔ `kenpom_rank_diff` (r ≈ 0.90) — rank tracks AdjEM closely
- `seed_diff` ↔ `log_seed_ratio` (r ≈ 0.95) — nonlinear transform of the same thing
- `seed_diff` ↔ `historical_upset_rate` (r ≈ 0.92) — historical rates are seed-determined
- `tempo_diff` ↔ `tempo_mismatch_magnitude` (r ≈ 0.85) — one is abs() of the other

**Action:** When two features have |r| > 0.80, the stepwise algorithm will naturally keep only one (the one that improves AIC more). No manual removal needed — but we log the pairs so the human can sanity-check which was retained.

### 3.3 VIF (Variance Inflation Factor) Check

After the correlation screen, compute VIF for each feature as a secondary multicollinearity diagnostic.

```python
def compute_vif(X: list[list[float]], feature_idx: int) -> float:
    """Compute VIF for feature at index feature_idx.
    
    VIF_j = 1 / (1 - R²_j)
    where R²_j is the R² from regressing feature j on all other features.
    
    VIF > 10 → severe multicollinearity, consider removing.
    VIF > 5  → moderate, monitor.
    VIF < 5  → acceptable.
    
    Implementation: Use the logistic module's linear regression helper
    (same gradient descent, just with MSE loss instead of log loss)
    to compute R² for each feature regressed on the others.
    
    Args:
        X: Feature matrix [n_samples][n_features].
        feature_idx: Which feature to compute VIF for.
    
    Returns:
        VIF value (float). 1.0 = no collinearity.
    """
    # Extract column feature_idx as y
    # Use remaining columns as X_other
    # Fit linear regression: y ~ X_other
    # R² = 1 - SS_res / SS_tot
    # VIF = 1 / (1 - R²)
```

**Note:** VIF computation requires a basic linear regression (OLS) fit for each feature. Since we're implementing gradient descent in `logistic.py`, we'll add a `linear_regression_r_squared()` helper there that minimizes MSE instead of log-loss. Same gradient descent loop, different loss function, ~30 lines of additional code.

### 3.4 Forward Selection Algorithm

```python
def forward_selection(
    X: list[list[float]],
    y: list[int],
    feature_names: list[str],
    max_features: int = 20,
    criterion: str = "aic"  # "aic" or "bic"
) -> StepwiseResult:
    """Forward stepwise selection using AIC/BIC.
    
    Start with intercept-only model. At each step, try adding each remaining
    feature and keep the one that most improves the information criterion.
    Stop when no addition improves the criterion.
    
    Algorithm:
        1. Fit intercept-only model. Compute AIC₀.
        2. For each candidate feature f not in model:
             a. Fit model with current features + f.
             b. Compute AIC_f.
        3. Let f* = argmin(AIC_f). If AIC_f* < AIC_current - ε:
             a. Add f* to model.
             b. Set AIC_current = AIC_f*.
             c. Go to step 2.
        4. Else: stop. Return current feature set.
    
    AIC = -2 × log_likelihood + 2 × k
    BIC = -2 × log_likelihood + k × log(n)
    
    where k = number of parameters (features + intercept),
          n = number of training examples.
    
    Args:
        X: Full feature matrix [n_samples][n_features].
        y: Binary labels (1=upset, 0=no upset).
        feature_names: Names for each column of X.
        max_features: Hard cap on features to select.
        criterion: "aic" or "bic". BIC penalizes complexity more heavily.
    
    Returns:
        StepwiseResult with selected_features, selected_indices, aic_history,
        final_model_coefficients, p_values.
    """
```

### 3.5 Backward Elimination Algorithm

```python
def backward_elimination(
    X: list[list[float]],
    y: list[int],
    feature_names: list[str],
    criterion: str = "aic"
) -> StepwiseResult:
    """Backward stepwise elimination using AIC/BIC.
    
    Start with all features. At each step, try removing each feature and
    keep the removal that most improves (or least hurts) the criterion.
    Stop when no removal improves the criterion.
    
    Algorithm:
        1. Fit full model with all features. Compute AIC_full.
        2. For each feature f in model:
             a. Fit model WITHOUT f.
             b. Compute AIC_{-f}.
        3. Let f* = argmin(AIC_{-f}). If AIC_{-f*} < AIC_current - ε:
             a. Remove f* from model.
             b. Set AIC_current = AIC_{-f*}.
             c. Go to step 2.
        4. Else: stop. Return current feature set.
    
    Args/Returns: Same structure as forward_selection.
    """
```

### 3.6 Bidirectional Stepwise (the main entry point)

```python
def bidirectional_stepwise(
    X: list[list[float]],
    y: list[int],
    feature_names: list[str],
    criterion: str = "aic",
    max_features: int = 20,
    verbose: bool = True
) -> StepwiseResult:
    """Bidirectional stepwise: forward selection with backward checks.
    
    At each step:
      1. Try adding the best remaining feature (forward step).
      2. After adding, check if any current feature can be removed (backward step).
      3. Repeat until no additions or removals improve the criterion.
    
    This avoids the "greedy trap" of pure forward selection (where an early
    addition blocks a better later combination).
    
    Args:
        X, y, feature_names: Training data.
        criterion: "aic" or "bic".
        max_features: Hard cap.
        verbose: Log each step to logger.
    
    Returns:
        StepwiseResult dataclass:
            selected_features: list[str]     — names of retained features
            selected_indices: list[int]       — column indices in X
            aic_history: list[float]          — AIC at each step
            final_coefficients: list[float]   — model weights for retained features
            p_values: dict[str, float]        — p-value for each retained feature
            vif_scores: dict[str, float]      — VIF for each retained feature
            removed_features: list[str]       — features eliminated (and why)
    """
```

### 3.7 Computing P-Values for Stepwise

P-values require standard errors of logistic regression coefficients, which require the Hessian (second derivative of the log-likelihood). We compute this approximately:

```python
def compute_coefficient_p_values(
    X: list[list[float]],
    y: list[int],
    coefficients: list[float]
) -> list[float]:
    """Compute Wald test p-values for logistic regression coefficients.
    
    Standard error of β_j:
        SE(β_j) = sqrt(diagonal element j of (X^T W X)^{-1})
    where W = diag(p_i × (1 - p_i)) is the weight matrix.
    
    Wald statistic: z_j = β_j / SE(β_j)
    P-value: 2 × (1 - Φ(|z_j|))  where Φ is the standard normal CDF.
    
    Implementation notes:
    - We need to compute (X^T W X)^{-1} — this is a (k×k) matrix inversion.
    - For k ≤ 20 features, this is tractable in pure Python.
    - Use Gauss-Jordan elimination for matrix inversion.
    - Standard normal CDF: use math.erfc() → Φ(z) = 0.5 × erfc(-z / sqrt(2))
    
    Args:
        X: Feature matrix [n_samples][k_features+1] (with intercept column).
        y: Binary labels.
        coefficients: Trained model weights [k+1].
    
    Returns:
        List of p-values, one per coefficient.
    """
```

**Matrix inversion detail:** For a k×k matrix where k ≤ 20, Gauss-Jordan elimination is O(k³) = O(8000) — trivially fast. Implementation:

```python
def invert_matrix(M: list[list[float]]) -> list[list[float]]:
    """Invert a square matrix using Gauss-Jordan elimination.
    
    Augment M with identity: [M | I]
    Row-reduce to: [I | M^{-1}]
    
    Handles singular/near-singular matrices by raising ValueError.
    
    Args:
        M: Square matrix as list of lists. Size n×n where n ≤ 30.
    
    Returns:
        M^{-1} as list of lists.
    
    Raises:
        ValueError: If matrix is singular (determinant ≈ 0).
    """
```

### 3.8 StepwiseResult Data Structure

```python
@dataclass
class StepwiseResult:
    """Result of stepwise feature selection."""
    selected_features: list[str]          # Names of retained features
    selected_indices: list[int]           # Column indices in the original feature matrix
    aic_history: list[float]              # AIC/BIC value at each step
    bic_history: list[float]              # BIC value at each step (computed even if AIC is criterion)
    final_coefficients: list[float]       # Logistic regression weights (incl. intercept at [0])
    p_values: dict[str, float]            # Feature name → Wald test p-value
    vif_scores: dict[str, float]          # Feature name → VIF after selection
    removed_features: list[tuple[str, str]]  # (feature_name, reason) pairs
    correlation_flags: list[tuple[str, str, float]]  # (feat_a, feat_b, r) with |r| > 0.80
    n_steps: int                          # Total forward + backward steps taken
```

### 3.9 Computational Cost

Each step of forward/backward selection fits a full logistic regression model. With:
- ~1,400 training examples
- Up to 28 features
- Up to 28 forward steps × 28 candidate features = 784 model fits
- Each fit: ~500 iterations of gradient descent × 1,400 examples × 28 features = ~20M multiply-adds
- Pure Python: ~10 seconds per model fit → ~8,000 seconds for full forward pass

**This is too slow.** Optimization strategies:

1. **Warm-start:** When adding one feature, initialize weights from the previous model (set the new weight to 0). Convergence in ~50 iterations instead of ~500. **10× speedup.**
2. **Reduce max iterations for screening:** During stepwise, use max_iter=200 and tolerance=1e-4 (less strict). Final model uses max_iter=10000 and tolerance=1e-7. **2× speedup.**
3. **Early stopping in AIC comparison:** If a candidate feature's partial fit (100 iterations) already has worse AIC than the current best candidate, skip remaining iterations. **~2× speedup.**

**Estimated total time with optimizations:** ~5–10 minutes on the VPS. Acceptable for an offline training step.

---

## 4. Logistic Regression (from scratch)

### 4.1 Module: `logistic.py`

This module implements:
- Logistic regression with L2 regularization (Ridge)
- Batch gradient descent with learning rate scheduling
- Feature standardization (z-score)
- Coefficient standard errors (for p-values)
- Prediction (sigmoid of linear combination)

### 4.2 Core Data Structures

```python
@dataclass
class LogisticModel:
    """A trained logistic regression model."""
    coefficients: list[float]     # [intercept, w1, w2, ..., wk]
    feature_names: list[str]      # [name1, name2, ..., namek]
    feature_means: list[float]    # [mean1, mean2, ..., meank] for standardization
    feature_stds: list[float]     # [std1, std2, ..., stdk] for standardization
    regularization: float         # L2 lambda used during training
    n_iterations: int             # Iterations until convergence
    final_log_likelihood: float   # Log-likelihood at convergence
    training_n: int               # Number of training examples
    convergence_history: list[float]  # Log-likelihood at each iteration (sparse: every 100 iters)
    
    def to_json(self) -> str: ...
    
    @classmethod
    def from_json(cls, json_str: str) -> 'LogisticModel': ...
    
    def save(self, path: str) -> None: ...
    
    @classmethod
    def load(cls, path: str) -> 'LogisticModel': ...
```

### 4.3 Feature Standardization

All features are z-score standardized before training. This is critical for gradient descent convergence (features on wildly different scales cause oscillation).

```python
def standardize_features(
    X: list[list[float]]
) -> tuple[list[list[float]], list[float], list[float]]:
    """Z-score standardize each feature column.
    
    For each feature j:
        mean_j = mean(X[:, j])
        std_j  = stdev(X[:, j])     # population stdev, using statistics.pstdev
        if std_j < 1e-10: std_j = 1.0  # constant feature, don't divide by zero
        X_standardized[:, j] = (X[:, j] - mean_j) / std_j
    
    NOTE: Do NOT standardize the intercept column (always 1.0).
    NOTE: At prediction time, apply the SAME means/stds from training.
    
    Args:
        X: Raw feature matrix [n_samples][n_features]. No intercept column.
    
    Returns:
        (X_standardized, means, stds)
    """
```

### 4.4 Training Algorithm

```python
def train_logistic(
    X: list[list[float]],
    y: list[int],
    learning_rate: float = 0.01,
    max_iterations: int = 10000,
    tolerance: float = 1e-7,
    l2_lambda: float = 0.01,
    lr_schedule: str = "constant",  # "constant", "decay", "bold_driver"
    warm_start_weights: list[float] | None = None,
    verbose: bool = False
) -> LogisticModel:
    """Train logistic regression via batch gradient descent with L2 regularization.
    
    Model: P(y=1 | x) = σ(w₀ + w₁x₁ + ... + wₖxₖ)
    Loss:  L = -Σ[yᵢ log(pᵢ) + (1-yᵢ) log(1-pᵢ)] + (λ/2) Σwⱼ²
           (negative log-likelihood + L2 penalty, excluding intercept from penalty)
    
    Gradient: ∂L/∂wⱼ = -Σ(yᵢ - pᵢ)xᵢⱼ + λwⱼ   (for j > 0)
              ∂L/∂w₀ = -Σ(yᵢ - pᵢ)              (intercept: no regularization)
    
    Update:  wⱼ ← wⱼ - α × ∂L/∂wⱼ
    
    Algorithm:
        1. Standardize X. Prepend intercept column (all 1s).
        2. Initialize weights to warm_start_weights or zeros.
        3. For t = 1 to max_iterations:
             a. Compute predictions: pᵢ = σ(w · xᵢ) for all i.
             b. Compute gradients: gⱼ = -Σ(yᵢ - pᵢ)xᵢⱼ/n + λwⱼ.
             c. Update weights: wⱼ -= α × gⱼ.
             d. Compute log-likelihood (every 10 iterations for efficiency).
             e. Check convergence: |ΔLL| < tolerance.
             f. Update learning rate per schedule.
        4. Compute coefficient standard errors (Hessian method, see §3.7).
        5. Return LogisticModel.
    
    Numerical stability:
        - Clip σ(z) to [1e-15, 1-1e-15] to avoid log(0).
        - Clip z to [-500, 500] to avoid exp() overflow.
    
    Args:
        X: Feature matrix [n][k] (raw, not yet standardized).
        y: Labels [n] (0 or 1).
        learning_rate: Initial learning rate α.
        max_iterations: Max gradient descent steps.
        tolerance: Convergence threshold on log-likelihood change.
        l2_lambda: L2 regularization strength. 0.0 = no regularization.
        lr_schedule: Learning rate strategy.
            "constant": α never changes.
            "decay": α_t = α₀ / (1 + 0.01 * t). Slow decay.
            "bold_driver": If loss improved, α *= 1.05. If worsened, α *= 0.5. Adaptive.
        warm_start_weights: Initial weight vector (for stepwise warm-starting).
        verbose: Log progress every 100 iterations.
    
    Returns:
        Trained LogisticModel.
    """
```

### 4.5 Prediction

```python
def predict_logistic(model: LogisticModel, x_raw: list[float]) -> float:
    """Predict P(y=1) for a single example.
    
    Steps:
        1. Standardize x_raw using model.feature_means and model.feature_stds.
        2. Prepend 1.0 (intercept).
        3. Compute z = dot(model.coefficients, x_standardized).
        4. Return σ(z) = 1 / (1 + exp(-z)).
    
    Args:
        model: Trained LogisticModel.
        x_raw: Raw feature vector [k] (same order as model.feature_names).
    
    Returns:
        Probability between 0.0 and 1.0.
    """

def predict_logistic_batch(model: LogisticModel, X_raw: list[list[float]]) -> list[float]:
    """Predict P(y=1) for a batch of examples.
    
    Args:
        model: Trained LogisticModel.
        X_raw: Feature matrix [n][k] (raw, unstandardized).
    
    Returns:
        List of n probabilities.
    """
```

### 4.6 Helper Functions

```python
def sigmoid(z: float) -> float:
    """Numerically stable sigmoid: 1 / (1 + exp(-z)).
    
    For z > 500:  return 1.0 - 1e-15
    For z < -500: return 1e-15
    Otherwise:    return 1.0 / (1.0 + math.exp(-z))
    """

def dot_product(a: list[float], b: list[float]) -> float:
    """Dot product of two vectors. len(a) must equal len(b)."""
    return sum(ai * bi for ai, bi in zip(a, b))

def log_likelihood(
    X: list[list[float]], y: list[int], w: list[float]
) -> float:
    """Compute log-likelihood: Σ[yᵢ log(pᵢ) + (1-yᵢ) log(1-pᵢ)].
    
    X includes intercept column. w includes intercept weight.
    Clip predictions to [1e-15, 1-1e-15] for numerical stability.
    """

def compute_aic(ll: float, k: int) -> float:
    """AIC = -2 × log_likelihood + 2 × k. Lower is better."""
    return -2.0 * ll + 2.0 * k

def compute_bic(ll: float, k: int, n: int) -> float:
    """BIC = -2 × log_likelihood + k × ln(n). Lower is better."""
    return -2.0 * ll + k * math.log(n)
```

### 4.7 Learning Rate Schedule Details

Three options, selectable at training time:

| Schedule | Formula | When to Use |
|----------|---------|-------------|
| `constant` | α_t = α₀ | Default. Simple, reliable. Use for final model training. |
| `decay` | α_t = α₀ / (1 + 0.01 × t) | When constant LR oscillates near convergence. Gentle decay. |
| `bold_driver` | If loss ↓: α *= 1.05. If loss ↑: α *= 0.5, revert step. | Fastest convergence. Use for stepwise (many small model fits). |

**Recommendation:** Use `bold_driver` during stepwise (speed matters), `constant` for final model training (reliability matters).

### 4.8 Convergence Criteria

The model has converged when **all** of:
1. |ΔLL| < tolerance (change in log-likelihood between iterations) for 5 consecutive iterations.
2. max(|gradient_j|) < tolerance × 10 (largest gradient component is small).
3. At least 50 iterations have completed (prevent premature convergence from flat initialization).

**Divergence detection:** If log-likelihood decreases for 10 consecutive iterations (after the first 50), the learning rate is too high. Automatically halve it and reset to last-good weights. Maximum 3 resets before raising `ConvergenceError`.

---

## 5. Random Forest (from scratch)

### 5.1 Module: `random_forest.py`

This module implements:
- CART decision trees (binary splits, Gini impurity)
- Bootstrap aggregation (bagging)
- Random feature subsets at each split
- Out-of-bag error estimation
- Feature importance via mean decrease in impurity
- Memory-efficient tree storage

### 5.2 Core Data Structures

```python
@dataclass
class TreeNode:
    """A node in a CART decision tree.
    
    Internal nodes: feature_index and threshold are set, left/right are children.
    Leaf nodes: prediction is set (probability of class 1), left/right are None.
    """
    feature_index: int | None = None    # Which feature to split on
    threshold: float | None = None      # Split threshold (go left if value <= threshold)
    left: 'TreeNode | None' = None      # Left child (value <= threshold)
    right: 'TreeNode | None' = None     # Right child (value > threshold)
    prediction: float | None = None     # Leaf: P(class 1) = n_class1 / n_total
    n_samples: int = 0                  # Number of training samples at this node
    impurity: float = 0.0              # Gini impurity at this node
    impurity_decrease: float = 0.0     # Weighted impurity decrease from this split

    def to_dict(self) -> dict:
        """Serialize to dict for JSON storage.
        
        Recursive structure:
        {"f": feature_index, "t": threshold, "l": left.to_dict(), "r": right.to_dict(),
         "p": prediction, "n": n_samples, "i": impurity}
        
        Compact keys to minimize JSON size (important for 300 trees).
        """
    
    @classmethod
    def from_dict(cls, d: dict) -> 'TreeNode':
        """Deserialize from dict."""


@dataclass
class DecisionTree:
    """A single CART decision tree."""
    root: TreeNode
    max_depth: int
    min_samples_leaf: int
    n_features_split: int          # Number of features considered at each split
    feature_importances: list[float]  # Per-feature importance (sum of impurity decreases)
    oob_indices: list[int]         # Indices NOT in this tree's bootstrap sample


@dataclass
class RandomForestModel:
    """A trained random forest model."""
    trees: list[DecisionTree]
    feature_names: list[str]
    n_trees: int
    max_depth: int
    min_samples_leaf: int
    n_features_split: int
    feature_importances: list[float]   # Averaged across all trees
    oob_score: float                   # Out-of-bag Brier score
    oob_predictions: list[float]       # OOB predicted probabilities for training set
    training_n: int
    
    def to_json(self) -> str: ...
    @classmethod
    def from_json(cls, json_str: str) -> 'RandomForestModel': ...
    def save(self, path: str) -> None: ...
    @classmethod
    def load(cls, path: str) -> 'RandomForestModel': ...
```

### 5.3 Gini Impurity

```python
def gini_impurity(y: list[int]) -> float:
    """Gini impurity for binary classification.
    
    Gini = 1 - p₀² - p₁²
    where p₁ = count(y=1)/len(y), p₀ = 1 - p₁.
    
    Gini = 0: pure node (all same class).
    Gini = 0.5: maximum impurity (50/50 split).
    
    Args:
        y: Binary labels (list of 0s and 1s).
    
    Returns:
        Gini impurity (0.0 to 0.5).
    """
    if len(y) == 0:
        return 0.0
    p1 = sum(y) / len(y)
    return 1.0 - p1 * p1 - (1.0 - p1) * (1.0 - p1)
```

### 5.4 Tree Building Algorithm (CART)

```python
def build_tree(
    X: list[list[float]],
    y: list[int],
    feature_indices: list[int] | None,  # Which features are available (all, for root)
    max_depth: int,
    min_samples_leaf: int,
    n_features_split: int,
    current_depth: int = 0,
    rng: random.Random = None
) -> TreeNode:
    """Build a CART decision tree recursively.
    
    Algorithm (for each node):
        1. If stopping criterion met → create leaf node.
           Stopping criteria:
             a. current_depth >= max_depth
             b. len(y) < 2 × min_samples_leaf (can't split and satisfy min leaf)
             c. gini_impurity(y) == 0 (pure node)
        
        2. Select random feature subset:
             - Sample n_features_split features from available features (without replacement).
             - This is the "random" in "random forest."
        
        3. Find best split:
             For each feature f in the random subset:
                 Sort examples by feature f value.
                 For each unique split point t (midpoint between consecutive values):
                     Compute weighted Gini after split:
                         Gini_split = (n_left/n) × Gini(y_left) + (n_right/n) × Gini(y_right)
                     where y_left = {y_i : x_i[f] <= t}, y_right = {y_i : x_i[f] > t}
                     
                     Track split with lowest Gini_split.
             
             Optimization: For each feature, iterate through sorted values to compute
             split quality incrementally (O(n) per feature, not O(n²)).
        
        4. If no valid split found (all splits produce one empty child) → create leaf.
        
        5. Split data and recurse:
             left_X, left_y  = examples where x[best_feature] <= best_threshold
             right_X, right_y = examples where x[best_feature] > best_threshold
             
             node.left  = build_tree(left_X, left_y, ..., current_depth + 1)
             node.right = build_tree(right_X, right_y, ..., current_depth + 1)
        
        6. Record impurity decrease for feature importance:
             node.impurity_decrease = n * gini(y) - n_left * gini(y_left) - n_right * gini(y_right)
    
    Args:
        X: Feature matrix [n_samples][n_features].
        y: Binary labels [n_samples].
        feature_indices: Which features can be selected (all n_features indices at start).
        max_depth: Maximum tree depth.
        min_samples_leaf: Minimum examples in any leaf.
        n_features_split: Number of features to consider at each split (sqrt(n_features)).
        current_depth: Current recursion depth.
        rng: Random number generator (seeded for reproducibility).
    
    Returns:
        Root TreeNode of the constructed tree.
    """
```

### 5.5 Split Finding Optimization

The naïve approach evaluates every possible split point — O(n × k) per node where n is samples and k is feature candidates. For 1,400 samples and ~5 features per split, this is manageable. But we optimize:

```python
def find_best_split(
    X: list[list[float]],
    y: list[int],
    candidate_features: list[int],
    min_samples_leaf: int
) -> tuple[int, float, float] | None:
    """Find the best binary split across candidate features.
    
    For each candidate feature:
        1. Compute (value, label) pairs and sort by value.
        2. Scan from left to right, maintaining running counts of class 0 and class 1
           on each side of the split.
        3. At each split point (midpoint between consecutive distinct values):
             - Compute Gini_left and Gini_right from running counts (O(1)).
             - Compute weighted Gini = (n_left × Gini_left + n_right × Gini_right) / n.
        4. Track the global best (feature, threshold, weighted_gini).
    
    Returns:
        (best_feature_index, best_threshold, best_impurity_decrease) or None if no valid split.
    """
```

**Complexity:** O(n × log(n) × m) per node, where m = n_features_split (sorting dominates). With n ≤ 1,400 and m ≈ 4, this is ~60,000 operations per node. A tree with depth 10 has ~2,000 nodes → ~120M operations per tree. In pure Python at ~10M ops/sec, that's ~12 seconds per tree.

### 5.6 Forest Training

```python
def train_random_forest(
    X: list[list[float]],
    y: list[int],
    feature_names: list[str],
    n_trees: int = 300,
    max_depth: int = 10,
    min_samples_leaf: int = 5,
    n_features_split: int | None = None,  # Default: int(sqrt(n_features))
    random_seed: int = 42,
    verbose: bool = True
) -> RandomForestModel:
    """Train a random forest classifier.
    
    Algorithm:
        For t = 1 to n_trees:
            1. Bootstrap sample: draw n examples WITH replacement from (X, y).
               Record which indices were NOT drawn (out-of-bag indices).
            
            2. Build tree on bootstrap sample using build_tree().
               At each split, randomly select n_features_split features.
            
            3. Record OOB indices for this tree.
            
            4. Compute feature importances for this tree (sum of impurity decreases
               per feature across all nodes).
        
        After all trees:
            5. Compute OOB predictions:
               For each training example i:
                   oob_pred_i = mean(tree_t.predict(x_i) for tree_t where i is OOB for tree_t)
               This gives an unbiased estimate of generalization performance.
            
            6. Compute OOB Brier score: mean((oob_pred_i - y_i)² for all i).
            
            7. Average feature importances across all trees.
    
    Args:
        X: Feature matrix [n][k]. NOT standardized (trees don't need it).
        y: Labels [n].
        feature_names: Names for each feature column.
        n_trees: Number of trees in the forest.
        max_depth: Maximum depth per tree.
        min_samples_leaf: Minimum samples in any leaf node.
        n_features_split: Features considered at each split. None = sqrt(n_features).
        random_seed: For reproducibility.
        verbose: Log progress every 50 trees.
    
    Returns:
        Trained RandomForestModel.
    """
```

### 5.7 Forest Prediction

```python
def predict_forest(model: RandomForestModel, x: list[float]) -> float:
    """Predict P(y=1) for a single example.
    
    Average the leaf predictions across all trees:
        P(y=1) = (1/T) × Σ tree_t.predict(x)
    
    where tree_t.predict(x) traverses the tree:
        node = root
        while node is not leaf:
            if x[node.feature_index] <= node.threshold:
                node = node.left
            else:
                node = node.right
        return node.prediction
    
    Args:
        model: Trained RandomForestModel.
        x: Feature vector [k] (raw, no standardization needed).
    
    Returns:
        Probability between 0.0 and 1.0.
    """

def predict_forest_batch(model: RandomForestModel, X: list[list[float]]) -> list[float]:
    """Predict P(y=1) for a batch."""
```

### 5.8 Memory Analysis

**The critical constraint: 3.7 GB RAM VPS.**

Tree memory estimation per tree:
- Each `TreeNode` has: feature_index (int, 28B), threshold (float, 24B), prediction (float, 24B), n_samples (int, 28B), impurity (float, 24B), left/right (pointers, 8B each). Plus Python object overhead (~64B).
- Total per node: ~208 bytes.
- Tree with max_depth=10: up to 2^10 - 1 = 1,023 nodes. Typically ~500-700 nodes (not all branches reach max depth).
- Per tree: ~700 × 208B ≈ 146 KB. Plus bootstrap index storage (~1,400 × 8B = 11 KB).
- Per tree total: ~157 KB.

Forest memory:
- 300 trees × 157 KB = **47 MB.** Well within budget.
- 500 trees × 157 KB = **79 MB.** Still fine.
- OOB tracking: 300 trees × 1,400 indices = 420,000 indices × 8B = **3.4 MB.**
- Feature matrix: 1,400 × 28 × 24B = **941 KB.**
- Total for 300 trees: **~52 MB.** We can easily do 500 trees if needed.

**JSON serialization size:**
- Compact format (short keys): ~300 bytes per node.
- 500 trees × 700 nodes × 300 bytes = **105 MB** JSON on disk. Acceptable.
- Can compress with gzip if needed, but 105 MB disk is fine.

**Training time estimation:**
- ~12 seconds per tree (see §5.5).
- 300 trees × 12 sec = **60 minutes.** Manageable for offline training.
- 500 trees × 12 sec = **100 minutes.** Still acceptable but pushing it.

**Recommendation: 300 trees, max_depth=10, min_samples_leaf=5.**

This gives us:
- ~52 MB RAM (1.4% of 3.7 GB budget)
- ~60 minutes training time
- ~105 MB model file on disk
- sqrt(28) ≈ 5 features per split

### 5.9 Feature Importance

```python
def compute_feature_importance(forest: RandomForestModel) -> list[tuple[str, float]]:
    """Compute mean decrease in impurity (MDI) for each feature.
    
    For each tree, each feature's importance = sum of (weighted impurity decrease)
    across all nodes that split on that feature.
    
    Forest importance = average across all trees, normalized to sum to 1.0.
    
    Returns:
        List of (feature_name, importance) tuples, sorted by importance descending.
    """
```

---

## 6. Model Comparison

### 6.1 Evaluation Metrics

Both models are evaluated on the same held-out validation set using these metrics. All implemented from scratch in `evaluate.py`.

```python
def brier_score(y_true: list[int], y_pred: list[float]) -> float:
    """Brier Score = mean((p_i - y_i)²).
    
    Range: [0, 1]. Lower is better.
    Reference: random guessing (always 0.5) = 0.25 for balanced classes.
    Target: < 0.20.
    """

def log_loss(y_true: list[int], y_pred: list[float], eps: float = 1e-15) -> float:
    """Log Loss = -mean(y_i × log(p_i) + (1-y_i) × log(1-p_i)).
    
    Range: [0, ∞). Lower is better.
    Reference: random = 0.693 (ln(2)).
    Target: < 0.60.
    Clip p_i to [eps, 1-eps] for numerical stability.
    """

def compute_auc(y_true: list[int], y_pred: list[float]) -> float:
    """AUC via the Wilcoxon-Mann-Whitney statistic.
    
    Algorithm:
        1. Separate predictions into positive (y=1) and negative (y=0) groups.
        2. For each (pos, neg) pair:
             count += 1 if pos_pred > neg_pred
             count += 0.5 if pos_pred == neg_pred
        3. AUC = count / (n_pos × n_neg)
    
    Complexity: O(n_pos × n_neg). For ~1,400 examples with ~30% upset rate,
    n_pos ≈ 420, n_neg ≈ 980, so ~411,600 comparisons. Fast.
    
    Range: [0, 1]. 0.5 = random. 1.0 = perfect. Target: > 0.72.
    """

def calibration_table(
    y_true: list[int], 
    y_pred: list[float], 
    n_bins: int = 10
) -> list[dict]:
    """Compute calibration statistics per probability bin.
    
    Bins: [0.0, 0.1), [0.1, 0.2), ..., [0.9, 1.0]
    
    For each bin:
        - n_samples: number of predictions in this bin
        - mean_predicted: average predicted probability
        - mean_actual: actual fraction of positives
        - calibration_error: |mean_predicted - mean_actual|
    
    Also compute ECE (Expected Calibration Error):
        ECE = Σ (n_bin / n_total) × |mean_predicted_bin - mean_actual_bin|
    
    Returns:
        List of dicts with bin statistics, plus ECE as a summary.
    """

def calibration_by_round(
    y_true: list[int],
    y_pred: list[float],
    rounds: list[int],
    n_bins: int = 5  # Fewer bins per round due to smaller samples
) -> dict[int, list[dict]]:
    """Per-round calibration: check calibration within each round separately.
    
    This is CRITICAL for the round-aware model. We need to verify:
    - When the model says "35% upset chance in R2," it actually happens 35% in R2.
    - The model isn't well-calibrated overall but systematically wrong in specific rounds.
    
    Returns:
        Dict mapping round_num → calibration table.
    """
```

### 6.2 Comparison Framework

```python
def compare_models(
    logistic_model: LogisticModel,
    forest_model: RandomForestModel,
    X_val: list[list[float]],
    y_val: list[int],
    rounds_val: list[int],  # Round numbers for each validation example
    feature_names: list[str]
) -> ModelComparison:
    """Compare logistic regression and random forest on validation set.
    
    Evaluates both models on all metrics and recommends the winner.
    
    Decision criteria (ordered by priority):
        1. Calibration (ECE): The model producing probabilities is our primary goal.
           Lower ECE wins. If ECE difference < 0.02, it's a tie on calibration.
        
        2. Brier Score: Combines calibration and discrimination.
           Lower Brier wins. If difference < 0.01, tie.
        
        3. Per-round calibration: Check if either model is systematically wrong
           in a specific round. A model that's great overall but terrible in E8+
           loses to a model that's consistently decent across all rounds.
        
        4. AUC: Discrimination ability. Less important than calibration for our use
           case but still matters. Higher wins.
        
        5. Log Loss: Penalizes confident wrong predictions. Lower wins.
        
        6. Interpretability tiebreaker: If all metrics are within tolerance,
           prefer logistic regression (inspectable coefficients, faster prediction,
           smaller model file).
    
    Returns:
        ModelComparison dataclass with all metrics and recommendation.
    """

@dataclass
class ModelComparison:
    logistic_metrics: dict[str, float]    # metric_name → value
    forest_metrics: dict[str, float]
    logistic_calibration: list[dict]
    forest_calibration: list[dict]
    logistic_round_calibration: dict[int, list[dict]]
    forest_round_calibration: dict[int, list[dict]]
    winner: str                           # "logistic" or "forest"
    reason: str                           # Human-readable explanation
    margin: dict[str, float]              # metric → (logistic - forest), negative = logistic better
```

### 6.3 Ensemble Option

If the two models are close, we can ensemble them:

```python
def ensemble_predict(
    logistic_model: LogisticModel,
    forest_model: RandomForestModel,
    x_raw: list[float],
    weight_logistic: float = 0.5
) -> float:
    """Ensemble prediction: weighted average of both models.
    
    P_ensemble = w × P_logistic + (1-w) × P_forest
    
    Default w=0.5 (equal weight). Tune w on validation set if ensembling.
    
    Only use if ensemble Brier score < both individual models on validation.
    """
```

**When to ensemble:**
- If logistic Brier = 0.195 and forest Brier = 0.198, and ensemble Brier = 0.190 → ensemble wins.
- If one model clearly dominates (Brier gap > 0.02) → use the winner alone. Ensembling a weak model with a strong one usually hurts.

### 6.4 Expected Outcomes

Based on the literature and our dataset size:

| Metric | Logistic (expected) | Forest (expected) | Seed-Only Baseline |
|--------|--------------------|--------------------|-------------------|
| Brier Score | 0.190 – 0.205 | 0.195 – 0.210 | ~0.220 |
| Log Loss | 0.55 – 0.60 | 0.57 – 0.62 | ~0.62 |
| AUC | 0.72 – 0.77 | 0.71 – 0.76 | ~0.70 |
| ECE | 0.02 – 0.04 | 0.03 – 0.06 | ~0.05 |

**Prediction:** Logistic regression is more likely to win because:
1. ~1,400 training examples favor simpler models.
2. Logistic regression is inherently well-calibrated when correctly specified.
3. Random forests tend to produce "lumpy" probability distributions (predictions cluster around leaf values) that require more data to smooth out.
4. Our features are mostly linear differentials — the relationship between AdjEM gap and upset probability is approximately logistic.

**Why include random forest anyway:** It's a sanity check. If the forest dramatically outperforms logistic regression, it means there are nonlinear interactions we're missing — and we should investigate. The forest's feature importance also helps validate the stepwise selection results.

---

## 7. Training Pipeline

### 7.1 Module: `train.py`

The training pipeline is a single script that orchestrates all steps from raw data to deployed model. It is designed to be run **offline** (manually, once per year) and produces JSON model artifacts that are loaded at prediction time.

### 7.2 End-to-End Pipeline

```python
def run_training_pipeline(
    kaggle_dir: str = "upset_model/data/kaggle",
    ratings_dir: str = "upset_model/data/ratings",
    output_dir: str = "upset_model/models",
    scrape_ratings: bool = False,       # Only True on first run
    use_extended_data: bool = False,     # Include 1985-2001 (seed-only features)
    criterion: str = "aic",             # Stepwise criterion
    n_trees: int = 300,                 # Random forest trees
    random_seed: int = 42,
    verbose: bool = True
) -> PipelineResult:
    """Run the complete training pipeline.
    
    Steps:
        1. DATA ACQUISITION
           a. Parse Kaggle CSVs → raw game records.
           b. (If scrape_ratings=True) Scrape Sports Reference ratings for 2002-2025.
           c. Join: game results + team ratings → complete records.
        
        2. DATA CLEANING
           a. Handle missing values (drop games where either team lacks ratings).
           b. Resolve team name mismatches using alias map.
           c. Remove 2020 (COVID, no tournament).
           d. Validate: no duplicate games, all seeds 1-16, all rounds 1-6.
        
        3. FEATURE COMPUTATION
           a. For each game, extract 28 features using features.extract_features().
           b. Compute historical upset rates from training subset only (no leakage).
           c. Compute SEED_DEFAULT_ADJEM from training subset only.
           d. Compute conference strength averages from training subset only.
        
        4. TRAIN / VALIDATION / TEST SPLIT (temporal)
           Split           Years          ~Games    Purpose
           ─────────       ──────         ──────    ─────────
           Training        2003-2019      ~1,050    Fit model weights + stepwise
           Validation      2021-2023      ~189      Hyperparameter tuning, model comparison
           Test            2024-2025      ~126      Final evaluation (NEVER touched during dev)
           
           Note: 2020 excluded (COVID). 2003 start (earliest Kaggle detailed data).
        
        5. STEPWISE FEATURE SELECTION (on training set only)
           a. Compute correlation matrix. Flag pairs with |r| > 0.80.
           b. Run bidirectional_stepwise() with criterion=AIC.
           c. Log selected features, AIC history, p-values, VIF scores.
           d. Output: optimal feature subset (expected: 10-15 features).
        
        6. TRAIN LOGISTIC REGRESSION
           a. Train on training set using only selected features.
           b. Hyperparameters: lr=0.01, l2_lambda=0.01, max_iter=10000.
           c. Save model to models/logistic_model.json.
        
        7. TRAIN RANDOM FOREST
           a. Train on training set using only selected features.
           b. Hyperparameters: n_trees=300, max_depth=10, min_samples_leaf=5.
           c. Compute OOB score.
           d. Save model to models/forest_model.json.
        
        8. MODEL COMPARISON (on validation set)
           a. Predict on validation set with both models.
           b. Compute all metrics: Brier, log loss, AUC, calibration, per-round calibration.
           c. Select winner based on comparison framework (§6.2).
           d. If models are close, also evaluate ensemble.
        
        9. RETRAIN WINNER ON TRAIN + VALIDATION
           a. Combine training + validation sets.
           b. Re-run stepwise selection on combined set (features should be stable).
           c. Retrain winning model on combined set.
           d. This maximizes training data for the final model.
        
        10. FINAL EVALUATION (on test set — ONE TIME ONLY)
            a. Predict on test set with final model.
            b. Report all metrics.
            c. Per-round calibration check.
            d. Sanity check: are results consistent with validation performance?
        
        11. EXPORT
            a. Save final model to models/active_model.json.
            b. Save evaluation report to models/evaluation_report.json.
            c. Log summary to console.
    
    Returns:
        PipelineResult with all models, metrics, and selected features.
    """
```

### 7.3 Data Acquisition Detail

#### 7.3.1 Kaggle CSV Parsing (`data_prep.py`)

```python
def parse_kaggle_results(kaggle_dir: str) -> list[dict]:
    """Parse Kaggle March Mania CSV files into game records.
    
    Reads:
        MNCAATourneyCompactResults.csv — every tournament game 1985-2025
            Columns: Season, DayNum, WTeamID, WScore, LTeamID, LScore, WLoc, NumOT
        
        MNCAATourneySeeds.csv — seed assignments per year
            Columns: Season, Seed, TeamID
            Seed format: "W01", "X16", "Y11a" (letter=region, number=seed, a/b=play-in)
        
        MTeams.csv — team ID → name mapping
            Columns: TeamID, TeamName, FirstD1Season, LastD1Season
        
        MNCAATourneyDetailedResults.csv — box scores 2003+
            Columns: Season, DayNum, WTeamID, WScore, LTeamID, LScore,
                     WFGM, WFGA, WFGM3, WFGA3, WFTM, WFTA, WOR, WDR, WAst, WTO, WStl, WBlk, WPF
                     (same for L prefix)
    
    Processing:
        1. Read CSV files using csv.DictReader.
        2. Parse seed strings: "W01" → region="W", seed=1. "Y11a" → region="Y", seed=11.
        3. For each tournament game:
             - Identify winner/loser by score.
             - Look up seeds for both teams in that season.
             - Determine round from DayNum (Kaggle convention: R1=days 134-135, R2=136-137, etc.)
             - Determine favorite/underdog by seed.
             - Set upset = 1 if lower_seed (higher seed number) won.
        4. For games with detailed results (2003+):
             - Compute per-game stats: FG%, 3PT rate, 3PT%, FT%, TO, ORB.
             - These are game-level, not season-level. We need season averages.
        5. Return list of game records.
    
    Returns:
        List of dicts with keys: year, round, fav_team_id, dog_team_id,
        fav_seed, dog_seed, fav_score, dog_score, upset (0/1), fav_team_name,
        dog_team_name. Plus box score fields when available.
    """

def parse_kaggle_regular_season(kaggle_dir: str) -> dict[tuple[int, int], dict]:
    """Parse regular season results to compute season-level team stats.
    
    Reads MRegularSeasonCompactResults.csv (all years) and
    MRegularSeasonDetailedResults.csv (2003+).
    
    Computes per-team per-season:
        - wins, losses, win_pct
        - points_per_game, points_allowed_per_game
        - SRS (Simple Rating System, computed iteratively — see below)
        - For 2003+: FG%, 3PT rate, 3PT%, FT%, TO rate, ORB rate
    
    SRS Computation (iterative algorithm, ~20 iterations to converge):
        SRS_i = MOV_i + (1/n_games) × Σ SRS_opp_j for all opponents j
        where MOV_i = average margin of victory for team i
        
        Initialize SRS = MOV for all teams.
        Repeat until convergence (max change < 0.001):
            For each team: SRS_new = MOV + mean(SRS_old of opponents)
        
        SOS = SRS - MOV (the schedule component).
    
    Returns:
        Dict mapping (season_year, team_id) → team stats dict.
    """
```

#### 7.3.2 Sports Reference Scraping (`scrape.py`)

```python
def scrape_sports_reference_ratings(
    start_year: int = 2002,
    end_year: int = 2025,
    output_dir: str = "upset_model/data/ratings",
    delay: float = 3.5  # seconds between requests — BE POLITE
) -> dict[int, list[dict]]:
    """Scrape advanced ratings from Sports Reference for each season.
    
    URL pattern: https://www.sports-reference.com/cbb/seasons/men/{YEAR}-ratings.html
    
    Parses the HTML table containing:
        School, Conf, W, L, SRS, SOS, ORtg, DRtg, NRtg (= ORtg - DRtg)
    
    Also scrapes school stats page for detailed stats:
        URL: https://www.sports-reference.com/cbb/seasons/men/{YEAR}-school-stats.html
        Fields: FGA, FGA3, FG%, 3P%, FT%, TRB%, ORB%, TOV%, etc.
    
    Rate limiting:
        - 3.5 second delay between requests (comply with robots.txt).
        - Total: ~48 requests (24 years × 2 pages) = ~3 minutes.
        - If 429/503 received, exponential backoff: wait 30s, 60s, 120s.
    
    Output: One JSON file per year in output_dir.
        {year}_ratings.json: [{school, conf, w, l, srs, sos, ortg, drtg, nrtg}, ...]
        {year}_stats.json: [{school, fga, fga3, fg_pct, three_pct, ft_pct, ...}, ...]
    
    Returns:
        Dict mapping year → list of team stat dicts.
    """
```

#### 7.3.3 Data Joining (`data_prep.py`)

```python
def join_datasets(
    game_records: list[dict],
    season_stats: dict[tuple[int, int], dict],
    ratings: dict[int, list[dict]],
    team_aliases: dict[str, str]
) -> list[dict]:
    """Join tournament game records with team season stats and ratings.
    
    The challenge: team names differ between sources.
    - Kaggle uses TeamID (numeric).
    - Kaggle MTeams.csv maps TeamID → TeamName.
    - Sports Reference uses school names that may differ.
    
    Joining strategy:
        1. For each game record, look up both teams' Kaggle TeamNames.
        2. Attempt exact match with Sports Ref school names.
        3. If no match, try team_aliases (existing TEAM_NAME_ALIASES + new ones).
        4. If still no match, try fuzzy matching:
             - Lowercase both, remove "university", "state" → "st.", etc.
             - If SequenceMatcher ratio > 0.85, accept.
        5. If no match, log warning and exclude game from training set.
    
    For each successfully joined game:
        Populate fav/dog stats from both Kaggle season stats and Sports Ref ratings.
        Priority: Sports Ref ratings (ORtg/DRtg/NRtg/SRS) > Kaggle-computed SRS.
    
    Returns:
        List of complete game records with all stats populated.
        Also returns join_report: {matched: N, unmatched: N, by_alias: N, by_fuzzy: N}.
    """
```

### 7.4 Data Leakage Prevention

**Critical:** Several features require historical aggregates that must be computed from TRAINING DATA ONLY.

| Feature | Leakage Risk | Mitigation |
|---------|-------------|------------|
| `historical_upset_rate` | If computed from all data (including test set years), we're using future information. | Compute from training years only. For validation/test, use the rates computed from training set. |
| `dog_quality_vs_seed` (uses SEED_DEFAULT_ADJEM) | If expected AdjEM per seed is computed from all years, it includes future data. | Compute per-seed average AdjEM from training years only. |
| `conference_strength_diff` | Conference average NRtg should not include future years. | Compute conference averages per-year (same-year data only — no leakage since it's same-season stats). |

```python
def compute_training_aggregates(training_games: list[dict]) -> dict:
    """Compute historical aggregates from training data only.
    
    Returns dict with:
        historical_upset_rates: {(fav_seed, dog_seed): upset_rate}
        seed_expected_adjem: {seed: mean_adjem}
    
    These are used when computing features for validation/test games.
    """
```

### 7.5 Handling Round Information in Training Data

Every tournament game has a round number. The Kaggle data encodes round via `DayNum`:

```python
def day_to_round(day_num: int) -> int:
    """Convert Kaggle DayNum to round number.
    
    Kaggle convention (varies slightly by year):
        Days 134-135: First Four (play-in) → round 0 (exclude from training)
        Days 136-137: Round of 64 → round 1
        Days 138-139: Round of 32 → round 2
        Days 143-144: Sweet 16 → round 3
        Days 145-146: Elite 8 → round 4
        Days 152:     Final Four → round 5
        Days 154:     Championship → round 6
    
    NOTE: Day numbers shifted after the tournament expanded. Use year-specific
    mapping for accuracy, or use the round-of-64 start day as anchor.
    """
```

**Training data per round (2003-2019, ~1,050 games):**

| Round | Games/Year | Total | Upset Rate |
|-------|-----------|-------|------------|
| R1 | 32 | ~512 | ~25% |
| R2 | 16 | ~256 | ~30% |
| S16 | 8 | ~128 | ~33% |
| E8 | 4 | ~64 | ~35% |
| F4 | 2 | ~32 | ~40% |
| Championship | 1 | ~16 | ~44% |

Later rounds have fewer training examples, but the round features and interactions help the model generalize. The model doesn't need per-round sub-models — it has a single model with round as a continuous feature and interaction terms.

### 7.6 PipelineResult Data Structure

```python
@dataclass
class PipelineResult:
    """Complete output of the training pipeline."""
    # Data
    n_games_total: int
    n_games_train: int
    n_games_val: int
    n_games_test: int
    join_report: dict                    # From data joining step
    
    # Feature selection
    stepwise_result: StepwiseResult
    all_features: list[str]              # All 28 candidate names
    selected_features: list[str]         # Surviving features (10-15)
    correlation_matrix: dict             # Full correlation matrix
    
    # Models
    logistic_model: LogisticModel
    forest_model: RandomForestModel
    
    # Comparison
    comparison: ModelComparison
    
    # Final model
    winner: str                          # "logistic", "forest", or "ensemble"
    final_model_path: str                # Path to active_model.json
    
    # Evaluation
    test_metrics: dict[str, float]       # Final test set metrics
    test_calibration: list[dict]         # Final test set calibration
    test_round_calibration: dict[int, list[dict]]  # Per-round calibration on test set
```

---

## 8. Prediction API

### 8.1 Module: `predict.py` — The Public Interface

This is the **only** file the bracket optimizer imports. It must be:
- Self-contained (no imports from the bracket optimizer)
- Fast (no disk I/O at prediction time after initialization)
- Stateless after initialization (thread-safe, no side effects)

```python
"""Public prediction API for the upset model.

Usage:
    from upset_model.predict import UpsetPredictor
    
    predictor = UpsetPredictor("upset_model/models/active_model.json")
    p_upset = predictor.predict(favorite_stats, underdog_stats, round_num=1)
"""

import json
import math
import logging
from pathlib import Path

logger = logging.getLogger("upset_model")


class UpsetPredictor:
    """Predict upset probability for NCAA tournament matchups.
    
    Loads a trained model (logistic regression or random forest) from JSON
    and provides a simple prediction interface.
    
    The predictor is stateless after __init__. All model parameters are
    loaded into memory. Prediction is pure computation (no I/O).
    
    Attributes:
        model_type: "logistic" or "forest" (determined from model file).
        feature_names: List of feature names the model expects.
        n_features: Number of features.
    """
    
    def __init__(self, model_path: str) -> None:
        """Load model from JSON file.
        
        Args:
            model_path: Path to model JSON file (logistic_model.json,
                       forest_model.json, or active_model.json).
        
        Raises:
            FileNotFoundError: If model file doesn't exist.
            ValueError: If model file is malformed.
        """
        # Load JSON
        # Detect model type from "model_type" key
        # For logistic: load coefficients, feature_means, feature_stds, feature_names
        # For forest: load all tree structures, feature_names
        # For ensemble: load both sub-models + ensemble weight
    
    def predict(
        self,
        favorite: dict,
        underdog: dict,
        round_num: int = 1
    ) -> float:
        """Predict P(underdog wins) for a single matchup.
        
        This is the PRIMARY public method. Everything else is internal.
        
        Args:
            favorite: Team stats dict for the higher-seeded team.
                Required keys: "seed" (int), "adj_em" (float).
                Optional keys (used if available, defaults otherwise):
                    "adj_o", "adj_d", "adj_t", "sos", "srs",
                    "wins", "losses", "kenpom_rank",
                    "three_pt_rate", "three_pct", "turnover_rate", "off_reb_pct",
                    "is_auto_bid", "tournament_appearances", "last_10_wins",
                    "conf_avg_nrtg", "conference"
            
            underdog: Team stats dict for the lower-seeded team (same keys).
            
            round_num: Tournament round (1-6).
                1 = Round of 64, 2 = Round of 32, 3 = Sweet 16,
                4 = Elite 8, 5 = Final Four, 6 = Championship.
        
        Returns:
            Float in [0.01, 0.99]: probability that the underdog wins.
            Higher = more likely upset.
        
        Example:
            >>> predictor = UpsetPredictor("models/active_model.json")
            >>> p = predictor.predict(
            ...     favorite={"seed": 5, "adj_em": 14.2, "adj_o": 112.5, "adj_d": 98.3, "adj_t": 68.0, ...},
            ...     underdog={"seed": 12, "adj_em": 12.8, "adj_o": 110.1, "adj_d": 97.3, "adj_t": 64.5, ...},
            ...     round_num=1
            ... )
            >>> print(f"P(12-seed upset) = {p:.3f}")
            P(12-seed upset) = 0.387
        """
        # 1. Extract features using features.extract_features(fav, dog, round_num)
        #    → dict of 28 feature values
        # 2. Select only the features this model was trained on (self.feature_names)
        #    → ordered list of float values
        # 3. Predict:
        #    - If logistic: standardize, dot product, sigmoid
        #    - If forest: traverse each tree, average leaf predictions
        #    - If ensemble: weighted average of both
        # 4. Clamp to [0.01, 0.99]
        # 5. Return
    
    def predict_matchup(
        self,
        team_a: dict,
        team_b: dict,
        round_num: int = 1
    ) -> float:
        """Predict P(team_a wins) for any matchup.
        
        Unlike predict(), this doesn't require knowing which team is the
        favorite. It determines favorite/underdog from seeds, then returns
        the probability from team_a's perspective.
        
        Args:
            team_a: Team stats dict (must include "seed").
            team_b: Team stats dict (must include "seed").
            round_num: Tournament round (1-6).
        
        Returns:
            Float in [0.01, 0.99]: probability that team_a wins.
        """
        # If team_a.seed < team_b.seed: team_a is favorite
        #   p_upset = self.predict(favorite=team_a, underdog=team_b, round_num)
        #   return 1.0 - p_upset
        # If team_b.seed < team_a.seed: team_b is favorite
        #   p_upset = self.predict(favorite=team_b, underdog=team_a, round_num)
        #   return p_upset  (team_a IS the underdog, so p_upset = P(team_a wins))
        # If same seed: use adj_em to determine favorite
    
    def get_model_info(self) -> dict:
        """Return model metadata for logging/debugging.
        
        Returns:
            Dict with model_type, n_features, feature_names, training_n,
            model_path, etc.
        """
    
    def explain(
        self,
        favorite: dict,
        underdog: dict,
        round_num: int = 1
    ) -> dict:
        """Explain a prediction: feature values, contributions, and final probability.
        
        For logistic model: shows each feature × coefficient contribution.
        For forest model: shows feature importance and average node values.
        
        Returns:
            Dict with:
                probability: float
                features: {name: value}
                contributions: {name: coefficient × standardized_value} (logistic only)
                top_factors: [{name, direction, magnitude}] sorted by impact
        """
```

### 8.2 Adapter for Bracket Optimizer's Team Dataclass

The bracket optimizer uses a `Team` dataclass (defined in `models.py`). The predictor expects plain dicts. We need a thin adapter:

```python
def team_to_stats_dict(team: 'Team') -> dict:
    """Convert bracket optimizer's Team dataclass to stats dict for UpsetPredictor.
    
    This function lives in the BRACKET OPTIMIZER code (not in upset_model),
    maintaining the isolation boundary.
    
    Args:
        team: A Team instance from src.models.
    
    Returns:
        Dict with keys matching UpsetPredictor.predict() expected input.
    """
    return {
        "seed": team.seed,
        "adj_em": team.adj_em,
        "adj_o": team.adj_o,
        "adj_d": team.adj_d,
        "adj_t": team.adj_t,
        "sos": team.sos,
        "srs": team.adj_em,        # SRS ≈ AdjEM for KenPom-sourced data
        "wins": team.wins,
        "losses": team.losses,
        "kenpom_rank": team.kenpom_rank,
        "conference": team.conference,
        "is_auto_bid": team.is_auto_bid,
        "tournament_appearances": team.tournament_appearances,
        # Fields below may not be available from current Team dataclass.
        # They'll use defaults in extract_features() if missing.
        # "three_pt_rate": ...,
        # "three_pct": ...,
        # "turnover_rate": ...,
        # "off_reb_pct": ...,
        # "last_10_wins": ...,
        # "conf_avg_nrtg": ...,
    }
```

### 8.3 Model JSON Schema

```json
{
    "model_type": "logistic",
    "version": "1.0",
    "trained_at": "2026-03-20T00:00:00Z",
    "training_years": [2003, 2019],
    "n_training_games": 1050,
    "feature_names": ["adj_em_diff", "seed_diff", "seed_x_adj_em", "round_num", ...],
    "n_features": 12,
    
    "logistic": {
        "coefficients": [-0.85, 0.092, -0.043, 0.0018, 0.12, ...],
        "feature_means": [14.2, 5.3, -72.1, 2.1, ...],
        "feature_stds": [8.7, 3.8, 55.2, 1.6, ...],
        "regularization": 0.01,
        "intercept_index": 0
    },
    
    "evaluation": {
        "validation_brier": 0.197,
        "validation_logloss": 0.572,
        "validation_auc": 0.743,
        "validation_ece": 0.031,
        "test_brier": 0.201,
        "test_logloss": 0.581,
        "test_auc": 0.738,
        "test_ece": 0.035
    },

    "feature_selection": {
        "method": "bidirectional_stepwise",
        "criterion": "aic",
        "n_candidates": 28,
        "n_selected": 12,
        "selected": ["adj_em_diff", "seed_diff", "seed_x_adj_em", ...],
        "removed": [["kenpom_rank_diff", "collinear with adj_em_diff"], ...]
    }
}
```

For a random forest model, replace the `"logistic"` key with:
```json
{
    "forest": {
        "n_trees": 300,
        "max_depth": 10,
        "min_samples_leaf": 5,
        "n_features_split": 4,
        "oob_brier": 0.199,
        "trees": [
            {
                "root": {"f": 0, "t": -3.2, "l": {...}, "r": {...}},
                "oob_indices": [3, 7, 12, ...]
            },
            ...
        ],
        "feature_importances": {"adj_em_diff": 0.28, "seed_diff": 0.22, ...}
    }
}
```

---

## 9. Integration with Bracket Optimizer

### 9.1 What Changes

The upset model replaces the **entire probability pipeline** in `sharp.py`. Currently, `compute_matchup_probability()` chains 6 sequential modifiers:

```
raw AdjEM prob → experience modifier → tempo mismatch → 
conference momentum → UPS modifier → seed prior blending
```

The new model replaces ALL of these with a single call:

```
UpsetPredictor.predict_matchup(team_a, team_b, round_num) → probability
```

### 9.2 Changes to `sharp.py`

**Functions to KEEP (unchanged):**
- `build_matchup_matrix()` — still iterates all pairwise matchups
- `analyze_matchups()` — still orchestrates the pipeline

**Functions to MODIFY:**
- `compute_matchup_probability()` — core change, see below

**Functions to DEPRECATE (but not delete yet):**
- `adj_em_to_win_prob()` — replaced by model
- `compute_upset_propensity_score()` — replaced by model features
- `apply_upset_propensity_modifier()` — replaced by model
- `apply_tournament_experience_modifier()` — captured by `experience_diff` feature
- `apply_tempo_mismatch_modifier()` — captured by `tempo_mismatch_magnitude` feature
- `apply_conference_momentum_modifier()` — captured by `is_auto_bid` feature
- `apply_seed_prior()` — the model IS the seed prior (trained on seed data)

### 9.3 New `compute_matchup_probability()`

```python
# At module level in sharp.py:
_predictor: UpsetPredictor | None = None

def _get_predictor() -> UpsetPredictor:
    """Lazy-load the upset prediction model."""
    global _predictor
    if _predictor is None:
        model_path = os.path.join(
            os.path.dirname(__file__), "..", "upset_model", "models", "active_model.json"
        )
        if os.path.exists(model_path):
            _predictor = UpsetPredictor(model_path)
            logger.info(f"Loaded upset model: {_predictor.get_model_info()}")
        else:
            logger.warning(f"Upset model not found at {model_path}, falling back to legacy pipeline")
    return _predictor


def compute_matchup_probability(team_a: Team, team_b: Team, round_num: int = 1) -> Matchup:
    """Compute win probability using the trained upset model.
    
    Falls back to legacy pipeline if model is not available.
    """
    predictor = _get_predictor()
    
    if predictor is not None:
        # NEW PATH: Use trained model
        stats_a = team_to_stats_dict(team_a)
        stats_b = team_to_stats_dict(team_b)
        
        prob_a_wins = predictor.predict_matchup(stats_a, stats_b, round_num)
        
        return Matchup(
            team_a=team_a.name,
            team_b=team_b.name,
            round_num=round_num,
            win_prob_a=prob_a_wins,
            raw_prob_a=prob_a_wins,  # No separate "raw" — model is the source of truth
            modifiers_applied=["upset_model_v1"]
        )
    else:
        # LEGACY FALLBACK: Original 6-modifier pipeline
        # (existing code, unchanged)
        ...
```

### 9.4 Impact on EMV Calculator

The EMV formula in the bracket optimizer:

```
EMV = P(upset) × points_gained × (1 - public_ownership) 
    - P(no upset) × points_lost × public_ownership
```

**No changes needed.** `P(upset)` is now produced by the trained model instead of the UPS pipeline. The EMV calculator consumes a probability — it doesn't care how it was computed.

**Key improvement:** The model produces **round-aware** probabilities. Previously, later-round matchups used only `adj_em_to_win_prob()` (no UPS, no modifiers for rounds 2+). Now, the model has explicit `round_num`, `round_x_seed_diff`, and `round_x_adj_em_diff` features, producing better-calibrated probabilities for S16, E8, F4, and Championship games.

This directly solves the "zero later-round upsets" problem: the bracket optimizer can now see that a 3-seed vs 2-seed in the Elite Eight has a meaningful upset probability (40-45%), not just the raw AdjEM delta.

### 9.5 Impact on `build_matchup_matrix()`

Currently, `build_matchup_matrix()` calls `compute_matchup_probability()` with `round_num=1` for all matchups (because it doesn't know the round for hypothetical future matchups).

**This needs to change.** The round-aware model means we should compute probabilities per-round:

```python
def build_matchup_matrix(teams: list[Team]) -> dict[str, dict[str, dict[int, float]]]:
    """Build matchup probability matrix with round-specific probabilities.
    
    Returns:
        Nested dict: matrix[team_a_name][team_b_name][round_num] = P(A beats B in round R).
        
        For memory efficiency, only compute rounds 1-4 in the full matrix.
        F4 and Championship (rounds 5-6) are computed on-demand during simulation.
    """
```

**Alternative (simpler):** Keep the existing matrix structure but add a `round_num` parameter:

```python
def get_matchup_probability(team_a: Team, team_b: Team, round_num: int) -> float:
    """Get P(team_a beats team_b) in the given round.
    
    Called during Monte Carlo simulation. Calls UpsetPredictor directly.
    No caching needed — prediction is O(k) for logistic, O(k × T) for forest.
    With k=12 features and T=300 trees, each prediction takes < 1ms.
    """
```

### 9.6 Backward Compatibility Plan

1. **Phase 1 (this implementation):** Add the upset_model module. Modify `compute_matchup_probability()` to use it when the model file exists, fall back to legacy otherwise.

2. **Phase 2 (after validation):** Run both pipelines in parallel on the 2025 tournament. Compare predictions. If the model is better, make it the default.

3. **Phase 3 (cleanup):** Remove legacy modifier functions from `sharp.py`. Update tests.

### 9.7 Changes to Team Dataclass

The existing `Team` dataclass is **almost** sufficient. It already has: `seed`, `adj_em`, `adj_o`, `adj_d`, `adj_t`, `sos`, `wins`, `losses`, `conference`, `tournament_appearances`, `is_auto_bid`, `kenpom_rank`.

**Missing fields that would improve the model (optional, for future):**
- `three_pt_rate`: float — three-point attempt rate
- `three_pct`: float — three-point percentage
- `turnover_rate`: float — turnover rate per possession
- `off_reb_pct`: float — offensive rebound percentage
- `last_10_wins`: int — wins in last 10 games
- `srs`: float — Simple Rating System (currently approximated from adj_em)
- `conf_avg_nrtg`: float — conference average net rating

**These are NOT required.** The `extract_features()` function uses sensible defaults when fields are missing. The model's Tier 1 features (`adj_em_diff`, `seed_diff`, `seed_x_adj_em`, `round_num`) don't need these fields. Adding them later improves the model marginally but isn't blocking.

---

## 10. Timeline and Coding Sessions

Each session is designed for one Coder agent spawn. Sessions are ordered by dependency. Each includes exact function signatures, expected inputs/outputs, and test criteria.

### Session 1: Data Acquisition & Preparation

**Goal:** Raw data → cleaned, joined training dataset.

**Files to create:**
- `upset_model/__init__.py` — empty (or minimal exports)
- `upset_model/data_prep.py` — Kaggle CSV parsing, SRS computation, data joining
- `upset_model/scrape.py` — Sports Reference scraper
- `upset_model/data/README.md` — Data provenance documentation

**Functions to implement:**

```python
# data_prep.py
def parse_kaggle_results(kaggle_dir: str) -> list[dict]
def parse_kaggle_regular_season(kaggle_dir: str) -> dict[tuple[int, int], dict]
def compute_srs(season_games: list[dict], max_iterations: int = 20) -> dict[int, dict]
def join_datasets(games, season_stats, ratings, aliases) -> list[dict]
def build_training_data(kaggle_dir, ratings_dir, output_path) -> list[dict]

# scrape.py
def scrape_ratings_page(year: int) -> list[dict]
def scrape_school_stats_page(year: int) -> list[dict]
def scrape_all_years(start: int, end: int, output_dir: str, delay: float) -> dict
```

**Input:** Kaggle CSVs in `upset_model/data/kaggle/` (manually downloaded), Sports Ref HTML.
**Output:** `upset_model/data/training/games.json` — list of ~1,400 game records with all team stats.

**Test criteria:**
- `games.json` has ≥ 1,000 games (2003-2025 minus 2020).
- Each game has: year, round (1-6), fav_seed, dog_seed, fav/dog adj_em, upset (0/1).
- No NaN or None in required fields.
- Spot-check: 2024 R1 1v16 matchups exist and upset=0 (no 16-seed upsets in 2024).
- Join rate > 90% (at least 90% of tournament teams matched to ratings).

**Estimated time:** 3-4 hours.

**Notes for coder:** 
- Kaggle CSVs must be manually downloaded first (requires Kaggle account). If not available, the coder should create a script that documents the download steps and works with mock data for testing.
- Sports Ref scraping: use `time.sleep(3.5)` between requests. Parse with `BeautifulSoup(html, 'html.parser')`. The ratings table has id `ratings` or is the main table on the page. Inspect the HTML structure before writing the parser.
- The SRS iterative computation converges quickly (MOV + mean opponent SRS). Start all teams at their MOV, iterate 20 times.

---

### Session 2: Feature Engineering & Logistic Regression

**Goal:** Feature extraction + logistic regression from scratch.

**Files to create:**
- `upset_model/features.py` — feature extraction
- `upset_model/logistic.py` — logistic regression implementation
- `upset_model/tests/test_features.py`
- `upset_model/tests/test_logistic.py`

**Functions to implement:**

```python
# features.py
SEED_DEFAULT_ADJEM: dict[int, float]  # copy from constants.py or compute from data
HISTORICAL_UPSET_RATES: dict[tuple[int, int], float]  # computed from training data

def extract_features(fav: dict, dog: dict, round_num: int) -> dict[str, float]
def features_to_vector(features: dict, feature_names: list[str]) -> list[float]
def build_feature_matrix(games: list[dict], feature_names: list[str]) -> tuple[list[list[float]], list[int]]
def compute_training_aggregates(training_games: list[dict]) -> dict
def lookup_historical_rate(fav_seed: int, dog_seed: int) -> float

# logistic.py
def sigmoid(z: float) -> float
def dot_product(a: list[float], b: list[float]) -> float
def log_likelihood(X, y, w) -> float
def compute_aic(ll, k) -> float
def compute_bic(ll, k, n) -> float
def standardize_features(X) -> tuple[list[list[float]], list[float], list[float]]
def train_logistic(X, y, learning_rate, max_iterations, tolerance, l2_lambda, lr_schedule, warm_start_weights, verbose) -> LogisticModel
def predict_logistic(model, x_raw) -> float
def predict_logistic_batch(model, X_raw) -> list[float]
def compute_coefficient_p_values(X, y, coefficients) -> list[float]
def invert_matrix(M) -> list[list[float]]
```

**Test criteria:**
- `test_logistic.py`:
  - Synthetic test: train on XOR-like data, verify convergence.
  - Train on linearly separable 2D data, verify weights have correct sign.
  - Verify sigmoid(0) = 0.5, sigmoid(large) ≈ 1.0, sigmoid(-large) ≈ 0.0.
  - Verify standardize then predict gives same result as manual computation.
  - Verify AIC decreases when adding an informative feature.
  - Verify L2 regularization shrinks coefficients toward zero.
  - Verify matrix inversion: A × A^{-1} ≈ I for a random 5×5 matrix.
  - Verify p-values: informative feature has p < 0.05, noise feature has p > 0.10.

- `test_features.py`:
  - Verify extract_features returns exactly 28 features.
  - Verify seed_diff is always >= 0 for fav.seed < dog.seed.
  - Verify adj_d_diff sign flip: positive when underdog has better defense.
  - Verify round_x_seed_diff = round_num × seed_diff.
  - Verify features with missing optional stats use reasonable defaults.
  - Verify feature_to_vector preserves order.

**Estimated time:** 4-5 hours.

**Notes for coder:**
- The logistic regression is the hardest part. Follow §4.4 exactly. Numerical stability matters — use the sigmoid clipping and log clipping from §4.6.
- The `bold_driver` learning rate schedule is important for stepwise performance in Session 3.
- `invert_matrix()` via Gauss-Jordan: augment [M | I], row-reduce. Watch for zero pivots (swap rows, or raise ValueError for singular matrices).
- For `compute_coefficient_p_values()`: the Hessian of logistic regression log-likelihood is X^T W X where W = diag(p_i × (1 - p_i)). Compute this, invert it, and take sqrt of diagonal elements for standard errors. Use `math.erfc()` for the normal CDF.

---

### Session 3: Random Forest & Stepwise Selection

**Goal:** Random forest from scratch + stepwise feature selection.

**Files to create:**
- `upset_model/random_forest.py` — CART trees + bagging
- `upset_model/selection.py` — stepwise selection
- `upset_model/tests/test_forest.py`

**Functions to implement:**

```python
# random_forest.py
def gini_impurity(y: list[int]) -> float
def find_best_split(X, y, candidate_features, min_samples_leaf) -> tuple | None
def build_tree(X, y, feature_indices, max_depth, min_samples_leaf, n_features_split, current_depth, rng) -> TreeNode
def predict_tree(root: TreeNode, x: list[float]) -> float
def train_random_forest(X, y, feature_names, n_trees, max_depth, min_samples_leaf, n_features_split, random_seed, verbose) -> RandomForestModel
def predict_forest(model, x) -> float
def predict_forest_batch(model, X) -> list[float]
def compute_feature_importance(forest) -> list[tuple[str, float]]

# selection.py
def compute_pearson_correlation(x: list[float], y_vals: list[float]) -> float
def compute_correlation_matrix(X, feature_names) -> dict
def compute_vif(X, feature_idx) -> float
def linear_regression_r_squared(X, y) -> float  # helper for VIF
def forward_selection(X, y, feature_names, max_features, criterion) -> StepwiseResult
def backward_elimination(X, y, feature_names, criterion) -> StepwiseResult
def bidirectional_stepwise(X, y, feature_names, criterion, max_features, verbose) -> StepwiseResult
```

**Test criteria:**
- `test_forest.py`:
  - Verify gini_impurity([0,0,0,0]) = 0.0, gini_impurity([0,0,1,1]) = 0.5.
  - Verify single tree on linearly separable data achieves 100% training accuracy.
  - Verify forest with 10 trees on simple data has lower error than single tree.
  - Verify OOB predictions are computed (no NaN/None for any training example).
  - Verify feature importance sums to ≈ 1.0.
  - Verify predict_forest returns values in [0, 1].
  - Verify tree serialization: to_dict() → from_dict() → same predictions.
  - Memory test: create 300 trees on 1,000 × 28 data, check RSS < 200 MB.

- `test_selection.py` (in test_forest.py or separate):
  - Verify forward selection on data with 1 informative + 4 noise features selects the informative one.
  - Verify backward elimination removes noise features.
  - Verify bidirectional gives same or better AIC than pure forward.
  - Verify correlation matrix: corr(x, x) = 1.0, corr(x, -x) = -1.0.
  - Verify VIF for uncorrelated features ≈ 1.0, for highly correlated pair > 5.

**Estimated time:** 5-6 hours.

**Notes for coder:**
- The random forest tree building is the most computationally intensive part. The `find_best_split()` optimization (incremental Gini computation) is critical for performance. Don't use a naïve O(n²) approach.
- For `find_best_split()`: sort examples by feature value, then scan left-to-right maintaining counts. At each split point, Gini can be computed in O(1) from running counts.
- Bootstrap sampling: `random.choices(range(n), k=n)` gives sampling with replacement.
- OOB indices: the set difference between `range(n)` and the bootstrap sample (use `set(range(n)) - set(bootstrap_indices)`).
- For stepwise: use `train_logistic()` with `lr_schedule="bold_driver"` and reduced `max_iterations=200` for speed. Warm-start when possible.
- The bidirectional stepwise should log each step: "Step 5: Added 'tempo_mismatch_magnitude' (AIC: 1234.5 → 1231.2)".

---

### Session 4: Training Pipeline & Evaluation

**Goal:** End-to-end training pipeline + evaluation metrics + model comparison.

**Files to create:**
- `upset_model/evaluate.py` — all evaluation metrics
- `upset_model/train.py` — training pipeline orchestration
- `upset_model/tests/test_pipeline.py`

**Functions to implement:**

```python
# evaluate.py
def brier_score(y_true, y_pred) -> float
def log_loss_metric(y_true, y_pred, eps) -> float
def compute_auc(y_true, y_pred) -> float
def calibration_table(y_true, y_pred, n_bins) -> list[dict]
def calibration_by_round(y_true, y_pred, rounds, n_bins) -> dict[int, list[dict]]
def expected_calibration_error(y_true, y_pred, n_bins) -> float
def compare_models(logistic_model, forest_model, X_val, y_val, rounds_val, feature_names) -> ModelComparison
def ensemble_predict(logistic_model, forest_model, x_raw, weight_logistic) -> float
def print_evaluation_report(comparison: ModelComparison) -> str

# train.py
def temporal_split(games, train_end, val_end) -> tuple[list, list, list]
def compute_training_aggregates(training_games) -> dict
def run_training_pipeline(kaggle_dir, ratings_dir, output_dir, ...) -> PipelineResult
def save_active_model(model, model_type, evaluation, feature_selection, path) -> None
```

**Test criteria:**
- `test_pipeline.py`:
  - Verify brier_score([1,0], [1.0, 0.0]) = 0.0 (perfect).
  - Verify brier_score([1,0], [0.5, 0.5]) = 0.25 (random).
  - Verify compute_auc with perfectly separated predictions = 1.0.
  - Verify compute_auc with random predictions ≈ 0.5.
  - Verify calibration_table bins are mutually exclusive and exhaustive.
  - Verify temporal_split: training games are all before validation games.
  - Integration test: run pipeline on synthetic data (50 games, 5 features), verify it produces model files.
  - Verify model JSON schema: required keys present, types correct.
  - If real data available: run full pipeline, verify Brier < 0.25 (better than random).

**Estimated time:** 3-4 hours.

**Notes for coder:**
- The `run_training_pipeline()` function should be callable as `python -m upset_model.train` from the command line.
- Add progress logging throughout — the full pipeline takes 60-90 minutes, and the user needs to know it's working.
- The `save_active_model()` function should produce a single JSON file with the schema from §8.3.
- For AUC: the Wilcoxon-Mann-Whitney approach is simpler than the trapezoidal ROC approach. Just count concordant pairs.
- For `calibration_by_round()`: if a round has < 20 examples, use 3 bins instead of 5 to avoid empty bins.

---

### Session 5: Integration with Bracket Optimizer

**Goal:** Wire the model into the bracket optimizer. Backward compatibility.

**Files to modify:**
- `src/sharp.py` — replace modifier pipeline with model call
- `src/models.py` — add optional fields to Team (non-breaking)

**Files to create:**
- `upset_model/predict.py` — public UpsetPredictor class (if not created in Session 2/4)
- `upset_model/__init__.py` — export UpsetPredictor

**Functions to implement/modify:**

```python
# predict.py (if not already complete)
class UpsetPredictor:
    def __init__(self, model_path: str): ...
    def predict(self, favorite: dict, underdog: dict, round_num: int) -> float: ...
    def predict_matchup(self, team_a: dict, team_b: dict, round_num: int) -> float: ...
    def get_model_info(self) -> dict: ...
    def explain(self, favorite: dict, underdog: dict, round_num: int) -> dict: ...

# sharp.py modifications
def team_to_stats_dict(team: Team) -> dict     # NEW
def _get_predictor() -> UpsetPredictor | None   # NEW
def compute_matchup_probability(...)  → Matchup  # MODIFIED (dual path: model or legacy)
```

**Test criteria:**
- All existing tests in `tests/test_sharp.py` still pass (legacy fallback works).
- New test: with model loaded, `compute_matchup_probability()` returns `modifiers_applied=["upset_model_v1"]`.
- New test: predictions are round-aware — P(upset) for a 5v12 matchup is different in R1 vs E8.
- New test: `predict_matchup(team_a, team_b)` = 1.0 - `predict_matchup(team_b, team_a)` (symmetry).
- New test: without model file, falls back to legacy pipeline (no crash).
- Integration test: run full bracket optimizer with model, verify it produces a valid bracket.
- Comparison test: run both pipelines on 2025 teams, log probability differences per matchup.

**Estimated time:** 2-3 hours.

**Notes for coder:**
- The `team_to_stats_dict()` adapter goes in `sharp.py`, NOT in `upset_model/`. The upset model must not import anything from `src/`.
- Lazy-load the predictor with `_get_predictor()` — don't import the model at module level. This ensures existing code works even if the model file doesn't exist.
- The `build_matchup_matrix()` change is OPTIONAL for this session. The simpler approach (call predictor directly during simulation with round_num) works fine and avoids a large matrix restructure. Flag it as a TODO.
- Keep all legacy functions in `sharp.py` but mark them with `# LEGACY — replaced by upset_model` comments. Do NOT delete them yet.

---

### Session Summary

| Session | Files | Functions | Tests | Hours | Dependencies |
|---------|-------|-----------|-------|-------|-------------|
| **1: Data** | 3 new | ~8 | Data validation | 3-4 | None (Kaggle CSVs must be pre-downloaded) |
| **2: Features + Logistic** | 4 new | ~16 | ~15 unit tests | 4-5 | Session 1 (for real data) or standalone with synthetic |
| **3: Forest + Stepwise** | 3 new | ~14 | ~12 unit tests | 5-6 | Session 2 (logistic.py used in stepwise) |
| **4: Pipeline + Eval** | 3 new | ~10 | ~10 tests | 3-4 | Sessions 1-3 |
| **5: Integration** | 2 modified, 1 new | ~6 | ~7 tests | 2-3 | Session 4 |
| **Total** | **16 files** | **~54 functions** | **~54 tests** | **17-22 hours** | |

**Critical path:** Sessions 1→2→3→4→5 are sequential. However, Sessions 2 and 3 can be partially parallelized if Session 2 produces `logistic.py` first (Session 3 imports it for stepwise). Session 1 can be partially skipped by using synthetic training data.

**Minimum viable product (Sessions 2+4+5 only):** If data acquisition is blocked, we can build and test the model architecture with synthetic data, then plug in real data later. The logistic regression, evaluation, and integration work regardless of data source.

---

## Appendix A: Glossary

| Term | Definition |
|------|-----------|
| **AdjEM** | Adjusted Efficiency Margin. Points scored minus points allowed per 100 possessions, adjusted for opponent quality. KenPom's signature metric. |
| **AdjO / AdjD** | Adjusted Offensive/Defensive Efficiency. Points per 100 possessions on offense/defense. |
| **AdjT** | Adjusted Tempo. Possessions per 40 minutes. |
| **AIC** | Akaike Information Criterion. Model selection metric: -2LL + 2k. Lower = better. |
| **AUC** | Area Under the ROC Curve. Measures discrimination ability. 0.5 = random, 1.0 = perfect. |
| **BIC** | Bayesian Information Criterion. Like AIC but penalizes complexity more: -2LL + k×ln(n). |
| **Brier Score** | Mean squared error of probability predictions. 0 = perfect, 0.25 = random (binary). |
| **CART** | Classification And Regression Trees. The tree-building algorithm (Gini splits). |
| **ECE** | Expected Calibration Error. Weighted average of per-bin calibration errors. |
| **EMV** | Expected Marginal Value. The expected point gain from picking an upset. |
| **Gini Impurity** | 1 - Σ(p_k²). Measures node impurity. 0 = pure, 0.5 = maximally impure (binary). |
| **NRtg** | Net Rating. ORtg - DRtg. Sports Reference's efficiency margin (analogous to AdjEM). |
| **OOB** | Out-of-Bag. Training examples not in a tree's bootstrap sample. Used for unbiased error estimation. |
| **SRS** | Simple Rating System. MOV + SOS. Sports Reference's team quality metric. |
| **SOS** | Strength of Schedule. Average opponent SRS. |
| **UPS** | Upset Propensity Score. The hand-tuned scorecard this model replaces. |
| **VIF** | Variance Inflation Factor. 1/(1-R²). Measures multicollinearity. >10 = problematic. |

## Appendix B: Risk Register

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Kaggle data not downloadable (account issues, format changes) | Low | High — blocks Session 1 | Create synthetic training data generator. 200 fake games with realistic distributions. Pipeline works on any data source. |
| Sports Reference blocks scraping (rate limiting, IP ban) | Medium | Medium — lose ratings features | Fall back to computing SRS from Kaggle regular season results. Feature set shrinks but core features (seed, computed SRS) still work. |
| Random forest training too slow (>3 hours) | Medium | Low — just use fewer trees | Reduce to 100 trees. Or skip forest entirely and use logistic only (which is the likely winner anyway). |
| Stepwise selection too slow (>1 hour) | Low | Low — use simpler selection | Skip backward steps. Use pure forward selection (faster, nearly as good). Or pre-filter by correlation and only run stepwise on 15 candidates instead of 28. |
| Model is poorly calibrated in later rounds | Medium | High — defeats the purpose | Use `round_num` as a strong feature. If calibration is still bad, train separate models per round-group: (R1-R2) and (S16+). More data for each. |
| L2 regularization kills important small effects | Low | Medium | Test λ ∈ {0.0, 0.001, 0.01, 0.1}. If key features vanish at λ=0.01, use λ=0.001. |
| Matrix inversion fails (singular Hessian) | Low | Low — only affects p-values | Add small diagonal perturbation (1e-8 × I) before inverting. P-values become approximate but stepwise still works. |
| Model JSON file too large for forest (>100 MB) | Low | Low — disk only, not RAM | Compress with gzip. Or reduce tree depth to 8 (fewer nodes per tree). |
| Team name join rate < 80% | Medium | Medium — reduced training data | Expand TEAM_NAME_ALIASES aggressively. Add fuzzy matching fallback. Log all unmatched names for manual review. |

## Appendix C: Why Both Models?

**"You said logistic will probably win. Why build a random forest too?"**

1. **Validation of feature selection.** Forest feature importance is computed differently from logistic p-values. If both agree on the top features, we have confidence. If they disagree, we investigate.

2. **Nonlinearity detection.** If the forest dramatically outperforms logistic, it means there are nonlinear interactions our feature engineering missed. That's a signal to add more interaction terms and re-run logistic.

3. **Robustness check.** If both models give similar Brier scores (within 0.01), the predictions are robust — not an artifact of model choice. If they diverge, one is overfitting.

4. **Ensemble opportunity.** If both models are decent but with different error patterns (logistic underestimates some upsets, forest underestimates others), averaging them can improve calibration.

5. **Future-proofing.** If we later get more training data (historical KenPom data, more years, additional features), the forest may overtake logistic. Having the infrastructure ready means we can switch without rebuilding.

**The honest answer:** Building both is ~5 hours of extra work (Session 3). The logistic implementation is already built for stepwise selection. The forest is educational and provides a sanity check. It's cheap insurance.