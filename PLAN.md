# Bracket Optimizer — Implementation Plan

## 1. Overview

The Bracket Optimizer is a Python system that generates an NCAA March Madness bracket optimized to **finish 1st in a 25-person pool**, not merely to be "most likely correct." It employs a contrarian strategy: finding high-value picks the public undervalues, then exploiting those edges via Monte Carlo simulation to maximize probability of winning.

The system has five modules that form a pipeline:

```
Scout (collect) → Sharp (model) → Contrarian (ownership) → Optimizer (simulate) → Analyst (output)
```

Data flows as JSON files through `data/`, final results land in `output/`.

---

## 2. Architecture

### 2.1 Module Dependency Graph

```
┌──────────┐     ┌──────────┐     ┌────────────┐
│  Scout   │────▶│  Sharp   │────▶│            │
│ (scrape) │     │ (model)  │     │  Optimizer │
└──────────┘     └──────────┘  ┌─▶│  (sim)     │
                               │  │            │
┌──────────┐     ┌────────────┐│  └─────┬──────┘
│  Scout   │────▶│ Contrarian ├┘        │
│ (scrape) │     │ (ownership)│         ▼
└──────────┘     └────────────┘   ┌──────────┐
                                  │  Analyst  │
                                  │ (output)  │
                                  └──────────┘
```

### 2.2 Data Flow

1. **Scout** scrapes KenPom team stats + ESPN bracket structure → writes `data/teams.json` and `data/bracket_structure.json`
2. **Sharp** reads both files → computes matchup probability matrix → writes `data/matchup_probabilities.json`
3. **Contrarian** reads ESPN pick data (or uses seed-based fallback) + team stats → writes `data/ownership.json` with leverage scores
4. **Optimizer** reads matchup probabilities + ownership data + bracket structure → runs Monte Carlo → writes `data/sim_results.json` and `data/optimal_brackets.json`
5. **Analyst** reads optimal brackets + all intermediate data → writes `output/bracket.md`, `output/analysis.md`, `output/bracket.txt` (ASCII)

### 2.3 Module Responsibilities

| Module | File | Reads | Writes | Role |
|--------|------|-------|--------|------|
| Scout | `scout.py` | Web / local HTML | `data/teams.json`, `data/bracket_structure.json`, `data/public_picks.json` | Data acquisition |
| Sharp | `sharp.py` | `data/teams.json`, `data/bracket_structure.json` | `data/matchup_probabilities.json` | Statistical modeling |
| Contrarian | `contrarian.py` | `data/teams.json`, `data/public_picks.json` (optional) | `data/ownership.json` | Public ownership & leverage |
| Optimizer | `optimizer.py` | `data/matchup_probabilities.json`, `data/ownership.json`, `data/bracket_structure.json` | `data/sim_results.json`, `data/optimal_brackets.json` | Monte Carlo + bracket construction |
| Analyst | `analyst.py` | `data/optimal_brackets.json`, `data/teams.json`, `data/ownership.json`, `data/sim_results.json` | `output/analysis.md`, `output/bracket.txt` | Human-readable output |

---

## 3. File Structure

```
bracket-optimizer/
├── PLAN.md                          # This file
├── main.py                          # CLI entry point (thin dispatcher)
├── config.json                      # Pool size, scoring, risk profile
├── src/
│   ├── __init__.py                  # Package marker (empty)
│   ├── models.py                    # All dataclasses (Team, Matchup, Bracket, etc.)
│   ├── scout.py                     # Module 1: KenPom + ESPN scraping
│   ├── sharp.py                     # Module 2: AdjEM → win prob, modifiers
│   ├── contrarian.py                # Module 3: Ownership model, leverage calc
│   ├── optimizer.py                 # Module 4: Monte Carlo sim + bracket builder
│   ├── analyst.py                   # Module 5: Markdown/ASCII output generation
│   ├── config.py                    # Config loading + defaults
│   ├── constants.py                 # Seeds, historical data, scoring tables
│   └── utils.py                     # Shared helpers (JSON I/O, logging, HTTP)
├── tests/
│   ├── __init__.py
│   ├── test_models.py               # Data model validation
│   ├── test_scout.py                # Scraper tests with fixture HTML
│   ├── test_sharp.py                # Win probability, modifiers, matrix
│   ├── test_contrarian.py           # Ownership estimation, leverage
│   ├── test_optimizer.py            # Monte Carlo, bracket construction
│   ├── test_analyst.py              # Output formatting
│   ├── test_integration.py          # End-to-end with mock data
│   └── fixtures/                    # Test HTML files + mock JSON
│       ├── kenpom_sample.html
│       ├── espn_bracketology_sample.html
│       ├── mock_teams.json
│       └── mock_bracket_structure.json
├── data/                            # Intermediate JSON (gitignored)
│   └── .gitkeep
└── output/                          # Final results (gitignored)
    └── .gitkeep
```

### File Purposes

| File | Purpose |
|------|---------|
| `main.py` | Parses CLI args (`collect`, `analyze`, `bracket`, `full`), dispatches to modules, handles `--pool-size`, `--file`, `--sims`, `--risk` flags |
| `config.json` | User-editable defaults: pool_size, scoring array, sim_count, risk_profile |
| `src/models.py` | All data structures as `@dataclass` classes with serialization |
| `src/scout.py` | HTTP fetching + HTML parsing for KenPom and ESPN |
| `src/sharp.py` | Logistic win probability, modifier application, matrix generation |
| `src/contrarian.py` | Public pick estimation, leverage calculation |
| `src/optimizer.py` | Monte Carlo engine, bracket construction, pool simulation |
| `src/analyst.py` | Markdown report, ASCII bracket, pick explanations |
| `src/config.py` | Loads `config.json`, merges CLI overrides, provides typed `Config` object |
| `src/constants.py` | Historical seed upset rates, default ownership curves, conference lists |
| `src/utils.py` | `fetch_url()`, `load_json()`, `save_json()`, `setup_logging()` |

---

## 4. Data Models

All models live in `src/models.py`. Every dataclass includes `to_dict()` → `dict` and `@classmethod from_dict(cls, d: dict) → Self` for JSON serialization.

### 4.1 Team

```
@dataclass
class Team:
    name: str                    # "Gonzaga"
    seed: int                    # 1-16
    region: str                  # "East", "West", "South", "Midwest"
    kenpom_rank: int             # 1-363
    adj_em: float                # Adjusted Efficiency Margin (e.g., +28.5)
    adj_o: float                 # Adjusted Offensive Efficiency
    adj_d: float                 # Adjusted Defensive Efficiency
    adj_t: float                 # Adjusted Tempo (possessions per 40 min)
    sos: float                   # Strength of Schedule
    wins: int
    losses: int
    conference: str              # "WCC", "SEC", etc.
    tournament_appearances: int  # Sweet 16+ appearances in last 3 years (default 0)
    is_auto_bid: bool            # Won conference tournament (default False)
    bracket_position: int        # 1-68 positional index in the bracket
```

**Notes:**
- `bracket_position` is the slot in the 68-team bracket (1-68). Slots 1-64 are the main draw. Slots 65-68 are play-in games.
- `tournament_appearances` and `is_auto_bid` may be set to defaults if not scrapeable; the modifier system treats them as optional adjustments.

### 4.2 Matchup

```
@dataclass
class Matchup:
    team_a: str                  # Team name (key into teams dict)
    team_b: str                  # Team name
    round_num: int               # 1-6 (R64, R32, S16, E8, F4, Championship)
    win_prob_a: float            # P(team_a wins), 0.0-1.0
    raw_prob_a: float            # Before modifiers
    modifiers_applied: list[str] # ["tempo_mismatch", "experience_bonus"]
```

### 4.3 BracketSlot

```
@dataclass
class BracketSlot:
    slot_id: int                 # Unique slot identifier (see Bracket Slot Numbering below)
    round_num: int               # 1-6
    region: str                  # "East"/"West"/"South"/"Midwest"/"FinalFour"
    seed_a: int                  # Expected top seed in this slot
    seed_b: int                  # Expected bottom seed in this slot
    team_a: str | None           # Populated after play-in resolution
    team_b: str | None           # Populated after play-in resolution
    feeds_into: int              # slot_id of next round game
```

### 4.4 BracketStructure

```
@dataclass
class BracketStructure:
    slots: list[BracketSlot]     # All 67 games (63 main + 4 play-in)
    regions: dict[str, list[str]]  # region name → list of team names in seed order
    play_in_games: list[tuple[str, str]]  # 4 play-in matchups
```

### 4.5 BracketPick

```
@dataclass
class BracketPick:
    slot_id: int                 # Which game
    round_num: int               # Which round
    winner: str                  # Team name picked to win
    confidence: str              # "lock" | "lean" | "gamble"
    leverage_score: float        # Leverage at this pick
    is_upset: bool               # Picked lower seed
```

### 4.6 CompleteBracket

```
@dataclass
class CompleteBracket:
    picks: list[BracketPick]     # All 67 picks (63 main + 4 play-in)
    champion: str                # Team picked to win it all
    final_four: list[str]        # 4 Final Four teams
    elite_eight: list[str]       # 8 Elite Eight teams
    label: str                   # "optimal", "safe", "aggressive"
    expected_score: float        # Expected ESPN score
    p_first_place: float         # P(finishing 1st in pool)
    p_top_three: float           # P(finishing top 3)
    expected_finish: float       # Expected finish position
```

### 4.7 OwnershipProfile

```
@dataclass
class OwnershipProfile:
    team: str                    # Team name
    seed: int
    round_ownership: dict[int, float]  # round_num → % of public picking this team to reach that round
    leverage_by_round: dict[int, float] # round_num → leverage score
    title_ownership: float       # % picking as champion
    title_leverage: float        # Model title prob / public title ownership
```

### 4.8 SimResult

```
@dataclass
class SimResult:
    sim_id: int
    actual_results: dict[int, str]    # slot_id → winning team name (ground truth for this sim)
    our_score: int                    # Our bracket score
    our_rank: int                     # 1-based rank in pool (1 = we won)
    opponent_scores: list[int]        # Scores of 25 opponent brackets
    champion: str                     # Who actually won the tournament in this sim
```

### 4.9 AggregateResults

```
@dataclass
class AggregateResults:
    total_sims: int
    p_first_place: float              # % of sims we finished 1st
    p_top_three: float                # % of sims we finished top 3
    expected_finish: float            # Mean finish position
    expected_score: float             # Mean bracket score
    median_score: float
    champion_frequency: dict[str, float]  # team → % of sims they won title
    value_picks: list[dict]           # Picks with highest leverage contribution
```

### 4.10 Config

```
@dataclass
class Config:
    pool_size: int                    # Default: 25
    scoring: list[int]                # Default: [10, 20, 40, 80, 160, 320]
    sim_count: int                    # Default: 10000
    risk_profile: str                 # "conservative" | "balanced" | "aggressive" | "auto"
    champion_min_leverage: float      # Default: 1.5
    min_contrarian_ff: int            # Default: 1 (at least 1 FF pick with <15% ownership)
    max_r1_upsets: int                # Default: 3
    data_dir: str                     # Default: "data"
    output_dir: str                   # Default: "output"
    kenpom_url: str
    espn_bracket_url: str
    espn_picks_url: str
    kenpom_file: str | None           # Override with local file
    espn_bracket_file: str | None
    espn_picks_file: str | None
```

### Bracket Slot Numbering Convention

The 63-game main bracket uses a binary-tree numbering scheme within each region:

- **Round of 64 (R1):** Each region has 8 games. Slots 1-8 (East), 9-16 (West), 17-24 (South), 25-32 (Midwest).
  - Slot 1: 1-seed vs 16-seed, Slot 2: 8-seed vs 9-seed, Slot 3: 5-seed vs 12-seed, etc.
  - Standard NCAA bracket order: (1v16, 8v9, 5v12, 4v13, 6v11, 3v14, 7v10, 2v15)
- **Round of 32 (R2):** Slots 33-36 (East), 37-40 (West), 41-44 (South), 45-48 (Midwest). Slot 33 = winner of Slot 1 vs winner of Slot 2, etc.
- **Sweet 16 (R3):** Slots 49-50 (East), 51-52 (West), 53-54 (South), 55-56 (Midwest).
- **Elite 8 (R4):** Slots 57 (East), 58 (West), 59 (South), 60 (Midwest).
- **Final Four (R5):** Slot 61 (East champ vs West champ), Slot 62 (South champ vs Midwest champ). *(Note: actual FF pairings depend on the year's bracket layout; this is the default.)*
- **Championship (R6):** Slot 63.
- **Play-in (R0):** Slots 64-67.

The `feeds_into` field on each BracketSlot identifies the next-round slot. This creates the tree structure needed for simulation.

---

## 5. Interfaces — All Public Functions

### 5.1 `src/utils.py`

```
def fetch_url(url: str, timeout: int = 30) -> str
    """Fetch URL content using urllib.request with browser User-Agent.
    
    Args:
        url: The HTTP/HTTPS URL to fetch.
        timeout: Request timeout in seconds.
    
    Returns:
        Decoded response body as string.
    
    Raises:
        ScrapingError: If HTTP error or timeout occurs.
    """

def load_json(filepath: str) -> dict | list
    """Load and parse a JSON file.
    
    Args:
        filepath: Path to the JSON file.
    
    Returns:
        Parsed JSON content.
    
    Raises:
        DataError: If file not found or invalid JSON.
    """

def save_json(data: dict | list, filepath: str) -> None
    """Write data to a JSON file with pretty-printing.
    
    Args:
        data: JSON-serializable data.
        filepath: Output path. Parent directories must exist.
    """

def setup_logging(verbose: bool = False) -> logging.Logger
    """Configure and return the application logger.
    
    Args:
        verbose: If True, set level to DEBUG. Otherwise INFO.
    
    Returns:
        Configured Logger instance.
    """
```

### 5.2 `src/config.py`

```
def load_config(config_path: str = "config.json", cli_overrides: dict | None = None) -> Config
    """Load configuration from JSON file, merged with CLI overrides.
    
    Priority: CLI flags > config.json > hardcoded defaults.
    
    Args:
        config_path: Path to config.json.
        cli_overrides: Dict of CLI argument overrides (e.g., {"pool_size": 50}).
    
    Returns:
        Populated Config dataclass.
    """

def auto_risk_profile(pool_size: int) -> str
    """Calculate risk profile from pool size.
    
    Smaller pools (≤10) → "conservative"
    Medium pools (11-50) → "balanced"  
    Large pools (51-200) → "aggressive"
    Huge pools (200+) → "very_aggressive"
    
    Args:
        pool_size: Number of entrants in the pool.
    
    Returns:
        Risk profile string.
    """
```

### 5.3 `src/scout.py`

```
def scrape_kenpom(url: str | None = None, filepath: str | None = None) -> list[Team]
    """Scrape KenPom ratings page for all D1 team statistics.
    
    Uses urllib + BeautifulSoup to parse the main ratings table.
    Extracts: rank, team name, conference, W-L, AdjEM, AdjO, AdjD, AdjT, 
    Luck, SOS (AdjEM), OppO, OppD, NCSOS (AdjEM).
    
    Args:
        url: KenPom URL to scrape. Defaults to constants.KENPOM_URL.
        filepath: If provided, read HTML from local file instead of URL.
    
    Returns:
        List of Team objects with stats populated. Seed, region, and 
        bracket_position will be unset (filled by bracket scraper).
    
    Raises:
        ScrapingError: If page structure doesn't match expected format.
    """

def scrape_espn_bracket(url: str | None = None, filepath: str | None = None) -> BracketStructure
    """Scrape ESPN Bracketology for projected bracket seedings and regions.
    
    Parses the bracket page to extract all 68 teams with their seeds,
    regions, and play-in game designations.
    
    Args:
        url: ESPN Bracketology URL.
        filepath: Local HTML file override.
    
    Returns:
        BracketStructure with all slots, regions, and play-in games populated.
    
    Raises:
        ScrapingError: If fewer than 68 teams found or structure unrecognizable.
    """

def scrape_espn_picks(url: str | None = None, filepath: str | None = None) -> dict[str, dict[int, float]] | None
    """Scrape ESPN Tournament Challenge public pick percentages.
    
    Returns pick data if available, None if the page isn't live yet.
    
    Args:
        url: ESPN Tournament Challenge URL.
        filepath: Local HTML file override.
    
    Returns:
        Dict mapping team_name → {round_num: pick_percentage} if available,
        None if data not yet published.
    
    Raises:
        ScrapingError: On network/parsing errors (distinct from "not available yet").
    """

def merge_team_data(teams: list[Team], bracket: BracketStructure) -> list[Team]
    """Merge KenPom stats with bracket seedings.
    
    Matches teams by name (with fuzzy matching for name discrepancies 
    between KenPom and ESPN, e.g., "UConn" vs "Connecticut").
    Sets seed, region, and bracket_position on each Team.
    
    Args:
        teams: Teams from KenPom scrape (have stats, no seedings).
        bracket: Bracket structure from ESPN (has seedings).
    
    Returns:
        List of 68 Teams with both stats and seeding info.
    
    Raises:
        DataError: If a bracketed team can't be matched to a KenPom team.
    """

def collect_all(config: Config) -> tuple[list[Team], BracketStructure]
    """Run the full data collection pipeline.
    
    Orchestrates: scrape KenPom → scrape ESPN bracket → merge → 
    optionally scrape ESPN picks → save all to data/.
    
    Args:
        config: Application configuration.
    
    Returns:
        Tuple of (merged team list, bracket structure).
    """
```

### 5.4 `src/sharp.py`

```
def adj_em_to_win_prob(adj_em_a: float, adj_em_b: float, tempo_a: float = 67.5, tempo_b: float = 67.5) -> float
    """Convert AdjEM differential to win probability using logistic model.
    
    Uses the formula: P(A wins) = 1 / (1 + 10^(-ΔEM / κ))
    where ΔEM = adj_em_a - adj_em_b and κ is the scaling constant (11.5).
    
    The tempo parameters are used to estimate expected possessions,
    which affects the variance of the outcome (more possessions = less variance = 
    favorites win more often). This is a secondary correction.
    
    Args:
        adj_em_a: Team A's Adjusted Efficiency Margin.
        adj_em_b: Team B's Adjusted Efficiency Margin.
        tempo_a: Team A's adjusted tempo. Default is D1 average.
        tempo_b: Team B's adjusted tempo. Default is D1 average.
    
    Returns:
        Probability that Team A wins, between 0.0 and 1.0.
    """

def apply_tournament_experience_modifier(base_prob: float, team_a_appearances: int, team_b_appearances: int) -> float
    """Adjust win probability based on recent tournament experience.
    
    Teams with Sweet 16+ appearances in the last 3 years get a slight boost.
    This captures the "been there before" effect documented in tournament research.
    
    Modifier: +0.02 per appearance for the more experienced team, capped at +0.05.
    Applied symmetrically (if A has more experience, A's prob goes up; if B, it goes down).
    
    Args:
        base_prob: Pre-modifier win probability for Team A.
        team_a_appearances: Team A's Sweet 16+ appearances in last 3 years.
        team_b_appearances: Team B's Sweet 16+ appearances in last 3 years.
    
    Returns:
        Modified win probability, clamped to [0.01, 0.99].
    """

def apply_tempo_mismatch_modifier(base_prob: float, tempo_a: float, tempo_b: float, adj_d_a: float, adj_d_b: float) -> float
    """Adjust for slow-tempo defensive teams' tournament advantage.
    
    In single-elimination tournament play, teams with elite defense and slow tempo
    tend to slightly outperform their regular-season metrics. This captures 
    the "you can't simulate a 68-game adjustment" factor.
    
    The modifier applies when one team is significantly slower AND has a 
    significantly better defense. It's a small bump (up to +0.03).
    
    A team is "slow defensive" if tempo < 65.0 AND AdjD < 95.0 (lower is better).
    
    Args:
        base_prob: Pre-modifier win probability for Team A.
        tempo_a: Team A's adjusted tempo.
        tempo_b: Team B's adjusted tempo.
        adj_d_a: Team A's adjusted defensive efficiency (lower = better).
        adj_d_b: Team B's adjusted defensive efficiency.
    
    Returns:
        Modified win probability, clamped to [0.01, 0.99].
    """

def apply_conference_momentum_modifier(base_prob: float, team_a: Team, team_b: Team) -> float
    """Adjust for conference tournament momentum (auto-bid hot teams).
    
    Power conference teams that earned an auto-bid (won their conf tournament)
    get a small boost as they're "playing with house money" and riding momentum.
    Mid-major auto-bid teams don't get this — they're expected to win their conf tourney.
    
    Modifier: +0.015 for power conference auto-bid teams.
    Power conferences: SEC, Big Ten, Big 12, ACC, Big East, AAC.
    
    Args:
        base_prob: Pre-modifier win probability for Team A.
        team_a: Full Team object for Team A.
        team_b: Full Team object for Team B.
    
    Returns:
        Modified win probability, clamped to [0.01, 0.99].
    """

def apply_seed_prior(model_prob: float, seed_a: int, seed_b: int) -> float
    """Blend model probability with historical seed-based upset rates.
    
    Uses Bayesian-style blending: final = w * model_prob + (1-w) * historical_prob
    where w = 0.75 (trust the model more than raw seed history).
    
    Historical seed matchup data comes from constants.HISTORICAL_SEED_WIN_RATES.
    
    Args:
        model_prob: Model-derived win probability for the team with seed_a.
        seed_a: Seed of Team A.
        seed_b: Seed of Team B.
    
    Returns:
        Blended win probability.
    """

def compute_matchup_probability(team_a: Team, team_b: Team) -> Matchup
    """Compute the full win probability for a matchup, applying all modifiers.
    
    Pipeline: raw AdjEM prob → experience modifier → tempo mismatch → 
    conference momentum → seed prior blending.
    
    Tracks which modifiers were applied and their individual effects.
    
    Args:
        team_a: Full Team object.
        team_b: Full Team object.
    
    Returns:
        Matchup with win_prob_a, raw_prob_a, and modifiers_applied populated.
    """

def build_matchup_matrix(teams: list[Team]) -> dict[str, dict[str, float]]
    """Build the full NxN matchup probability matrix for all 68 teams.
    
    Computes P(A beats B) for every possible pairing. The matrix is 
    antisymmetric: P(B beats A) = 1 - P(A beats B).
    
    Only the upper triangle is computed; the lower triangle is derived.
    
    Args:
        teams: List of all 68 tournament teams with stats and seedings.
    
    Returns:
        Nested dict: matchup_matrix[team_a_name][team_b_name] = P(A beats B).
        Also saves to data/matchup_probabilities.json.
    """
```

### 5.5 `src/contrarian.py`

```
def estimate_seed_ownership(seed: int, round_num: int) -> float
    """Estimate public pick percentage based on seed and round.
    
    Uses historical ESPN Tournament Challenge data averages stored in
    constants.SEED_OWNERSHIP_CURVES.
    
    Args:
        seed: Team's tournament seed (1-16).
        round_num: Tournament round (1-6).
    
    Returns:
        Estimated percentage of public brackets picking this seed-line
        team to reach this round (0.0-1.0). This is per-team, not per-seed-line.
    """

def build_ownership_profiles(teams: list[Team], espn_picks: dict[str, dict[int, float]] | None = None) -> list[OwnershipProfile]
    """Build ownership profiles for all 68 teams.
    
    If ESPN pick data is available, uses it directly. Otherwise, uses 
    seed-based estimation as fallback, with adjustments for:
    - KenPom rank relative to seed (under-seeded teams get slightly higher ownership)
    - Brand-name programs (historically over-picked, hardcoded list in constants)
    
    Args:
        teams: All 68 tournament teams.
        espn_picks: ESPN pick percentages if available (team → round → pct).
    
    Returns:
        List of OwnershipProfile, one per team.
    """

def calculate_leverage(model_prob: float, public_ownership: float) -> float
    """Calculate leverage score for a pick.
    
    Leverage = model_prob / public_ownership
    
    Leverage > 1.0 means the model likes this team more than the public.
    Leverage < 1.0 means the public overvalues this team.
    
    Handles edge case: if public_ownership < 0.005 (0.5%), cap it at 0.005 
    to prevent infinite leverage from near-zero ownership.
    
    Args:
        model_prob: Our model's probability for this outcome.
        public_ownership: Fraction of public brackets making this pick.
    
    Returns:
        Leverage score (float, ≥ 0).
    """

def find_value_picks(ownership_profiles: list[OwnershipProfile], min_leverage: float = 1.5) -> list[dict]
    """Identify high-leverage picks across all rounds.
    
    Scans all teams at all rounds and returns picks where leverage exceeds 
    the threshold. Sorted by leverage descending.
    
    Args:
        ownership_profiles: All team ownership profiles.
        min_leverage: Minimum leverage to qualify as a value pick.
    
    Returns:
        List of dicts with keys: team, round, model_prob, public_ownership, leverage.
    """

def analyze_ownership(teams: list[Team], config: Config) -> list[OwnershipProfile]
    """Run the full ownership analysis pipeline.
    
    Orchestrates: load/estimate picks → build profiles → calculate leverage →
    save to data/ownership.json.
    
    Args:
        teams: All 68 tournament teams.
        config: Application configuration.
    
    Returns:
        List of OwnershipProfile for all teams.
    """
```

### 5.6 `src/optimizer.py`

```
def simulate_tournament(matchup_matrix: dict[str, dict[str, float]], bracket: BracketStructure, rng: random.Random) -> dict[int, str]
    """Simulate one complete tournament using matchup probabilities.
    
    Walks through the bracket round by round. For each game, uses 
    matchup_matrix to get P(A beats B), then draws a random number to 
    determine the winner. The winner advances to the next slot via feeds_into.
    
    Args:
        matchup_matrix: P(A beats B) for all pairs.
        bracket: Tournament bracket structure.
        rng: Seeded Random instance for reproducibility.
    
    Returns:
        Dict mapping slot_id → winning team name for all 63 main-draw games.
    """

def generate_public_bracket(ownership_profiles: list[OwnershipProfile], bracket: BracketStructure, matchup_matrix: dict[str, dict[str, float]], rng: random.Random) -> CompleteBracket
    """Generate one simulated public bracket using ownership distributions.
    
    For each game, selects the winner based on public pick percentages.
    Must maintain bracket consistency: if Team A is picked to win R2, they 
    must also be picked to win R1 (correlated advancement).
    
    Uses a "champion-first" approach:
    1. Pick the champion weighted by title_ownership.
    2. For each round, pick winners weighted by round_ownership, but constrained
       so the champion's path is clear.
    3. For remaining games not on champion's path, use round_ownership weights.
    
    Args:
        ownership_profiles: Public pick distributions.
        bracket: Bracket structure.
        matchup_matrix: Used for secondary tiebreaking.
        rng: Random instance.
    
    Returns:
        A plausible public bracket.
    """

def score_bracket(bracket_picks: dict[int, str], actual_results: dict[int, str], scoring: list[int], bracket_structure: BracketStructure) -> int
    """Score a bracket against actual tournament results.
    
    For each game, if bracket_picks[slot_id] == actual_results[slot_id],
    add scoring[round_num - 1] points.
    
    Args:
        bracket_picks: Dict of slot_id → picked winner.
        actual_results: Dict of slot_id → actual winner.
        scoring: Points per round [R1, R2, S16, E8, F4, Championship].
        bracket_structure: Needed to determine round_num for each slot.
    
    Returns:
        Total bracket score (int).
    """

def evaluate_bracket_in_pool(our_picks: dict[int, str], actual_results: dict[int, str], opponent_brackets: list[dict[int, str]], scoring: list[int], bracket_structure: BracketStructure) -> tuple[int, int]
    """Score our bracket and determine our rank in the pool.
    
    Args:
        our_picks: Our bracket picks.
        actual_results: Simulated tournament results.
        opponent_brackets: List of opponent bracket picks.
        scoring: Points per round.
        bracket_structure: For round number lookup.
    
    Returns:
        Tuple of (our_score, our_rank) where rank is 1-indexed.
    """

def construct_candidate_bracket(teams: list[Team], matchup_matrix: dict[str, dict[str, float]], ownership_profiles: list[OwnershipProfile], bracket: BracketStructure, config: Config, strategy: str = "balanced") -> CompleteBracket
    """Construct a candidate bracket using strategy constraints.
    
    The bracket construction is a constrained optimization:
    1. Select champion: highest leverage among teams with title prob > threshold.
    2. Build champion's path: clear the way from R1 to championship.
    3. Select remaining Final Four: at least 1 must have <15% ownership.
    4. Fill Elite Eight, Sweet 16, etc. using highest-probability picks 
       unless leverage on the underdog is compelling.
    5. Round 1: mostly chalk, max N upsets (where N = config.max_r1_upsets).
    6. Enforce correlation: every team picked to advance must also be 
       picked to win in all prior rounds.
    
    Strategy variants:
    - "conservative": champion leverage > 1.2, max 1 R1 upset, favor chalk
    - "balanced": champion leverage > 1.5, max 3 R1 upsets, mix of chalk and value
    - "aggressive": champion leverage > 2.0, max 5 R1 upsets, prioritize differentiation
    
    Args:
        teams: All 68 teams.
        matchup_matrix: Win probabilities.
        ownership_profiles: Public ownership data.
        bracket: Bracket structure.
        config: Configuration.
        strategy: "conservative", "balanced", or "aggressive".
    
    Returns:
        A complete, consistent bracket with all picks, champion, and FF.
    """

def run_monte_carlo(our_bracket: CompleteBracket, matchup_matrix: dict[str, dict[str, float]], ownership_profiles: list[OwnershipProfile], bracket: BracketStructure, config: Config) -> AggregateResults
    """Run the full Monte Carlo simulation to evaluate a bracket.
    
    For each of N simulations:
    1. Simulate the actual tournament results using matchup_matrix.
    2. Generate pool_size opponent brackets using public ownership.
    3. Score our bracket and all opponents.
    4. Record our rank.
    
    Aggregates across all sims to compute P(1st), P(top 3), expected finish, etc.
    
    Uses multiprocessing-safe random seeds: base_seed + sim_id for reproducibility.
    
    Args:
        our_bracket: The bracket to evaluate.
        matchup_matrix: Win probability matrix.
        ownership_profiles: For generating opponent brackets.
        bracket: Tournament structure.
        config: Pool size, sim count, scoring.
    
    Returns:
        AggregateResults with win probability estimates and diagnostics.
    """

def optimize_bracket(teams: list[Team], matchup_matrix: dict[str, dict[str, float]], ownership_profiles: list[OwnershipProfile], bracket: BracketStructure, config: Config) -> list[CompleteBracket]
    """Run the full optimization loop to find the best bracket.
    
    Strategy:
    1. Generate 3 candidate brackets (conservative, balanced, aggressive).
    2. Run Monte Carlo on each.
    3. Additionally, generate 5-10 "perturbation" brackets by modifying 
       the best performer's picks at key decision points (champion, FF, specific upsets).
    4. Run Monte Carlo on perturbations.
    5. Return the top 3 brackets (optimal + 2 alternates) sorted by P(1st).
    
    The perturbation approach avoids brute-force search (2^63 is impossible) while 
    still exploring the neighborhood of good solutions.
    
    Args:
        teams: All 68 teams.
        matchup_matrix: Win probabilities.
        ownership_profiles: Public ownership.
        bracket: Bracket structure.
        config: Configuration.
    
    Returns:
        List of 3 CompleteBrackets: [optimal, safe_alternate, aggressive_alternate],
        sorted by P(1st) descending, with the safe and aggressive being the 
        runner-ups from the evaluation.
    """
```

### 5.7 `src/analyst.py`

```
def explain_pick(pick: BracketPick, team: Team, opponent_name: str, ownership: OwnershipProfile) -> str
    """Generate a human-readable explanation for a non-chalk pick.
    
    Includes: stat edge (AdjEM comparison), leverage score, public ownership,
    and a narrative reason why this pick has value.
    
    Args:
        pick: The bracket pick to explain.
        team: Full team data for the picked team.
        opponent_name: Name of the team they beat.
        ownership: Ownership profile for the picked team.
    
    Returns:
        Markdown-formatted explanation paragraph.
    """

def assign_confidence_tier(pick: BracketPick, matchup_prob: float) -> str
    """Assign a confidence tier emoji to a pick.
    
    🔒 Lock: win_prob ≥ 0.75 (heavy favorite, obvious pick)
    👍 Lean: 0.55 ≤ win_prob < 0.75 (model-favored but not certain)
    🎲 Gamble: win_prob < 0.55 (genuine upset pick, high leverage)
    
    Args:
        pick: The bracket pick.
        matchup_prob: Win probability for the picked team.
    
    Returns:
        One of "🔒 Lock", "👍 Lean", "🎲 Gamble".
    """

def generate_analysis_report(bracket: CompleteBracket, teams: list[Team], ownership_profiles: list[OwnershipProfile], sim_results: AggregateResults, matchup_matrix: dict[str, dict[str, float]]) -> str
    """Generate the full markdown analysis report.
    
    Sections:
    - Executive Summary: champion, FF, P(1st), expected finish
    - Key Differentiators: the 5-8 picks that most separate us from the field
    - Round-by-Round Breakdown: every pick with confidence tier, upsets highlighted
    - Risk Assessment: what needs to go right, biggest vulnerabilities
    - Alternate Brackets: summary comparison of the 3 options
    
    Args:
        bracket: The optimal bracket.
        teams: All team data.
        ownership_profiles: Ownership/leverage data.
        sim_results: Monte Carlo results.
        matchup_matrix: For including win probabilities in explanations.
    
    Returns:
        Complete markdown report as string.
    """

def generate_ascii_bracket(bracket: CompleteBracket, bracket_structure: BracketStructure) -> str
    """Generate an ASCII-art bracket visualization.
    
    Renders a text-based bracket with team names, seeds, and round progression.
    Uses box-drawing characters for connecting lines.
    Width-constrained to 120 characters for terminal display.
    
    Renders one region at a time (top to bottom: East, West, South, Midwest)
    then Final Four / Championship at the bottom.
    
    Args:
        bracket: The bracket to render.
        bracket_structure: For positional layout.
    
    Returns:
        ASCII bracket as multi-line string.
    """

def generate_all_output(brackets: list[CompleteBracket], teams: list[Team], ownership_profiles: list[OwnershipProfile], sim_results: AggregateResults, matchup_matrix: dict[str, dict[str, float]], bracket_structure: BracketStructure, config: Config) -> None
    """Run the full output pipeline.
    
    Generates and saves:
    - output/analysis.md: Full analysis report
    - output/bracket.txt: ASCII bracket visualization
    - output/summary.json: Machine-readable summary of results
    
    Args:
        brackets: Top 3 brackets [optimal, safe, aggressive].
        teams: All team data.
        ownership_profiles: Ownership data.
        sim_results: Monte Carlo results for the optimal bracket.
        matchup_matrix: Win probability matrix.
        bracket_structure: Bracket layout.
        config: Configuration.
    """
```

### 5.8 `src/constants.py`

```
KENPOM_URL: str                  # "https://kenpom.com"
ESPN_BRACKET_URL: str            # "https://www.espn.com/mens-college-basketball/bracketology"
ESPN_PICKS_URL: str              # "https://fantasy.espn.com/tournament-challenge-bracket/"

HISTORICAL_SEED_WIN_RATES: dict[tuple[int, int], float]
    # Maps (higher_seed, lower_seed) → P(higher seed wins)
    # Key matchups from NCAA tournament history:
    # (1, 16): 0.993, (2, 15): 0.938, (3, 14): 0.851, (4, 13): 0.793,
    # (5, 12): 0.649, (6, 11): 0.625, (7, 10): 0.607, (8, 9): 0.519
    # Plus non-standard matchups for later rounds (1v8, 1v4, etc.)

SEED_OWNERSHIP_CURVES: dict[int, dict[int, float]]
    # Maps seed → {round_num: avg_public_pick_pct}
    # Example: 1: {1: 0.97, 2: 0.88, 3: 0.72, 4: 0.55, 5: 0.35, 6: 0.25}
    #          5: {1: 0.65, 2: 0.30, 3: 0.10, 4: 0.03, 5: 0.01, 6: 0.005}

BRAND_NAME_BOOST: dict[str, float]
    # Teams historically over-picked by public. Maps team → multiplier on ownership.
    # e.g., {"Duke": 1.3, "Kentucky": 1.25, "North Carolina": 1.25, "Kansas": 1.2, ...}

POWER_CONFERENCES: list[str]
    # ["SEC", "Big Ten", "Big 12", "ACC", "Big East", "AAC"]

SCORING_ESPN_STANDARD: list[int]
    # [10, 20, 40, 80, 160, 320]

BRACKET_SEED_ORDER: list[tuple[int, int]]
    # Standard bracket matchup order within a region:
    # [(1, 16), (8, 9), (5, 12), (4, 13), (6, 11), (3, 14), (7, 10), (2, 15)]

TEAM_NAME_ALIASES: dict[str, str]
    # For fuzzy matching between KenPom and ESPN names.
    # e.g., {"Connecticut": "UConn", "St. John's (NY)": "St. John's", ...}
```

### 5.9 `main.py`

```
def parse_args() -> argparse.Namespace
    """Parse CLI arguments.
    
    Commands: collect, analyze, bracket, full
    
    Global flags:
        --pool-size INT      Pool size (default: from config.json)
        --sims INT           Number of simulations (default: 10000)
        --risk STR           Risk profile: conservative|balanced|aggressive|auto
        --config PATH        Path to config.json (default: ./config.json)
        --verbose            Enable debug logging
        --seed INT           Random seed for reproducibility
    
    Scout flags:
        --kenpom-file PATH   Use local KenPom HTML file
        --espn-bracket-file PATH  Use local ESPN bracket HTML
        --espn-picks-file PATH    Use local ESPN picks HTML
    
    Returns:
        Parsed arguments namespace.
    """

def cmd_collect(config: Config) -> None
    """Execute the 'collect' command — run data collection pipeline."""

def cmd_analyze(config: Config) -> None
    """Execute the 'analyze' command — run model + optimization."""

def cmd_bracket(config: Config) -> None
    """Execute the 'bracket' command — generate output from existing data."""

def cmd_full(config: Config) -> None
    """Execute the 'full' command — collect → analyze → bracket."""

def main() -> None
    """CLI entry point."""
```

---

## 6. The Statistical Model

### 6.1 Core Win Probability: AdjEM → Sigmoid

The primary predictor is **KenPom Adjusted Efficiency Margin (AdjEM)**. AdjEM measures points scored minus points allowed per 100 possessions, adjusted for opponent strength and game location.

**Formula:**

```
ΔEM = AdjEM_A - AdjEM_B
P(A wins) = 1 / (1 + 10^(-ΔEM / κ))
```

Where **κ = 11.5** is the scaling constant calibrated from historical NCAA tournament data. This value means:
- ΔEM of 0 → 50% win probability (equal teams)
- ΔEM of +11.5 → 75% win probability
- ΔEM of +23 → ~90% win probability
- ΔEM of +30 → ~95% win probability

**Why this formula:** It's a logistic function using base-10 (common in Elo-family systems). The choice of κ=11.5 comes from fitting historical tournament results. Alternative: use base-e with a different scale factor, but 11.5 with base-10 is the convention in the KenPom ecosystem.

### 6.2 Possession-Count Variance Adjustment

Higher-tempo games have more possessions, reducing outcome variance (law of large numbers). This slightly helps favorites in high-tempo matchups.

```
expected_possessions = (tempo_a + tempo_b) / 2 * 0.4  # Rough game possessions
avg_possessions = 67.5 * 0.4  # D1 average (≈67 possessions)
variance_factor = sqrt(avg_possessions / expected_possessions)
adjusted_ΔEM = ΔEM * variance_factor
```

This is a **small** correction (typically ±1-2% on win probability) but directionally correct.

### 6.3 Modifiers (Applied Sequentially)

All modifiers are additive adjustments to the base win probability, applied in order, with clamping to [0.01, 0.99] after each step.

**Modifier 1: Tournament Experience**
- Count each team's Sweet 16+ appearances in the last 3 seasons.
- Difference `d = appearances_A - appearances_B`.
- Adjustment: `+0.02 * clamp(d, -2, +2)` (so max ±0.04 for 2+ appearances difference).
- Rationale: Coaching staff and players with deep tournament runs handle pressure better.

**Modifier 2: Tempo Mismatch (Slow Defensive Teams)**
- A team qualifies as "slow-defensive" if `tempo < 65.0` AND `AdjD < 95.0`.
- If exactly one team qualifies: that team gets `+0.03` to their win probability.
- If both or neither qualify: no adjustment.
- Rationale: March Madness rewards defensive grinders. Fewer possessions = more variance in the other direction, which slightly favors defensive teams in single-game contexts. This counteracts the possession-variance adjustment above for these specific teams.

**Modifier 3: Conference Tournament Momentum**
- If a team is an auto-bid AND from a power conference: `+0.015` to their win probability.
- If both teams qualify: cancel out.
- Rationale: A team that won the SEC tournament is peaking. A team that won the Patriot League tournament was just expected to.

### 6.4 Bayesian Seed Prior Blending

The model probability is blended with historical seed-matchup win rates:

```
final_prob = w * model_prob + (1 - w) * historical_prob
w = 0.75
```

**Why blend?** Pure AdjEM sometimes overvalues mid-majors and undervalues experienced low-seeds. Historical seed data captures structural advantages (bracket positioning, rest, travel) that AdjEM doesn't account for. The 0.75 weight ensures the model dominates but doesn't ignore centuries of seed-line data.

**Historical data source:** `constants.HISTORICAL_SEED_WIN_RATES` stores win rates for all standard seed matchups, compiled from every NCAA tournament since 1985.

For non-standard matchups in later rounds (e.g., 3-seed vs 7-seed in Sweet 16), use the seed matchup's historical rate if available, otherwise fall back to pure model probability (w=1.0).

### 6.5 The Matchup Matrix

The output of the Sharp module is a 68×68 matrix where `matrix[A][B]` = P(A beats B). Properties:
- `matrix[A][B] + matrix[B][A] = 1.0` (antisymmetric)
- `matrix[A][A]` is undefined / not stored
- Stored as a nested dict of team names → team names → float
- Serialized to `data/matchup_probabilities.json`

### 6.6 Monte Carlo Tournament Simulation

Each simulation walks the bracket tree from Round 1 to the Championship:

```
For each round 1-6:
    For each game in this round:
        team_a = winner from feeder slot A (or initial team)
        team_b = winner from feeder slot B (or initial team)
        p = matchup_matrix[team_a][team_b]
        if random() < p:
            result[slot_id] = team_a
        else:
            result[slot_id] = team_b
```

Play-in games (Round 0) are resolved first to determine which teams fill the four contested slots.

**Random seed strategy:** Each sim uses `rng = Random(base_seed + sim_id)` for reproducibility. The base_seed comes from CLI `--seed` or defaults to a hash of today's date.

---

## 7. The Optimization Strategy

### 7.1 Why Not Brute Force?

A complete bracket has 63 games, each with 2 outcomes = 2^63 ≈ 9.2 × 10^18 possible brackets. Even if we only consider "plausible" brackets (following seed expectations mostly), the space is enormous. Brute force is impossible.

### 7.2 The Actual Strategy: Constrained Heuristic + Perturbation Search

**Phase 1: Construct Candidate Brackets (3 strategies)**

Each candidate bracket is built top-down using constrained heuristics:

1. **Select Champion** (most important single pick, worth 320 points):
   - Compute `title_probability` for each team by running 1,000 quick sims.
   - Compute `title_leverage = title_probability / title_ownership`.
   - Filter: only teams with `title_leverage > threshold` (varies by strategy).
   - Among qualifying teams, select the one with highest `title_probability * title_leverage` (balances being likely AND differentiated).

2. **Build Champion's Path** (must be consistent):
   - Given the champion, fill in their wins from R1 through Championship.
   - For each game on the champion's path, the opponent is the strongest team they'd likely face from the other half of the sub-bracket.
   - The champion must beat every team on their path — no contradictions.

3. **Select Remaining Final Four** (3 more teams):
   - At least 1 must have `title_ownership < 15%` (contrarian constraint).
   - From the remaining 3 regions, select the team with best `probability * leverage` product.
   - Their paths are also built out consistently.

4. **Fill Remaining Games** (bottom-up within each sub-bracket):
   - For each game not on any FF team's path, pick the team with higher win probability.
   - Exception: if the underdog's leverage > 2.0 AND their win probability > 0.35, consider the upset.
   - Round 1 constraint: max N upsets total (varies by strategy).

5. **Assign Confidence Tiers** to each pick based on win probability.

**Strategy Variants:**

| Parameter | Conservative | Balanced | Aggressive |
|-----------|-------------|----------|------------|
| Champion min leverage | 1.2 | 1.5 | 2.0 |
| Min contrarian FF picks (<15% owned) | 0 | 1 | 2 |
| Max R1 upsets | 1 | 3 | 5 |
| Upset leverage threshold | 3.0 | 2.0 | 1.5 |
| Upset min win prob | 0.40 | 0.35 | 0.30 |

**Phase 2: Evaluate via Monte Carlo**

Each candidate bracket is run through `run_monte_carlo()`:
- 10,000 simulations per bracket.
- Each sim: simulate actual tournament + 25 opponent brackets + score + rank.
- Output: P(1st place), P(top 3), expected finish.

**Phase 3: Perturbation Search (Local Optimization)**

Take the best-performing bracket from Phase 2. Generate 5-10 perturbations:

- **Champion swap:** Try the 2nd and 3rd highest-leverage champion options.
- **Final Four swap:** For each FF slot, try the 2nd-best candidate.
- **Upset toggle:** Flip the top 3 highest-leverage potential upsets (add if not present, remove if present).
- Each perturbation maintains bracket consistency (rebuild paths after each swap).

Run Monte Carlo on each perturbation. Take the overall best.

**Phase 4: Output**

Return the top 3 distinct brackets sorted by P(1st place):
1. **Optimal** — highest P(1st).
2. **Safe Alternate** — from the remaining, whichever has the highest P(top 3).
3. **Aggressive Alternate** — from the remaining, whichever has the most differentiation (highest sum of leverage scores).

### 7.3 Opponent Bracket Generation

The 25 simulated opponents are generated to reflect realistic public pool composition:
- Each opponent bracket is built using public ownership probabilities.
- Champion selected weighted by `title_ownership`.
- Each round's picks are weighted by `round_ownership[round_num]`.
- Bracket consistency enforced: if a team is picked to advance, they win all prior rounds.
- Some randomness in the generation — the 25 brackets will NOT be identical.

### 7.4 Pool Scoring

ESPN Standard: Round 1 = 10pts/correct, Round 2 = 20, Sweet 16 = 40, Elite 8 = 80, Final Four = 160, Championship = 320 per correct pick.

**Maximum possible score:** 32×10 + 16×20 + 8×40 + 4×80 + 2×160 + 1×320 = 320 + 320 + 320 + 320 + 320 + 320 = **1920 points**.

Key insight: the Championship game alone is worth 320/1920 = **16.7%** of the total possible score. Getting the champion right is by far the most leveraged decision.

### 7.5 Risk Calibration by Pool Size

The `auto_risk_profile` adjusts contrarian-ness based on pool size:

- **Small pool (≤10):** You only need to beat 9 people. Chalk + a few smart picks wins. Conservative.
- **Medium pool (11-50):** The default 25-person case. Need to differentiate but not be reckless. Balanced.
- **Large pool (51-200):** More entrants = more chalk brackets to beat = need more contrarian picks. Aggressive.
- **Huge pool (200+):** Must be very different from the field to win. Very aggressive (not explicitly built as a separate strategy, but uses aggressive with lowered thresholds).

---

## 8. Error Handling

### 8.1 Custom Exception Hierarchy

```
class BracketOptimizerError(Exception):
    """Base exception for all bracket optimizer errors."""

class ScrapingError(BracketOptimizerError):
    """Raised when web scraping fails (network, parsing, structure change)."""

class DataError(BracketOptimizerError):
    """Raised when data is missing, malformed, or inconsistent."""

class ConfigError(BracketOptimizerError):
    """Raised when configuration is invalid."""

class BracketConsistencyError(BracketOptimizerError):
    """Raised when a bracket has inconsistent picks (team advances without winning prior)."""
```

### 8.2 Error Handling Strategy by Module

**Scout (scraping):**
- All HTTP requests wrapped in try/except with timeout handling.
- If a page structure doesn't match expected CSS selectors/table structure: raise `ScrapingError` with diagnostic message including what was expected vs found.
- Fallback: every scraping function accepts a `filepath` parameter. If the URL fails, the user can download the HTML and pass it via `--kenpom-file` etc.
- Log warnings when a team name can't be matched (fuzzy matching tolerates minor differences).
- If fewer than 68 teams found in bracket scrape: raise `ScrapingError` with count.

**Sharp (model):**
- Win probabilities clamped to [0.01, 0.99] — never 0% or 100%.
- If a team is in the bracket but not in KenPom data (extremely unlikely): use seed-based defaults for AdjEM (1-seed → +25, 16-seed → −10, etc.) and log a warning.
- NaN/infinity checks on all probability calculations.

**Contrarian (ownership):**
- Division-by-zero prevention: ownership capped at minimum 0.005 for leverage calculation.
- If ESPN picks unavailable: log info and use seed-based fallback (not an error).

**Optimizer (simulation):**
- Bracket consistency validation before and after construction. Every team in a later round must appear as the winner of their earlier round game. Violation → `BracketConsistencyError`.
- Monte Carlo progress logging every 1,000 sims.
- If 0 sims produce a 1st-place finish for any bracket: warn that sim_count may be too low.

**CLI (main.py):**
- All commands wrapped in try/except. Errors print user-friendly messages with suggestions.
- `--verbose` mode prints full stack traces.
- Exit codes: 0 = success, 1 = user error (bad args, missing data), 2 = runtime error.

---

## 9. Testing Strategy

### 9.1 Unit Tests

All tests use `unittest` (stdlib). Run via `python3 -m pytest tests/` or `python3 -m unittest discover tests/`.

**`test_models.py`:**
- Test `to_dict()` / `from_dict()` round-trip for every dataclass.
- Test default values.
- Test that invalid data (e.g., seed > 16) raises appropriate errors.

**`test_scout.py`:**
- Test KenPom parsing with fixture HTML (`fixtures/kenpom_sample.html`).
- Verify correct extraction of all fields (rank, AdjEM, AdjO, etc.).
- Test ESPN bracket parsing with fixture HTML.
- Verify 68 teams extracted with correct seeds and regions.
- Test `merge_team_data()` with known mismatched names (UConn/Connecticut).
- Test fuzzy matching edge cases.
- Test error handling when fixture has unexpected structure.

**`test_sharp.py`:**
- Test `adj_em_to_win_prob()` with known inputs:
  - Equal teams (ΔEM=0): should return 0.5.
  - 1-seed vs 16-seed (~ΔEM=30): should return ~0.95.
  - Moderate mismatch (ΔEM=10): should return ~0.72.
- Test each modifier in isolation:
  - Experience: team with 3 appearances vs team with 0 → prob increases.
  - Tempo mismatch: slow defensive team gets boost.
  - Conference momentum: power conf auto-bid gets boost.
- Test seed prior blending: verify correct weighting.
- Test matchup matrix antisymmetry: `P(A,B) + P(B,A) ≈ 1.0`.
- Test probability clamping: never below 0.01 or above 0.99.

**`test_contrarian.py`:**
- Test `estimate_seed_ownership()`: 1-seed should have ~25% title ownership, 16-seed ~0%.
- Test `calculate_leverage()`: model_prob=0.3, ownership=0.1 → leverage=3.0.
- Test leverage with near-zero ownership (floor at 0.005).
- Test `find_value_picks()`: verify filtering by min_leverage.
- Test brand-name boost application.

**`test_optimizer.py`:**
- **Deterministic simulation test:** With known probabilities and fixed random seed, verify the tournament simulation produces expected results.
- **1-seed vs 16-seed test:** Set up a bracket where every game is 1v16. Run 1000 sims. 1-seed should win >95% of sims.
- **Bracket consistency test:** After `construct_candidate_bracket()`, verify no team appears in a round without winning prior rounds.
- **Scoring test:** Construct known results and known picks, verify score calculation.
- **Rank calculation test:** Verify correct ranking with ties.
- **Public bracket generation:** Verify generated brackets are consistent and roughly follow ownership distributions.

**`test_analyst.py`:**
- Test `assign_confidence_tier()` boundaries.
- Test `explain_pick()` output includes team name, stat, and leverage.
- Test ASCII bracket is valid (correct number of lines, teams appear in right spots).
- Test markdown report has all required sections.

**`test_integration.py`:**
- End-to-end test with mock data (fixture teams + fixture bracket structure).
- Run `cmd_full()` with mock data, verify all output files created.
- Verify output JSON is parseable.
- Verify output bracket has exactly 63 picks.

**`test_bracket_integrity.py`** (CRITICAL — single-elimination invariants):
- **Single elimination rule:** Every team that loses is immediately eliminated — they must not appear in any subsequent round.
- **Exactly 1 champion:** The final bracket must have exactly one winner of the championship game.
- **No team appears twice in the same round.**
- **Winner must have won every prior game:** Trace champion backwards — they must be the winner of their semifinal, their Elite 8 game, Sweet 16, R32, and R1.
- **Every game has exactly 2 participants:** No byes in the main bracket (play-in games resolve first).
- **Advancement consistency:** If Team A is picked to win in Round N, Team A must also be picked to win in Round N-1 (they can't skip rounds).
- **63 games total:** 32 + 16 + 8 + 4 + 2 + 1 = 63 main bracket games (plus up to 4 play-in).
- **Each region produces exactly 1 Final Four team.**
- **Opponent brackets also pass all integrity checks** — the Monte Carlo sim must generate valid brackets for the simulated pool opponents too.
- Run these checks on EVERY bracket the optimizer produces (optimal + safe + aggressive alternates).

### 9.2 Edge Cases to Test

- **Play-in games:** Teams in slots 65-68 correctly resolve before R1.
- **Identical AdjEM:** Two teams with identical stats → ~50/50.
- **Extreme mismatch:** AdjEM diff > 40 → probability near 1.0 but not exactly 1.0.
- **All chalk bracket:** Verify it can be constructed (no upsets).
- **Maximum chaos bracket:** Verify it can be constructed (every game an upset).
- **Single simulation:** `--sims 1` should work without crashing.
- **Pool size 1:** Only us, should always finish 1st.
- **Empty ESPN picks:** Fallback to seed-based ownership should work seamlessly.
- **Name matching failures:** Team in bracket not found in KenPom → proper error message with the unmatched name.

### 9.3 Fixture Data

Create fixture HTML files by saving actual KenPom/ESPN pages (sanitized). Also create `mock_teams.json` and `mock_bracket_structure.json` with 16-team (4 regions × 4 teams) mini-brackets for faster testing.

The 16-team mini-bracket is useful for optimizer tests (reduces simulation time 10x while preserving structural correctness).

---

## 10. Dependencies

### 10.1 Third-Party

| Package | Version | Purpose |
|---------|---------|---------|
| `beautifulsoup4` | ≥4.12 | HTML parsing for KenPom and ESPN scraping |

**That's it.** One dependency.

### 10.2 Standard Library Modules Used

| Module | Purpose |
|--------|---------|
| `urllib.request` | HTTP fetching (no requests library) |
| `urllib.error` | HTTP error handling |
| `json` | JSON serialization/deserialization |
| `math` | `log`, `exp`, `sqrt` for probability calculations |
| `random` | `Random` class for Monte Carlo simulation |
| `statistics` | `mean`, `median` for aggregate results |
| `dataclasses` | `@dataclass`, `field`, `asdict` for data models |
| `argparse` | CLI argument parsing |
| `logging` | Structured logging |
| `pathlib` | File path handling |
| `typing` | Type hints |
| `collections` | `defaultdict`, `Counter` |
| `copy` | `deepcopy` for bracket perturbation |
| `hashlib` | Default random seed from date |
| `datetime` | Date handling for default seed |
| `unittest` | Testing framework |
| `textwrap` | ASCII bracket text formatting |
| `os` | Environment/path utilities |

### 10.3 Installation

```
pip install beautifulsoup4
```

Or with a requirements.txt:
```
beautifulsoup4>=4.12
```

---

## 11. Implementation Order

Build and test in this order. Each module should be fully testable before starting the next.

### Phase 1: Foundation (Days 1-2)

1. **`src/models.py`** — All dataclasses with `to_dict()` / `from_dict()`. This is the shared vocabulary.
   - Test: `test_models.py`

2. **`src/constants.py`** — Historical data tables, URLs, team name aliases.
   - No tests needed (static data).

3. **`src/config.py`** — Config loading, defaults, risk profile calculation.
   - Test: basic config loading tests in `test_integration.py`.

4. **`src/utils.py`** — `fetch_url()`, `load_json()`, `save_json()`, logging setup.
   - Test: JSON round-trip, URL fetching with mock.

5. **`config.json`** — Default configuration file.

### Phase 2: Data Collection (Day 3)

6. **`src/scout.py`** — Scraping functions. Start with `scrape_kenpom()` since we know it works.
   - Build fixture HTML files for testing.
   - Test: `test_scout.py` with fixtures.
   - Milestone: `python3 main.py collect` produces `data/teams.json` and `data/bracket_structure.json`.

### Phase 3: Statistical Model (Day 4)

7. **`src/sharp.py`** — Win probability engine. Build and test each function in isolation.
   - Test: `test_sharp.py` — verify probability calculations against known values.
   - Milestone: `data/matchup_probabilities.json` is generated.

### Phase 4: Ownership & Leverage (Day 5)

8. **`src/contrarian.py`** — Ownership estimation and leverage calculation.
   - Test: `test_contrarian.py`.
   - Milestone: `data/ownership.json` is generated with leverage scores.

### Phase 5: The Engine (Days 6-8)

9. **`src/optimizer.py`** — The big one. Build in sub-stages:
   a. `simulate_tournament()` — single sim works correctly.
   b. `score_bracket()` — scoring is correct.
   c. `generate_public_bracket()` — opponent generation works.
   d. `evaluate_bracket_in_pool()` — pool ranking works.
   e. `construct_candidate_bracket()` — bracket construction with constraints.
   f. `run_monte_carlo()` — full sim loop.
   g. `optimize_bracket()` — perturbation search.
   - Test: `test_optimizer.py` at each sub-stage.
   - Milestone: `data/optimal_brackets.json` with 3 brackets and P(1st) estimates.

### Phase 6: Output (Day 9)

10. **`src/analyst.py`** — Report generation. Can be built once we have bracket data (even mock data).
    - Test: `test_analyst.py`.
    - Milestone: `output/analysis.md` and `output/bracket.txt` are generated.

### Phase 7: Integration (Day 10)

11. **`main.py`** — CLI dispatcher. Wire all modules together.
    - Test: `test_integration.py` — full end-to-end with mock data.
    - Milestone: `python3 main.py full` runs the complete pipeline.

### Phase 8: Polish

12. Error messages, logging quality, edge case handling.
13. Performance: profile Monte Carlo, optimize if needed (10K sims × 25 opponents × 63 games should take <60 seconds on modern hardware).
14. README.md with usage instructions.

---

## Appendix A: Example config.json

```json
{
    "pool_size": 25,
    "scoring": [10, 20, 40, 80, 160, 320],
    "sim_count": 10000,
    "risk_profile": "auto",
    "champion_min_leverage": 1.5,
    "min_contrarian_ff": 1,
    "max_r1_upsets": 3,
    "random_seed": null
}
```

## Appendix B: Example Output Structure

**`output/analysis.md`** (abbreviated):

```markdown
# 🏀 March Madness 2026 — Optimized Bracket

## Summary
- **Champion:** Houston (3-seed, South) — 🎲 Gamble
- **Final Four:** Duke, Houston, Purdue, Marquette
- **P(1st place in 25-person pool):** 8.3%
- **P(Top 3):** 19.7%
- **Expected finish:** 6.2
- **Expected score:** 1,040

## Key Differentiators
Your bracket stands out from the field in these picks:

1. **Houston as Champion** (Leverage: 2.8) — Only 7% of public brackets...
2. **Marquette to Final Four** (Leverage: 2.1) — ...
...

## Round-by-Round Breakdown
### Round 1 (10 pts each)
| Game | Pick | Seed | Confidence | Win Prob |
|------|------|------|-----------|----------|
| (1) Duke vs (16) Norfolk St | Duke | 1 | 🔒 Lock | 0.98 |
...
```

## Appendix C: Performance Estimates

For 10,000 simulations with a 25-person pool:
- **Tournament simulations:** 10,000 × 63 games = 630,000 game resolutions
- **Opponent bracket generation:** 10,000 × 25 × 63 = 15,750,000 game picks
- **Scoring:** 10,000 × 26 × 63 = 16,380,000 score checks
- **Total operations:** ~33M simple operations → **<30 seconds** on modern hardware with pure Python
- **With perturbation search** (8 candidates × 10,000 sims): ~**4 minutes** total

If performance is an issue, the biggest win is reducing `sim_count` to 5,000 (minimal accuracy loss) or reducing perturbation candidates.

## Appendix D: Team Name Fuzzy Matching Algorithm

Since KenPom and ESPN use different team name formats, `merge_team_data()` needs a matching strategy:

1. **Exact match** — try first.
2. **Alias lookup** — check `TEAM_NAME_ALIASES` dict.
3. **Normalized match** — lowercase, strip periods/apostrophes, collapse whitespace. "St. John's (NY)" → "st johns ny", "St. John's" → "st johns".
4. **Substring containment** — if one name contains the other (e.g., "North Carolina" in "North Carolina Tar Heels").
5. **Failure** — raise `DataError` with both names for manual resolution.

Log every non-exact match at INFO level so the user can verify.
