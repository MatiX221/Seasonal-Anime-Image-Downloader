# src/utils.py

import difflib
import re
from datetime import datetime
from typing import Iterable

from .config import SEASON_START_MONTH, VALID_FORMATS, VALID_TITLE_LANGUAGES
_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def fuzzy_match(word: str, possibilities: Iterable[str], cutoff: float = 0.6) -> str | None:
    """Return the closest match from possibilities, or None."""
    candidates = list(possibilities)
    matches = difflib.get_close_matches(word.lower(), [candidate.lower() for candidate in candidates], n=1, cutoff=cutoff)
    if not matches:
        return None
    return next(candidate for candidate in candidates if candidate.lower() == matches[0])


def parse_choices(
    values: list[str],
    valid: tuple[str, ...],
    option: str,
    fuzzy: bool = False,
) -> tuple[list[str], tuple[str, str] | None]:
    """
    Parse CLI values like ["tv,", "ona"] or ["tv,ona"] into canonical values.

    Args:
        values: Raw tokens from argparse (each may contain commas)
        valid: Allowed values; matching is case-insensitive
        option: Option name, used in error messages
        fuzzy: Whether to accept close matches and return a correction

    Returns:
        Canonical values and an optional (raw, corrected) fuzzy correction

    Raises:
        ValueError: If a value is not in valid or nothing was given
    """
    canonical = {value.lower(): value for value in valid}
    items: list[str] = []
    raw_parts: list[str] = []
    fixed_parts: list[str] = []
    had_typo = False

    for value in values:
        for part in re.split(r"[,\s]+", value):
            raw = part.strip()
            key = raw.lower()
            if not key:
                continue
            if key in canonical:
                resolved = canonical[key]
                raw_parts.append(raw)
                fixed_parts.append(resolved.lower())
            else:
                match = fuzzy_match(key, canonical.keys()) if fuzzy else None
                if match is None:
                    close = fuzzy_match(key, canonical.keys())
                    hint = f" Did you mean '{canonical[close]}'?" if close else ""
                    raise ValueError(f"Invalid value '{raw}' for {option}.{hint} Valid: {', '.join(valid)}")
                resolved = canonical[match]
                had_typo = True
                raw_parts.append(raw)
                fixed_parts.append(match)

            if resolved not in items:
                items.append(resolved)
    if not items:
        raise ValueError(f"{option} needs at least one value. Valid: {', '.join(valid)}")
    correction = (",".join(raw_parts), ",".join(fixed_parts)) if had_typo else None
    return items, correction


def pick_title(
    anime: dict,
    languages: tuple[str, ...] | list[str] = ("romaji",),
) -> str:
    """Pick the first non-empty title in the requested language order."""
    titles = anime.get("title") or {}
    for language in languages:
        value = (titles.get(language) or "").strip()
        if value:
            return value
    return str(anime.get("id"))


def sanitize_filename(name: str, max_length: int = 100) -> str:
    """
    Sanitize a string to be used as a filename
    
    Args:
        name: Original string (anime title, etc.)
        max_length: Maximum filename length
    
    Returns:
        Sanitized filename string safe for all operating systems
    """
    # Remove or replace invalid characters for Windows/Linux/Mac
    # Invalid chars: < > : " / \ | ? *
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    
    # Replace multiple spaces with single space
    name = re.sub(r'\s+', ' ', name)
    
    # Strip leading/trailing whitespace and dots (Windows issue)
    name = name.strip().strip('.')
    
    # Truncate to max length
    if len(name) > max_length:
        name = name[:max_length].strip()
    
    # Fallback if empty after sanitization
    if not name:
        name = "untitled"

    if name.split(".")[0].upper() in _WINDOWS_RESERVED:
        name = f"_{name}"
    
    return name


def get_current_season() -> str:
    """
    Determine the current anime season based on the current date,
    using the same season boundaries as AniList

    Returns:
        Season name: 'Winter', 'Spring', 'Summer', or 'Fall'
    """
    month = datetime.now().month

    if month <= 3:
        return "Winter"
    elif month <= 6:
        return "Spring"
    elif month <= 9:
        return "Summer"
    else:
        return "Fall"


def format_season_name(season: str, year: int) -> str:
    """
    Format season and year into a standardized string
    
    Args:
        season: Season name (case-insensitive)
        year: Year number
    
    Returns:
        Formatted string like "Winter 2025"
    """
    season = season.strip().capitalize()
    return f"{season} {year}"


def normalize_season(season: str) -> str:
    """
    Normalize season name (handles 'Autumn' -> 'Fall' conversion)
    
    Args:
        season: Season name
    
    Returns:
        Normalized season name for AniList API
    """
    season = season.strip().upper()
    if season == 'AUTUMN':
        return 'FALL'
    return season