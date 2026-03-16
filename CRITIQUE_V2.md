# CRITIQUE V2 — Final Re-Grade

**Reviewer:** Dickie V  
**Date:** 2026-03-16  
**Previous Grade:** D+  
**System Version:** V2 (complete rewrite)

---

## FINAL GRADE: B

From a D+ to a B. That's not a participation trophy — you earned that. The foundations went from cardboard to concrete. Let me tell you exactly why, component by component.

---

## Component Grades

### 1. Data Pipeline — A-

| Metric | Score |
|--------|-------|
| Data Sources | A |
| Match Rate | A- |
| ESPN Integration | B+ |
| Bracket Ingestion | A |

**What's right:**
- REAL KenPom for 365 teams, scraped live. Not a CSV from 2019. Not a guess. Live data.
- REAL bracket from ncaa.com. 68 teams, 0 unmatched. That's clean.
- REAL ESPN People's Bracket via Playwright API interception — that's sharp tradecraft. You're intercepting the Gambit API, not scraping HTML. That's how a professional does it.
- Alias resolution at 92.5% match rate on training data (100% of trainable games).
- Retry logic, caching, timestamped snapshots. Production-grade data ops.

**What's not:**
- ESPN picks are R1 only. The log says `Parsed ESPN picks for rounds: [1]`. Rounds 2–6 use decay multipliers (R2=85%, R3=65% of R1 ownership). That's a reasonable heuristic but it's **estimated data pretending to be real data** for the most important ownership signals — the later rounds where leverage matters most. For a pool optimizer, R3–R6 ownership accuracy is worth more than R1.
- The `whopickedwhom` page timed out. You handled it gracefully, but you're leaving real data on the table.

### 2. Upset Prediction Model — B-

| Metric | Score |
|--------|-------|
| Training Data | B+ |
| Model Architecture | B |
| Evaluation Honesty | A |
| Predictive Power | C+ |

**What's right:**
- 738 REAL tournament games, 2011–2025. Clean data with D2 contamination removed, AdjEM scale fixed for 5 years, aliases covering edge cases like NC State's 2024 Final Four run.
- sklearn ensemble (LR + RF + GBM) is the right toolbox for this sample size.
- **LOO-CV with year-based groups is honest evaluation.** You didn't leak. You didn't cherry-pick. AUC 0.697 for Logistic is what it is. You reported it straight. That's integrity.
- 16 features after dropping Barttorvik (which had garbage data in 75% of years). Right call — garbage in, garbage out.

**What concerns me:**
- **AUC 0.697 is a modest edge.** Seed-only baseline is 0.665. Your best model adds 5% lift. In gambling terms, that's the difference between a 52% bettor and a 50% bettor. Real, but thin. A sharp system I'd put real money behind would want 0.72+.
- **738 samples is thin for ML.** You're training 3 models on 738 rows with 16 features. That's not dangerous (Logistic handles it fine), but the trees are going to overfit on noise. The RF and GBM AUCs being *below* Logistic (0.677 and 0.667 vs 0.698) confirms this — the flexible models are finding patterns that don't generalize.
- **The ensemble HURTS you.** LR=0.698, Ensemble=0.686. Averaging in two weaker models degrades your best model. Either weight the ensemble toward LR (e.g., 0.6/0.2/0.2) or just use LR. The V4 review even noted "Logistic model's stability confirms it's the right production choice for this data size."
- **No Barttorvik means no Four Factors.** EFG%, turnover rate, offensive rebounding, and free throw rate are among the most predictive features for March Madness upsets. You dropped them for good reason (data quality), but that's still a real capability gap.

### 3. Matchup Probability Engine (sharp.py) — B

| Metric | Score |
|--------|-------|
| Core Model Integration | B+ |
| Modifier System | B- |
| Edge Case Handling | B |

**What's right:**
- Ensemble model is the primary probability source. Good.
- Extreme seed clamps for 1v16 (min 93% favorite) and 2v15 (min 85% favorite). Necessary guardrail.
- The `adj_em_to_win_prob` with tournament-specific kappa=13.0 (vs 11.5 regular season) is a real insight. Tournament variance IS higher.

**What concerns me:**
- **UPS is dead code.** `compute_upset_propensity_score`, `apply_upset_propensity_modifier`, `apply_tournament_experience_modifier`, `apply_tempo_mismatch_modifier`, `apply_conference_momentum_modifier`, `apply_seed_prior` — these functions all exist in sharp.py but **are never called from `compute_matchup_probability`** when the ensemble model is loaded. The ensemble path bypasses all of them. That's ~200 lines of research-grade modifier code sitting inert. Either integrate them or delete them.
- **The extreme seed clamp interacts badly with the EMV floor.** For a 15-over-2 matchup (seed gap 13, ≥12 triggers clamp), the underdog gets clamped to max 15%. Your EMV floor in the optimizer says `if p_upset < 0.15: emv = -999`. So every 15-over-2 matchup gets **exactly** 15% and slides right past the floor. That's why Tennessee St. (15, AdjEM -1.83) over Iowa St. (2, AdjEM +32.42) made it into the bracket despite a 34-point AdjEM gap. The clamp + floor conspire to make 15-over-2 look like a viable EMV play. Historically, 15-seeds win ~6.25% of the time, not 15%. This is a calibration bug that inflates Cinderella picks.

### 4. Ownership & Leverage (contrarian.py) — B+

| Metric | Score |
|--------|-------|
| ESPN Data Integration | B+ |
| Leverage Formula | A- |
| Profile Construction | B |

**What's right:**
- Pool-size-aware leverage: `prob / ((pool_size - 1) * ownership + 1)` is the correct formula. This is what separates a 10-person office pool from a 1000-person contest. Most bracket tools ignore this. You didn't.
- Brand name boost for blue bloods (historically over-picked). Real effect.
- Uses actual ESPN R1 data when available.

**What concerns me:**
- `update_leverage_with_model` uses `seed_factor ** n` for rounds 2–5 instead of actual advancement probabilities from the Monte Carlo sim that you already run. You compute `title_probs` via simulation and use them for round 6, but rounds 2–5 use a crude power curve. You have the simulation infrastructure — use it.
- R2–R6 ownership is estimated, not real (ESPN only gave R1). Your leverage calculations for later rounds — where leverage matters most — are built on two estimates multiplied together. Estimate × estimate = wide error bars.

### 5. Optimizer Architecture — B+

| Metric | Score |
|--------|-------|
| Pipeline Design | A- |
| Champion Selection | A- |
| Scenario Generation | B |
| Upset Selection (EMV) | B |
| Monte Carlo Evaluation | B- |
| Output Diversity | B |

**What's right:**
- **Top-down construction is correct.** Champion → FF paths → fill remaining. This is how sharps build brackets. You lock the high-value skeleton first, then optimize around it.
- **Scenario-based approach** (chalk, contrarian, chaos) gives a real portfolio. Two chalk, two contrarian, two chaos = 6 brackets, pick best 3. Smart.
- **EMV-based upset selection** is principled. Expected Marginal Value considers both upset probability AND ownership scarcity. This is the right framework.
- **Champion candidates filtered by pool-size-aware threshold.** Min 8% title prob for 25-person pool. Four candidates: Michigan (17.2%), Arizona (14.8%), Duke (13.2%), Florida (9.2%). All defensible.
- **Amendment 4 forces different champions across scenarios.** Chaos scenarios MUST use candidate[1]+, never candidate[0]. This prevents the optimizer from converging on a single answer.

**What concerns me:**

- **500 simulations is thin.** P(1st) = 6.6% from 500 sims means 33 first-place finishes observed. The 95% confidence interval on that is roughly ±2.2% (4.4% to 8.8%). That's a wide spread. For production-quality estimates, you need 10,000+. At 500, you're getting a rough sketch, not a measurement.

- **Scenarios aren't actually that different.** chalk_0 and chalk_1 share the exact same 8 R1 upsets. They only diverge on one later-round upset (Gonzaga vs Tennessee St.). The contrarian scenarios share those same 8 upsets plus 2 more. The chaos scenarios share them plus 5 more. The upset selection is dominated by the same top-EMV picks regardless of scenario — because EMV is deterministic given the same matchup matrix. The "scenario" framework changes the champion and chaos level, but the actual upset picks are a superset, not an alternative.

- **Tennessee St. (15) making the R2 and potentially Elite 8.** The aggressive bracket has this 15-seed with -1.83 AdjEM beating Iowa St. (+32.42), then Santa Clara, then getting picked to beat Virginia to reach the Elite 8. In a bracket pool, a 15-seed in the E8 is a 0.02% event. The leverage is huge *if* it happens, but the probability is so low that the EMV should be deeply negative. This got through because: (a) the 15% clamp artificially inflates the R1 probability, and (b) the later-round upset EMV doesn't properly account for the compounding improbability.

- **No correlation modeling in opponent brackets.** The opponent generator picks a champion and then fills round by round using ownership weights. But in reality, bracket picks are correlated — if someone picks Michigan as champion, they pick Michigan in every round. The code handles this for the champion, but not for other teams. A bracket that picks Duke in the E8 is more likely to have picked Duke in R1, R2, R3. The opponent model treats each game independently (modulo champion), which underestimates the field's concentration.

### 6. Output Quality — B

| Metric | Score |
|--------|-------|
| Champion Pick | A- |
| Final Four | B+ |
| Upset Portfolio | B- |
| Actionability | B |

**The Optimal Bracket:**
- **Champion: Michigan** (1-seed, AdjEM 37.59). Strong pick. Second-highest AdjEM behind Duke's 38.90, but Michigan has better path/ownership value.
- **FF: Arizona, Houston, Michigan, Duke** — All 1-seeds and a 2-seed. In a 25-person pool, this is reasonable. Not trying to be cute with the Final Four.
- **E8: Duke, Louisville, Arizona, Gonzaga, Florida, Houston, Michigan, Virginia** — Louisville (6) and Gonzaga (3) as upsets to reach E8 adds differentiation without being reckless.
- **R1 Upsets: 8 total** — Iowa (9/8), Utah St. (9/8), VCU (11/6), Santa Clara (10/7), Texas A&M (10/7), Saint Louis (9/8), North Dakota St. (14/3), Tennessee St. (15/2). The 8/9 and 9/8 flips are fine (coin flips). The 10/7s are solid value. The 14/3 and 15/2 are where I raise an eyebrow. Historical base rate for 14-over-3 is ~15% and 15-over-2 is ~6%. The model is over-indexing on these.
- **P(1st) = 6.6%** in a 25-person pool vs 4.0% random baseline. That's +2.6% absolute, or +65% relative. Meaningful but not transformative.

**Format & Presentation:**
- Clean ASCII bracket with confidence tiers (Lock/Lean/Gamble). Readable.
- Analysis.md with key differentiators ranked by leverage. Useful.
- Summary.json with all metrics. Machine-readable.
- Three output brackets (optimal/safe/aggressive) with distinct champions. Good portfolio.

---

## What Changed Since D+ (Verified)

| Claim | Verified? | Notes |
|-------|-----------|-------|
| Complete optimizer rewrite | ✅ Yes | Scenario-based, top-down, EMV — fundamentally different architecture |
| sklearn ensemble on 738 real games | ✅ Yes | LR+RF+GBM, LOO-CV AUC 0.697 |
| REAL 2026 bracket from ncaa.com | ✅ Yes | 68 teams, 0 unmatched |
| REAL ESPN People's Bracket R1 picks | ✅ Yes | Playwright API interception, 60 teams, 1.1M+ brackets |
| REAL KenPom for 365 teams | ✅ Yes | Live scrape, all stats present |
| Model data bugs fixed | ✅ Yes | AdjEM scale, aliases (92.5%), Barttorvik dropped, D2 removed |
| LOO-CV AUC 0.697 honest | ✅ Yes | Year-based LOGO, no leakage detected |
| Later-round upsets working | ✅ Yes | R2–R5 EMV-based upset injection confirmed |
| Pool-size-aware champion formula | ✅ Yes | `prob / ((pool_size - 1) * ownership + 1)` |
| No fake data | ✅ Yes | Every data source traced to real origin |

Every claim checks out. That's not nothing.

---

## What Would Make This an A

1. **Fix the 15-seed calibration bug.** The clamp-floor interaction needs resolution. Either raise the EMV floor to 0.20 for seed gaps ≥13, or use actual model probabilities without clamping (let the model speak). Tennessee St. over Iowa St. should NOT be in the optimal bracket.

2. **Bump sims to 10,000.** 500 is a prototype. Your pipeline already runs in ~3 minutes for 500 sims. 10K would take ~60 minutes. Run it overnight. The P(1st) estimate needs to be stable.

3. **Weight the ensemble toward Logistic.** LR AUC 0.698 > Ensemble 0.686. Use 0.6/0.2/0.2 weighting or just use LR solo for production. The V4 review already told you this.

4. **Use MC-derived advancement probabilities** for the leverage calculation, not `seed_factor ** n`. You already run 2000-sim title probability estimation. Extend it to track round-by-round advancement for all teams. You have the infrastructure.

5. **Make scenarios actually diverge.** The upset picks should differ between scenarios, not just be supersets. In a chalk scenario, pick FEWER upsets from the same EMV list. In a chaos scenario, REPLACE some of the moderate upsets with higher-variance plays, don't just add more. Each scenario should tell a different story of what March looks like.

6. **Get ESPN R2+ data.** The whopickedwhom page has it. It timed out once — retry with different timing, or hit the API directly with the scoring period parameter. Real R2–R6 ownership is worth 10x the estimated version.

7. **Source Four Factors data** from somewhere reliable. KenPom has it (behind the paywall). This is the biggest feature gap in the model.

---

## The Bottom Line

**D+ → B is a three-letter-grade jump.** That doesn't happen without serious work. The data is real. The model is honest. The optimizer architecture is sound. The pool-size awareness is smart. The output is usable.

You're not a sharp yet. A sharp system would have AUC 0.72+, 10K+ sims, and perfect calibration on extreme matchups. But you're no longer embarrassing. You're a competent mid-major program that made the tournament. The ceiling is there if you fix the calibration issues and bump the simulation depth.

**Michigan as champion is a strong pick.** I'd put that bracket in a pool.

I wouldn't bet my mortgage on it. But I'd bet $50.

---

**Final Grade: B**

| Component | Grade | Weight | Weighted |
|-----------|-------|--------|----------|
| Data Pipeline | A- | 20% | 3.7 × 0.20 = 0.74 |
| Upset Model | B- | 20% | 2.7 × 0.20 = 0.54 |
| Matchup Engine | B | 15% | 3.0 × 0.15 = 0.45 |
| Ownership/Leverage | B+ | 15% | 3.3 × 0.15 = 0.50 |
| Optimizer Architecture | B+ | 20% | 3.3 × 0.20 = 0.66 |
| Output Quality | B | 10% | 3.0 × 0.10 = 0.30 |
| **Weighted GPA** | | | **3.19 / 4.0 = B** |

— Dickie V
