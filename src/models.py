"""Data models for the bracket optimizer.

All dataclasses support JSON serialization via to_dict() and from_dict() methods.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Team:
    """Represents a tournament team with stats and seeding information.
    
    Attributes:
        name: Team name (e.g., "Gonzaga").
        seed: Tournament seed (1-16).
        region: Region assignment ("East", "West", "South", "Midwest").
        kenpom_rank: KenPom ranking (1-363).
        adj_em: Adjusted Efficiency Margin.
        adj_o: Adjusted Offensive Efficiency.
        adj_d: Adjusted Defensive Efficiency.
        adj_t: Adjusted Tempo (possessions per 40 min).
        sos: Strength of Schedule.
        wins: Regular season wins.
        losses: Regular season losses.
        conference: Conference affiliation (e.g., "WCC", "SEC").
        tournament_appearances: Sweet 16+ appearances in last 3 years.
        is_auto_bid: Won conference tournament.
        bracket_position: Slot position in 68-team bracket (1-68).
    """
    name: str
    seed: int = 0
    region: str = ""
    kenpom_rank: int = 0
    adj_em: float = 0.0
    adj_o: float = 0.0
    adj_d: float = 0.0
    adj_t: float = 67.5
    luck: float = 0.0
    sos: float = 0.0
    wins: int = 0
    losses: int = 0
    conference: str = ""
    tournament_appearances: int = 0
    is_auto_bid: bool = False
    bracket_position: int = 0
    # Phase 2 fields (Torvik, momentum, betting)
    barthag: Optional[float] = None
    wab: Optional[float] = None
    last10_adj_em: Optional[float] = None
    last10_win_pct: Optional[float] = None
    spread: Optional[float] = None
    # LRMC fields (top-25 performance)
    top25_wins: Optional[int] = None
    top25_losses: Optional[int] = None
    top25_games: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        d = {
            "name": self.name,
            "seed": self.seed,
            "region": self.region,
            "kenpom_rank": self.kenpom_rank,
            "adj_em": self.adj_em,
            "adj_o": self.adj_o,
            "adj_d": self.adj_d,
            "adj_t": self.adj_t,
            "luck": self.luck,
            "sos": self.sos,
            "wins": self.wins,
            "losses": self.losses,
            "conference": self.conference,
            "tournament_appearances": self.tournament_appearances,
            "is_auto_bid": self.is_auto_bid,
            "bracket_position": self.bracket_position
        }
        # Only include Phase 2 fields if set
        if self.barthag is not None:
            d["barthag"] = self.barthag
        if self.wab is not None:
            d["wab"] = self.wab
        if self.last10_adj_em is not None:
            d["last10_adj_em"] = self.last10_adj_em
        if self.last10_win_pct is not None:
            d["last10_win_pct"] = self.last10_win_pct
        if self.spread is not None:
            d["spread"] = self.spread
        if self.top25_wins is not None:
            d["top25_wins"] = self.top25_wins
        if self.top25_losses is not None:
            d["top25_losses"] = self.top25_losses
        if self.top25_games is not None:
            d["top25_games"] = self.top25_games
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> 'Team':
        """Create Team from dictionary."""
        return cls(
            name=d["name"],
            seed=d.get("seed", 0),
            region=d.get("region", ""),
            kenpom_rank=d.get("kenpom_rank", 0),
            adj_em=d.get("adj_em", 0.0),
            adj_o=d.get("adj_o", 0.0),
            adj_d=d.get("adj_d", 0.0),
            adj_t=d.get("adj_t", 67.5),
            luck=d.get("luck", 0.0),
            sos=d.get("sos", 0.0),
            wins=d.get("wins", 0),
            losses=d.get("losses", 0),
            conference=d.get("conference", ""),
            tournament_appearances=d.get("tournament_appearances", 0),
            is_auto_bid=d.get("is_auto_bid", False),
            bracket_position=d.get("bracket_position", 0),
            barthag=d.get("barthag"),
            wab=d.get("wab"),
            last10_adj_em=d.get("last10_adj_em"),
            last10_win_pct=d.get("last10_win_pct"),
            spread=d.get("spread"),
            top25_wins=d.get("top25_wins"),
            top25_losses=d.get("top25_losses"),
            top25_games=d.get("top25_games"),
        )


@dataclass
class Matchup:
    """Represents a single game matchup with win probability.
    
    Attributes:
        team_a: Team name (key into teams dict).
        team_b: Team name.
        round_num: Tournament round (1-6).
        win_prob_a: Probability team_a wins (0.0-1.0).
        raw_prob_a: Probability before modifiers applied.
        modifiers_applied: List of modifier names applied.
    """
    team_a: str
    team_b: str
    round_num: int
    win_prob_a: float
    raw_prob_a: float
    modifiers_applied: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "team_a": self.team_a,
            "team_b": self.team_b,
            "round_num": self.round_num,
            "win_prob_a": self.win_prob_a,
            "raw_prob_a": self.raw_prob_a,
            "modifiers_applied": self.modifiers_applied
        }
    
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> 'Matchup':
        """Create Matchup from dictionary."""
        return cls(
            team_a=d["team_a"],
            team_b=d["team_b"],
            round_num=d["round_num"],
            win_prob_a=d["win_prob_a"],
            raw_prob_a=d["raw_prob_a"],
            modifiers_applied=d.get("modifiers_applied", [])
        )


@dataclass
class BracketSlot:
    """Represents a single game slot in the tournament bracket.
    
    Attributes:
        slot_id: Unique slot identifier (1-67).
        round_num: Tournament round (0-6, where 0 is play-in).
        region: Region ("East"/"West"/"South"/"Midwest"/"FinalFour").
        seed_a: Expected top seed in this slot.
        seed_b: Expected bottom seed in this slot.
        team_a: Populated team name after play-in resolution.
        team_b: Populated team name after play-in resolution.
        feeds_into: slot_id of next round game (0 for championship).
    """
    slot_id: int
    round_num: int
    region: str
    seed_a: int
    seed_b: int
    team_a: str | None = None
    team_b: str | None = None
    feeds_into: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "slot_id": self.slot_id,
            "round_num": self.round_num,
            "region": self.region,
            "seed_a": self.seed_a,
            "seed_b": self.seed_b,
            "team_a": self.team_a,
            "team_b": self.team_b,
            "feeds_into": self.feeds_into
        }
    
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> 'BracketSlot':
        """Create BracketSlot from dictionary."""
        return cls(
            slot_id=d["slot_id"],
            round_num=d["round_num"],
            region=d["region"],
            seed_a=d["seed_a"],
            seed_b=d["seed_b"],
            team_a=d.get("team_a"),
            team_b=d.get("team_b"),
            feeds_into=d.get("feeds_into", 0)
        )


@dataclass
class BracketStructure:
    """Represents the complete tournament bracket structure.
    
    Attributes:
        slots: All 67 game slots (63 main + 4 play-in).
        regions: Region name to list of team names in seed order.
        play_in_games: List of 4 play-in matchups as (team_a, team_b) tuples.
    """
    slots: list[BracketSlot]
    regions: dict[str, list[str]]
    play_in_games: list[tuple[str, str]] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "slots": [slot.to_dict() for slot in self.slots],
            "regions": self.regions,
            "play_in_games": self.play_in_games
        }
    
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> 'BracketStructure':
        """Create BracketStructure from dictionary."""
        return cls(
            slots=[BracketSlot.from_dict(s) for s in d["slots"]],
            regions=d["regions"],
            play_in_games=[tuple(g) for g in d.get("play_in_games", [])]
        )


@dataclass
class BracketPick:
    """Represents a single pick in a completed bracket.
    
    Attributes:
        slot_id: Which game slot.
        round_num: Which tournament round.
        winner: Team name picked to win.
        confidence: "lock" | "lean" | "gamble".
        leverage_score: Leverage value at this pick.
        is_upset: Whether picked the lower seed.
    """
    slot_id: int
    round_num: int
    winner: str
    confidence: str
    leverage_score: float
    is_upset: bool
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "slot_id": self.slot_id,
            "round_num": self.round_num,
            "winner": self.winner,
            "confidence": self.confidence,
            "leverage_score": self.leverage_score,
            "is_upset": self.is_upset
        }
    
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> 'BracketPick':
        """Create BracketPick from dictionary."""
        return cls(
            slot_id=d["slot_id"],
            round_num=d["round_num"],
            winner=d["winner"],
            confidence=d["confidence"],
            leverage_score=d["leverage_score"],
            is_upset=d["is_upset"]
        )


@dataclass
class CompleteBracket:
    """Represents a complete bracket with all picks and metadata.
    
    Attributes:
        picks: All 67 picks (63 main + 4 play-in).
        champion: Team picked to win championship.
        final_four: 4 Final Four teams.
        elite_eight: 8 Elite Eight teams.
        label: "optimal", "safe", "aggressive".
        expected_score: Expected ESPN score.
        p_first_place: P(finishing 1st in pool).
        p_top_three: P(finishing top 3).
        expected_finish: Expected finish position.
    """
    picks: list[BracketPick]
    champion: str
    final_four: list[str]
    elite_eight: list[str]
    label: str
    expected_score: float
    p_first_place: float
    p_top_three: float
    expected_finish: float
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "picks": [pick.to_dict() for pick in self.picks],
            "champion": self.champion,
            "final_four": self.final_four,
            "elite_eight": self.elite_eight,
            "label": self.label,
            "expected_score": self.expected_score,
            "p_first_place": self.p_first_place,
            "p_top_three": self.p_top_three,
            "expected_finish": self.expected_finish
        }
    
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> 'CompleteBracket':
        """Create CompleteBracket from dictionary."""
        return cls(
            picks=[BracketPick.from_dict(p) for p in d["picks"]],
            champion=d["champion"],
            final_four=d["final_four"],
            elite_eight=d["elite_eight"],
            label=d["label"],
            expected_score=d["expected_score"],
            p_first_place=d["p_first_place"],
            p_top_three=d["p_top_three"],
            expected_finish=d["expected_finish"]
        )


@dataclass
class OwnershipProfile:
    """Represents public ownership and leverage for a team.
    
    Attributes:
        team: Team name.
        seed: Tournament seed.
        round_ownership: Round number to percentage of public picking team to reach that round.
        leverage_by_round: Round number to leverage score.
        title_ownership: Percentage picking as champion.
        title_leverage: Model title probability / public title ownership.
    """
    team: str
    seed: int
    round_ownership: dict[int, float]
    leverage_by_round: dict[int, float]
    title_ownership: float
    title_leverage: float
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "team": self.team,
            "seed": self.seed,
            "round_ownership": {str(k): v for k, v in self.round_ownership.items()},
            "leverage_by_round": {str(k): v for k, v in self.leverage_by_round.items()},
            "title_ownership": self.title_ownership,
            "title_leverage": self.title_leverage
        }
    
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> 'OwnershipProfile':
        """Create OwnershipProfile from dictionary."""
        return cls(
            team=d["team"],
            seed=d["seed"],
            round_ownership={int(k): v for k, v in d["round_ownership"].items()},
            leverage_by_round={int(k): v for k, v in d["leverage_by_round"].items()},
            title_ownership=d["title_ownership"],
            title_leverage=d["title_leverage"]
        )


@dataclass
class SimResult:
    """Represents the result of a single Monte Carlo simulation.
    
    Attributes:
        sim_id: Simulation number.
        actual_results: Slot ID to winning team name (ground truth).
        our_score: Our bracket score in this sim.
        our_rank: 1-based rank in pool (1 = we won).
        opponent_scores: Scores of opponent brackets.
        champion: Who won the tournament in this sim.
    """
    sim_id: int
    actual_results: dict[int, str]
    our_score: int
    our_rank: int
    opponent_scores: list[int]
    champion: str
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "sim_id": self.sim_id,
            "actual_results": {str(k): v for k, v in self.actual_results.items()},
            "our_score": self.our_score,
            "our_rank": self.our_rank,
            "opponent_scores": self.opponent_scores,
            "champion": self.champion
        }
    
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> 'SimResult':
        """Create SimResult from dictionary."""
        return cls(
            sim_id=d["sim_id"],
            actual_results={int(k): v for k, v in d["actual_results"].items()},
            our_score=d["our_score"],
            our_rank=d["our_rank"],
            opponent_scores=d["opponent_scores"],
            champion=d["champion"]
        )


@dataclass
class AggregateResults:
    """Aggregated results across all Monte Carlo simulations.
    
    Attributes:
        total_sims: Number of simulations run.
        p_first_place: Percentage of sims we finished 1st.
        p_top_three: Percentage of sims we finished top 3.
        expected_finish: Mean finish position.
        expected_score: Mean bracket score.
        median_score: Median bracket score.
        champion_frequency: Team to percentage of sims they won title.
        value_picks: Picks with highest leverage contribution.
    """
    total_sims: int
    p_first_place: float
    p_top_three: float
    expected_finish: float
    expected_score: float
    median_score: float
    champion_frequency: dict[str, float]
    value_picks: list[dict[str, Any]]
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_sims": self.total_sims,
            "p_first_place": self.p_first_place,
            "p_top_three": self.p_top_three,
            "expected_finish": self.expected_finish,
            "expected_score": self.expected_score,
            "median_score": self.median_score,
            "champion_frequency": self.champion_frequency,
            "value_picks": self.value_picks
        }
    
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> 'AggregateResults':
        """Create AggregateResults from dictionary."""
        return cls(
            total_sims=d["total_sims"],
            p_first_place=d["p_first_place"],
            p_top_three=d["p_top_three"],
            expected_finish=d["expected_finish"],
            expected_score=d["expected_score"],
            median_score=d["median_score"],
            champion_frequency=d["champion_frequency"],
            value_picks=d["value_picks"]
        )


@dataclass
class Config:
    """Application configuration.
    
    Attributes:
        pool_size: Number of entrants in pool.
        scoring: Points per round [R1, R2, S16, E8, F4, Championship].
        sim_count: Number of Monte Carlo simulations.
        risk_profile: "conservative"|"balanced"|"aggressive"|"auto".
        champion_min_leverage: Minimum leverage for champion pick.
        min_contrarian_ff: Minimum number of FF picks with <15% ownership.
        max_r1_upsets: Maximum Round 1 upsets.
        data_dir: Directory for intermediate data.
        output_dir: Directory for final output.
        kenpom_url: KenPom ratings URL.
        espn_bracket_url: ESPN Bracketology URL.
        espn_picks_url: ESPN Tournament Challenge URL.
        kenpom_file: Local file override for KenPom.
        espn_bracket_file: Local file override for ESPN bracket.
        espn_picks_file: Local file override for ESPN picks.
        random_seed: Random seed for reproducibility (None = use date hash).
        year: Tournament year.
        espn_cache_max_age_hours: Max age of ESPN picks cache before refresh.
        force_espn_refresh: Force fresh ESPN picks scrape (bypass cache).
        no_espn: Skip ESPN picks scraping entirely (use seed-based).
        strict_espn: Require real ESPN data (fail if unavailable). Default True.
    """
    pool_size: int = 25
    scoring: list[int] = field(default_factory=lambda: [10, 20, 40, 80, 160, 320])
    sim_count: int = 10000
    risk_profile: str = "auto"
    champion_min_leverage: float = 1.5
    min_contrarian_ff: int = 1
    max_r1_upsets: int = 3
    data_dir: str = "data"
    output_dir: str = "results/output"
    kenpom_url: str = "https://kenpom.com"
    espn_bracket_url: str = "https://www.espn.com/mens-college-basketball/bracketology"
    espn_picks_url: str = "https://fantasy.espn.com/tournament-challenge-bracket/"
    kenpom_file: str | None = None
    espn_bracket_file: str | None = None
    espn_picks_file: str | None = None
    random_seed: int | None = None
    year: int = 2026
    espn_cache_max_age_hours: float = 2.0
    force_espn_refresh: bool = False
    no_espn: bool = False
    strict_espn: bool = True
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "pool_size": self.pool_size,
            "scoring": self.scoring,
            "sim_count": self.sim_count,
            "risk_profile": self.risk_profile,
            "champion_min_leverage": self.champion_min_leverage,
            "min_contrarian_ff": self.min_contrarian_ff,
            "max_r1_upsets": self.max_r1_upsets,
            "data_dir": self.data_dir,
            "output_dir": self.output_dir,
            "kenpom_url": self.kenpom_url,
            "espn_bracket_url": self.espn_bracket_url,
            "espn_picks_url": self.espn_picks_url,
            "kenpom_file": self.kenpom_file,
            "espn_bracket_file": self.espn_bracket_file,
            "espn_picks_file": self.espn_picks_file,
            "random_seed": self.random_seed,
            "year": self.year,
            "espn_cache_max_age_hours": self.espn_cache_max_age_hours,
            "force_espn_refresh": self.force_espn_refresh,
            "no_espn": self.no_espn,
            "strict_espn": self.strict_espn
        }
    
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> 'Config':
        """Create Config from dictionary."""
        return cls(
            pool_size=d.get("pool_size", 25),
            scoring=d.get("scoring", [10, 20, 40, 80, 160, 320]),
            sim_count=d.get("sim_count", 10000),
            risk_profile=d.get("risk_profile", "auto"),
            champion_min_leverage=d.get("champion_min_leverage", 1.5),
            min_contrarian_ff=d.get("min_contrarian_ff", 1),
            max_r1_upsets=d.get("max_r1_upsets", 3),
            data_dir=d.get("data_dir", "data"),
            output_dir=d.get("output_dir", "output"),
            kenpom_url=d.get("kenpom_url", "https://kenpom.com"),
            espn_bracket_url=d.get("espn_bracket_url", "https://www.espn.com/mens-college-basketball/bracketology"),
            espn_picks_url=d.get("espn_picks_url", "https://fantasy.espn.com/tournament-challenge-bracket/"),
            kenpom_file=d.get("kenpom_file"),
            espn_bracket_file=d.get("espn_bracket_file"),
            espn_picks_file=d.get("espn_picks_file"),
            random_seed=d.get("random_seed"),
            year=d.get("year", 2026),
            espn_cache_max_age_hours=d.get("espn_cache_max_age_hours", 2.0),
            force_espn_refresh=d.get("force_espn_refresh", False),
            no_espn=d.get("no_espn", False),
            strict_espn=d.get("strict_espn", True)
        )


class BracketOptimizerError(Exception):
    """Base exception for all bracket optimizer errors."""
    pass


class ScrapingError(BracketOptimizerError):
    """Raised when web scraping fails (network, parsing, structure change)."""
    pass


class DataError(BracketOptimizerError):
    """Raised when data is missing, malformed, or inconsistent."""
    pass


class ConfigError(BracketOptimizerError):
    """Raised when configuration is invalid."""
    pass


class BracketConsistencyError(BracketOptimizerError):
    """Raised when a bracket has inconsistent picks."""
    pass


@dataclass
class ChampionCandidate:
    """A team evaluated as a potential tournament champion.
    
    Attributes:
        team_name: Team name string (key into team/ownership maps).
        seed: Tournament seed (1-16).
        region: Tournament region.
        title_prob: Probability of winning the tournament (from quick Monte Carlo).
        title_ownership: Fraction of public brackets picking this team as champion.
        path_difficulty: Product of P(champion beats each opponent on most likely path).
                        Range [0, 1]. 1.0 = easiest possible path. Lower = harder.
        pool_value: Pool-size-adjusted champion value = title_prob / ((N-1) * ownership + 1).
        adjusted_value: pool_value * sqrt(path_difficulty). Final ranking score.
    """
    team_name: str
    seed: int
    region: str
    title_prob: float
    title_ownership: float
    path_difficulty: float
    pool_value: float
    adjusted_value: float
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "team_name": self.team_name,
            "seed": self.seed,
            "region": self.region,
            "title_prob": self.title_prob,
            "title_ownership": self.title_ownership,
            "path_difficulty": self.path_difficulty,
            "pool_value": self.pool_value,
            "adjusted_value": self.adjusted_value
        }
    
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> 'ChampionCandidate':
        """Create ChampionCandidate from dictionary."""
        return cls(
            team_name=d["team_name"],
            seed=d["seed"],
            region=d["region"],
            title_prob=d["title_prob"],
            title_ownership=d["title_ownership"],
            path_difficulty=d["path_difficulty"],
            pool_value=d["pool_value"],
            adjusted_value=d["adjusted_value"]
        )


@dataclass
class Scenario:
    """A coherent tournament narrative that drives bracket construction.
    
    Attributes:
        scenario_id: Unique identifier (e.g., "chalk_0", "contrarian_1", "chaos_2").
        scenario_type: One of "chalk", "contrarian", "chaos".
        champion: Team name picked to win it all.
        champion_seed: Seed of champion (for logging/validation).
        final_four: Dict mapping region name → team name for each FF slot.
        chaos_regions: List of region names where above-average upset activity is expected.
                      Empty for chalk scenarios. 1-2 regions for contrarian. 2+ for chaos.
        cinderella: Team name of a low seed with a deep run (None if no Cinderella).
        cinderella_target_round: How far the Cinderella should advance (3=S16, 4=E8). 
                                None if no Cinderella.
        chaos_level: "LOW", "MEDIUM", or "HIGH". Controls upset budget.
    """
    scenario_id: str
    scenario_type: str
    champion: str
    champion_seed: int
    final_four: dict[str, str]
    chaos_regions: list[str]
    cinderella: str | None
    cinderella_target_round: int | None
    chaos_level: str
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "scenario_id": self.scenario_id,
            "scenario_type": self.scenario_type,
            "champion": self.champion,
            "champion_seed": self.champion_seed,
            "final_four": self.final_four,
            "chaos_regions": self.chaos_regions,
            "cinderella": self.cinderella,
            "cinderella_target_round": self.cinderella_target_round,
            "chaos_level": self.chaos_level
        }
    
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> 'Scenario':
        """Create Scenario from dictionary."""
        return cls(
            scenario_id=d["scenario_id"],
            scenario_type=d["scenario_type"],
            champion=d["champion"],
            champion_seed=d["champion_seed"],
            final_four=d["final_four"],
            chaos_regions=d["chaos_regions"],
            cinderella=d.get("cinderella"),
            cinderella_target_round=d.get("cinderella_target_round"),
            chaos_level=d["chaos_level"]
        )


@dataclass
class PathInfo:
    """The most likely path a team takes through the bracket to a target round.
    
    Attributes:
        team_name: Team following this path.
        target_round: The round this path reaches (5=FF, 6=championship).
        opponents: List of (slot_id, opponent_name, win_prob) tuples representing
                  each game the team must win, ordered R1 → target_round.
        path_probability: Product of all win_prob values. P(team wins every game on this path).
        path_slots: List of slot_ids that this path occupies (these picks are locked).
    """
    team_name: str
    target_round: int
    opponents: list[tuple[int, str, float]]
    path_probability: float
    path_slots: list[int]
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "team_name": self.team_name,
            "target_round": self.target_round,
            "opponents": self.opponents,
            "path_probability": self.path_probability,
            "path_slots": self.path_slots
        }
    
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> 'PathInfo':
        """Create PathInfo from dictionary."""
        return cls(
            team_name=d["team_name"],
            target_round=d["target_round"],
            opponents=[tuple(o) for o in d["opponents"]],
            path_probability=d["path_probability"],
            path_slots=d["path_slots"]
        )


@dataclass
class UpsetCandidate:
    """A potential upset pick evaluated for Expected Marginal Value.
    
    Attributes:
        slot_id: The game slot where the upset occurs.
        round_num: Tournament round (1-4).
        favorite: Team name of the higher-seeded team.
        underdog: Team name of the lower-seeded team.
        fav_seed: Favorite's seed number.
        dog_seed: Underdog's seed number.
        upset_prob: P(underdog wins this game).
        fav_ownership: Fraction of public brackets picking the favorite to advance past this round.
        dog_ownership: Fraction of public brackets picking the underdog to advance past this round.
        emv: Expected Marginal Value. Positive = picking this upset increases P(1st).
        ups: Upset Propensity Score (from sharp.py).
        advancement_prob: P(underdog wins R2 | underdog wins R1). From UPSET_ADVANCEMENT_RATE.
        region: The region this game is in.
        on_ff_path: True if either team in this game is on a Final Four path (skip if True).
    """
    slot_id: int
    round_num: int
    favorite: str
    underdog: str
    fav_seed: int
    dog_seed: int
    upset_prob: float
    fav_ownership: float
    dog_ownership: float
    emv: float
    ups: float
    advancement_prob: float
    region: str
    on_ff_path: bool
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "slot_id": self.slot_id,
            "round_num": self.round_num,
            "favorite": self.favorite,
            "underdog": self.underdog,
            "fav_seed": self.fav_seed,
            "dog_seed": self.dog_seed,
            "upset_prob": self.upset_prob,
            "fav_ownership": self.fav_ownership,
            "dog_ownership": self.dog_ownership,
            "emv": self.emv,
            "ups": self.ups,
            "advancement_prob": self.advancement_prob,
            "region": self.region,
            "on_ff_path": self.on_ff_path
        }
    
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> 'UpsetCandidate':
        """Create UpsetCandidate from dictionary."""
        return cls(
            slot_id=d["slot_id"],
            round_num=d["round_num"],
            favorite=d["favorite"],
            underdog=d["underdog"],
            fav_seed=d["fav_seed"],
            dog_seed=d["dog_seed"],
            upset_prob=d["upset_prob"],
            fav_ownership=d["fav_ownership"],
            dog_ownership=d["dog_ownership"],
            emv=d["emv"],
            ups=d["ups"],
            advancement_prob=d["advancement_prob"],
            region=d["region"],
            on_ff_path=d["on_ff_path"]
        )


@dataclass
class EvaluatedBracket:
    """A complete bracket with Monte Carlo evaluation results attached.
    
    Wraps CompleteBracket with richer evaluation metadata for comparison and selection.
    
    Attributes:
        bracket: The underlying CompleteBracket.
        scenario_id: Which scenario produced this bracket (for traceability).
        p_first: P(finishing 1st in pool).
        p_top_three: P(finishing top 3 in pool).
        expected_finish: Mean finish position.
        expected_score: Mean bracket score.
        champion_correct_rate: Fraction of sims where our champion won.
        p_first_given_champion_correct: P(1st | our champion wins). Key diagnostic metric.
        num_r1_upsets: Count of R1 upset picks.
        num_distinct_picks: Number of picks that differ from pure chalk.
    """
    bracket: CompleteBracket
    scenario_id: str
    p_first: float
    p_top_three: float
    expected_finish: float
    expected_score: float
    champion_correct_rate: float
    p_first_given_champion_correct: float
    num_r1_upsets: int
    num_distinct_picks: int
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "bracket": self.bracket.to_dict(),
            "scenario_id": self.scenario_id,
            "p_first": self.p_first,
            "p_top_three": self.p_top_three,
            "expected_finish": self.expected_finish,
            "expected_score": self.expected_score,
            "champion_correct_rate": self.champion_correct_rate,
            "p_first_given_champion_correct": self.p_first_given_champion_correct,
            "num_r1_upsets": self.num_r1_upsets,
            "num_distinct_picks": self.num_distinct_picks
        }
    
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> 'EvaluatedBracket':
        """Create EvaluatedBracket from dictionary."""
        return cls(
            bracket=CompleteBracket.from_dict(d["bracket"]),
            scenario_id=d["scenario_id"],
            p_first=d["p_first"],
            p_top_three=d["p_top_three"],
            expected_finish=d["expected_finish"],
            expected_score=d["expected_score"],
            champion_correct_rate=d["champion_correct_rate"],
            p_first_given_champion_correct=d["p_first_given_champion_correct"],
            num_r1_upsets=d["num_r1_upsets"],
            num_distinct_picks=d["num_distinct_picks"]
        )
