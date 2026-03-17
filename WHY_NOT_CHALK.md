# Why BERNS_CHALK Doesn't Win Every Time

**BERNS_CHALK maximizes a different objective than winning the pool.**

BERNS_CHALK always picks the team with the highest model win probability in every matchup. This maximizes **expected correct picks** — i.e., it's the most *accurate* bracket. But winning a pool requires maximizing **P(your score > everyone else's score)**. These are fundamentally different objectives.

---

## The Core Problem: You Score Relative to the Field

When BERNS_CHALK picks Duke as champion (say, 35% win probability), and Duke wins — **so do the 55% of pool entrants who also picked Duke**. You score 320 points on the championship pick. So do they. Your relative gain is **zero**.

The only time BERNS_CHALK gains an advantage is when it's right and the field is wrong. But BERNS_CHALK is designed to agree with the field — it picks the most probable team in every game, and the most probable teams are exactly what the public picks.

---

## The Math of Pool Winning

For a champion pick in a 25-person pool:

| Strategy | Win Prob | Ownership | Happens... | When right: you beat... |
|---|---|---|---|---|
| BERNS_CHALK (Duke) | 35% | 55% → ~14 people | 35% of sims | only 11 others on title, must win everywhere else |
| Contrarian (Kansas) | 12% | 15% → ~4 people | 12% of sims | 21 people on title, much easier to finish 1st |

The contrarian path: **12% × P(beat 3 people on remaining picks)** can exceed **35% × P(beat 13 people on remaining picks)** — especially because those 13 BERNS_CHALK clones also agree on all the other favorites.

---

## The Variance Argument

BERNS_CHALK is a **low-variance strategy**. It scores consistently near the pool average — slightly above, because it's accurate. But "slightly above average" rarely wins a 25-person pool. You need a **spike** — a tournament path that goes right for you and wrong for most others.

The optimizer deliberately introduces **good variance**: upsets that are correlated with leapfrogging the most people at once. When a 4-seed Final Four pick hits, you don't just score 160 points — you score 160 points while ~75% of the field scores 0 on that slot.

---

## The Ownership Trap

Opponent brackets in the Monte Carlo are generated weighted by `title_ownership` and `round_ownership` from Yahoo public pick data. This means opponent brackets are **heavily correlated with each other and with BERNS_CHALK** — they all cluster around the same favorites.

In a simulation where 80% of the pool has the same Final Four, BERNS_CHALK is in that cluster. Everyone in the cluster rises and falls together. The bracket that picked a different Final Four team — and got it right — leapfrogs all of them at once.

---

## The Precise Formula

The optimizer computes EMV (Expected Marginal Value) for each potential upset:

```
EMV = P(upset) × ownership_gain − P(chalk) × ownership_cost
```

BERNS_CHALK ignores this entirely. It only considers `P(upset)`. The optimizer asks the additional question: *what does picking this team do to my position relative to the pool?*

---

## The Paradox

BERNS_CHALK will likely have the **highest expected score** and a solid **P(top 3)**. But P(1st place) is specifically about winning, not about being good. In any sufficiently large pool, the winner almost always got lucky on at least one high-leverage, low-ownership pick. BERNS_CHALK has zero such picks — it has no path to a big relative score spike.

**Analogy**: BERNS_CHALK is like a stock portfolio that perfectly tracks the index. You'll never dramatically underperform. But you'll also never outperform — because everyone else is also indexed. To beat the field, you need a concentrated position that the field doesn't have.

---

## Why More Simulations Don't Help BERNS_CHALK

More simulations converge to the true P(1st) — they just measure it more precisely. The true P(1st) for BERNS_CHALK is structurally limited regardless of sim count.

**Proof with a single-game example:**

Simplified pool: 1 game (championship), 10 people, 320 points.

- Team A: 80% win prob, 90% ownership (9 of 10 people pick A)
- Team B: 20% win prob, 10% ownership (1 of 10 people picks B)

**If you pick A (BERNS_CHALK):**
- A wins (80%): you and 8 opponents all have 320 pts → you win the tiebreak 1/9 of the time
- B wins (20%): you have 0, the one contrarian has 320 → you lose
- **P(1st) = 0.80 × (1/9) + 0.20 × 0 = 8.9%**

**If you pick B (contrarian):**
- A wins (80%): you have 0, everyone else has 320 → you lose
- B wins (20%): you and 1 opponent both have 320 → you win 1/2 of the time
- **P(1st) = 0.80 × 0 + 0.20 × (1/2) = 10.0%**

The 20% underdog has higher P(1st) than the 80% favorite. No amount of simulation changes this — it's a mathematical fact about the ownership distribution.

### The General Condition

Pick B over A when:

```
ownership_A / ownership_B  >  prob_A / prob_B
```

i.e., when the public's overconfidence ratio exceeds the true probability ratio. In the example: `90/10 = 9 > 80/20 = 4`. B wins.

This is exactly leverage: `prob_B / ownership_B = 20/10 = 2.0 > 1`. The public is undervaluing B relative to the model.

### What More Sims Actually Do

The Monte Carlo estimates a real quantity. With 3000 sims you might measure BERNS_CHALK's P(1st) as 8.7% ± 0.5%. With 100,000 sims you'd get 8.9% ± 0.1%. The true value is still 8.9% — and the optimizer's bracket is truly at 10%+ regardless of how precisely you measure either one.

More sims reduce **measurement noise**. They cannot change the underlying structure that BERNS_CHALK picks the same teams as most opponents, meaning it wins when they win and loses when they lose.

---

## Summary

| | BERNS_CHALK | Optimizer Output |
|---|---|---|
| Objective | Max expected correct picks | Max P(1st place) |
| Champion | Most likely to win | Best leverage vs. ownership |
| Upsets | None | EMV-positive only |
| Variance | Low | Targeted high |
| Expected score | Highest | Slightly lower |
| P(top 3) | High | Lower |
| P(1st place) | Lower | Higher |
