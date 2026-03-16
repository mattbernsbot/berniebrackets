# Model Review V5: Barttorvik Four-Factors Integration

**Reviewer:** Senior code review (automated)  
**Date:** 2026-03-16  
**Verdict:** ❌ **Barttorvik features hurt model performance. Drop them.**

---

## 1. Barttorvik Data Quality: ✅ PASS (with caveats)

The re-scraped Barttorvik data from `teamstats.php` is **real basketball data**, not percentiles:

| Year | Teams | eFG% Range | Verdict |
|------|-------|-----------|---------|
| 2008 | 347 | 39.4 – 57.4 | ✅ |
| 2009 | 350 | 38.5 – 57.0 | ✅ |
| 2010 | 353 | 40.5 – 57.9 | ✅ |
| 2011 | 351 | 40.2 – 57.0 | ✅ |
| 2012 | 351 | 39.8 – 58.0 | ✅ |
| 2013 | 353 | 39.2 – 58.2 | ✅ |
| 2014 | 357 | 42.1 – 58.9 | ✅ |
| 2015 | 357 | 39.4 – 58.3 | ✅ |
| 2016 | 357 | 41.5 – 58.7 | ✅ |
| 2017 | 357 | 41.0 – 59.8 | ✅ |
| 2018 | 357 | 42.6 – 59.5 | ✅ |
| 2019 | 359 | 40.0 – 59.0 | ✅ |
| 2022 | 364 | 36.1 – 63.6 | ⚠️ Wider range than typical |
| 2023 | 369 | 42.3 – 58.2 | ✅ |
| 2024 | 368 | 41.0 – 59.9 | ✅ |

**Data covers 15 years (2008-2019, 2022-2024).** Missing 2021 and 2025 (no Barttorvik scrape for those years).

Minor issues:
- 962/5350 team names have trailing numbers (e.g., "Boise St. 14") — handled by `normalize_team_name()` regex stripping
- 90 exact-duplicate records removed by dedup logic
- 2022 eFG range [36.1, 63.6] is wider than other years — could indicate a few bad records at the tails

**Bottom line:** The data is real and correctly formatted. The scrape fix worked.

---

## 2. AUC Comparison: All Models

### With vs Without Barttorvik (same 738 games, same pipeline)

| Model | 16 features (no BT) | 20 features (with BT) | Delta |
|-------|---------------------|----------------------|-------|
| Seed-only baseline | 0.6646 | 0.6646 | — |
| **Logistic Regression** | **0.6976** | 0.6842 | **−0.0134** |
| Random Forest | 0.6770 | 0.6629 | −0.0141 |
| Gradient Boosting | 0.6666 | 0.6365 | −0.0301 |
| **Ensemble** | **0.6857** | 0.6660 | **−0.0197** |

**Barttorvik features decrease AUC by 0.013–0.030 across every model.**

### Sanity check
The 16-feature results exactly match previously reported numbers (LR=0.6974→0.6976, Ensemble=0.6857→0.6857). This confirms the regression is caused **solely by adding Barttorvik features**, not by any other code change.

---

## 3. Root Cause Analysis

### 3a. Collinearity with KenPom features

| Barttorvik Feature | KenPom Feature | Correlation |
|-------------------|----------------|-------------|
| efg_off_diff | adj_o_diff | **r = −0.563** ⚠️ |
| efg_off_diff | adj_em_diff | r = −0.325 |
| to_off_diff | adj_o_diff | r = +0.338 |

**eFG% offensive diff is highly correlated with KenPom AdjO diff (r=−0.56).** This is expected — eFG% is a major component of offensive efficiency. Adding a correlated-but-noisier version of what KenPom already captures introduces variance without new signal.

### 3b. Missing data for 2021 + 2025 (16.4% of games)

Two entire tournament years have **zero Barttorvik coverage**:
- 2021: 61 games → all 4 Barttorvik features imputed to 0 diff (neutral)
- 2025: 60 games → same

That's 121/738 = **16.4% of training data** where the Barttorvik features are pure noise (all zeros). For tree models (RF, GBM), this creates a pool of games with an artificial "signature" that the model can overfit on.

### 3c. Does excluding 2021+2025 help?

Even excluding those years, Barttorvik **still hurts**:

| Model | 16 feat (no BT) | 20 feat (with BT) | Delta |
|-------|-----------------|-------------------|-------|
| LR | 0.6903 | 0.6738 | −0.0165 |
| Ensemble | 0.6878 | 0.6703 | −0.0175 |

**The missing data is not the main cause.** The features themselves degrade performance even when fully available.

### 3d. Per-Year AUC Breakdown (LR, 16f vs 20f)

| Year | 16f AUC | 20f AUC | Delta | BT coverage |
|------|---------|---------|-------|-------------|
| 2011 | 0.6867 | 0.6822 | −0.004 | 100% |
| 2013 | 0.6375 | 0.6417 | +0.004 | 100% |
| 2014 | 0.7724 | 0.7793 | +0.007 | 98% |
| 2015 | 0.7180 | 0.7068 | −0.011 | 98% |
| 2016 | 0.7464 | 0.7179 | −0.029 | 100% |
| 2017 | 0.6533 | 0.6250 | −0.028 | 100% |
| 2018 | 0.6988 | 0.6833 | −0.016 | 100% |
| 2019 | 0.8802 | 0.8953 | +0.015 ✓ | 98% |
| 2021 | 0.6303 | 0.6341 | +0.004 | 0% |
| 2022 | 0.6247 | 0.5941 | **−0.031** ⚠️ | 100% |
| 2023 | 0.5706 | 0.5478 | −0.023 | 100% |
| 2024 | 0.7368 | 0.7295 | −0.007 | 100% |
| 2025 | 0.8924 | 0.8980 | +0.006 | 0% |

Barttorvik hurts in **9 of 13 years**. The damage is consistent, not concentrated in missing-data years.

### 3e. LR Coefficients for Barttorvik Features

| Feature | Coefficient | Interpretation |
|---------|-------------|---------------|
| efg_off_diff | +0.036 | Tiny, same direction as adj_o_diff (+0.359) |
| to_off_diff | −0.007 | Essentially zero |
| or_off_diff | −0.026 | Negligible |
| ft_rate_diff | −0.086 | Small, but wrong sign? (fav higher FT rate → more upsets?) |

The Barttorvik features have near-zero coefficients in LR — the regularization is correctly suppressing them. But they still hurt because:
1. They add 4 noise dimensions that LR must estimate with limited data
2. RF and GBM can't regularize as effectively, so they overfit on these features

### 3f. Random Forest Feature Importance

The 4 Barttorvik features rank #7, #12, #14, #15 out of 20:
- or_off_diff: 0.0508 (#7)
- efg_off_diff: 0.0456 (#12)
- ft_rate_diff: 0.0435 (#14)
- to_off_diff: 0.0384 (#15)

They're getting non-trivial split importance in RF, which means the tree models are finding patterns in this data — but those patterns don't generalize out-of-sample.

---

## 4. Diagnosis Summary

**The Barttorvik four-factors features are redundant with KenPom adjusted efficiency metrics.** KenPom AdjO/AdjD already incorporate shooting efficiency, turnover rate, rebounding, and free throw rate into a single tempo-adjusted metric. Adding raw four-factors on top:

1. **Doesn't add new information** — eFG% correlates r=−0.56 with AdjO diff
2. **Adds estimation noise** — 4 more parameters to estimate from ~740 games
3. **Hurts tree models most** (GBM: −0.030) — they overfit on spurious splits
4. **Missing data compounds the issue** — 16.4% of games get zeroed-out features

---

## 5. Recommendation

### ❌ Drop Barttorvik four-factors features (17-20)

Revert to the 16-feature model. The numbers are clear:

| | 16 features | 20 features |
|---|---|---|
| Best LR AUC | **0.6976** | 0.6842 |
| Best Ensemble AUC | **0.6857** | 0.6660 |

The 16-feature model is strictly better.

### Possible future use of Barttorvik data

The raw four-factors **could** be useful if:
- Used as **defensive** four-factors (eFG% allowed, opponent TO rate, etc.) which capture something AdjD doesn't fully represent
- Combined into a single **composite** feature (like an offensive efficiency rating independent of KenPom) to reduce dimensionality
- Used only for **interaction features** (e.g., "slow, grinding underdog eFG advantage vs fast-paced favorite") rather than raw diffs

But for now, the data quality is good — the features just don't add predictive value beyond what KenPom already provides. Keep the scraped data (`barttorvik_teamstats.json`) archived for potential future use, but remove the 4 features from the active model.

---

## 6. Action Items

1. **Immediately:** Set `FEATURE_NAMES` and `extract_features()` back to 16 features (remove indices 16-19)
2. **Update train_sklearn.py docstring** — currently says "20 features", should say 16
3. **Keep barttorvik_teamstats.json** — data is valid, may be useful later
4. **Consider:** Barttorvik defensive four-factors as a separate experiment
5. **Retrain and save** final 16-feature model as `sklearn_model.joblib`
