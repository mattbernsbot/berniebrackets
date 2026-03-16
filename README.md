# March Madness Bracket Optimizer

A Python system that generates NCAA March Madness brackets optimized to **finish 1st in a pool**, not merely to be "most likely correct."

## Overview

Unlike traditional bracket predictors that maximize expected accuracy, this optimizer uses a **contrarian strategy**: it identifies high-value picks that the public undervalues, then exploits those edges via Monte Carlo simulation to maximize the probability of winning your pool.

### The Strategy

1. **Scout**: Scrape team statistics from KenPom and bracket data from ESPN
2. **Sharp**: Build a statistical model converting team stats to win probabilities
3. **Contrarian**: Estimate public ownership and calculate leverage scores
4. **Optimizer**: Run Monte Carlo simulations to find brackets that maximize P(1st place)
5. **Analyst**: Generate human-readable analysis and recommendations

## Key Features

- **Contrarian picks**: Finds teams the public undervalues relative to their true win probability
- **Pool-size aware**: Adjusts risk tolerance based on pool size (10 vs 100 people requires different strategies)
- **Monte Carlo simulation**: 10,000+ tournament simulations to estimate win probability
- **Multiple strategies**: Generates conservative, balanced, and aggressive bracket options
- **Full transparency**: Explains every pick with leverage scores and confidence tiers

## Installation

### Requirements

- Python 3.10+
- beautifulsoup4 (already installed)
- pytest (already installed)

No additional dependencies needed! Uses only Python standard library plus BeautifulSoup.

### Setup

```bash
cd bracket-optimizer
```

That's it. The system is ready to run.

## Quick Start

### Run the Complete Pipeline

```bash
python3 main.py full
```

This will:
1. Collect data from KenPom and ESPN (or use mock data if unavailable)
2. Build the statistical model
3. Calculate ownership and leverage
4. Run Monte Carlo optimization
5. Generate analysis reports

Results will be in `output/`:
- `analysis.md` - Full bracket analysis with explanations
- `bracket.txt` - ASCII bracket visualization
- `summary.json` - Machine-readable results

### Custom Pool Size

```bash
python3 main.py full --pool-size 50 --risk aggressive
```

### Use Local Data Files

If you've downloaded HTML files manually:

```bash
python3 main.py collect --kenpom-file kenpom.html --espn-bracket-file bracket.html
```

## Usage

### Commands

- `collect` - Scrape data from web (or load from local files)
- `analyze` - Run model and optimization on existing data
- `bracket` - Generate output reports from optimized brackets
- `full` - Run entire pipeline (collect → analyze → bracket)

### Global Options

```
--pool-size INT      Pool size (default: 25)
--sims INT           Number of Monte Carlo simulations (default: 10000)
--risk PROFILE       conservative|balanced|aggressive|auto
--config PATH        Path to config.json
--verbose, -v        Enable debug logging
--seed INT           Random seed for reproducibility
```

### Examples

**Conservative bracket for small pool:**
```bash
python3 main.py full --pool-size 10 --risk conservative
```

**Aggressive bracket for large pool:**
```bash
python3 main.py full --pool-size 200 --risk aggressive
```

**Fast test run:**
```bash
python3 main.py full --sims 1000 --verbose
```

**Reproducible results:**
```bash
python3 main.py full --seed 42
```

## Configuration

Edit `config.json` to customize defaults:

```json
{
  "pool_size": 25,
  "scoring": [10, 20, 40, 80, 160, 320],
  "sim_count": 10000,
  "risk_profile": "auto",
  "champion_min_leverage": 1.5,
  "min_contrarian_ff": 1,
  "max_r1_upsets": 3
}
```

### Risk Profiles

- **conservative**: Favor chalk, min upsets, champion must have 1.2x+ leverage
- **balanced** (default for 25-person pools): Mix of chalk and value picks
- **aggressive**: Maximum differentiation, champion must have 2.0x+ leverage
- **auto**: Automatically selects based on pool size

## Understanding the Output

### Analysis Report (`output/analysis.md`)

The report includes:

1. **Executive Summary**
   - Champion pick
   - Final Four and Elite Eight
   - P(1st place), P(Top 3), Expected finish

2. **Key Differentiators**
   - High-leverage picks that separate your bracket from the field
   - Leverage scores show value (model prob / public ownership)

3. **Round-by-Round Breakdown**
   - Every pick with confidence tier
   - Upsets highlighted

4. **Risk Assessment**
   - What needs to go right
   - Biggest vulnerabilities

### Confidence Tiers

- 🔒 **Lock**: Win probability ≥ 75% (chalk pick, very safe)
- 👍 **Lean**: Win probability 55-75% (model-favored, some risk)
- 🎲 **Gamble**: Win probability < 55% (true upset, high leverage)

### Leverage Scores

Leverage = Model Probability / Public Ownership

- **Leverage > 2.0**: Extreme value pick (model loves it, public ignores it)
- **Leverage 1.5-2.0**: Good value pick
- **Leverage 1.0-1.5**: Slight edge
- **Leverage < 1.0**: Public overvalues this pick (avoid)

## The Statistical Model

### Core Formula

Win probability based on **KenPom Adjusted Efficiency Margin (AdjEM)**:

```
P(A wins) = 1 / (1 + 10^(-ΔEM / 11.5))
```

Where ΔEM = AdjEM_A - AdjEM_B

### Modifiers

1. **Tournament Experience** (+0.02 per Sweet 16+ appearance in last 3 years)
2. **Tempo Mismatch** (+0.03 for slow defensive teams in tournament context)
3. **Conference Momentum** (+0.015 for power conference auto-bid teams)
4. **Seed Prior Blending** (75% model, 25% historical seed matchup data)

### Why This Works

Traditional models maximize **expected correctness**. But in a pool, finishing 2nd with a "good" bracket earns nothing. You need to **win**.

This optimizer:
- Identifies where the public is wrong
- Takes calculated risks on high-leverage picks
- Balances differentiation with probability
- Optimizes for **P(1st place)**, not expected score

## Testing

Run the full test suite:

```bash
python3 -m pytest tests/ -v
```

### Critical Tests

The **bracket integrity tests** (`test_bracket_integrity.py`) enforce single-elimination rules:
- Lose once = out (no team appears after losing)
- Every advancement requires winning all prior games
- Exactly 1 champion
- 63 games total
- Each region produces exactly 1 Final Four team

These tests ensure all generated brackets are structurally valid.

## Architecture

### Module Pipeline

```
Scout → Sharp → Contrarian → Optimizer → Analyst
```

### Data Flow

```
KenPom/ESPN → teams.json, bracket_structure.json
              ↓
           matchup_probabilities.json
              ↓
           ownership.json
              ↓
      Monte Carlo simulation
              ↓
      optimal_brackets.json
              ↓
     analysis.md, bracket.txt
```

### File Structure

```
bracket-optimizer/
├── main.py                  # CLI entry point
├── config.json              # Configuration
├── src/
│   ├── models.py            # Data models
│   ├── constants.py         # Historical data
│   ├── utils.py             # HTTP, JSON, logging
│   ├── config.py            # Config loading
│   ├── scout.py             # Data collection
│   ├── sharp.py             # Statistical model
│   ├── contrarian.py        # Ownership analysis
│   ├── optimizer.py         # Monte Carlo engine
│   └── analyst.py           # Output generation
├── tests/
│   ├── test_models.py
│   ├── test_sharp.py
│   ├── test_contrarian.py
│   ├── test_optimizer.py
│   ├── test_bracket_integrity.py  # CRITICAL
│   └── test_integration.py
├── data/                    # Intermediate JSON (gitignored)
└── output/                  # Final results (gitignored)
```

## Performance

For 10,000 simulations with a 25-person pool:
- ~33 million operations
- **< 30 seconds** on modern hardware (pure Python)
- With perturbation search (3 strategies + 5 variants): **~2-4 minutes**

To speed up:
- Use `--sims 5000` (minimal accuracy loss)
- Use `--sims 1000` for quick testing

## Troubleshooting

### "No module named src"

Make sure you're in the `bracket-optimizer/` directory when running commands.

### Scraping Fails

Use local HTML files:
```bash
python3 main.py collect --kenpom-file path/to/kenpom.html
```

Or the system will fall back to mock data for testing.

### Tests Fail

Run with verbose output:
```bash
python3 -m pytest tests/ -v --tb=short
```

### Simulations Too Slow

Reduce sim count:
```bash
python3 main.py full --sims 1000
```

## Advanced Usage

### Custom Scoring System

Some pools use non-standard scoring. Edit `config.json`:

```json
{
  "scoring": [10, 20, 40, 80, 160, 320]
}
```

Standard ESPN: `[10, 20, 40, 80, 160, 320]`

### Batch Analysis

Test multiple pool sizes:

```bash
for size in 10 25 50 100; do
  python3 main.py full --pool-size $size --seed 42
  mv output output_$size
done
```

### Reproducible Research

Always use the same seed for comparisons:

```bash
python3 main.py full --seed 2026
```

## Limitations

1. **Simplified ESPN Scraping**: The current ESPN bracket scraper uses mock data. For production use, you'd need to implement actual HTML parsing for the current year's bracket.

2. **No Live Tournament Updates**: This is a pre-tournament optimizer. It doesn't adjust during the tournament.

3. **Public Ownership Estimation**: Without access to live ESPN Tournament Challenge data, ownership is estimated from historical seed-based curves. This is surprisingly accurate but not perfect.

4. **Single Strategy per Run**: The optimizer evaluates 3 strategies, but you must choose one. It doesn't hedge by submitting multiple brackets.

## Future Enhancements

- Real-time ESPN bracket parsing
- Live ESPN Tournament Challenge pick data integration
- Injuries and recent performance adjustments
- Multi-bracket optimization (for pools allowing multiple entries)
- Web UI for bracket visualization
- Historical back-testing against past tournaments

## Credits

Based on research into:
- KenPom's adjusted efficiency metrics
- Historical NCAA tournament upset patterns
- Game theory optimal tournament pool strategy
- ESPN Tournament Challenge public pick distribution analysis

## License

MIT License - See PLAN.md for full implementation specification.

---

**Built for serious bracket pool competitors who want to win, not just participate.**

