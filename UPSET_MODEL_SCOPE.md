# Upset Prediction Model — Scoping Document

> **Goal:** Replace the hand-tuned Upset Propensity Score (UPS) in `sharp.py` with a logistic regression model trained on historical NCAA tournament data.
>
> **Constraints:** Python 3.10+ stdlib only (no sklearn/pandas/numpy). beautifulsoup4 available for scraping. Must predict thousands of matchups in seconds.

---

## 1. Data Availability

### 1.1 Tournament Game Results (the Y variable)

We need every NCAA tournament game from 1985–2025 with: winning team, losing team, seeds, scores, round, year.

| Source | URL | Format | Years | Games | Notes |
|--------|-----|--------|-------|-------|-------|
| **Kaggle "March Machine Learning Mania"** | `kaggle.com/competitions/march-machine-learning-mania-2025/data` (annual competition, updated each year) | CSV | 1985–2025 | ~2,500+ tournament games | **Best option.** Provides `MNCAATourneyCompactResults.csv` and `MNCAATourneyDetailedResults.csv` with TeamIDs, scores, locations. Also includes `MNCAATourneySeeds.csv` mapping TeamID→Seed per year. Free to download (requires Kaggle account). Files: `MNCAATourneyCompactResults.csv`, `MNCAATourneySeeds.csv`, `MTeams.csv`. |
| **Sports Reference (sports-reference.com/cbb)** | `sports-reference.com/cbb/postseason/men/{YEAR}-ncaa.html` | HTML (scrapable) | 1985–2025 | ~2,500+ | Full bracket results by year. Scrapable with beautifulsoup4. Provides scores but extracting seeds requires cross-referencing. Rate-limited (be polite). |
| **data.world NCAA tournament datasets** | `data.world/datasets/ncaa-tournament` | CSV | varies | varies | Community-uploaded datasets. Quality varies. Some include seeds + scores. |
| **Wikipedia NCAA tournament pages** | `en.wikipedia.org/wiki/{YEAR}_NCAA_Division_I_men%27s_basketball_tournament` | HTML | 1985–2025 | ~2,500+ | Bracket results with seeds. Scrapable but messy parsing. |

**Recommendation:** Use the **Kaggle competition dataset** as the primary source. It's the gold standard — clean CSVs, consistent TeamIDs, updated annually. Download once, store locally. Approximately **2,500–2,600 tournament games** from 1985–2025 (excluding 2020, which was cancelled — COVID). That's ~63 games/year × 40 years ≈ 2,520 games (minus 2020).

### 1.2 Team Quality Metrics (the X variables)

We need season-level team stats that approximate what KenPom provides: adjusted efficiency margin, offensive/defensive efficiency, tempo, strength of schedule.

| Source | URL | Format | Years | Notes |
|--------|-----|--------|-------|-------|
| **Kaggle competition data** | Same as above | CSV | 2003–2025 | `MNCAATourneyDetailedResults.csv` has box score details (FGM, FGA, FTM, etc.) from which we can compute efficiency. Also regular season results for computing SOS. |
| **Sports Reference Advanced Ratings** | `sports-reference.com/cbb/seasons/men/{YEAR}-ratings.html` | HTML table (CSV export available) | 2002–2025 | Provides **SRS** (Simple Rating System = MOV + SOS), **ORtg**, **DRtg**, **NRtg** (Net Rating = ORtg - DRtg). These are publicly available SRS-based efficiency metrics — not KenPom, but correlated (~0.95 with KenPom AdjEM). **This is our best free KenPom proxy.** |
| **Bart Torvik (barttorvik.com)** | `barttorvik.com/trank.php?year={YEAR}` | HTML (JS-rendered, hard to scrape) | 2008–2025 | T-Rank system, very similar to KenPom. Cloudflare-protected, difficult to scrape programmatically. |
| **KenPom (kenpom.com)** | `kenpom.com` | HTML (paywall) | 2002–2025 | The gold standard but **requires subscription ($25/year)**. Cannot legally redistribute. Our current system already scrapes it for the current year. Historical archives exist but are behind the paywall. |
| **Kaggle regular season results** | Same competition | CSV | 1985–2025 | `MRegularSeasonCompactResults.csv` — every regular season game with scores. From this we can compute our own SRS/efficiency metrics going back to 1985. |

**Recommendation: A two-tier approach.**

1. **Primary (2002–2025, ~24 seasons, ~1,500 tournament games):** Scrape Sports Reference advanced ratings tables. These give us ORtg, DRtg, SRS, SOS, and tempo for every D1 team per year. Join with Kaggle tournament results by team+year. This covers the modern analytics era with strong features.

2. **Fallback (1985–2001, ~17 seasons, ~1,000 tournament games):** Use Kaggle regular season results to compute basic SRS (margin of victory + strength of schedule) and win percentage. These won't have ORtg/DRtg but seed-based features still work. We can compute a crude efficiency margin from scoring data.

**Total usable dataset: ~2,500 games. Feature-rich subset: ~1,500 games (2002–2025).**

### 1.3 Data Acquisition Plan

```
Step 1: Download Kaggle March Mania dataset (one-time, manual)
        → MNCAATourneyCompactResults.csv
        → MNCAATourneySeeds.csv  
        → MTeams.csv
        → MRegularSeasonCompactResults.csv
        Store in: data/historical/kaggle/

Step 2: Scrape Sports Reference ratings for 2002–2025 (one-time)
        → URL pattern: sports-reference.com/cbb/seasons/men/{YEAR}-ratings.html
        → Parse HTML table with beautifulsoup4
        → Extract: School, Conf, W, L, SRS, SOS, ORtg, DRtg, NRtg
        → Rate limit: 3-second delay between requests (24 requests total)
        Store in: data/historical/ratings/

Step 3: Join datasets by team name + year
        → Build: data/historical/training_data.json
        → Each row: {year, round, seed_a, seed_b, team_a_stats, team_b_stats, winner}
```

---

## 2. Feature Engineering

### 2.1 Candidate Features

Every feature below is framed from the perspective of `P(lower_seed_wins)` — i.e., upset probability.

| # | Feature | Formula | Rationale | Data Source | Priority |
|---|---------|---------|-----------|-------------|----------|
| 1 | **seed_diff** | `dog_seed - fav_seed` | The single most predictive feature. A 12-5 gap (7) is very different from a 9-8 gap (1). | Kaggle seeds | **Must have** |
| 2 | **log_seed_ratio** | `log(dog_seed / fav_seed)` | Captures nonlinearity: 16v1 is much harder than 9v8 even though seed_diff is similar proportionally. Compresses extreme matchups. | Kaggle seeds | **Must have** |
| 3 | **nrtg_diff** | `underdog_NRtg - favorite_NRtg` | Net rating gap = quality gap. A 12-seed with NRtg of +18 vs a 5-seed with NRtg of +20 is a tiny gap. A 12-seed at +8 vs a 5-seed at +25 is huge. This is our KenPom AdjEM proxy. | Sports Ref ratings | **Must have** |
| 4 | **sos_diff** | `underdog_SOS - favorite_SOS` | Strength of schedule differential. Underdogs from tougher schedules may be underseeded. | Sports Ref ratings | High |
| 5 | **win_pct_diff** | `underdog_win% - favorite_win%` | Raw win percentage gap. Partially redundant with nrtg_diff but captures "battle-tested" teams. | Kaggle results | Medium |
| 6 | **ortg_diff** | `underdog_ORtg - favorite_ORtg` | Offensive efficiency gap. Underdogs with elite offense can score in bunches. | Sports Ref ratings | Medium |
| 7 | **drtg_diff** | `favorite_DRtg - underdog_DRtg` | Defensive efficiency gap (note: lower DRtg = better defense, so reversed). Underdogs with elite defense compress variance. | Sports Ref ratings | Medium |
| 8 | **seed_x_nrtg_interaction** | `seed_diff × nrtg_diff` | Interaction: a large seed gap WITH a small quality gap = classic upset setup. A large seed gap WITH a large quality gap = chalk. This interaction captures "better than their seed." | Computed | High |
| 9 | **underdog_nrtg_vs_seed_expected** | `underdog_NRtg - expected_NRtg_for_seed` | How much better is the underdog than a typical team at their seed? We compute `expected_NRtg_for_seed` as the historical mean NRtg by seed. An 11-seed with NRtg of +20 when the typical 11-seed is +10 screams upset. | Computed from historical averages | High |
| 10 | **favorite_nrtg_vs_seed_expected** | `favorite_NRtg - expected_NRtg_for_seed` | How much better/worse is the favorite relative to their seed? A weak 2-seed (low NRtg for a 2) is vulnerable. | Computed | Medium |
| 11 | **round_num** | `1, 2, 3, 4, 5, 6` | Upset rates vary by round. R1 has more data and different dynamics than E8. | Kaggle results | Medium |
| 12 | **is_5v12** | Binary indicator | The 5v12 matchup historically has a specific upset dynamic (12-seeds win ~35% historically, higher than 6v11 seed_diff would suggest). | Computed | Low |
| 13 | **conference_strength_diff** | `mean conference NRtg` differential | Mid-major conference underdogs may be undervalued by seeds. | Sports Ref | Low |

### 2.2 Feature Selection Rationale

**Start with a minimal model (4 features), validate, then expand:**

- **Tier 1 (baseline model, 3-4 features):** `seed_diff`, `nrtg_diff`, `seed_x_nrtg_interaction`
- **Tier 2 (expanded model, 6-8 features):** Add `sos_diff`, `ortg_diff`, `drtg_diff`, `underdog_nrtg_vs_seed_expected`
- **Tier 3 (full model, 10+ features):** Add `round_num`, `win_pct_diff`, conference features

**Why this matters:** With ~1,500 feature-rich games (2002–2025), we can safely fit 8-10 features without overfitting. Rule of thumb: need ~10-20 observations per parameter for logistic regression. At 1,500 games and 10 features (+ intercept = 11 parameters), we have ~136 observations per parameter. Comfortable.

### 2.3 Handling Year-to-Year Variation

Team quality changes every year — that's the whole point. Our features handle this correctly because:

- We use **same-season ratings** for each game. A 2019 matchup uses 2019 NRtg values.
- Features are **relative** (differentials), not absolute. We don't care that a 2015 team had NRtg +20 and a 2024 team had NRtg +22 — we care about the gap between the two teams in their game.
- Seed-based features are inherently normalized — a 5-seed in 2005 and a 5-seed in 2024 have the same seed.

**No special handling needed.** This is one of logistic regression's strengths.

### 2.4 Interaction Terms

**Yes, include `seed_diff × nrtg_diff`.** This is the single most important interaction:

- **seed_diff = 7, nrtg_diff = -2:** "The 12-seed is almost as good as the 5-seed." → High upset probability.
- **seed_diff = 7, nrtg_diff = -20:** "The 12-seed is way worse than the 5-seed." → Low upset probability (correctly seeded).
- Without the interaction, the model treats seed_diff and nrtg_diff as additive, missing this crucial dynamic.

Other interaction terms (e.g., `ortg_diff × drtg_diff`) are likely noise with our sample size. Keep it simple.

---

## 3. Model Design

### 3.1 Feasibility: Logistic Regression from Scratch

**Absolutely feasible.** Logistic regression is one of the simplest ML models:

```
P(upset) = σ(w₀ + w₁x₁ + w₂x₂ + ... + wₙxₙ)
σ(z) = 1 / (1 + exp(-z))
```

All we need:
- `math.exp()` for the sigmoid
- `math.log()` for the log-likelihood (optional, for monitoring convergence)
- Lists of floats for the feature matrix and weight vector
- A training loop (gradient descent)

**No numpy, no sklearn, no external dependencies.** This is ~100-150 lines of Python.

### 3.2 Implementation: Gradient Descent

**Use batch gradient descent** (not stochastic, not Newton's method):

- **Why not Newton's method?** Requires computing and inverting a Hessian matrix. Matrix inversion in pure Python is doable but painful — O(n³) with nested loops, error-prone, and slow for debugging. Not worth the complexity for 10 features.
- **Why not SGD?** Our dataset is small (~1,500-2,500 rows). Batch gradient is fine — processes the entire dataset each iteration. No mini-batch infrastructure needed.
- **Why batch gradient descent?** Simple, reliable, easy to implement. With 1,500 rows and 10 features, each iteration is O(1,500 × 10) = 15,000 multiply-adds. Even in pure Python, 1,000 iterations takes < 1 second.

**Algorithm:**

```
Initialize weights w = [0, 0, ..., 0]  (n+1 values including intercept)
For each iteration t = 1 to T:
    For each training example i:
        z_i = w·x_i  (dot product)
        p_i = sigmoid(z_i)
        error_i = y_i - p_i
    For each weight j:
        gradient_j = sum(error_i * x_ij for all i) / N
        w_j += learning_rate * gradient_j  (note: gradient ASCENT on log-likelihood)
    Optionally check convergence (change in log-likelihood < epsilon)
```

**Hyperparameters:**
- Learning rate: `0.01` (safe default; can tune via grid search)
- Max iterations: `10,000` (will converge well before)
- Convergence threshold: `1e-6` (change in log-likelihood)
- L2 regularization: `λ = 0.01` (add `-λ * w_j` to gradient to prevent overfitting)

### 3.3 Number of Parameters

| Model Tier | Features | Parameters (incl. intercept) | Observations per Parameter |
|-----------|----------|------------------------------|---------------------------|
| Tier 1 (baseline) | 3 | 4 | 375–625 |
| Tier 2 (expanded) | 7 | 8 | 188–313 |
| Tier 3 (full) | 10 | 11 | 136–227 |

All tiers are safe. Even Tier 3 has >100 observations per parameter, well above the rule-of-thumb minimum of 10-20.

### 3.4 One Model vs. Per-Round Models

**Use one model for all rounds**, with `round_num` as a feature (or round indicators).

Reasons:
- **Sample size:** Round 1 has ~1,280 games (32/year × 40 years). Sweet 16 has ~640. Elite 8 has ~320. Final Four has ~160. Per-round models for late rounds would be severely underpowered.
- **The mechanics of upset prediction don't fundamentally change by round.** A 5-point NRtg gap is a 5-point NRtg gap whether it's R1 or the Elite 8.
- **Round can be a feature** if there's a round-specific effect (there probably is — upsets are slightly more common in R1 due to the "new matchup" factor).

### 3.5 Dependent Variable

**Use `P(lower seed wins)` — i.e., `y = 1` if the lower-seeded team (higher seed number) wins, `y = 0` if the higher seed wins.**

Why:
- This is what we're actually trying to predict — upset probability.
- Features naturally align: `seed_diff` is always positive (dog_seed - fav_seed > 0), `nrtg_diff` is typically negative (underdogs are usually weaker).
- The intercept captures the base rate of upsets across all seed matchups.
- For same-seed matchups (8v9, rare same-seed later-round games), we can define the "underdog" as the team with the lower NRtg, or simply model `P(team_A wins)` using signed differentials.

**Edge case — 8v9 matchups:** Seed_diff = 1. Historically ~48% "upset" rate (9 over 8). The model should naturally handle this since NRtg_diff will dominate when seeds are close.

---

## 4. Training & Validation

### 4.1 Train/Test Split

**Use temporal splitting (the only valid approach for time-series sports data):**

| Split | Years | ~Games | Purpose |
|-------|-------|--------|---------|
| **Training** | 2002–2019 | ~1,080 | Fit model weights. Excludes 2020 (cancelled). |
| **Validation** | 2021–2023 | ~189 | Tune hyperparameters (learning rate, regularization). |
| **Test** | 2024–2025 | ~126 | Final evaluation. Never touch during development. |

**Why temporal, not random?** Random splitting leaks future information. A model trained on 2024 data and tested on 2015 data has seen the future. Temporal splits respect the causal structure of time.

**Why start at 2002?** That's when Sports Reference advanced ratings begin. For the 1985–2001 games with seed-only features, we can train a separate "seed-only" baseline model to compare against.

**Alternative: Walk-forward validation.** Train on 2002–Y, predict Y+1. Repeat for Y = 2014..2024. This gives us 10 out-of-sample tournament predictions — more robust than a single test set, but more complex to implement. Worth doing in a second iteration.

### 4.2 Evaluation Metrics

| Metric | What It Measures | Target | How to Compute |
|--------|-----------------|--------|----------------|
| **Brier Score** | Mean squared error of predicted probabilities: `mean((p_i - y_i)²)` | < 0.20 (random = 0.25 for balanced classes) | Stdlib: `sum((p-y)**2) / n` |
| **Log Loss** | Information-theoretic calibration: `-mean(y·log(p) + (1-y)·log(1-p))` | < 0.60 (lower = better; random ≈ 0.693) | Stdlib: `math.log()` |
| **Calibration** | Does "predicted 30%" mean "actually 30%"? | Calibration curve should hug the diagonal | Bin predictions into deciles, compare mean predicted vs. actual upset rate per bin |
| **AUC** | Discrimination — can the model rank upsets higher than non-upsets? | > 0.70 (0.50 = random) | Implement from scratch: sort by predicted probability, compute rank-sum statistic |
| **Accuracy** | At threshold 0.5, how often is the model right? | > 65% (seed baseline ≈ 70%) | Less important than calibration for our use case |

**The most important metric is calibration.** We don't need the model to classify upsets — we need it to produce accurate probabilities that feed into the EMV calculator. A model that says "35% upset chance" should be right about 35% of the time.

### 4.3 Calibration Check

```
Bin predictions:  [0.0-0.1), [0.1-0.2), ..., [0.9-1.0]
For each bin:
    actual_rate = count(upsets in bin) / count(games in bin)
    predicted_mean = mean(predicted probabilities in bin)
    → These should be approximately equal
```

With ~1,500 games, bins of size 0.1 give us ~150 games per bin on average (though distribution will be skewed — most games have low upset probability). We may need wider bins (quintiles instead of deciles) for the tails.

**Reliability diagram:** Plot predicted vs. actual. Points on the y=x diagonal = perfectly calibrated.

### 4.4 Overfitting Risk

**Low, with appropriate regularization.**

- 1,500 games ÷ 11 parameters = 136 observations per parameter. This is generous for logistic regression.
- L2 regularization (`λ = 0.01`) penalizes large weights, preventing the model from fitting noise.
- Temporal split ensures no data leakage.
- Logistic regression is inherently low-variance (linear decision boundary). Overfitting is much more of a concern with trees/neural nets.

**Signs of overfitting to watch for:**
- Training log-loss << validation log-loss (gap > 0.05)
- Model assigns extreme probabilities (>95% or <5%) to many games
- Coefficients are very large in magnitude (>10) without regularization

---

## 5. Integration

### 5.1 Replacing the UPS Scorecard

The current pipeline in `compute_matchup_probability()` is:

```
raw AdjEM prob → experience modifier → tempo mismatch → 
conference momentum → UPS modifier → seed prior blending
```

The trained logistic regression model replaces **the entire chain** — not just UPS. Here's why:

- The current `adj_em_to_win_prob()` uses a hand-tuned κ = 13.0 logistic function. The trained model learns this parameter from data.
- The experience, tempo, and momentum modifiers are ad-hoc. If these effects are real, the model will learn them through correlated features (e.g., defensive efficiency captures the "slow defensive team" effect).
- The seed prior blending is a Bayesian hack to compensate for a weak model. A well-calibrated logistic model doesn't need it.

**New pipeline:**

```python
def predict_upset_probability(fav: Team, dog: Team, round_num: int) -> float:
    """Predict P(underdog wins) using trained logistic model."""
    features = extract_features(fav, dog, round_num)
    z = dot_product(MODEL_COEFFICIENTS, features)  # includes intercept
    return 1.0 / (1.0 + math.exp(-z))

def compute_matchup_probability(team_a: Team, team_b: Team, round_num: int) -> Matchup:
    """Simplified matchup probability using logistic model."""
    if team_a.seed < team_b.seed:
        p_upset = predict_upset_probability(fav=team_a, dog=team_b, round_num=round_num)
        prob_a_wins = 1.0 - p_upset
    elif team_b.seed < team_a.seed:
        p_upset = predict_upset_probability(fav=team_b, dog=team_a, round_num=round_num)
        prob_a_wins = p_upset  # team_a IS the underdog
    else:
        # Same seed — use NRtg differential directly
        prob_a_wins = seed_neutral_probability(team_a, team_b)
    
    return Matchup(team_a=team_a.name, team_b=team_b.name, round_num=round_num,
                   win_prob_a=prob_a_wins, raw_prob_a=prob_a_wins, modifiers_applied=["logistic_model"])
```

This is **dramatically simpler** than the current 6-modifier pipeline.

### 5.2 Model Coefficient Storage

**Store coefficients as constants in `constants.py`** — retrain manually once per year (or less).

```python
# Trained logistic regression coefficients (2002-2025 data)
# Last updated: 2026-03-XX
# Features: [intercept, seed_diff, nrtg_diff, seed_x_nrtg, sos_diff, ortg_diff, drtg_diff, underdog_quality]
UPSET_MODEL_COEFFICIENTS = [
    -1.234,   # intercept
     0.089,   # seed_diff (positive = higher seed diff → more upset-prone, but this is counterintuitive — expect negative)
    # ... etc, values TBD from training
]

UPSET_MODEL_FEATURE_MEANS = [...]  # For standardization
UPSET_MODEL_FEATURE_STDS = [...]   # For standardization
```

**Why not retrain each year?**
- The model is trained on 20+ years of data. One new year adds ~63 games (~4% of training set). The coefficients won't change meaningfully.
- Retraining requires downloading updated Kaggle data + scraping Sports Reference. That's a manual process anyway.
- Storing constants means **zero runtime dependencies** — no training data needed, no scraping at prediction time.

**When to retrain:** Once per year after the tournament ends (April), when new results are available. Or never, if the model performs well.

### 5.3 Integration with EMV Calculator

The EMV calculator uses `win_prob_a` from the `Matchup` object. No changes needed downstream — the model outputs a probability, which flows into the same EMV formula:

```
EMV = P(upset) × points_gained × (1 - public_ownership) - P(no_upset) × points_lost × public_ownership
```

The only change is that `P(upset)` is now computed by the logistic model instead of the UPS + modifier pipeline.

**Bonus:** The logistic model produces better-calibrated probabilities, so the EMV calculator makes better decisions. A well-calibrated model is the single highest-leverage improvement to the entire bracket optimizer.

---

## 6. What's Realistic

### 6.1 Best Achievable Model

Given our constraints (no sklearn, limited data, simple logistic regression), here's what's realistic:

**Expected performance (Tier 2 model, ~7 features):**
- **Brier Score:** 0.19–0.21 (vs. seed-only baseline ~0.22, random = 0.25)
- **Log Loss:** 0.55–0.60 (vs. seed-only ~0.62, random = 0.693)
- **AUC:** 0.72–0.76 (vs. seed-only ~0.70, random = 0.50)
- **Calibration:** Good for predictions in the 15%–50% range (where most upset-relevant games fall). Weak at extremes (<10%, >90%) due to sparse data.

**For context:** The academic literature on NCAA tournament prediction using logistic regression with KenPom-style features reports AUC of 0.74–0.78 and Brier scores of 0.18–0.21. Our free-data version should be within ~2% of that.

### 6.2 Is Logistic Regression the Right Choice?

**Yes, definitively.** Here's why:

1. **Sample size favors simple models.** With ~1,500 feature-rich games, logistic regression is likely optimal. More complex models (random forests, gradient boosting) would overfit or provide marginal improvement.

2. **Calibration is our goal, not classification.** Logistic regression is inherently well-calibrated when the model is correctly specified. Tree-based models often need post-hoc calibration (Platt scaling, isotonic regression) — which is itself logistic regression.

3. **Interpretability matters.** We can inspect coefficients: "a 1-point NRtg advantage for the underdog increases upset probability by X%." This helps debug and build trust.

4. **Speed.** Prediction is a single dot product + sigmoid — O(n_features). Thousands of predictions per millisecond, even in pure Python.

5. **Implementation simplicity.** No hyperparameter tuning nightmare. No tree-building. No ensemble logic. Just gradient descent on a convex loss function — guaranteed to converge to the global optimum.

**What we'd lose by NOT using logistic regression:**
- More complex models might capture nonlinear interactions we miss. But our explicit interaction term (`seed_diff × nrtg_diff`) handles the most important one.
- Diminishing returns: the difference between a 0.20 Brier score and a 0.19 Brier score is negligible in practice.

### 6.3 Expected Improvement Over Hand-Tuned Scorecard

The current UPS system has several weaknesses the trained model fixes:

| Issue | Current UPS | Trained Model |
|-------|-------------|---------------|
| **Weights are made up** | `tempo_mismatch: 0.20`, etc. — no empirical basis | Weights learned from 1,500+ games |
| **Binary features** | `tempo_mismatch` is 0, 0.5, or 1.0 — crude | Continuous features capture nuance |
| **Missing data** | `free_throw_edge` is hardcoded to 0.5 | No placeholder features — only real data |
| **Not calibrated** | UPS output is arbitrary 0-1 scale, doesn't map to actual probability | Output IS a probability (by construction) |
| **Stacking modifiers** | 6 sequential additive adjustments can compound errors | Single model, single prediction |
| **No validation** | No way to know if it's working | Brier score, calibration curves, temporal validation |

**Conservative estimate:** The trained model improves Brier score by 0.02–0.04 over the current system (a 10-15% reduction in prediction error). This translates to:
- Better identification of "live" upset candidates (fewer false positives)
- More accurate EMV calculations → better bracket differentiation
- Estimated improvement in P(1st place) of 1-3 percentage points in a 25-person pool

### 6.4 Timeline Estimate

| Session | Work | Hours |
|---------|------|-------|
| **Session 1** | Data acquisition: Download Kaggle CSVs, write scraper for Sports Reference ratings tables, build joined dataset. | 3-4 |
| **Session 2** | Feature engineering: Extract features from joined data, compute interaction terms, standardize. Write `training_data.json`. | 2-3 |
| **Session 3** | Model implementation: Write logistic regression from scratch (gradient descent, prediction, evaluation metrics). Train Tier 1 baseline model. | 3-4 |
| **Session 4** | Validation & tuning: Walk-forward validation, calibration analysis, hyperparameter tuning, expand to Tier 2 features. | 2-3 |
| **Session 5** | Integration: Replace UPS pipeline in `sharp.py`, store coefficients in `constants.py`, update `compute_matchup_probability()`, run existing tests. | 2-3 |
| **Total** | | **12-17 hours across 5 sessions** |

**Critical path:** Session 1 (data acquisition) is the bottleneck. If Kaggle data downloads cleanly and Sports Reference scraping works, the rest is straightforward. If scraping breaks (rate limiting, HTML changes), we may need an extra session.

---

## Appendix A: Data Schema

### Training Example (one per tournament game)

```json
{
    "year": 2024,
    "round": 1,
    "fav_seed": 5,
    "dog_seed": 12,
    "fav_nrtg": 22.5,
    "dog_nrtg": 18.1,
    "fav_ortg": 118.2,
    "dog_ortg": 112.5,
    "fav_drtg": 95.7,
    "dog_drtg": 94.4,
    "fav_sos": 8.5,
    "dog_sos": 2.1,
    "fav_win_pct": 0.786,
    "dog_win_pct": 0.750,
    "upset": 1
}
```

### Derived Features (computed at training time)

```json
{
    "seed_diff": 7,
    "log_seed_ratio": 0.875,
    "nrtg_diff": -4.4,
    "sos_diff": -6.4,
    "ortg_diff": -5.7,
    "drtg_diff": 1.3,
    "seed_x_nrtg": -30.8,
    "underdog_quality": 8.1,
    "round_num": 1
}
```

## Appendix B: Key URLs

| Resource | URL |
|----------|-----|
| Kaggle March Mania 2025 (or latest) | `https://www.kaggle.com/competitions/march-machine-learning-mania-2025` |
| Kaggle March Mania datasets page | `https://www.kaggle.com/competitions/march-machine-learning-mania-2025/data` |
| Sports Ref ratings (template) | `https://www.sports-reference.com/cbb/seasons/men/{YEAR}-ratings.html` |
| Sports Ref tournament results (template) | `https://www.sports-reference.com/cbb/postseason/men/{YEAR}-ncaa.html` |
| Sports Ref school stats (template) | `https://www.sports-reference.com/cbb/seasons/men/{YEAR}-school-stats.html` |
| Bart Torvik T-Rank | `https://barttorvik.com/trank.php?year={YEAR}` |
| KenPom (current year, paywall) | `https://kenpom.com` |
| GitHub: March-Madness-ML (reference impl) | `https://github.com/adeshpande3/March-Madness-ML` |

## Appendix C: Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Sports Reference blocks scraping | Can't get historical ratings | Fall back to computing SRS from Kaggle regular season results. More work but achievable. |
| Kaggle competition format changes | CSV column names differ | Pin to a specific year's dataset. The 2024 competition data covers 1985-2024. |
| Team name mismatches between sources | Join failures, lost data | Build a comprehensive alias map (we already have `TEAM_NAME_ALIASES` in constants.py). |
| Model is poorly calibrated at extremes | Bad predictions for 1v16, 2v15 | Use seed_diff bins: if predicted probability is outside historical range for that seed matchup, clamp to range. |
| L2 regularization hurts small effects | Tempo/defense features get shrunk to zero | Test with and without regularization. If key features are zeroed out, reduce λ. |
| 2020 COVID gap | Missing 1 year of data | Trivial — 63 missing games out of 2,500. Just skip year 2020. |
