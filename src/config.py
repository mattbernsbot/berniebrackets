"""Configuration loading and risk profile calculation.

Handles merging config.json defaults with CLI overrides.
"""

from src.models import Config, ConfigError
from src.utils import load_json


def load_config(config_path: str = "config.json", cli_overrides: dict | None = None) -> Config:
    """Load configuration from JSON file, merged with CLI overrides.
    
    Priority: CLI flags > config.json > hardcoded defaults.
    
    Args:
        config_path: Path to config.json.
        cli_overrides: Dict of CLI argument overrides (e.g., {"pool_size": 50}).
    
    Returns:
        Populated Config dataclass.
    """
    # Start with defaults
    config_dict = {}
    
    # Load from file if it exists
    try:
        file_config = load_json(config_path)
        config_dict.update(file_config)
    except Exception:
        # File doesn't exist or is invalid - use defaults
        pass
    
    # Apply CLI overrides
    if cli_overrides:
        config_dict.update({k: v for k, v in cli_overrides.items() if v is not None})
    
    # Create Config object
    config = Config.from_dict(config_dict)
    
    # Auto-calculate risk profile if set to "auto"
    if config.risk_profile == "auto":
        config.risk_profile = auto_risk_profile(config.pool_size)
    
    # Validate
    if config.pool_size < 1:
        raise ConfigError("pool_size must be at least 1")
    
    if config.sim_count < 100:
        raise ConfigError("sim_count must be at least 100")
    
    if config.risk_profile not in ["conservative", "balanced", "aggressive"]:
        raise ConfigError(f"Invalid risk_profile: {config.risk_profile}")
    
    if len(config.scoring) != 6:
        raise ConfigError("scoring must have exactly 6 values (one per round)")
    
    return config


def auto_risk_profile(pool_size: int) -> str:
    """Calculate risk profile from pool size.
    
    Smaller pools (≤10) → "conservative"
    Medium pools (11-50) → "balanced"
    Large pools (51-200) → "aggressive"
    
    Args:
        pool_size: Number of entrants in the pool.
    
    Returns:
        Risk profile string.
    """
    if pool_size <= 10:
        return "conservative"
    elif pool_size <= 50:
        return "balanced"
    else:
        return "aggressive"
