# CRITIQUE — Bracket Optimizer System
### By Dickie V, Baby! 🏀

**Date:** March 15, 2026  
**Requested by:** The CTO  
**System Version:** Iteration 3, post-amendment  
**Simulation Run:** 2,000 sims, 25-person pool, ESPN standard scoring

---

## The Verdict Up Front

I'm going to be straight with you, baby. You hired me to tell you the truth, and here it is: **this system, as it runs right now, would lose you the pool.** Not just "probably won't win" — it is actively performing WORSE than random chance. Every single bracket it produces has a lower P(1st) than the 4% you'd get by throwing darts at the bracket while blindfolded.

Your "optimal" bracket: **2.5% P(1st).** Your safe alternate: **2.15%.** Your aggressive alternate: **2.0%.** Random chance in a 25-person pool is **4.0%.** You have built a machine that is mathematically worse than no machine at all.

But here's the thing — and this is why I'm not just walking out the door — the BONES are here. The statistical model in `sharp.py` is actually pretty good. The constants are solid. The conceptual framework is sound. The problem is the optimizer doesn't use any of it correctly. It's like having a Ferrari engine bolted to a shopping cart frame.

Let me break this down.

---

## 1. Does This System Actually Give an Edge in a 25-Person Pool?

**No. It gives you a DISADVANTAGE.**

The numbers don't lie:
- Optimal bracket: 2.5% P(1st), expected finish 9.3 out of 25
- Safe alternate: 2.15% P(1st), expected finish 7.6
- Aggressive alternate: 2.0% P(1st), expected finish 7.7

Your frat brother who picks Duke to win it all, fills in mostly chalk, throws in a couple 12-over-5 upsets because "it always happens," and calls it a day? He has a better bracket than your optimizer produces. That's not an exaggeration. That is a mathematical fact based on your own system's Monte Carlo numbers.

**Why?** Three compounding failures:

**A) The system doesn't pick the best team to win.** Duke has an AdjEM of +39.18. That's DOMINANT. That's historically elite. The system picks Houston (2.5% bracket) and Michigan (the other two). It literally never considers Duke as champion because Duke is a 1-seed and the aggressive strategy is constrained to seeds 2-6 only. The conservative allows 1-2 seeds, but the champion selection uses a `title_prob * leverage` formula that deprioritizes the most-likely champion because the public also likes them. This is the cardinal sin of pool strategy.

**B) The system picks too many garbage upsets.** 12 first-round upsets in the optimal bracket. Twelve! Including TWO 13-over-4 upsets (New Mexico over St. John's AND South Florida over Tennessee). Historically, one 13-over-4 happens per tournament on average. TWO in the same bracket is a ~5% probability event. Each wrong upset costs you 10 points AND cascading points in later rounds. You're paying a massive expected value penalty for "differentiation" that rarely materializes.

**C) The P(1st) numbers themselves are corrupted.** The review identified an off-by-one bug where championship picks in opponent brackets look up round 7 ownership (which doesn't exist) and default to 0.5. This means your simulated opponents are picking champions essentially randomly — making it EASIER to beat them. In reality, ~50% of a 25-person pool will pick a 1-seed champion. Your actual P(1st) against real opponents is worse than what's reported.

---

## 2. Is the Champion Selection Logic Right?

**It is catastrophically wrong for this specific year.**

Let me give you the sharp's perspective on champion selection in a 25-person pool:

**When to pick the chalk champion (Duke this year):**
- When the #1 team is clearly separated from the field (Duke's AdjEM +39.18 is ~1 point above Michigan's +38.38 and ~2 points above Arizona's +37.56)
- When the pool is small (25 people = only ~6 other Duke brackets to compete with)
- When the point multiplier for the championship (320 points!) dwarfs the differentiation value of being contrarian

**When to go contrarian on champion:**
- When there are 2-3 teams bunched at the top with similar odds (2019: Virginia/Duke/Gonzaga/UNC all legitimate)
- When the pool is LARGE (100+ people, where 25+ opponents also have the chalk champion)
- When you have specific information that the favorite is vulnerable (injury, bad matchup in their bracket region, etc.)

**The math on Duke as champion for THIS pool:**

Duke public ownership is approximately 25-32% (1-seed with brand-name boost). In a 25-person pool, that means ~6-8 people will also pick Duke. If Duke wins, you're competing with those 6-8 for first, and your edge comes from differentiation in the earlier rounds. P(winning the pool | Duke wins and you picked Duke) ≈ 1/7 = 14%.

If you pick Houston as champion (let's say ~8-11% public ownership), maybe 2 people in the pool have Houston. If Houston wins, P(winning | Houston wins and you picked them) ≈ 1/3 = 33%. BUT Houston's probability of actually winning the tournament is dramatically lower than Duke's. 

Expected value calculation (simplified):
- Duke champion bracket: P(Duke wins) × P(1st | Duke wins) = ~28% × ~14% = **3.9%**
- Houston champion bracket: P(Houston wins) × P(1st | Houston wins) = ~8% × ~33% = **2.6%**

Duke is the correct champion pick for a 25-person pool. PERIOD. The leverage formula isn't wrong in principle, but it's being applied without regard to the absolute magnitude of title probability. A team needs to clear a minimum title-probability threshold before leverage should even factor in.

**Here's the kicker:** your system has Duke in the Final Four in every bracket. It KNOWS Duke is elite. It just refuses to pull the trigger on Duke as champion because the `STRATEGY_CHAMPION_SEEDS` constraint for the aggressive bracket is `[2, 3, 4, 5, 6]` — it literally excludes 1-seeds! And for conservative/balanced, the leverage calculation deprioritizes Duke because the public likes them. This is the system outsmarting itself.

**My recommendation:** For a 25-person pool, your "conservative" and "balanced" brackets should BOTH have Duke as champion. Only your aggressive bracket should try a non-Duke champion, and that champion should be a legitimate 1 or 2 seed — Michigan, Arizona, or Houston — not a 4-seed from the American Athletic Conference.

---

## 3. Are the Upset Picks Smart or Random?

**They are leverage-chasing garbage picks with no basketball intelligence behind them.**

Let me audit the 12 R1 upsets in the "optimal" bracket:

| Pick | Seed Matchup | Verdict |
|------|-------------|---------|
| Villanova (9) over Georgia (8) | 8/9 | Fine — coin flip, not really an upset |
| New Mexico (13) over St. John's (4) | 4/13 | **TERRIBLE** — this is a leverage chase, not a basketball pick |
| Saint Louis (11) over Saint Mary's (6) | 6/11 | Questionable without checking their actual AdjEM gap |
| San Diego St. (12) over Arkansas (5) | 5/12 | **Maybe OK** — need to verify SDSU's actual metrics |
| South Florida (13) over Tennessee (4) | 4/13 | **TERRIBLE** — two 13-over-4 upsets?? |
| SMU (11) over BYU (6) | 6/11 | Could be defensible, need to check stats |
| VCU (12) over Louisville (5) | 5/12 | Classic 12/5 territory, could be fine |
| TCU (11) over Wisconsin (6) | 6/11 | THREE 11-over-6 upsets is too many |
| Auburn (10) over UCLA (7) | 7/10 | Could be defensible |
| Clemson (9) over North Carolina (8) | 8/9 | Fine — near coin flip |
| Indiana (12) over Texas Tech (5) | 5/12 | THREE 12-over-5 upsets is ambitious |
| Texas (10) over Kentucky (7) | 7/10 | Could be defensible |

**The problems:**

1. **Three 11-over-6 upsets.** Historical average is 1.5 per tournament. Picking three is aggressive even for the aggressive bracket. And these aren't carefully selected — they're whatever had the highest leverage score.

2. **Two 13-over-4 upsets.** Historical average is 0.83 per tournament. TWO is a low-probability parlay. If either of these teams is even remotely mediocre by KenPom, this is pure madness.

3. **Three 12-over-5 upsets.** This happens ~13% of the time historically. You're betting on a rare outcome.

4. **No rationale beyond leverage.** The system doesn't check: Is South Florida actually a good team that's under-seeded? Or are they a middling mid-major that won their conference tournament? The "Upset Propensity Score" exists in `sharp.py` but the review confirms the optimizer doesn't use it for individual upset selection. It's baked into the matchup matrix, which means every 12-seed gets the same generic UPS treatment. A 12-seed that's #30 in KenPom (genuinely dangerous) gets treated the same as a 12-seed that's #80 (no shot).

5. **Zero upset advancement.** Not a single upset winner is advanced past R1. The system picks San Diego St. to beat Arkansas, then immediately loses to South Florida in R2. What? If you believe in San Diego St. enough to pick them as a 12/5 upset, you should at least consider them against a 13-seed in R2. This is where the real pool differentiation lives — a 12-seed in the Sweet 16 is MASSIVELY contrarian. But the system can't see that because it fills upsets as a R1 afterthought.

**What a sharp would do:** Pick EXACTLY the right 1-2 twelve-over-five upsets, maybe advance one to the Sweet 16. Pick ONE eleven-over-six. Maybe one 13-over-4 IF the 13-seed's KenPom numbers scream "under-seeded." Leave the 14+ seeds alone in a 25-person pool. Total: 7-9 R1 upsets, 2-3 of which are coin-flip 8/9 games that don't even count as real upsets.

---

## 4. Is the Monte Carlo Simulation Trustworthy?

**No. The P(1st) numbers are unreliable for three specific reasons.**

**A) The off-by-one bug corrupts opponent brackets.**

The code review identified that `generate_public_bracket()` looks up `round_ownership.get(round_num + 1, default)`. For the championship game (round 6), this queries round 7, which doesn't exist. The fallback value makes all championship picks in opponent brackets essentially random. This means your simulated opponents aren't behaving like real pool participants. Real people in a 25-person pool converge heavily on 1-seed champions. Your simulation has opponents picking 7-seeds as champion with meaningful probability.

**B) 2,000 simulations is too few for reliable P(1st) estimates.**

At 2.5% P(1st), you're looking at ~50 first-place finishes out of 2,000 sims. The standard error is √(0.025 × 0.975 / 2000) ≈ 0.35%. So your 2.5% estimate could easily be anywhere from 1.8% to 3.2%. That's a ±30% error band. You can't meaningfully distinguish between brackets at this resolution. The PLAN says 10,000 sims — use 10,000.

**C) The matchup matrix is round-agnostic.**

`build_matchup_matrix()` calls `compute_matchup_probability(team_a, team_b)` without passing `round_num`. Everything defaults to round 1. This means the R1-specific seed prior blending weight (w=0.60, heavy historical weight) is applied to late-round matchups too. A 1-seed vs 3-seed matchup in the Elite Eight uses the same probability as if they met in the first round. The round-dependent blending that was carefully designed in the amendment (0.60 → 0.65 → 0.70 → 0.80) is completely unused for its intended purpose.

**What this means:** The simulation is internally consistent but doesn't represent reality well. The P(1st) numbers are directionally useful (you can compare brackets to each other) but the absolute values are unreliable. A 2.5% P(1st) in this simulation might be 4% or 1.5% against real opponents.

---

## 5. What's Missing?

Here's what a real sharp would add to this system, in order of importance:

**A) Path analysis for the champion.**

You don't just pick a champion — you pick a champion with a CLEAR PATH. Who is in Duke's region? If Duke has to go through Michigan (AdjEM +38.38) in the Elite Eight, that's a tough path. If their toughest matchup is Purdue (AdjEM +30.37), that's much easier. Path difficulty should be a first-class input to champion selection. The current system ignores it completely.

**B) Correlated upset picks.**

If you pick a 12-seed to beat a 5-seed, the 4-seed in that quarter of the bracket just got a MUCH easier R2 game. The system should recognize that picking an upset creates downstream value for the surviving higher seed. "If San Diego State beats Arkansas, then Tennessee has an easy R2" — this kind of thinking is completely absent.

**C) Actual ESPN bracket pick data.**

The system falls back to seed-based ownership estimates because it can't scrape ESPN pick data. But ESPN pick data IS the single most important input for a pool optimization strategy. Without it, your leverage calculations are based on generic historical averages, not what's happening THIS year with THIS year's teams. If you can get pick percentages — even approximate ones from Twitter polls or sports media — that's worth more than every fancy modifier in `sharp.py` combined.

**D) Conference tournament results and injury news.**

The system has no concept of what's happened in the last two weeks. Conference tournament champions, key injuries, hot streaks — this is the stuff that separates a sharp's March bracket from a December preseason projection. The system treats the bracket as a static snapshot of KenPom ratings.

**E) Matchup-specific analysis.**

Not all AdjEM gaps are created equal. A team with elite 3-point shooting has an inherent variance advantage in single-elimination — they can get hot and beat anyone, or go cold and lose to anyone. A team that wins through rebounding and defense has less variance. The system treats every +10 AdjEM team identically regardless of HOW they generate their margin. 

**F) The bracket the CTO actually asked for.**

The CTO specifically said: "Shouldn't almost every bracket show Duke?" He's right! The system ignores his basketball instinct, which is frankly better than the system's output.

---

## 6. What Would I Change RIGHT NOW?

If Selection Sunday is tomorrow and I need to make this system produce a usable bracket TODAY, here's my priority list:

### Fix #1: Force Duke as Champion (5 minutes)
Change `STRATEGY_CHAMPION_SEEDS` so conservative and balanced both include Duke (seed 1). Better yet, hardcode Duke as champion for conservative and balanced. Use Michigan or Houston for aggressive. This alone probably improves your P(1st) by 2+ percentage points.

### Fix #2: Kill the Bracket Inconsistency Bug (30 minutes)
The championship game says "Duke vs Arizona → Winner: Houston." **HOUSTON ISN'T IN THE GAME.** The system sets the champion before building the Final Four, then the FF build doesn't include the champion in its path. The championship slot gets overwritten with the pre-selected champion name regardless of who's actually playing. This means your bracket is INVALID. You can't submit a bracket where the champion didn't play in the championship game.

### Fix #3: Reduce R1 Upsets to 7-8 and Make Them Smart (1 hour)
Cap the conservative bracket at 5-6 upsets (2 coin-flips + 3 real upsets). Cap balanced at 7-8. Cap aggressive at 9-10. Remove the double-13 picks. Use KenPom AdjEM gap as the primary filter: only pick upsets where the AdjEM gap is < 8 points AND the underdog has a specific edge (slow defensive team, experienced coach, conference tournament champion).

### Fix #4: Fix the Off-by-One Bug in Opponent Bracket Generation (15 minutes)
Change the round 7 lookup to round 6 for the championship game in `generate_public_bracket()`. This makes your Monte Carlo results meaningful.

### Fix #5: Advance At Least One Upset Winner (30 minutes)
If you're bold enough to pick a 12-over-5 upset, pick a world where that 12-seed also beats the 4/13 winner in R2. One Sweet 16 Cinderella per bracket. This is where the pool-winning magic happens.

### Fix #6: Make the Three Brackets Actually Different (1 hour)
Right now, the "safe alternate" and "aggressive alternate" are NEARLY IDENTICAL BRACKETS. They share the same Final Four (Duke, Michigan, Arizona, Florida) and the same Elite Eight. The only differences are a handful of R1 picks. That's three entry fees for one bracket strategy. You're paying triple for the same bet.

The three brackets should be:
1. **Conservative:** Duke wins, all four 1-seeds in FF, 5-6 R1 upsets, maximize P(top 3)
2. **Balanced:** Duke wins, three 1-seeds + one 2/3-seed in FF (Houston or Vanderbilt), 7-8 R1 upsets with one Cinderella S16 run, maximize P(1st)
3. **Aggressive:** Michigan or Houston wins, two 1-seeds + two contrarian FF teams, 9-10 R1 upsets, go for the boom-or-bust win

### Fix #7: Bump Sims to 10,000 (0 minutes, just change the flag)
`--sims 10000`. It takes 3-4 minutes. Just do it.

---

## 7. System Grade

### Grade: D+

**Breakdown:**

| Component | Grade | Notes |
|-----------|-------|-------|
| Statistical model (sharp.py) | B+ | κ=13.0 is smart, UPS is well-designed, round-dependent blending is correct. Would be A- if the matchup matrix actually used round_num. |
| Constants & historical data | A- | Solid research, correct values, well-structured. |
| Contrarian/ownership model | C | Reasonable fallback estimates, but the leverage calculation dominates champion selection too aggressively. Without real ESPN pick data, the whole ownership model is educated guessing. |
| Optimizer (the actual brain) | F | Doesn't use the tools it's been given. Doesn't build top-down. Doesn't differentiate strategies. Produces invalid brackets. Has an off-by-one that corrupts Monte Carlo. The safe and aggressive alternates are near-clones. This module needs to be rewritten. |
| Output & analysis | C+ | Readable, shows the right information, but doesn't flag its own bugs (like the champion not being in the championship game). The "Key Differentiators" section has San Diego St. to R32 at 15.18x leverage — that number is nonsensical and should trigger a sanity check. |
| **Overall as a pool weapon** | **D+** | Would lose you money at the current output. Has the right conceptual framework and some genuinely good statistical work. But the optimizer is broken, and that's the only module that matters for bracket output. |

---

## The Bottom Line

You built a Ferrari engine (sharp.py), connected it to broken transmission (optimizer.py), and put bald tires on it (missing the actual ESPN bracket data). The car looks impressive on the showroom floor but it can't drive.

**Would I use this system's output to fill out a bracket today?** Absolutely not. I'd be better off picking Duke to win, filling in chalk, circling two 12/5 upsets that my gut tells me look right, and calling it a day. That's a 5-minute bracket that would outperform your computer's best effort.

**Could this system be good with the fixes above?** Yes, genuinely. The architecture is sound. The probability model is solid. The ownership concept is correct. Fix the optimizer, fix the champion logic, fix the bugs, and you'd have something that could legitimately push your P(1st) to 8-10% — double random chance. That's real edge.

But right now? It's not there, baby. IT'S NOT THERE.

—Dickie V 🏀

---

*P.S. — One more thing. The system generated its bracket from KenPom rankings because ESPN Bracketology returned a 404. That means the seedings and regions are auto-generated, not the actual NCAA selections. If you're running this for real brackets, you need the actual bracket — everything downstream of fake seedings is meaningless. Get the real bracket from ESPN or enter it manually once Selection Sunday announces it.*
