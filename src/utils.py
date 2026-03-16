"""Utility functions for HTTP, JSON, and logging.

Provides common functionality used across all modules.
"""

import json
import logging
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

from src.models import ScrapingError, DataError


def fetch_url(url: str, timeout: int = 30) -> str:
    """Fetch URL content using urllib.request with browser User-Agent.
    
    Args:
        url: The HTTP/HTTPS URL to fetch.
        timeout: Request timeout in seconds.
    
    Returns:
        Decoded response body as string.
    
    Raises:
        ScrapingError: If HTTP error or timeout occurs.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept-Encoding': 'identity',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        raise ScrapingError(f"HTTP error fetching {url}: {e.code} {e.reason}")
    except urllib.error.URLError as e:
        raise ScrapingError(f"URL error fetching {url}: {e.reason}")
    except TimeoutError:
        raise ScrapingError(f"Timeout fetching {url}")
    except Exception as e:
        raise ScrapingError(f"Unexpected error fetching {url}: {e}")


def load_json(filepath: str) -> dict | list:
    """Load and parse a JSON file.
    
    Args:
        filepath: Path to the JSON file.
    
    Returns:
        Parsed JSON content.
    
    Raises:
        DataError: If file not found or invalid JSON.
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        raise DataError(f"File not found: {filepath}")
    except json.JSONDecodeError as e:
        raise DataError(f"Invalid JSON in {filepath}: {e}")
    except Exception as e:
        raise DataError(f"Error loading {filepath}: {e}")


def save_json(data: dict | list, filepath: str) -> None:
    """Write data to a JSON file with pretty-printing.
    
    Args:
        data: JSON-serializable data.
        filepath: Output path. Parent directories must exist.
    """
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        raise DataError(f"Error saving to {filepath}: {e}")


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure and return the application logger.
    
    Args:
        verbose: If True, set level to DEBUG. Otherwise INFO.
    
    Returns:
        Configured Logger instance.
    """
    logger = logging.getLogger("bracket_optimizer")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    
    # Remove existing handlers
    logger.handlers = []
    
    # Console handler
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    
    # Format
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    
    return logger


def ensure_dir(dirpath: str) -> None:
    """Ensure a directory exists, creating it if necessary.
    
    Args:
        dirpath: Path to directory.
    """
    Path(dirpath).mkdir(parents=True, exist_ok=True)
