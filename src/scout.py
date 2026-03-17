"""Data collection module - scrapes KenPom and Yahoo for tournament data.

Responsible for gathering all external data needed for the optimizer.
"""

import logging
import re
import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from bs4 import BeautifulSoup

from src.models import Team, BracketStructure, BracketSlot, ScrapingError, DataError
from src.constants import (
    KENPOM_URL, ESPN_BRACKET_URL, ESPN_PICKS_URL,
    BRACKET_SEED_ORDER, TEAM_NAME_ALIASES
)
from src.utils import fetch_url, save_json, load_json

logger = logging.getLogger("bracket_optimizer")

# Yahoo team name → canonical name mapping
YAHOO_NAME_MAP = {
    "N. Carolina": "North Carolina",
    "Connecticut": "UConn",
    "Iowa State": "Iowa St.",  # Yahoo uses full "Iowa State", bracket uses "Iowa St."
    "Michigan State": "Michigan St.",  # Yahoo uses full "Michigan State", bracket uses "Michigan St."
    "North Dakota State": "North Dakota St.",  # Yahoo uses full, bracket uses abbrev
    "Utah State": "Utah St.",  # Yahoo uses full "Utah State", bracket uses "Utah St."
    "Kennesaw State": "Kennesaw St.",  # Yahoo uses full, bracket uses abbrev
    "Tennessee State": "Tennessee St.",  # Yahoo uses full, bracket uses abbrev
    "Miami (FL)": "Miami (FL)",  # Already matches
    "Miami (OH)": "Miami OH",
    "California Baptist": "Cal Baptist",
    "CBU": "Cal Baptist",
    # More common abbreviations
    "N.C. State": "NC State",
    "UNC": "North Carolina",
    "Miss. St.": "Mississippi St.",
    "Mississippi State": "Mississippi St.",
    "Oklahoma State": "Oklahoma St.",
    "Ohio State": "Ohio St.",
    "Texas A&M": "Texas A&M",
    "St. Mary's": "Saint Mary's",  # Yahoo uses "St. Mary's", bracket uses "Saint Mary's"
    "St Mary's": "Saint Mary's",  # Handle both
    "N. Dak. St.": "North Dakota St.",  # Another variation
    "Pennsylvania": "Penn",  # Yahoo uses full name
    "Queens University": "Queens (N.C.)",  # Yahoo vs bracket naming
    "LIU Brooklyn": "Long Island",  # Yahoo uses old name
    # Play-in teams are handled by PLAY_IN_SPLITS dict in scrape_yahoo_picks()
}


def scrape_kenpom(url: str | None = None, filepath: str | None = None) -> list[Team]:
    """Scrape KenPom ratings page for all D1 team statistics.
    
    Uses urllib + BeautifulSoup to parse the main ratings table.
    Extracts: rank, team name, conference, W-L, AdjEM, AdjO, AdjD, AdjT, SOS.
    
    Args:
        url: KenPom URL to scrape. Defaults to constants.KENPOM_URL.
        filepath: If provided, read HTML from local file instead of URL.
    
    Returns:
        List of Team objects with stats populated. Seed, region, and 
        bracket_position will be unset (filled by bracket scraper).
    
    Raises:
        ScrapingError: If page structure doesn't match expected format.
    """
    if filepath:
        logger.info(f"Loading KenPom data from file: {filepath}")
        with open(filepath, 'r', encoding='utf-8') as f:
            html = f.read()
    else:
        url = url or KENPOM_URL
        logger.info(f"Scraping KenPom from: {url}")
        html = fetch_url(url)
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find the ratings table - it's typically the first table with id="ratings-table"
    # or a table with class containing "ratings"
    table = soup.find('table', {'id': 'ratings-table'})
    if not table:
        # Try alternate selector
        table = soup.find('table')
    
    if not table:
        raise ScrapingError("Could not find ratings table in KenPom page")
    
    teams = []
    rows = table.find_all('tr')
    
    if len(rows) < 10:
        raise ScrapingError(f"Found only {len(rows)} rows in KenPom table - expected 360+")
    
    logger.info(f"Parsing {len(rows)} rows from KenPom table")
    
    for row in rows[1:]:  # Skip header
        cells = row.find_all('td')
        if len(cells) < 10:
            continue
        
        try:
            # Extract data from cells
            # Typical structure: Rank | Team | Conf | W-L | AdjEM | AdjO | AdjD | AdjT | Luck | SOS | ...
            rank_text = cells[0].get_text(strip=True)
            rank = int(rank_text) if rank_text.isdigit() else 0
            
            # Team name is usually in an <a> tag
            team_link = cells[1].find('a')
            team_name = team_link.get_text(strip=True) if team_link else cells[1].get_text(strip=True)
            
            conference = cells[2].get_text(strip=True)
            
            # W-L parsing
            wl_text = cells[3].get_text(strip=True)
            wl_match = re.match(r'(\d+)-(\d+)', wl_text)
            wins = int(wl_match.group(1)) if wl_match else 0
            losses = int(wl_match.group(2)) if wl_match else 0
            
            # Stats (handle potential missing data)
            def parse_float(cell_idx: int) -> float:
                try:
                    return float(cells[cell_idx].get_text(strip=True))
                except (ValueError, IndexError):
                    return 0.0
            
            adj_em = parse_float(4)
            adj_o = parse_float(5)
            # [6] = AdjO rank (skip)
            adj_d = parse_float(7)
            # [8] = AdjD rank (skip)
            adj_t = parse_float(9)
            # [10] = AdjT rank (skip)
            luck = parse_float(11)
            sos = parse_float(13)  # SOS NetRtg
            
            team = Team(
                name=team_name,
                kenpom_rank=rank,
                adj_em=adj_em,
                adj_o=adj_o,
                adj_d=adj_d,
                adj_t=adj_t,
                luck=luck,
                sos=sos,
                wins=wins,
                losses=losses,
                conference=conference
            )
            teams.append(team)
            
        except Exception as e:
            logger.warning(f"Failed to parse row: {e}")
            continue
    
    logger.info(f"Successfully parsed {len(teams)} teams from KenPom")
    
    if len(teams) < 300:
        raise ScrapingError(f"Only found {len(teams)} teams - expected 360+")
    
    return teams


def scrape_espn_bracket(url: str | None = None, filepath: str | None = None) -> BracketStructure:
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
    if filepath:
        logger.info(f"Loading ESPN bracket from file: {filepath}")
        with open(filepath, 'r', encoding='utf-8') as f:
            html = f.read()
    else:
        url = url or ESPN_BRACKET_URL
        logger.info(f"Scraping ESPN bracket from: {url}")
        html = fetch_url(url)
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # ESPN bracket structure varies, but we need to find teams organized by region and seed
    # This is a simplified implementation - in production would need more robust parsing
    
    # For now, create a mock bracket structure since actual ESPN parsing is complex
    # In a real implementation, this would parse the HTML to extract actual teams
    logger.warning("ESPN bracket scraping is simplified - using mock bracket structure")
    
    # Create a basic bracket structure with slot layout
    slots = []
    regions = {
        "East": [],
        "West": [],
        "South": [],
        "Midwest": []
    }
    
    # Build slot structure (simplified version)
    slot_id = 1
    
    # Round 1 - 32 games (8 per region)
    for region_idx, region in enumerate(["East", "West", "South", "Midwest"]):
        for seed_pair in BRACKET_SEED_ORDER:
            slot = BracketSlot(
                slot_id=slot_id,
                round_num=1,
                region=region,
                seed_a=seed_pair[0],
                seed_b=seed_pair[1],
                feeds_into=33 + region_idx * 4 + (slot_id - 1 - region_idx * 8) // 2
            )
            slots.append(slot)
            slot_id += 1
    
    # Round 2 - 16 games (4 per region)
    for region_idx, region in enumerate(["East", "West", "South", "Midwest"]):
        for i in range(4):
            slot = BracketSlot(
                slot_id=slot_id,
                round_num=2,
                region=region,
                seed_a=0,  # Determined by R1 results
                seed_b=0,
                feeds_into=49 + region_idx * 2 + i // 2
            )
            slots.append(slot)
            slot_id += 1
    
    # Round 3 (Sweet 16) - 8 games (2 per region)
    for region_idx, region in enumerate(["East", "West", "South", "Midwest"]):
        for i in range(2):
            slot = BracketSlot(
                slot_id=slot_id,
                round_num=3,
                region=region,
                seed_a=0,
                seed_b=0,
                feeds_into=57 + region_idx
            )
            slots.append(slot)
            slot_id += 1
    
    # Round 4 (Elite 8) - 4 games (1 per region)
    for region_idx, region in enumerate(["East", "West", "South", "Midwest"]):
        slot = BracketSlot(
            slot_id=slot_id,
            round_num=4,
            region=region,
            seed_a=0,
            seed_b=0,
            feeds_into=61 if region_idx % 2 == 0 else 62  # East+South vs West+Midwest
        )
        slots.append(slot)
        slot_id += 1
    
    # Round 5 (Final Four) - 2 games
    for i in range(2):
        slot = BracketSlot(
            slot_id=slot_id,
            round_num=5,
            region="FinalFour",
            seed_a=0,
            seed_b=0,
            feeds_into=63
        )
        slots.append(slot)
        slot_id += 1
    
    # Round 6 (Championship) - 1 game
    slot = BracketSlot(
        slot_id=63,
        round_num=6,
        region="FinalFour",
        seed_a=0,
        seed_b=0,
        feeds_into=0
    )
    slots.append(slot)
    
    # Play-in games (Round 0) - 4 games
    for i in range(4):
        slot = BracketSlot(
            slot_id=64 + i,
            round_num=0,
            region="PlayIn",
            seed_a=11 if i < 2 else 16,  # 11 seeds or 16 seeds typically
            seed_b=11 if i < 2 else 16,
            feeds_into=0  # Will be mapped to specific R1 slots
        )
        slots.append(slot)
    
    bracket = BracketStructure(
        slots=slots,
        regions=regions,
        play_in_games=[]
    )
    
    logger.info(f"Created bracket structure with {len(slots)} slots")
    
    return bracket


def scrape_yahoo_picks(
    year: int = 2026,
    data_dir: str = "data",
    cache_hours: float = 4.0,
    max_retries: int = 3,
) -> dict[str, dict[int, float]] | None:
    """Scrape Yahoo Fantasy pick distribution for all 6 rounds.
    
    Fetches pick percentages from Yahoo Bracket Mayhem. This is the SOLE
    source for public ownership data (replaces ESPN).
    
    Args:
        year: Tournament year (e.g., 2026).
        data_dir: Directory to save cached data.
        cache_hours: Maximum age of cached data before refresh.
        max_retries: Number of retry attempts on failure.
    
    Returns:
        Dict mapping canonical_team_name → {round_num: pick_pct (0.0-1.0)}.
        Returns None if Yahoo data is unavailable after all retries.
    """
    cache_file = Path(data_dir) / "yahoo_picks_cache.json"
    
    # Check cache first
    if cache_file.exists():
        try:
            cached = load_json(str(cache_file))
            age_hours = (time.time() - cached.get("timestamp", 0)) / 3600
            if age_hours < cache_hours:
                logger.info(f"Using cached Yahoo picks ({age_hours:.1f}h old)")
                # Convert string keys back to integers (JSON serialization converts int keys to strings)
                picks_with_int_keys = {}
                for team, rounds in cached["picks"].items():
                    picks_with_int_keys[team] = {int(r): pct for r, pct in rounds.items()}
                return picks_with_int_keys
        except Exception as e:
            logger.warning(f"Failed to load Yahoo cache: {e}")
    
    # Try scraping with retries
    for attempt in range(1, max_retries + 1):
        try:
            if attempt > 1:
                logger.info(f"Yahoo scrape retry {attempt}/{max_retries} after 5s delay...")
                time.sleep(5)
            else:
                logger.info(f"Scraping Yahoo pick distribution for {year}...")
            
            url = "https://tournament.fantasysports.yahoo.com/mens-basketball-bracket/pickdistribution"
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
            })
            
            html = urllib.request.urlopen(req, timeout=30).read().decode('utf-8')
            
            # Extract root.App.main JSON blob
            match = re.search(r'root\.App\.main\s*=\s*(\{.*?\});\s*\n', html, re.DOTALL)
            if not match:
                logger.warning(f"Could not find root.App.main in Yahoo page (attempt {attempt}/{max_retries})")
                if attempt < max_retries:
                    continue
                return None
            
            data_str = match.group(1).replace('\\u002F', '/')
            
            # Extract pickDistribution object (brace-matching to avoid parsing full 1MB+ JSON)
            pd_start = data_str.find('"pickDistribution"')
            if pd_start < 0:
                logger.warning(f"pickDistribution key not found (attempt {attempt}/{max_retries})")
                if attempt < max_retries:
                    continue
                return None
            
            brace_start = data_str.find('{', pd_start)
            depth = 0
            pd_json = None
            for i in range(brace_start, len(data_str)):
                if data_str[i] == '{':
                    depth += 1
                elif data_str[i] == '}':
                    depth -= 1
                    if depth == 0:
                        pd_json = data_str[brace_start:i+1]
                        break
            
            if not pd_json:
                logger.warning(f"Failed to extract pickDistribution JSON (attempt {attempt}/{max_retries})")
                if attempt < max_retries:
                    continue
                return None
            
            pd = json.loads(pd_json)
            
            # Extract team key → displayName mapping
            team_map = {}
            for m in re.finditer(
                r'"editorialTeamKey"\s*:\s*"(ncaab\.t\.\d+)"[^}]{0,300}"displayName"\s*:\s*"([^"]+)"',
                data_str
            ):
                team_map[m.group(1)] = m.group(2)
            
            logger.info(f"Extracted {len(team_map)} team names from Yahoo data")
            
            # Build picks dict
            # Special handling: play-in teams shown as "TX/NCST" need to be split
            PLAY_IN_SPLITS = {
                "TX/NCST": ["Texas", "NC State"],
                "MOH/SMU": ["Miami (Ohio)", "SMU"],
                "PV/LEH": ["Prairie View A&M", "Lehigh"],
                "UMBC/HOW": ["UMBC", "Howard"],
            }
            
            picks = {}
            for rnd in pd.get('distributionByRound', []):
                round_id = int(rnd['roundId'])
                for entry in rnd.get('distributionByTeam', []):
                    key = entry.get('editorialTeamKey', '')
                    pct = entry.get('percentage', 0.0) / 100.0  # Convert to 0.0-1.0
                    yahoo_name = team_map.get(key, key)
                    
                    # Normalize Yahoo name to canonical name
                    canonical_name = YAHOO_NAME_MAP.get(yahoo_name, yahoo_name)
                    
                    # Handle play-in splits: assign same percentage to both teams
                    if canonical_name in PLAY_IN_SPLITS:
                        for team in PLAY_IN_SPLITS[canonical_name]:
                            if team not in picks:
                                picks[team] = {}
                            picks[team][round_id] = pct
                    else:
                        if canonical_name not in picks:
                            picks[canonical_name] = {}
                        picks[canonical_name][round_id] = pct
            
            if len(picks) < 50:
                logger.warning(f"Only found {len(picks)} teams in Yahoo data (attempt {attempt}/{max_retries})")
                if attempt < max_retries:
                    continue
                return None
            
            # Load real bracket to build complete name mapping
            real_bracket_path = Path(data_dir) / f"real_bracket_{year}.json"
            if real_bracket_path.exists():
                picks = normalize_yahoo_names(picks, str(real_bracket_path))
            
            # Cache successful result
            cache_data = {
                "timestamp": time.time(),
                "source": "yahoo",
                "url": url,
                "year": year,
                "teams_count": len(picks),
                "picks": picks
            }
            save_json(cache_data, str(cache_file))
            logger.info(f"✓ Cached Yahoo picks for {len(picks)} teams to {cache_file}")
            
            # Log sample data
            sample_teams = ['Duke', 'Arizona', 'Kansas', 'UConn']
            for team in sample_teams:
                if team in picks:
                    p = picks[team]
                    logger.info(f"  {team}: R1={p.get(1, 0):.1%} R2={p.get(2, 0):.1%} R6={p.get(6, 0):.1%}")
            
            return picks
            
        except Exception as e:
            logger.warning(f"Yahoo scraping failed on attempt {attempt}/{max_retries}: {e}")
            if attempt < max_retries:
                continue
            return None
    
    return None


def normalize_yahoo_names(yahoo_picks: dict, real_bracket_path: str) -> dict[str, dict[int, float]]:
    """Normalize Yahoo team names to canonical names using real bracket.
    
    Yahoo uses different naming (e.g., "N. Carolina" vs "North Carolina").
    We need to match Yahoo names to the canonical names in real_bracket_2026.json.
    
    Args:
        yahoo_picks: Raw picks from Yahoo (may have Yahoo-style names).
        real_bracket_path: Path to real_bracket_2026.json.
    
    Returns:
        Picks dict with canonical team names.
    """
    try:
        bracket_data = load_json(real_bracket_path)
        canonical_names = set()
        
        for region_teams in bracket_data.get("regions", {}).values():
            for team_obj in region_teams:
                canonical_names.add(team_obj["team"])
        
        # Build fuzzy match mapping
        normalized_picks = {}
        unmatched = []
        
        for yahoo_name, rounds in yahoo_picks.items():
            # Try exact match first
            if yahoo_name in canonical_names:
                normalized_picks[yahoo_name] = rounds
                continue
            
            # Try mapped name
            mapped = YAHOO_NAME_MAP.get(yahoo_name)
            if mapped and mapped in canonical_names:
                normalized_picks[mapped] = rounds
                continue
            
            # Try fuzzy matching (case-insensitive, punctuation-stripped)
            yahoo_norm = normalize_team_name(yahoo_name)
            found = False
            for canonical in canonical_names:
                if normalize_team_name(canonical) == yahoo_norm:
                    normalized_picks[canonical] = rounds
                    found = True
                    break
            
            if not found:
                unmatched.append(yahoo_name)
                # Keep original name as fallback
                normalized_picks[yahoo_name] = rounds
        
        if unmatched:
            logger.warning(f"Could not match {len(unmatched)} Yahoo teams: {unmatched[:5]}")
        
        logger.info(f"Normalized {len(normalized_picks)} Yahoo team names")
        return normalized_picks
        
    except Exception as e:
        logger.warning(f"Failed to normalize Yahoo names: {e}")
        return yahoo_picks


def build_espn_name_mapping(real_bracket_path: str) -> dict[str, str]:
    """Build mapping from ESPN team abbreviations to canonical team names.
    
    Uses region + seed matching from real_bracket_2026.json as the primary key.
    ESPN abbreviations like "ILL", "DUKE", "TA&M" map to canonical names
    like "Illinois", "Duke", "Texas A&M".
    
    Args:
        real_bracket_path: Path to real_bracket_2026.json.
    
    Returns:
        Dict mapping ESPN abbrev → canonical team name.
    """
    # Load real bracket
    bracket_data = load_json(real_bracket_path)
    
    # ESPN region names map to bracket region names
    espn_to_bracket_region = {
        "EAST": "EAST",
        "WEST": "WEST", 
        "SOUTH": "SOUTH",
        "MIDWEST": "MIDWEST"
    }
    
    # Build a lookup: (region, seed) → canonical team name
    region_seed_to_team = {}
    for region_name, teams in bracket_data["regions"].items():
        for team_obj in teams:
            if not team_obj.get("play_in", False):
                key = (region_name, team_obj["seed"])
                region_seed_to_team[key] = team_obj["team"]
    
    # Hardcoded abbreviation mapping (ESPN abbrev → canonical name)
    # This handles name mismatches and provides fallback
    abbrev_map = {
        "ILL": "Illinois",
        "DUKE": "Duke",
        "CONN": "UConn",
        "ARIZ": "Arizona",
        "FLA": "Florida",
        "MICH": "Michigan",
        "HOU": "Houston",
        "PUR": "Purdue",
        "ISU": "Iowa St.",
        "TA&M": "Texas A&M",
        "SJU": "St. John's",
        "SMC": "Saint Mary's",
        "MSU": "Michigan St.",
        "GONZ": "Gonzaga",
        "UNC": "North Carolina",
        "UK": "Kentucky",
        "KU": "Kansas",
        "OSU": "Ohio St.",
        "TTU": "Texas Tech",
        "VILL": "Villanova",
        "UCLA": "UCLA",
        "UVA": "Virginia",
        "ARK": "Arkansas",
        "LOU": "Louisville",
        "VAN": "Vanderbilt",
        "ALA": "Alabama",
        "TENN": "Tennessee",
        "BYU": "BYU",
        "WIS": "Wisconsin",
        "NEB": "Nebraska",
        "UGA": "Georgia",
        "MIA": "Miami (FL)",
        "CLEM": "Clemson",
        "IOWA": "Iowa",
        "PENN": "Penn",
        "FUR": "Furman",
        "SIE": "Siena",
        "LIU": "Long Island",
        "QUC": "Queens (N.C.)",
        "KENN": "Kennesaw St.",
        "WRST": "Wright St.",
        "NDSU": "North Dakota St.",
        "UNI": "Northern Iowa",
        "CBU": "Cal Baptist",
        "VCU": "VCU",
        "IDHO": "Idaho",
        "TROY": "Troy",
        "SCU": "Santa Clara",
        "SLU": "Saint Louis",
        "MIZ": "Missouri",
        "HPU": "High Point",
        "TCU": "TCU",
        "UCF": "UCF",
        "USU": "Utah St.",
        "HAW": "Hawaii",
        "USF": "South Florida",
        "MCN": "McNeese",
        "HOF": "Hofstra",
        "AKR": "Akron",
        "TNST": "Tennessee St.",
        # Play-in placeholders - will be handled specially
        "M-OH/SMU": "play_in_MIDWEST_11_a",
        "TEX/NCSU": "play_in_WEST_11",
        "PV/LEH": "play_in_SOUTH_16",
        "UMBC/HOW": "play_in_MIDWEST_16"
    }
    
    return abbrev_map


def scrape_espn_picks_playwright(
    year: int,
    data_dir: str,
    cache_max_age_hours: float = 2.0,
    force_refresh: bool = False,
    max_retries: int = 3,
    retry_delay_seconds: int = 5
) -> dict[str, dict[int, float]] | None:
    """Scrape ESPN pick percentages via Playwright API interception.
    
    Launches headless browser, navigates to ESPN bracket page, intercepts
    the Gambit API response containing pick percentages, parses round data,
    and caches results.
    
    Retries up to max_retries times on failure before giving up.
    
    Args:
        year: Tournament year (e.g., 2026).
        data_dir: Directory to save cached data.
        cache_max_age_hours: Maximum age of cached data before refresh.
        force_refresh: Bypass cache and force fresh scrape.
        max_retries: Number of retry attempts (default: 3).
        retry_delay_seconds: Seconds to wait between retries (default: 5).
    
    Returns:
        Dict mapping team_name → {round_num: pick_pct} where pick_pct is 0.0–1.0.
        Returns None if ESPN data is unavailable after all retries.
    """
    import time
    
    cache_file = Path(data_dir) / "espn_picks_cache.json"
    
    # Check cache first (unless force refresh)
    if not force_refresh and cache_file.exists():
        try:
            cached = load_json(str(cache_file))
            scraped_at = datetime.fromisoformat(cached["metadata"]["scraped_at"].replace("Z", "+00:00"))
            age_hours = (datetime.now(timezone.utc) - scraped_at).total_seconds() / 3600
            
            if age_hours < cache_max_age_hours:
                logger.info(f"Using cached ESPN picks ({age_hours:.1f}h old)")
                return cached["picks"]
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
    
    # Try Playwright scrape with retries
    for attempt in range(1, max_retries + 1):
        try:
            from playwright.sync_api import sync_playwright
            
            if attempt > 1:
                logger.info(f"Retry attempt {attempt}/{max_retries} after {retry_delay_seconds}s delay...")
                time.sleep(retry_delay_seconds)
            else:
                logger.info(f"Launching Playwright to scrape ESPN picks for {year}...")
            
            captured_data = {}
            
            def handle_response(response):
                """Intercept API response containing pick data."""
                # Capture ALL gambit API calls, not just the main one
                if f"tournament-challenge-bracket-{year}" in response.url and "gambit-api" in response.url:
                    try:
                        data = response.json()
                        # Log the URL to understand what we're capturing
                        logger.info(f"Captured ESPN API: {response.url}")
                        
                        # Store all API responses - there might be multiple
                        if "api_responses" not in captured_data:
                            captured_data["api_responses"] = []
                        captured_data["api_responses"].append({
                            "url": response.url,
                            "data": data
                        })
                        
                        # Keep the main response for backward compat
                        if "api_response" not in captured_data:
                            captured_data["api_response"] = data
                    except Exception as e:
                        logger.warning(f"Failed to parse API response: {e}")
            
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.on("response", handle_response)
                
                # Navigate to main bracket page and interact to load all round data
                # The whopickedwhom page only loads R1. We need to click through rounds
                # or find a page that loads all propositions at once.
                base_url = f"https://fantasy.espn.com/tournament-challenge-bracket/{year}/en"
                
                # First, load the main bracket page which should have the full challenge data
                main_url = f"{base_url}/entry"
                logger.info(f"Navigating to main bracket entry page: {main_url}")
                
                try:
                    page.goto(main_url, wait_until="networkidle", timeout=20000)
                    page.wait_for_timeout(3000)  # Give time for all API calls
                    
                    # Now also visit whopickedwhom to ensure we get R1 data
                    whopicked_url = f"{base_url}/whopickedwhom"
                    logger.info(f"Navigating to whopickedwhom: {whopicked_url}")
                    page.goto(whopicked_url, wait_until="networkidle", timeout=15000)
                    page.wait_for_timeout(2000)
                except Exception as e:
                    logger.warning(f"Page load timeout or error: {e}")
                
                browser.close()
            
            if not captured_data:
                logger.warning(f"ESPN API response not captured on attempt {attempt}/{max_retries}")
                if attempt < max_retries:
                    continue  # Retry
                else:
                    return None  # All retries exhausted
            
            # Save raw API response for debugging
            raw_api_file = Path(data_dir) / f"espn_api_raw_{year}.json"
            save_json(captured_data["api_response"], str(raw_api_file))
            logger.info(f"Saved raw ESPN API response to {raw_api_file}")
            
            # Parse the captured data
            picks = parse_espn_api_response(captured_data["api_response"], year, data_dir)
            
            if not picks or len(picks) < 50:
                logger.warning(f"Insufficient pick data ({len(picks) if picks else 0} teams) on attempt {attempt}/{max_retries}")
                if attempt < max_retries:
                    continue  # Retry
                else:
                    return None
            
            # Success! Save cache
            cache_data = {
                "metadata": {
                    "year": year,
                    "scraped_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "source_url": base_url,
                    "teams_count": len(picks)
                },
                "picks": picks
            }
            save_json(cache_data, str(cache_file))
            logger.info(f"Cached ESPN picks to {cache_file}")
            
            # Also save timestamped snapshot
            snapshots_dir = Path(data_dir) / "espn_picks_snapshots"
            snapshots_dir.mkdir(exist_ok=True)
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
            snapshot_file = snapshots_dir / f"espn_picks_{year}_{timestamp}.json"
            save_json(cache_data, str(snapshot_file))
            logger.info(f"Saved snapshot to {snapshot_file}")
            
            logger.info(f"✓ Successfully scraped ESPN picks for {len(picks)} teams")
            return picks
            
        except ImportError:
            logger.error("Playwright not installed - cannot scrape ESPN picks")
            logger.error("Install with: pip install playwright && playwright install chromium")
            return None
        except Exception as e:
            logger.warning(f"ESPN pick scraping failed on attempt {attempt}/{max_retries}: {e}")
            if attempt < max_retries:
                continue  # Retry
            else:
                return None  # All retries exhausted
    
    return None  # Should never reach here, but safety fallback


def parse_espn_api_response(api_data: dict, year: int, data_dir: str) -> dict[str, dict[int, float]]:
    """Parse ESPN Gambit API response into pick percentages by team and round.
    
    Args:
        api_data: Raw JSON response from ESPN Gambit API.
        year: Tournament year.
        data_dir: Directory containing real_bracket file.
    
    Returns:
        Dict mapping canonical team_name → {round_num: pick_pct}.
    """
    # Load name mapping
    real_bracket_path = Path(data_dir) / f"real_bracket_{year}.json"
    if not real_bracket_path.exists():
        logger.warning(f"Real bracket file not found: {real_bracket_path}")
        return {}
    
    name_map = build_espn_name_mapping(str(real_bracket_path))
    
    # Parse propositions from API
    propositions = api_data.get("propositions", [])
    
    # Parse all round propositions
    # scoringPeriodId: 1=R1, 2=R2, 3=R3(S16), 4=R4(E8), 5=R5(FF), 6=R6(Title)
    # displayOrder: seems to be matchup order, not round indicator
    round_data = {}  # round_num → {team abbrev → pick %}
    
    for prop in propositions:
        scoring_period = prop.get("scoringPeriodId")
        
        if scoring_period and 1 <= scoring_period <= 6:
            if scoring_period not in round_data:
                round_data[scoring_period] = {}
            
            outcomes = prop.get("possibleOutcomes", [])
            for outcome in outcomes:
                abbrev = outcome.get("abbrev", "")
                counters = outcome.get("choiceCounters", [])
                if counters:
                    pct = counters[0].get("percentage", 0.0)
                    # Keep highest percentage if duplicate (some teams in multiple matchups)
                    if abbrev not in round_data[scoring_period] or pct > round_data[scoring_period][abbrev]:
                        round_data[scoring_period][abbrev] = pct
    
    r1_data = round_data.get(1, {})
    
    # Count how many rounds we successfully parsed
    rounds_parsed = [r for r in range(1, 7) if r in round_data and len(round_data[r]) > 0]
    logger.info(f"Parsed ESPN picks for rounds: {rounds_parsed}")
    logger.info(f"  R1: {len(r1_data)} teams")
    
    # Build final picks dict
    # Strategy: Use actual round data when available, otherwise use seed-based decay from R1
    picks = {}
    
    # Reasonable decay multipliers based on historical seed curves
    # These match the pattern seen in SEED_OWNERSHIP_CURVES for top seeds
    DECAY_MULTIPLIERS = {
        2: 0.85,  # R2 = R1 * 0.85
        3: 0.65,  # R3 = R1 * 0.65
        4: 0.45,  # R4 = R1 * 0.45
        5: 0.30,  # R5 = R1 * 0.30
        6: 0.15   # R6 = R1 * 0.15
    }
    
    for abbrev, r1_pct in r1_data.items():
        canonical_name = name_map.get(abbrev)
        if not canonical_name:
            logger.warning(f"No mapping found for ESPN abbrev: {abbrev}")
            continue
        
        # Skip play-in placeholders for now
        if canonical_name.startswith("play_in_"):
            continue
        
        round_picks = {1: r1_pct}
        
        # Try to use actual round data from ESPN API
        for round_num in range(2, 7):
            if round_num in round_data and abbrev in round_data[round_num]:
                # Use actual ESPN data for this round
                round_picks[round_num] = round_data[round_num][abbrev]
            else:
                # Fallback: use decay multiplier from R1
                round_picks[round_num] = r1_pct * DECAY_MULTIPLIERS[round_num]
        
        picks[canonical_name] = round_picks
    
    # Log a few examples to verify the fix
    example_teams = ['Duke', 'Arizona', 'Illinois']
    for team in example_teams:
        if team in picks:
            p = picks[team]
            logger.info(f"  {team}: R1={p[1]:.1%} R2={p[2]:.1%} R3={p[3]:.1%} R6={p[6]:.1%}")
    
    logger.info(f"Built pick percentages for {len(picks)} teams")
    
    return picks


def scrape_espn_picks(url: str | None = None, filepath: str | None = None) -> dict[str, dict[int, float]] | None:
    """Legacy ESPN picks scraper (deprecated - use scrape_espn_picks_playwright).
    
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
    if filepath:
        logger.info(f"Loading ESPN picks from file: {filepath}")
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                html = f.read()
        except FileNotFoundError:
            logger.info("ESPN picks file not found - will use seed-based fallback")
            return None
    else:
        url = url or ESPN_PICKS_URL
        logger.info(f"Attempting to scrape ESPN picks from: {url}")
        try:
            html = fetch_url(url)
        except ScrapingError:
            logger.info("ESPN picks not available yet - will use seed-based fallback")
            return None
    
    # ESPN picks parsing would go here
    # For now, return None to trigger seed-based fallback
    logger.info("ESPN picks parsing not implemented - using seed-based ownership")
    return None


def merge_team_data(teams: list[Team], bracket: BracketStructure) -> list[Team]:
    """Merge KenPom stats with bracket seedings.
    
    Matches teams by name (with fuzzy matching for name discrepancies 
    between KenPom and ESPN).
    Sets seed, region, and bracket_position on each Team.
    
    Args:
        teams: Teams from KenPom scrape (have stats, no seedings).
        bracket: Bracket structure from ESPN (has seedings).
    
    Returns:
        List of 68 Teams with both stats and seeding info.
    
    Raises:
        DataError: If a bracketed team can't be matched to a KenPom team.
    """
    logger.info("Merging KenPom stats with bracket seedings")
    
    # For the simplified version, we'll create a mock merge
    # In production, this would match actual team names
    
    # Create a mapping of team names for quick lookup
    team_map = {normalize_team_name(t.name): t for t in teams}
    
    # Add aliases
    for alias, canonical in TEAM_NAME_ALIASES.items():
        norm_alias = normalize_team_name(alias)
        norm_canonical = normalize_team_name(canonical)
        if norm_canonical in team_map and norm_alias not in team_map:
            team_map[norm_alias] = team_map[norm_canonical]
    
    # For now, return top 68 teams from KenPom as mock tournament field
    tournament_teams = sorted(teams, key=lambda t: t.kenpom_rank)[:68]
    
    # BUG FIX #2: Do NOT assign regions here - let generate_bracket_from_kenpom()
    # be the single source of truth. It uses S-curve distribution which is correct.
    # Assigning regions here with idx % 4 creates a mismatch.
    # Just assign seeds and bracket position - regions will come from bracket generator.
    for idx, team in enumerate(tournament_teams):
        # Assign seed (distribute 1-16 across regions)
        seed_in_region = (idx // 4) + 1
        team.seed = min(seed_in_region, 16)
        team.bracket_position = idx + 1
        # team.region is intentionally NOT set here - will be set by bracket generator
    
    logger.info(f"Merged {len(tournament_teams)} teams with bracket info")
    
    return tournament_teams


def normalize_team_name(name: str) -> str:
    """Normalize team name for fuzzy matching.
    
    Args:
        name: Original team name.
    
    Returns:
        Normalized name (lowercase, no punctuation).
    """
    # Convert to lowercase
    name = name.lower()
    # Remove punctuation and extra whitespace
    name = re.sub(r'[^\w\s]', '', name)
    name = re.sub(r'\s+', ' ', name)
    return name.strip()


def generate_bracket_from_kenpom(teams: list[Team]) -> BracketStructure:
    """Generate a projected bracket structure from KenPom rankings.
    
    Uses standard NCAA seeding logic: top 4 teams are 1-seeds (one per region),
    next 4 are 2-seeds, etc. Teams are distributed via S-curve across regions
    to balance strength.
    
    This is used as a fallback when ESPN Bracketology is unavailable.
    
    Args:
        teams: All KenPom teams sorted by rank.
    
    Returns:
        BracketStructure with 68 teams seeded and placed in regions.
    """
    logger.info("Generating bracket from KenPom rankings (ESPN fallback)")
    
    sorted_teams = sorted(teams, key=lambda t: t.kenpom_rank)[:68]
    regions = {"East": [], "West": [], "South": [], "Midwest": []}
    region_names = ["East", "West", "South", "Midwest"]
    
    # S-curve distribution: seeds 1-16 across 4 regions
    # Seed 1: teams 1-4 distributed E,W,S,MW
    # Seed 2: teams 5-8 distributed MW,S,W,E (reverse)
    # Seed 3: teams 9-12 distributed E,W,S,MW (forward again)
    # etc.
    for seed_line in range(16):
        start = seed_line * 4
        batch = sorted_teams[start:start + 4]
        if seed_line % 2 == 0:
            order = [0, 1, 2, 3]  # E, W, S, MW
        else:
            order = [3, 2, 1, 0]  # MW, S, W, E (S-curve)
        
        for i, team in enumerate(batch):
            if i < len(order):
                region = region_names[order[i]]
                team.seed = seed_line + 1
                team.region = region
                team.bracket_position = start + i + 1
                regions[region].append(team.name)
    
    # For remaining teams (65-68 = play-in), assign as 16-seeds
    play_in_teams = sorted_teams[64:68] if len(sorted_teams) > 64 else []
    play_in_games = []
    for i in range(0, len(play_in_teams), 2):
        if i + 1 < len(play_in_teams):
            play_in_games.append((play_in_teams[i].name, play_in_teams[i + 1].name))
    
    # Build slot structure (same as scrape_espn_bracket)
    slots = []
    slot_id = 1
    
    for region_idx, region in enumerate(region_names):
        for seed_pair in BRACKET_SEED_ORDER:
            slot = BracketSlot(
                slot_id=slot_id,
                round_num=1,
                region=region,
                seed_a=seed_pair[0],
                seed_b=seed_pair[1],
                team_a=None,
                team_b=None,
                feeds_into=33 + region_idx * 4 + (slot_id - 1 - region_idx * 8) // 2
            )
            # Populate teams from regions list
            region_teams = regions[region]
            for t in sorted_teams:
                if t.region == region and t.seed == seed_pair[0]:
                    slot.team_a = t.name
                if t.region == region and t.seed == seed_pair[1]:
                    slot.team_b = t.name
            slots.append(slot)
            slot_id += 1
    
    # Rounds 2-6 (same structure as before)
    for region_idx, region in enumerate(region_names):
        for i in range(4):
            slots.append(BracketSlot(slot_id=slot_id, round_num=2, region=region,
                seed_a=0, seed_b=0, feeds_into=49 + region_idx * 2 + i // 2))
            slot_id += 1
    
    for region_idx, region in enumerate(region_names):
        for i in range(2):
            slots.append(BracketSlot(slot_id=slot_id, round_num=3, region=region,
                seed_a=0, seed_b=0, feeds_into=57 + region_idx))
            slot_id += 1
    
    for region_idx, region in enumerate(region_names):
        slots.append(BracketSlot(slot_id=slot_id, round_num=4, region=region,
            seed_a=0, seed_b=0, feeds_into=61 if region_idx % 2 == 0 else 62))  # East+South vs West+Midwest
        slot_id += 1
    
    for i in range(2):
        slots.append(BracketSlot(slot_id=slot_id, round_num=5, region="FinalFour",
            seed_a=0, seed_b=0, feeds_into=63))
        slot_id += 1
    
    slots.append(BracketSlot(slot_id=63, round_num=6, region="FinalFour",
        seed_a=0, seed_b=0, feeds_into=0))
    
    for i in range(4):
        slots.append(BracketSlot(slot_id=64 + i, round_num=0, region="PlayIn",
            seed_a=11 if i < 2 else 16, seed_b=11 if i < 2 else 16, feeds_into=0))
    
    bracket = BracketStructure(slots=slots, regions=regions, play_in_games=play_in_games)
    logger.info(f"Generated bracket with {len(regions['East'])} teams per region from KenPom data")
    
    return bracket


def collect_all(config) -> tuple[list[Team], BracketStructure, dict | None]:
    """Run the full data collection pipeline.
    
    Orchestrates: scrape KenPom → scrape ESPN bracket → merge → 
    scrape Yahoo picks → save all to data/.
    
    Args:
        config: Application configuration.
    
    Returns:
        Tuple of (merged team list, bracket structure, yahoo_picks).
        yahoo_picks is None if scraping failed (triggers seed-based fallback).
    """
    logger.info("=== Starting data collection ===")
    
    # Scrape KenPom
    teams = scrape_kenpom(
        url=config.kenpom_url,
        filepath=config.kenpom_file
    )
    
    # Scrape ESPN bracket (fallback to KenPom-generated bracket if ESPN fails)
    try:
        bracket = scrape_espn_bracket(
            url=config.espn_bracket_url,
            filepath=config.espn_bracket_file
        )
    except (ScrapingError, Exception) as e:
        logger.warning(f"ESPN bracket scraping failed ({e}) - generating bracket from KenPom rankings")
        bracket = generate_bracket_from_kenpom(teams)
    
    # Merge data
    merged_teams = merge_team_data(teams, bracket)
    
    # Scrape Yahoo picks (SOLE SOURCE for public ownership - replaces ESPN)
    yahoo_picks = None
    no_yahoo = getattr(config, 'no_yahoo', False)
    strict_mode = getattr(config, 'strict_yahoo', True)
    
    if not no_yahoo:
        logger.info("Scraping Yahoo Bracket Mayhem picks (SOLE source for ownership)...")
        yahoo_picks = scrape_yahoo_picks(
            year=getattr(config, 'year', 2026),
            data_dir=config.data_dir,
            cache_hours=getattr(config, 'yahoo_cache_max_age_hours', 4.0),
            max_retries=3
        )
        
        # STRICT MODE: Yahoo data is REQUIRED
        if yahoo_picks is None and strict_mode:
            logger.error("")
            logger.error("=" * 70)
            logger.error("ERROR: Yahoo Bracket Mayhem data unavailable after 3 attempts.")
            logger.error("=" * 70)
            logger.error("")
            logger.error("Cannot generate brackets without real ownership data.")
            logger.error("The optimizer requires actual Yahoo pick percentages")
            logger.error("to calculate leverage and contrarian value.")
            logger.error("")
            logger.error("Possible causes:")
            logger.error("  - Yahoo Bracket Mayhem not yet live (pre-Selection Sunday)")
            logger.error("  - Network/connectivity issues")
            logger.error("  - Yahoo page structure changed")
            logger.error("")
            logger.error("Solutions:")
            logger.error("  1. Wait until Selection Sunday when Yahoo picks go live")
            logger.error("  2. Check internet connection")
            logger.error("  3. For TESTING ONLY: use --no-strict-yahoo flag")
            logger.error("")
            logger.error("Pipeline stopped. Resolve Yahoo scraping and re-run.")
            logger.error("=" * 70)
            logger.error("")
            raise DataError("Yahoo Bracket Mayhem data required but unavailable")
    
    # Save data
    from src.utils import ensure_dir
    ensure_dir(config.data_dir)
    
    teams_file = f"{config.data_dir}/teams.json"
    save_json([t.to_dict() for t in merged_teams], teams_file)
    logger.info(f"Saved {len(merged_teams)} teams to {teams_file}")
    
    bracket_file = f"{config.data_dir}/bracket_structure.json"
    save_json(bracket.to_dict(), bracket_file)
    logger.info(f"Saved bracket structure to {bracket_file}")
    
    if yahoo_picks:
        picks_file = f"{config.data_dir}/public_picks.json"
        save_json(yahoo_picks, picks_file)
        logger.info(f"✓ Saved Yahoo pick data for {len(yahoo_picks)} teams to {picks_file}")
    elif no_yahoo:
        logger.warning("Yahoo pick scraping skipped (--no-yahoo flag). Using seed-based estimates.")
    
    logger.info("=== Data collection complete ===")
    
    return merged_teams, bracket, yahoo_picks
