#!/usr/bin/env python3
"""March Madness Bracket Optimizer - CLI entry point.

Orchestrates the full pipeline: data collection, modeling, optimization, and output.
"""

import argparse
import os
import sys
import logging

from src.config import load_config
from src.utils import setup_logging, load_json
from src.models import Team, BracketStructure, OwnershipProfile


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments.
    
    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="March Madness Bracket Optimizer - Find the bracket that maximizes P(1st place)",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Commands
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # collect command
    collect_parser = subparsers.add_parser('collect', help='Scrape data from KenPom and ESPN')
    
    # analyze command
    analyze_parser = subparsers.add_parser('analyze', help='Run model and optimization')
    
    # bracket command
    bracket_parser = subparsers.add_parser('bracket', help='Generate output from existing data')

    # full command
    full_parser = subparsers.add_parser('full', help='Run complete pipeline (collect → analyze → bracket)')

    # GitHub Pages flag for commands that produce HTML
    for subparser in [bracket_parser, full_parser]:
        subparser.add_argument('--update-github-pages', action='store_true',
                               help='Copy index.html to docs/index.html after generation')
    
    # Global flags (available for all commands)
    for subparser in [collect_parser, analyze_parser, bracket_parser, full_parser]:
        subparser.add_argument('--pool-size', type=int, help='Pool size (default: 25)')
        subparser.add_argument('--sims', type=int, help='Number of simulations (default: 10000)')
        subparser.add_argument('--risk', choices=['conservative', 'balanced', 'aggressive', 'auto'], 
                             help='Risk profile (default: auto)')
        subparser.add_argument('--config', default='config.json', help='Path to config.json')
        subparser.add_argument('--verbose', '-v', action='store_true', help='Enable debug logging')
        subparser.add_argument('--seed', type=int, help='Random seed for reproducibility')
    
    # Scout-specific flags
    for subparser in [collect_parser, full_parser]:
        subparser.add_argument('--kenpom-file', help='Use local KenPom HTML file')
        subparser.add_argument('--espn-bracket-file', help='Use local ESPN bracket HTML')
        subparser.add_argument('--year', type=int, default=2026, help='Tournament year (default: 2026)')
        subparser.add_argument('--force-yahoo-refresh', action='store_true', 
                             help='Force fresh Yahoo pick scrape (ignore cache)')
        subparser.add_argument('--no-yahoo', action='store_true',
                             help='Skip Yahoo pick scraping (use seed-based)')
        subparser.add_argument('--no-strict-yahoo', action='store_true',
                             help='Allow seed-based fallback if Yahoo unavailable (TESTING ONLY)')
        subparser.add_argument('--first-four', type=str, default='',
                             help='Comma-separated First Four winners (e.g. "Texas,Howard")')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    return args


def cmd_collect(config) -> None:
    """Execute the 'collect' command — run data collection pipeline."""
    import os.path
    from src.scout import collect_all
    from src.load_real_bracket import load_real_bracket
    from src.utils import save_json, ensure_dir
    
    logger = logging.getLogger("bracket_optimizer")
    logger.info("Running data collection pipeline")
    
    # Check if real bracket exists; if not, try to fetch from ncaa.com
    real_bracket_file = f"{config.data_dir}/real_bracket_2026.json"

    if not os.path.exists(real_bracket_file):
        logger.info("Real bracket not found — attempting to fetch from ncaa.com")
        try:
            import subprocess
            # Step 1: Fetch raw HTML
            result = subprocess.run(
                [sys.executable, 'scripts/fetch_real_bracket.py'],
                capture_output=True, text=True, timeout=60
            )
            # Step 2: Use the more reliable game-pod parser if raw HTML exists
            raw_html = f"{config.data_dir}/ncaa_bracket_2026_raw.html"
            if os.path.exists(raw_html):
                result2 = subprocess.run(
                    [sys.executable, 'scripts/parse_bracket_html.py'],
                    capture_output=True, text=True, timeout=30
                )
                if result2.returncode == 0:
                    logger.info("Successfully parsed real bracket from ncaa.com")
                else:
                    logger.warning(f"Bracket parse failed: {result2.stderr[:200] if result2.stderr else 'unknown error'}")
            elif result.returncode == 0:
                logger.info("Successfully fetched real bracket from ncaa.com")
            else:
                logger.warning(f"Bracket fetch failed: {result.stderr[:200] if result.stderr else 'unknown error'}")
        except Exception as e:
            logger.warning(f"Could not fetch real bracket: {e}")

    if os.path.exists(real_bracket_file):
        logger.info("Found real bracket - loading from ncaa.com data")
        
        # First scrape ALL KenPom teams (not just top 68)
        from src.scout import scrape_kenpom
        all_kenpom_teams = scrape_kenpom(
            url=config.kenpom_url,
            filepath=config.kenpom_file
        )
        logger.info(f"Scraped {len(all_kenpom_teams)} teams from KenPom")
        
        # Save ALL KenPom teams temporarily for bracket matching
        temp_kenpom_file = f"{config.data_dir}/teams_kenpom_temp.json"
        save_json([t.to_dict() for t in all_kenpom_teams], temp_kenpom_file)
        
        # Also run Yahoo picks collection (but don't need the merged teams from collect_all)
        from src.scout import scrape_yahoo_picks
        yahoo_picks = scrape_yahoo_picks(
            year=getattr(config, 'year', 2026),
            data_dir=config.data_dir,
            cache_hours=getattr(config, 'yahoo_cache_max_age_hours', 4.0),
            max_retries=3
        )
        
        # Check strict mode for Yahoo picks
        if yahoo_picks is None and getattr(config, 'strict_yahoo', True):
            from src.models import DataError
            logger.error("Yahoo Bracket Mayhem data required but unavailable")
            raise DataError("Yahoo Bracket Mayhem data required but unavailable")
        
        # Now load real bracket and match with KenPom
        ff_winners = [w.strip() for w in config.first_four.split(',') if w.strip()] if getattr(config, 'first_four', '') else []
        teams, bracket = load_real_bracket(real_bracket_file, temp_kenpom_file, first_four_winners=ff_winners)

        # Enrich teams with Torvik (barthag, wab) and LRMC (top25 record)
        from src.enrich import enrich_teams
        teams = enrich_teams(teams, config.data_dir)

        # Save merged + enriched data
        ensure_dir(config.data_dir)
        teams_file = f"{config.data_dir}/teams.json"
        save_json([t.to_dict() for t in teams], teams_file)
        logger.info(f"Saved {len(teams)} enriched teams to {teams_file}")
        
        bracket_file = f"{config.data_dir}/bracket_structure.json"
        save_json(bracket.to_dict(), bracket_file)
        logger.info(f"Saved bracket structure to {bracket_file}")
        
        # Save Yahoo picks to public_picks.json
        if yahoo_picks:
            picks_file = f"{config.data_dir}/public_picks.json"
            save_json(yahoo_picks, picks_file)
            logger.info(f"✓ Yahoo pick data collected for {len(yahoo_picks)} teams")
            logger.info(f"✓ Saved to {picks_file}")
        
        # Clean up temp file
        os.remove(temp_kenpom_file)
    else:
        logger.info("Real bracket not found - using KenPom-generated bracket")
        teams, bracket, yahoo_picks = collect_all(config)

        # Enrich fallback teams too
        from src.enrich import enrich_teams
        from src.utils import save_json
        teams = enrich_teams(teams, config.data_dir)
        save_json([t.to_dict() for t in teams], f"{config.data_dir}/teams.json")

    logger.info(f"✓ Collected data for {len(teams)} teams")


def cmd_analyze(config) -> None:
    """Execute the 'analyze' command — run model + optimization."""
    from src.utils import load_json
    from src.models import Team, BracketStructure, OwnershipProfile
    from src.sharp import analyze_matchups
    from src.contrarian import analyze_ownership, update_leverage_with_model
    from src.optimizer import optimize_bracket
    
    logger = logging.getLogger("bracket_optimizer")
    logger.info("Running analysis pipeline")
    
    # Load teams and bracket
    teams_data = load_json(f"{config.data_dir}/teams.json")
    teams = [Team.from_dict(t) for t in teams_data]
    
    bracket_data = load_json(f"{config.data_dir}/bracket_structure.json")
    bracket = BracketStructure.from_dict(bracket_data)
    
    logger.info(f"Loaded {len(teams)} teams and bracket structure")
    
    # Build matchup matrix
    matchup_matrix = analyze_matchups(teams, config)
    
    # Analyze ownership (initial seed-based estimates)
    ownership_profiles = analyze_ownership(teams, config)
    
    # Estimate title probabilities via quick Monte Carlo (needed for leverage calculation)
    from src.optimizer import estimate_title_probabilities
    title_probs = estimate_title_probabilities(matchup_matrix, bracket, sim_count=2000, base_seed=config.random_seed if config.random_seed else 42)
    
    # Update leverage with actual model probabilities (pool-size-aware, with title probs)
    ownership_profiles = update_leverage_with_model(ownership_profiles, teams, matchup_matrix, bracket, config.pool_size, title_probs)
    
    # Save updated ownership profiles
    from src.utils import save_json, ensure_dir
    ensure_dir(config.data_dir)
    ownership_file = f"{config.data_dir}/ownership.json"
    save_json([p.to_dict() for p in ownership_profiles], ownership_file)
    logger.info(f"Updated and saved ownership profiles with leverage scores")
    
    # Optimize brackets (returns all ~24 evaluated brackets, sorted by P(1st))
    all_brackets = optimize_bracket(teams, matchup_matrix, ownership_profiles, bracket, config)

    # Save all brackets for standalone cmd_bracket workflow
    brackets_file = f"{config.data_dir}/all_brackets.json"
    save_json([b.to_dict() for b in all_brackets], brackets_file)
    logger.info(f"Saved {len(all_brackets)} evaluated brackets to {brackets_file}")

    logger.info("✓ Analysis complete")
    return all_brackets


def cmd_bracket(config, brackets=None) -> None:
    """Execute the 'bracket' command — generate output from existing data."""
    from src.utils import load_json
    from src.models import Team, BracketStructure, OwnershipProfile, CompleteBracket
    from src.analyst import generate_all_output

    logger = logging.getLogger("bracket_optimizer")
    logger.info("Generating output files")

    # Load supporting data
    teams_data = load_json(f"{config.data_dir}/teams.json")
    teams = [Team.from_dict(t) for t in teams_data]

    bracket_data = load_json(f"{config.data_dir}/bracket_structure.json")
    bracket = BracketStructure.from_dict(bracket_data)

    ownership_data = load_json(f"{config.data_dir}/ownership.json")
    ownership_profiles = [OwnershipProfile.from_dict(p) for p in ownership_data]

    matchup_matrix = load_json(f"{config.data_dir}/matchup_probabilities.json")

    # Load brackets from file if not passed in-memory (standalone mode)
    if brackets is None:
        brackets_data = load_json(f"{config.data_dir}/all_brackets.json")
        brackets = [CompleteBracket.from_dict(b) for b in brackets_data]

    # Generate output
    generate_all_output(brackets, teams, ownership_profiles, matchup_matrix, bracket, config)

    logger.info("✓ Output generation complete")


def cmd_full(config) -> None:
    """Execute the 'full' command — collect → analyze → bracket."""
    import glob
    logger = logging.getLogger("bracket_optimizer")
    logger.info("Running full pipeline")
    
    # Clear stale data from previous runs (but preserve real bracket!)
    preserve_files = {
        f"{config.data_dir}/real_bracket_2026.json",
        f"{config.data_dir}/ncaa_bracket_2026_raw.html",
        f"{config.data_dir}/kenpom_2026_live.json",
        f"{config.data_dir}/torvik_2026_live.json",
        f"{config.data_dir}/lrmc_2026_live.json",
    }
    
    for stale in glob.glob(f"{config.data_dir}/*.json"):
        if stale not in preserve_files:
            os.remove(stale)
            logger.debug(f"Removed {stale}")
    
    logger.info("Cleared previous run data (preserved real bracket)")
    
    cmd_collect(config)
    all_brackets = cmd_analyze(config)
    cmd_bracket(config, brackets=all_brackets)

    logger.info("✓ Full pipeline complete")
    logger.info(f"Results available in {config.output_dir}/")


def main() -> None:
    """CLI entry point."""
    args = parse_args()
    
    # Build CLI overrides
    cli_overrides = {}
    if args.pool_size:
        cli_overrides['pool_size'] = args.pool_size
    if args.sims:
        cli_overrides['sim_count'] = args.sims
    if args.risk:
        cli_overrides['risk_profile'] = args.risk
    if args.seed:
        cli_overrides['random_seed'] = args.seed
    
    # Scout file overrides
    if hasattr(args, 'kenpom_file') and args.kenpom_file:
        cli_overrides['kenpom_file'] = args.kenpom_file
    if hasattr(args, 'espn_bracket_file') and args.espn_bracket_file:
        cli_overrides['espn_bracket_file'] = args.espn_bracket_file
    
    # Yahoo picks scraping overrides
    if hasattr(args, 'year') and args.year:
        cli_overrides['year'] = args.year
    if hasattr(args, 'force_yahoo_refresh') and args.force_yahoo_refresh:
        cli_overrides['force_yahoo_refresh'] = True
    if hasattr(args, 'no_yahoo') and args.no_yahoo:
        cli_overrides['no_yahoo'] = True
    if hasattr(args, 'no_strict_yahoo') and args.no_strict_yahoo:
        cli_overrides['strict_yahoo'] = False
    if hasattr(args, 'first_four') and args.first_four:
        cli_overrides['first_four'] = args.first_four

    # Load configuration
    try:
        config = load_config(args.config, cli_overrides)
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)
    
    # Setup logging
    logger = setup_logging(args.verbose)
    
    # Commands that produce HTML output always get a fresh timestamped results dir
    if args.command in ('bracket', 'full'):
        from datetime import datetime, timezone
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
        config.output_dir = f"results/{timestamp}"

    # Dispatch to command
    try:
        if args.command == 'collect':
            cmd_collect(config)
        elif args.command == 'analyze':
            cmd_analyze(config)
        elif args.command == 'bracket':
            cmd_bracket(config)
        elif args.command == 'full':
            cmd_full(config)
        else:
            print(f"Unknown command: {args.command}")
            sys.exit(1)
    
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.exception(f"Error: {e}")
        if args.verbose:
            raise
        sys.exit(2)

    # GitHub Pages: copy index.html → docs/<pool_size>tm/index.html
    if getattr(args, 'update_github_pages', False) and args.command in ('bracket', 'full'):
        import shutil
        src = os.path.join(config.output_dir, 'index.html')
        subfolder = f"{config.pool_size}tm"
        dst_dir = os.path.join('docs', subfolder)
        dst = os.path.join(dst_dir, 'index.html')
        if os.path.exists(src):
            os.makedirs(dst_dir, exist_ok=True)
            shutil.copy2(src, dst)
            logger.info(f"✓ Copied index.html → {dst}")
        else:
            logger.warning(f"index.html not found at {src}, skipping GitHub Pages update")


if __name__ == "__main__":
    main()
