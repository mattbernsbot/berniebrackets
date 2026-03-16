# FEATURE ROADMAP: Upset Prediction Model v2

*Authored by: Dickie V — statistician, sharp, and college basketball degenerate*
*Date: 2026-03-15*

---

## Current Model Baseline

- **Games:** 799 NCAA tournament games (2011–2025)
- **Features:** 9 (seed_diff, round_num, adj_em_diff, adj_o_diff, adj_d_diff, adj_t_diff, seed×adj_em, round×seed, round×adj_em)
- **AUC:** 0.733 (ensemble) vs 0.686 (seed-only) = **+6.8% lift**
- **Training data:** 4,604 KenPom team-season records from archive.org

---

## ⚠️ OVERFITTING CONSTRAINT — READ THIS FIRST

With **~800 games** and a binary outcome, we are severely sample-limited. Here's the math:

- **Rule of thumb (Events Per Variable):** For logistic regression, you want ≥10–20 events per predictor. With upsets being ~30% of games (~240 upsets), that gives us a **hard ceiling of ~12–24 total features** before overfitting becomes dangerous.
- **We already have 9.** That means we can realistically add **3–12 more features**, depending on correlation structure and regularization.
- **Correlated features are cheaper** — if a new feature is somewhat redundant with existing ones, the effective dimensionality increase is smaller. But truly orthogonal features eat capacity fast.
- **Random forest is more forgiving** than logistic regression for feature count, but with 800 rows, even RF will start memorizing noise past ~20 features.

### Practical Strategy
1. **Add features in batches of 2–3**, evaluate with nested cross-validation after each batch
2. **Use L1 regularization** (Lasso) to automatically zero out weak features
3. **Prioritize features with HIGH expected signal and LOW correlation with existing features** (adj_em_diff already captures most "team quality" — we need orthogonal information)
4. **Consider PCA or feature selection** if we go past 15 total features
5. **The single best bang-for-buck move:** Add KenPom's "Luck" rating. It's orthogonal to everything we have and directly measures regression-to-mean risk.

**Bottom line: We're shopping for 5–8 surgical additions, not a feature buffet.**

---

## TIER 1: HIGHEST PRIORITY (High Expected Lift, Easy–Medium Acquisition)

These are the features I'd bet my mortgage on. They capture information **orthogonal** to our current efficiency metrics and have strong theoretical reasons to predict upsets.

---

### 1.1 — KenPom "Luck" Rating

**What:** KenPom's Luck metric measures the deviation between a team's actual win-loss record and what their efficiency stats predict. A team with Luck = +0.05 has won ~5% more games than their underlying quality suggests. High-luck teams are **regression bombs** — they've been winning close games at unsustainable rates.

**Why it predicts upsets:** This is THE classic upset predictor. A 3-seed with Luck = +0.08 is a paper tiger. They looked great all year but their record flatters them. In a single-elimination tournament, regression to the mean is brutal. Conversely, a 10-seed with Luck = -0.04 is *underseeded* — they're better than their record shows.

The key insight: the selection committee seeds teams based largely on **record**, which includes luck. KenPom efficiency (which we already use) partially corrects for this, but Luck is the *residual* — the part of the record that efficiency *doesn't* explain. Using the luck differential between matchup opponents directly captures "how much is this seed gap inflated by noise?"

**Expected predictive power:** ⭐⭐⭐ **HIGH**
- This is likely our single highest-value addition. Studies consistently show high-luck teams underperform seeds in March.
- Estimated AUC lift: +1.5–3.0% (significant for a single feature)
- Crucially, this is **nearly orthogonal** to adj_em_diff — it captures something our model completely misses

**Data source:**
- **KenPom archive via archive.org** — We're ALREADY scraping KenPom from the Wayback Machine for adj_em/adj_o/adj_d/adj_t. The Luck column is on the **same page**. We literally just need to add one more column to our existing scraper.
- URL pattern: `https://web.archive.org/web/*/kenpom.com` (same as current pipeline)
- The "Luck" column appears on the main rankings table at `kenpom.com`

**Acquisition difficulty:** ⭐ **EASY** — It's already in our data pipeline. Just parse one more column.

**Historical availability:** 2002–present (KenPom's full history). We have 2011–2025 already scraped.

**Feature engineering:**
- `luck_diff` = lower_seed_luck - higher_seed_luck
- `higher_seed_luck` alone (high luck = upset risk)
- Consider `luck × seed_diff` interaction (luck matters more in big seed gaps)

---

### 1.2 — Three-Point Rate (3PAr) and Three-Point Percentage (3P%)

**What:** 3PAr = percentage of field goal attempts that are 3-pointers. 3P% = accuracy on those attempts. Together they measure a team's reliance on and proficiency at long-range shooting.

**Why it predicts upsets:** Three-point shooting is the **great equalizer** in college basketball. It's also the **highest-variance shot** in the game. A mid-major that lives by the three can absolutely torch a blue blood on a hot shooting night — and get blown out on a cold one.

The mechanism is statistical: if Team A scores mostly on 2s and free throws (low variance), their scoring is predictable game-to-game. If Team B jacks up 30 threes a game, their point total has a much wider distribution. Wide distributions = more upsets.

But there's a subtlety: it's the **underdog's** 3-point profile that matters most. A high-3PAr underdog has more upset *potential* but also more blowout loss potential. The favorite's 3P defense also matters — if the favorite can't guard the arc, they're vulnerable.

**Expected predictive power:** ⭐⭐⭐ **HIGH**
- 3-point variance is one of the most well-documented upset mechanisms in basketball analytics
- This is partially captured by adj_o_diff (good 3pt shooting → better offense) but the **variance component** is completely missing from our model
- Estimated AUC lift: +1.0–2.0%

**Data source:**
- **KenPom Four Factors** — Available at `kenpom.com/stats.php?s=RankeFG_Pct` (eFG%, which includes 3P impact) and related pages. The Wayback Machine has these pages archived.
  - Specifically: `kenpom.com/stats.php?s=RankFG3Pct` (3P%) and `kenpom.com/stats.php?s=Rank3PA_per_FGA` (3PAr, i.e., 3-point attempt rate)
  - Defensive versions: `kenpom.com/stats.php?s=RankDeFG_Pct` etc.
- **Barttorvik** — `barttorvik.com/trank.php` has similar data, free, no paywall. T-Rank data goes back to 2008.
  - URL: `https://barttorvik.com/trank.php?year=2024&sort=&top=0&conlimit=All`
  - Can also get team-level shooting splits
- **Sports Reference / College Basketball Reference:**
  - `https://www.sports-reference.com/cbb/seasons/men/2024-school-stats.html`
  - Free, goes back to ~2010 with full shooting splits
  - Easier to scrape than KenPom (no paywall, clean HTML tables)

**Acquisition difficulty:** ⭐⭐ **EASY-MEDIUM**
- If we extend our KenPom archive scraper to hit the Four Factors pages: Easy
- Barttorvik alternative: Easy (clean tables, no paywall)
- Sports Reference: Easy (structured HTML, well-known scraping target)

**Historical availability:**
- KenPom: 2002–present
- Barttorvik: 2008–present
- Sports Reference: ~1993–present (but data quality improves after 2002)

**Feature engineering:**
- `three_point_rate_diff` = underdog_3PAr - favorite_3PAr
- `underdog_3PAr` alone (high = more variance = more upset potential)
- `three_point_pct_diff` = underdog_3P% - favorite_3P%
- Consider: `underdog_3PAr × seed_diff` (3-point variance matters more in big mismatches)

---

### 1.3 — Free Throw Percentage

**What:** Team free throw shooting percentage over the season.

**Why it predicts upsets:** Free throws are the **pressure shot** of March Madness. In a close game in the final 2 minutes, the team at the line decides the outcome. Unlike 3-pointers (which are about variance), free throws are about **execution under pressure** — and they're the one stat where individual skill matters most and opponent defense matters least.

The upset angle: many mid-majors have experienced upperclassmen who shoot 75%+ from the line. Many elite recruits at blue bloods are shaky free throw shooters (one-and-done freshmen). A 12-seed with seniors who shoot 78% from the line will *close out* close games. A 5-seed with freshmen shooting 68% will choke them away.

This is also the **most independent** shooting stat from overall efficiency — a team can have great adj_em but terrible FT%. It's genuinely orthogonal information.

**Expected predictive power:** ⭐⭐ **MEDIUM-HIGH**
- Not as powerful as Luck or 3PAr in isolation, but captures a real mechanism (close-game execution)
- Estimated AUC lift: +0.5–1.5%
- Most valuable as a **late-game proxy** when combined with other features

**Data source:**
- **Same sources as 3P data** — KenPom Four Factors, Barttorvik, Sports Reference all have FT%
- KenPom: `kenpom.com/stats.php?s=RankFT_Pct`
- Sports Reference: same team stats pages
- Barttorvik: included in standard team rankings export

**Acquisition difficulty:** ⭐ **EASY** — Same scraping pipeline as 3P data. One additional column.

**Historical availability:** 2002–present (KenPom), much further back via Sports Reference

**Feature engineering:**
- `ft_pct_diff` = underdog_FT% - favorite_FT%
- `underdog_ft_pct` alone
- Consider: `ft_pct_diff × round_num` (FT% matters more in later rounds when games are tighter)

---

### 1.4 — Turnover Rate (TO%)

**What:** Turnovers per 100 possessions (both offensive and defensive).

**Why it predicts upsets:** Turnovers are **chaos**. A team that turns it over 20% of possessions is playing with fire every trip down the floor. For favorites, high turnover rate is a vulnerability — it gives the underdog free possessions and shortens the effective game. For underdogs, *forcing* turnovers (defensive TO%) is an equalizer — if you can't outshoot a better team, steal the ball.

Pressing teams (think VCU's "Havoc" in 2011, Loyola Chicago's disciplined ball-handling in 2018) leverage this asymmetry. A mid-major that doesn't turn it over and forces turnovers can hang with anyone.

**Expected predictive power:** ⭐⭐ **MEDIUM**
- Partially captured by adj_em_diff (turnovers hurt efficiency) but the **variance and chaos** component is independent
- Especially powerful when the favorite has high offensive TO% (sloppy teams get upset more)
- Estimated AUC lift: +0.5–1.0%

**Data source:**
- **KenPom Four Factors:** `kenpom.com/stats.php?s=RankTO_Pct` (offensive) and `kenpom.com/stats.php?s=RankDTO_Pct` (defensive/forced)
- **Barttorvik:** Included in standard team data
- **Sports Reference:** Team stats pages include turnovers per game

**Acquisition difficulty:** ⭐ **EASY** — Same pipeline as above

**Historical availability:** 2002–present

**Feature engineering:**
- `to_rate_diff` = favorite_offensive_TO% - underdog_offensive_TO% (positive = favorite is sloppier)
- `underdog_defensive_to_rate` (high = underdog forces turnovers = chaos agent)
- `favorite_offensive_to_rate` alone (sloppy favorites get upset)

---

### 1.5 — Vegas Point Spread

**What:** The pre-game point spread set by Las Vegas sportsbooks for each tournament game.

**Why it predicts upsets:** The point spread is, without exaggeration, the **single most informative number** in sports prediction. It represents the consensus of a market with billions of dollars at stake. The spread incorporates *everything* — efficiency, matchups, injuries, travel, public perception, sharp money, you name it. It's a better predictor of game outcomes than any model an academic has ever built.

For upset prediction specifically, the spread tells us something seeds DON'T: **how vulnerable the favorite actually is in THIS specific game.** A 2-seed might be a 12-point favorite against a 15-seed, or only a 4-point favorite against a different 15-seed. That gap is pure gold.

Additionally, spread vs. seed-implied spread gives us a **market correction** — when Vegas thinks the committee got it wrong.

**Expected predictive power:** ⭐⭐⭐ **HIGH**
- The spread alone typically achieves AUC 0.75+ for game outcomes
- But our model already has adj_em_diff, which is correlated with the spread (~0.7–0.8 correlation)
- The **residual** information (spread after controlling for efficiency) captures injuries, matchup-specific factors, market wisdom
- Estimated AUC lift: +1.0–2.5% (large because it's a fundamentally different information source)
- Risk: high correlation with existing features may limit marginal value

**Data source:**
- **Kaggle NCAA Tournament datasets:** Several datasets include historical spreads
  - `https://www.kaggle.com/datasets/andrewsundberg/college-basketball-dataset` — includes some spread data
- **Sports Reference game logs:** Don't include spreads directly
- **Covers.com:** Historical ATS results and spreads
  - `https://www.covers.com/ncaab/matchups` — game-by-game spreads
  - Requires scraping, but data is public
- **SportsBookReview (SBR):** Historical lines archive
  - `https://www.sportsbookreview.com/betting-odds/ncaa-basketball/` — current and recent lines
- **Odds API (paid):** `https://the-odds-api.com/` — historical odds data, paid tier
- **KillerSports.com:** Free historical NCAA tournament ATS data
  - `https://killersports.com/ncaa/query` — custom queries for historical spreads
- **Goldsheet / historical archives:**
  - Various sports data archives have tournament spreads going back to the 1980s
- **Best free option: Evan Miyakawa's historical lines dataset on Kaggle/GitHub**
  - Search for "NCAA tournament historical point spreads" — several researchers have compiled these

**Acquisition difficulty:** ⭐⭐⭐ **MEDIUM-HARD**
- No single clean API for historical tournament spreads
- Best approach: scrape Covers.com for 2011–2025 tournament games, or find a compiled dataset
- May need to manually match games between our dataset and spread dataset

**Historical availability:**
- Reliable: 2005–present (digital sportsbook era)
- Spotty: 1990–2005
- Very sparse: pre-1990

**Feature engineering:**
- `spread` (raw Vegas spread, favorite negative)
- `spread_vs_seed_expected` = actual_spread - expected_spread_for_seed_matchup (market correction)
- `spread_vs_adj_em_predicted` = spread - model_predicted_spread (captures info beyond efficiency)

---

## TIER 2: HIGH PRIORITY (Medium-High Expected Lift, Medium Acquisition)

These features capture real mechanisms but are slightly harder to get or slightly less predictive than Tier 1.

---

### 2.1 — Offensive Rebounding Rate (OR%)

**What:** Percentage of available offensive rebounds a team grabs.

**Why it predicts upsets:** Offensive rebounds are **second chances**, and second chances are how inferior teams extend possessions and stay in games. A team that gets 35% of its own misses is going to get extra shots, extra fouls on the opponent, and extra possessions. For underdogs, offensive rebounding extends the game and increases variance. For favorites, *defensive* rebounding (denying second chances) is a way to slam the door.

The 2016 Villanova team that won it all? Elite defensive rebounding. They ended possessions on the first shot. Upsets happen when inferior teams get multiple looks.

**Expected predictive power:** ⭐⭐ **MEDIUM**
- Partially captured by offensive/defensive efficiency, but the rebounding *rate* is somewhat independent
- Most valuable for identifying specific upset mechanisms (the scrappy underdog that won't go away)
- Estimated AUC lift: +0.3–0.8%

**Data source:**
- **KenPom Four Factors:** `kenpom.com/stats.php?s=RankOR_Pct` and `kenpom.com/stats.php?s=RankDOR_Pct`
- **Barttorvik, Sports Reference** — same as other Four Factors

**Acquisition difficulty:** ⭐ **EASY** — Same pipeline as other Four Factors

**Historical availability:** 2002–present

**Feature engineering:**
- `or_pct_diff` = underdog_OR% - favorite_OR%
- `underdog_or_pct` alone (scrappy underdogs)
- `favorite_dor_pct` alone (favorites that don't rebound = vulnerable)

---

### 2.2 — Coach NCAA Tournament Experience

**What:** Number of previous NCAA tournament appearances and wins for each team's head coach.

**Why it predicts upsets:** March Madness is a **different sport** than the regular season. The pressure is unique, the preparation window is unique, the single-elimination format is unique. Coaches who've been there know how to prepare. They know how to scout. They know how to manage the moment.

Think about it: Tom Izzo (Michigan State) with a 7-seed is DANGEROUS. He's been to 8 Final Fours. His teams consistently overperform their seed. Meanwhile, a first-time tournament coach with a 2-seed might be in over his head — different preparation timeline, media distractions, players who've never experienced this pressure.

The data backs this up. Coaches with 5+ tournament appearances win at a meaningfully higher rate than first-timers at the same seed line.

**Expected predictive power:** ⭐⭐ **MEDIUM-HIGH**
- Strong theoretical basis and anecdotal evidence
- Some of this is captured by seed (good coaches get good seeds) but the *residual* — experienced coach with a low seed — is powerful
- Estimated AUC lift: +0.5–1.5%

**Data source:**
- **Sports Reference Coach Pages:**
  - `https://www.sports-reference.com/cbb/coaches/` — individual coach pages with full tournament history
  - Example: `https://www.sports-reference.com/cbb/coaches/tom-izzo-1.html`
  - Includes: seasons, wins, tournament appearances, tournament wins, Final Fours
- **Wikipedia NCAA Tournament pages:** Each year's bracket page lists coaches
- **NCAA.com historical brackets:** `https://www.ncaa.com/news/basketball-men/article/ncaa-tournament-bracket-history`
- **Manual compilation option:** There are only ~68 coaches per tournament. For 15 years = ~500 unique coaches. Feasible.
- **Best compiled source:** Kaggle's NCAA tournament datasets often include coach names, which can be cross-referenced with Sports Reference

**Acquisition difficulty:** ⭐⭐⭐ **MEDIUM**
- Need to: (1) get coach name for each team-year, (2) look up their cumulative tournament record at that point in time
- Not a single table — requires cross-referencing
- Could semi-automate: scrape coach assignments per team per year from Sports Reference, then calculate cumulative tournament stats

**Historical availability:**
- Sports Reference: Complete coaching records back to the 1890s
- Practical: very clean data from 2000–present

**Feature engineering:**
- `coach_tourney_appearances_diff` = underdog_coach_appearances - favorite_coach_appearances
- `underdog_coach_tourney_wins` (experienced underdog coach = upset risk)
- `favorite_coach_first_timer` (binary: 1 if favorite's coach has 0 prior tournament games)
- `coach_tourney_win_pct_diff`

---

### 2.3 — Conference Strength / Conference Adjusted Metrics

**What:** The strength of the conference each team plays in, and whether a team might be over- or under-seeded relative to their conference.

**Why it predicts upsets:** The selection committee has **known biases**. They over-reward teams from power conferences (ACC, Big Ten, Big 12, SEC) and under-reward mid-majors. A team from the Mountain West with a 28-4 record that gets a 10-seed might actually be a 7-seed talent level.

More specifically: mid-major teams that dominated weak conferences may have inflated records (like a high-luck team), while power conference teams that went 22-10 in a brutal league are battle-tested.

We can capture this by looking at the *residual* between a team's seed and what their KenPom ranking would predict. If KenPom says they're #15 but they got a 7-seed, that team is overseeded.

**Expected predictive power:** ⭐⭐ **MEDIUM**
- Some of this is already captured by adj_em_diff (KenPom adjusts for SOS)
- The *residual* — seed vs. KenPom rank — is useful but partially redundant with seed×adj_em interaction
- Estimated AUC lift: +0.3–0.8%

**Data source:**
- **We already have this data!** KenPom rank vs. actual seed = immediate feature
- Conference affiliations: Sports Reference, KenPom, Barttorvik all include conference

**Acquisition difficulty:** ⭐ **EASY** — Derivable from existing data

**Historical availability:** Same as our current data (2011–2025)

**Feature engineering:**
- `kenpom_rank_vs_seed_diff` = (underdog_kenpom_rank - seed_implied_kenpom_rank) - (favorite's same metric)
- `conference_power_indicator` (power 6 conference = 1, mid-major = 0)
- `cross_conference_matchup` (power vs. mid-major = 1)

---

### 2.4 — Experience / Roster Continuity

**What:** Percentage of minutes returning from last year's roster, or years of experience on the roster.

**Why it predicts upsets:** College basketball has become a **transfer portal circus**, and the teams that have continuity — guys who've played together for 2–3 years — have a massive edge in March when preparation time is short and execution matters.

Think about the classic Cinderellas: Loyola Chicago 2018 (seniors everywhere), Saint Peter's 2022 (experienced roster), Oral Roberts 2021 (Max Abmas was a junior). These were old, experienced teams that didn't crack under pressure.

Meanwhile, a 2-seed that's a collection of 5-star freshmen and portal transfers who've been together 6 months? They're vulnerable when the game plan gets disrupted.

**Expected predictive power:** ⭐⭐ **MEDIUM-HIGH**
- Strong theoretical basis, especially in the modern transfer portal era
- Somewhat orthogonal to efficiency metrics — experience captures *resilience* and *cohesion*
- Estimated AUC lift: +0.5–1.5%

**Data source:**
- **Barttorvik:** `barttorvik.com` tracks "Continuity" (% of minutes returning). This is the cleanest source.
  - URL: `https://barttorvik.com/trank.php?year=2024` — columns include experience metrics
  - Also has "experience" rating
- **EvanMiya.com:** `https://evanmiya.com/` — tracks roster continuity and returning production
- **Sports Reference:** Individual player pages show minutes by year — can compute returning minutes
  - Would require: get roster per team per year, look up each player's prior year minutes
  - Doable but labor-intensive
- **KenPom:** Has some experience data but behind paywall and not consistently archived

**Acquisition difficulty:** ⭐⭐ **MEDIUM**
- Barttorvik is the easiest path — scrape the main rankings table which includes experience/continuity metrics
- Goes back to 2008, which covers most of our training window

**Historical availability:**
- Barttorvik: 2008–present
- EvanMiya: ~2020–present (too recent for our needs)
- Sports Reference: 2010–present with effort

**Feature engineering:**
- `experience_diff` = underdog_experience - favorite_experience
- `underdog_experience` alone (experienced underdogs are dangerous)
- `continuity_diff` = underdog_returning_minutes_pct - favorite_returning_minutes_pct

---

### 2.5 — Tempo Mismatch / Adjusted Tempo Differential

**What:** The difference in preferred pace (possessions per 40 minutes) between the two teams.

**Why it predicts upsets:** We already have adj_t_diff, but there's a deeper question: **does the magnitude of tempo mismatch matter?** When a 70-possession team plays a 62-possession team, who controls the pace? And does that matter for upset probability?

Theory: upsets are more likely when the underdog can **slow the game down**. Fewer possessions = smaller sample size = more variance = more upsets. A slow-paced underdog facing a fast favorite is trying to make the game "shorter" — and shorter games have more randomness.

The classic example: every time a disciplined, slow mid-major takes down a fast-paced blue blood. They grind it into a 55-50 game and anything can happen in a 5-possession margin.

**Expected predictive power:** ⭐⭐ **MEDIUM**
- We already have adj_t_diff, so the marginal lift is uncertain
- The **mismatch magnitude** (absolute value) and **direction** (who's slower) could add something
- Estimated AUC lift: +0.2–0.6%

**Data source:**
- **Already in our data!** We have adj_t from KenPom. Just need feature engineering.

**Acquisition difficulty:** ⭐ **EASY** — Pure feature engineering on existing data

**Feature engineering:**
- `tempo_mismatch` = abs(underdog_adj_t - favorite_adj_t)
- `underdog_slower` = 1 if underdog_adj_t < favorite_adj_t, else 0
- `tempo_mismatch × underdog_slower` (slow underdog vs fast favorite interaction)

---

## TIER 3: MEDIUM PRIORITY (Moderate Expected Lift, Variable Acquisition)

Worth pursuing after Tier 1 and Tier 2, but either harder to get or less certain to help.

---

### 3.1 — Geographic Proximity / Travel Distance

**What:** Distance between each team's campus and the tournament game site.

**Why it predicts upsets:** First and second round games are played at 8 different sites around the country. The committee assigns teams to sites — and nearby teams get a **de facto home court advantage**. The crowd is louder, the travel is shorter, the routine is less disrupted.

A 12-seed that's 50 miles from the arena and a 5-seed that traveled 2,000 miles? That 12-seed has a real edge the stats don't capture.

This effect is **strongest in rounds 1-2** (regional sites, closer to home) and diminishes by the Final Four (neutral site, everyone travels).

**Expected predictive power:** ⭐⭐ **MEDIUM**
- Well-documented effect in sports analytics literature (~1.5–2 point home court advantage)
- Only applies to first weekend (rounds 1-2), diminishes after
- Estimated AUC lift: +0.3–0.8%

**Data source:**
- **Tournament bracket data:** Need game sites for each round, each year
  - NCAA.com historical brackets: `https://www.ncaa.com/brackets/basketball-men/d1` (current and historical)
  - Sports Reference: `https://www.sports-reference.com/cbb/postseason/men/` — has game locations
  - Wikipedia: Each year's tournament page lists all venue cities
- **Team campus locations:** Simple lookup — Wikipedia, college database, or geocoding
- **Distance calculation:** Haversine formula between campus coordinates and game site coordinates

**Acquisition difficulty:** ⭐⭐⭐ **MEDIUM**
- Need: (1) game site for each tournament game, (2) campus location for each team, (3) distance calculation
- Game sites require manual compilation or scraping from Sports Reference/Wikipedia
- Campus locations: one-time geocoding of ~350 schools

**Historical availability:**
- Complete: 2002–present (game sites are well-documented)
- Partial: 1985–2002

**Feature engineering:**
- `travel_distance_diff` = favorite_distance - underdog_distance (positive = underdog is closer)
- `underdog_is_local` = 1 if underdog is within 200 miles
- `favorite_travel_distance` alone (long-distance favorites = upset risk)
- `distance_diff × round_1_or_2` (only matters in early rounds)

---

### 3.2 — Regular Season Momentum (Last 10 Games)

**What:** Win-loss record, point differential, and/or efficiency metrics over the final 10 regular-season and conference tournament games.

**Why it predicts upsets:** Teams are not static. A team that went 28-3 but lost 3 of their last 5 is a VERY different animal than a team that won their last 12. Injuries, fatigue, chemistry issues, defensive slumps — these all show up in late-season performance.

The committee seeds based on the full body of work, but the last 10 games tell you more about the **current team** than games from November. A fading favorite is ripe for an upset.

**Expected predictive power:** ⭐⭐ **MEDIUM**
- Captures recency effects that season-long metrics miss
- Partially redundant with KenPom (which weights recent games somewhat) but the explicit momentum signal could help
- Estimated AUC lift: +0.3–0.8%

**Data source:**
- **Sports Reference game logs:**
  - `https://www.sports-reference.com/cbb/schools/duke/2024-schedule.html` — full game-by-game results
  - Scrape last 10 games for each tournament team
- **Barttorvik:** Has game-by-game data accessible per team
- **ESPN game logs:** `https://www.espn.com/mens-college-basketball/team/schedule/_/id/{team_id}/season/2024`

**Acquisition difficulty:** ⭐⭐⭐ **MEDIUM**
- Need game-by-game results for ~68 teams × 15 years = ~1,000 team-seasons
- Each requires scraping a schedule page and computing last-10 metrics
- Doable but non-trivial scraping volume

**Historical availability:** 2002–present (Sports Reference), 2008–present (Barttorvik)

**Feature engineering:**
- `last10_win_pct_diff` = underdog_last10_win_pct - favorite_last10_win_pct
- `favorite_last10_losses` (raw count of recent losses — fading favorites)
- `momentum_direction_diff` (last 10 win% minus season win% — captures trend)

---

### 3.3 — Conference Tournament Performance

**What:** How each team performed in their conference tournament immediately before the NCAA tournament.

**Why it predicts upsets:** Conference tournaments are the **dress rehearsal** for March Madness. Teams that won their conference tournament (especially by beating good teams) have momentum, confidence, and recent high-pressure game experience. Teams that got bounced in the first round of their conference tournament may be limping in.

For mid-majors: winning the conference tournament is often how they GET IN — so they arrive hot. For power conference teams: an early conference tournament exit might signal problems.

**Expected predictive power:** ⭐⭐ **MEDIUM**
- Captures short-term form and psychological state
- Somewhat redundant with momentum features
- Estimated AUC lift: +0.2–0.5%

**Data source:**
- **Sports Reference:** Conference tournament brackets and results
  - `https://www.sports-reference.com/cbb/postseason/` — lists all conference tournament results
- **Wikipedia:** Each conference tournament has a dedicated page per year
- **ESPN bracket pages:** Conference tournament brackets

**Acquisition difficulty:** ⭐⭐⭐ **MEDIUM-HARD**
- Need to compile conference tournament results across 30+ conferences × 15 years
- Data is available but scattered — no single table

**Historical availability:** 2002–present

**Feature engineering:**
- `underdog_conf_tourney_champ` = 1 if underdog won their conference tournament
- `favorite_conf_tourney_early_exit` = 1 if favorite lost in first 2 rounds of conf tournament
- `conf_tourney_games_played_diff` (more games played = hotter but possibly more fatigued)

---

### 3.4 — Effective Field Goal Percentage (eFG%)

**What:** Field goal percentage adjusted for the extra value of 3-pointers. eFG% = (FG + 0.5 × 3P) / FGA.

**Why it predicts upsets:** eFG% is the **most important of the Four Factors** (shooting, turnovers, rebounding, free throws). While our adj_o already captures overall offensive efficiency, eFG% isolates pure shooting quality from turnover rate and offensive rebounding. A team with high eFG% but high turnover rate is a different profile than a team with moderate eFG% but pristine ball-handling.

**Expected predictive power:** ⭐⭐ **MEDIUM**
- Partially captured by adj_o_diff, but the decomposition into Four Factors components provides more granular information
- Estimated AUC lift: +0.2–0.5%

**Data source:** Same as other Four Factors — KenPom, Barttorvik, Sports Reference

**Acquisition difficulty:** ⭐ **EASY** — Same scraping pipeline

**Historical availability:** 2002–present

**Feature engineering:**
- `efg_diff` = underdog_eFG% - favorite_eFG%
- `defensive_efg_diff` (opponent eFG% allowed)

---

## TIER 4: LOWER PRIORITY (Speculative or Hard to Acquire)

These are features with theoretical appeal but either hard to get, questionable marginal value, or at risk of overfitting.

---

### 4.1 — Defensive Style (Zone vs. Man, Press vs. Halfcourt)

**What:** Whether a team primarily plays man-to-man, zone, or a mixture; whether they press full-court or play halfcourt defense.

**Why it predicts upsets:** Unusual defenses can **disrupt preparation**. Syracuse's 2-3 zone has historically given tournament opponents fits because teams rarely face a full-game zone during the regular season. Similarly, full-court pressing teams (VCU's "Havoc") create chaos that more talented teams sometimes can't handle with limited prep time.

**Expected predictive power:** ⭐ **LOW-MEDIUM**
- Strong in specific cases (Syracuse, VCU) but hard to quantify broadly
- Very few teams play primary zone — sample size issue
- Estimated AUC lift: +0.1–0.4%

**Data source:**
- **Synergy Sports / InStat:** Has play-type data but requires paid subscription and is not historically archived
- **Hoop-Math.com:** `https://hoop-math.com/` — has some shooting type data (at-rim, mid-range, 3pt) which proxies style
  - Goes back to ~2013
- **Manual classification:** Basketball analysts (Bart Torvik, KenPom) sometimes publish defensive style classifications, but not systematically
- **Proxy approach:** High steal rate + high TO% forced = pressing team. Low adj_t = halfcourt-oriented.

**Acquisition difficulty:** ⭐⭐⭐⭐ **HARD**
- No clean historical dataset of defensive style classifications
- Would need to either manually classify or use proxies (steal rate, block rate, opponent 3PAr)

**Historical availability:** Limited. Proxies: 2002+. Direct style data: ~2013+

### 4.2 — Injury Impact

**What:** Whether key players are injured, limited, or suspended for tournament games.

**Why it predicts upsets:** Injuries are the **single biggest source of unpriced information** in betting markets — and even the market doesn't get injuries right. A 1-seed missing their best player is a completely different team. But we're building a pre-tournament model, so we'd need to capture injury status right before the tournament.

**Expected predictive power:** ⭐⭐⭐ **HIGH** (but nearly impossible to systematically capture historically)

**Data source:**
- **No reliable historical injury database** for college basketball
- DonBest injury reports, ESPN injury reports, team beat reporters — all ephemeral
- **Would require manual compilation** per game, per year

**Acquisition difficulty:** ⭐⭐⭐⭐⭐ **VERY HARD**
- Retrospective injury data for 800+ games would require reading game previews for each
- Not feasible for historical model training
- **Possible for live prediction** (check injury reports before current tournament)

**Historical availability:** Essentially unavailable in structured form

**Recommendation:** Skip for model training. Use for manual adjustments during live prediction only.

### 4.3 — Days Rest Between Games

**What:** Number of days between a team's previous game and their tournament game (relevant for rounds 2+).

**Why it predicts upsets:** Fatigue matters, especially for teams that went deep in their conference tournament. A team that played a conference tournament final on Sunday and then plays Thursday has less rest than a team that got a first-round bye. In later tournament rounds, the team that played a grueling overtime game vs. the team that won by 20 has different energy levels.

**Expected predictive power:** ⭐ **LOW-MEDIUM**
- Only applies to rounds 2+ within the tournament (everyone has similar rest for Round 1)
- Conference tournament fatigue could matter for Round 1
- Estimated AUC lift: +0.1–0.3%

**Data source:**
- **Derivable from game dates** — Sports Reference has all game dates
- For rounds 2+: the tournament schedule is fixed and public
- For conf tournament fatigue: need conf tournament dates (available from Sports Reference)

**Acquisition difficulty:** ⭐⭐ **EASY-MEDIUM**

**Historical availability:** Complete

### 4.4 — Brand Name / Blue Blood Factor

**What:** Whether a team is a traditional basketball power (Kansas, Duke, Kentucky, North Carolina, UCLA, etc.).

**Why it predicts upsets:** There are two competing effects: (1) Blue bloods may get favorable seeds from the committee, making them appear safer picks — but if they're *overseeded* relative to their actual quality, they're upset targets. (2) Blue bloods may have intangible advantages (recruiting pipeline, coach experience, media intimidation) that make them *harder* to upset.

**Expected predictive power:** ⭐ **LOW**
- Most of the "blue blood effect" is already captured by coaching experience and KenPom quality
- The residual is likely noise
- Estimated AUC lift: +0.0–0.2%

**Data source:**
- **Trivial:** Hardcode a list of ~15 blue blood programs

**Acquisition difficulty:** ⭐ **EASY** — One lookup table

**Recommendation:** Low priority. If we add coaching experience, this becomes redundant.

---

## PRIORITIZED IMPLEMENTATION PLAN

### Phase 1: Quick Wins (Week 1)
*Expected combined AUC lift: +2.5–4.5%*

| # | Feature | Expected Lift | Effort | Source |
|---|---------|--------------|--------|--------|
| 1 | **KenPom Luck** | +1.5–3.0% | ⭐ Easy | Already in our scraping pipeline |
| 2 | **Tempo Mismatch Features** | +0.2–0.6% | ⭐ Easy | Feature engineering on existing adj_t data |
| 3 | **Seed vs. KenPom Rank Residual** | +0.3–0.8% | ⭐ Easy | Derivable from existing data |

These three require **zero new data acquisition**. Luck is one extra column from our existing KenPom scraper. Tempo mismatch and seed-rank residual are pure feature engineering. Do these FIRST.

### Phase 2: Four Factors Expansion (Week 2)
*Expected additional AUC lift: +1.5–3.0%*

| # | Feature | Expected Lift | Effort | Source |
|---|---------|--------------|--------|--------|
| 4 | **3-Point Rate (3PAr)** | +1.0–2.0% | ⭐⭐ Easy-Med | KenPom Four Factors pages or Barttorvik |
| 5 | **Free Throw %** | +0.5–1.5% | ⭐ Easy | Same scraping run as 3PAr |
| 6 | **Turnover Rate** | +0.5–1.0% | ⭐ Easy | Same scraping run |
| 7 | **Offensive Rebound Rate** | +0.3–0.8% | ⭐ Easy | Same scraping run |

All four come from the **same KenPom Four Factors page** (or Barttorvik). One scraper, four features. The Four Factors decompose our existing adj_o and adj_d into their components, giving the model more granular information about *how* teams score and defend.

**Barttorvik scraping recommendation:**
- Primary URL: `https://barttorvik.com/trank.php?year={year}&sort=&top=0&conlimit=All`
- Free, no login, clean HTML table
- Includes: eFG%, TO%, OR%, FTRate, and their defensive equivalents
- Goes back to 2008 — covers our 2011–2025 training window

### Phase 3: External Data Integration (Weeks 3–4)
*Expected additional AUC lift: +1.5–3.0%*

| # | Feature | Expected Lift | Effort | Source |
|---|---------|--------------|--------|--------|
| 8 | **Vegas Point Spread** | +1.0–2.5% | ⭐⭐⭐ Medium-Hard | Covers.com, Kaggle datasets |
| 9 | **Coach Tournament Experience** | +0.5–1.5% | ⭐⭐⭐ Medium | Sports Reference coach pages |
| 10 | **Experience / Roster Continuity** | +0.5–1.5% | ⭐⭐ Medium | Barttorvik |

These require new data sources but offer substantial orthogonal information.

### Phase 4: Situational Features (If AUC Still Improving)
*Expected additional AUC lift: +0.5–1.5%*

| # | Feature | Expected Lift | Effort | Source |
|---|---------|--------------|--------|--------|
| 11 | **Geographic Proximity** | +0.3–0.8% | ⭐⭐⭐ Medium | Sports Reference + geocoding |
| 12 | **Momentum (Last 10 games)** | +0.3–0.8% | ⭐⭐⭐ Medium | Sports Reference game logs |
| 13 | **Conf Tournament Results** | +0.2–0.5% | ⭐⭐⭐ Medium-Hard | Sports Reference |

**STOP HERE. Do not add more features.** With 800 games, we'll be at ~20 features after Phase 4, which is our practical ceiling. Any more and we're fitting noise.

---

## REALISTIC AUC TARGETS

| Stage | Total Features | Expected AUC | Notes |
|-------|---------------|-------------|-------|
| Current | 9 | 0.733 | Baseline ensemble |
| After Phase 1 | 12–13 | 0.750–0.770 | Quick wins, zero new data |
| After Phase 2 | 16–18 | 0.770–0.800 | Four Factors decomposition |
| After Phase 3 | 19–21 | 0.790–0.820 | External data integration |
| After Phase 4 | 22–25 | 0.800–0.830 | Situational — diminishing returns |

**Realistic ceiling with 800 games: AUC ~0.82–0.84.** Beyond that, we need more training data (more years) or fundamentally different modeling approaches (game-level simulations, player-based models).

---

## CRITICAL REMINDERS

1. **Validate after EACH phase** with nested 5-fold CV. If AUC doesn't improve, don't add more features.
2. **Use L1 regularization** (Lasso) to automatically handle feature selection.
3. **Watch for multicollinearity:** Four Factors components are correlated with adj_o/adj_d. Consider replacing adj_o/adj_d with Four Factors components rather than adding both.
4. **The Luck feature alone might give us half the total possible improvement.** Test it first, in isolation.
5. **Vegas spread might cannibalize adj_em_diff.** Test both: (a) adding spread alongside adj_em, (b) replacing adj_em with spread. The market may be a better single feature.
6. **Feature interactions matter more than feature count.** A few well-chosen interactions (luck × seed_diff, 3PAr × round) may outperform adding 5 weak main effects.

---

## DATA SOURCE SUMMARY

| Source | URL | What We Get | Historical Range | Difficulty |
|--------|-----|-------------|-----------------|------------|
| KenPom (archive.org) | `web.archive.org/web/*/kenpom.com` | Luck, all efficiency metrics | 2002–present | Easy (already scraping) |
| KenPom Four Factors (archive.org) | `web.archive.org/web/*/kenpom.com/stats.php?s=*` | eFG%, TO%, OR%, FTRate | 2002–present | Easy |
| Barttorvik | `barttorvik.com/trank.php?year={year}` | Four Factors, experience, continuity | 2008–present | Easy (free, clean tables) |
| Sports Reference | `sports-reference.com/cbb/` | Game logs, coaches, schedules, locations | 1993–present | Medium (volume) |
| Covers.com | `covers.com/ncaab/matchups` | Vegas spreads, ATS results | ~2005–present | Medium-Hard |
| Kaggle datasets | `kaggle.com/datasets` (search NCAA) | Compiled spreads, results, some features | Varies | Easy (pre-compiled) |
| Hoop-Math | `hoop-math.com` | Shot type distribution | 2013–present | Medium |
| NCAA.com | `ncaa.com/brackets/basketball-men/d1` | Bracket history, game sites | 2000–present | Medium |

---

*"It's upset time, baby! And the teams that get upset are the ones with LUCKY records, SHAKY free throws, and a FIRST-TIME coach who's never been to the Big Dance. That's a DIAPER DANDY waiting to get knocked off!"*

— Dickie V
