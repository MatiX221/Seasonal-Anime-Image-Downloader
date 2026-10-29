# src/seasons.py

import re
from dataclasses import dataclass
from datetime import datetime

from .config import SEASONS, MIN_YEAR, YEAR_WEIGHT, SEASON_ALIASES
from .utils import format_season_name, fuzzy_match

ALIASES = SEASON_ALIASES
WILDCARD_ANY = "ANY"
WILDCARD_YEAR = "YEAR"


@dataclass(frozen=True)
class Job:
    """One season of one year, or a whole year when season is None"""
    season: str | None
    year: int

    @property
    def name(self) -> str:
        """Folder name: 'Winter 2025', or just '2025' for a whole year"""
        if self.season is None:
            return str(self.year)
        return format_season_name(self.season, self.year)

    @property
    def label(self) -> str:
        """Name for logs: 'Winter 2025' or 'Year 2025'"""
        if self.season is None:
            return f"Year {self.year}"
        return self.name

    @property
    def sort_key(self) -> tuple[int, int]:
        return (self.year, -1 if self.season is None else SEASONS.index(self.season))

    @property
    def weight(self) -> int:
        """How much work this job is, counted in seasons"""
        return YEAR_WEIGHT if self.season is None else 1


def max_year() -> int:
    """Latest year accepted: next year (AniList has shows for it, but nothing further ahead)"""
    return datetime.now().year + 1


def _split(values: list[str] | None) -> list[str]:
    """Split raw CLI tokens on commas and whitespace"""
    items: list[str] = []
    for value in values or []:
        items.extend(part for part in re.split(r"[,\s]+", value) if part)
    return items


def parse_year(text: str) -> int:
    """
    Parse and validate a single year

    Raises:
        ValueError: If it is not a number or is outside MIN_YEAR..max_year()
    """
    try:
        year = int(text)
    except ValueError:
        raise ValueError(f"'{text}' is not a valid year") from None
    upper = max_year()
    if not MIN_YEAR <= year <= upper:
        raise ValueError(f"Year {year} is out of range ({MIN_YEAR}-{upper})")
    return year


_RANGE_RE = re.compile(r"^(\d+)-(\d+)$")


def parse_years(text: str) -> list[int]:
    """
    Parse a single year or an inclusive range: '2025' or '2023-2026'

    Raises:
        ValueError: If the text is not a valid year or range, or the range is reversed
    """
    match = _RANGE_RE.match(text)
    if match:
        start = parse_year(match.group(1))
        end = parse_year(match.group(2))
        if start > end:
            raise ValueError(f"Invalid year range '{text}': {start} is after {end}")
        return list(range(start, end + 1))
    if "-" in text:
        raise ValueError(f"Invalid year range '{text}'. Use START-END without spaces, like 2023-2026")
    return [parse_year(text)]


def _parse_season_item(item: str, previous: str | None) -> tuple[str, list[int] | None, str]:
    """
    Parse one season item: NAME, NAME:YEAR or NAME:START-END

    Returns:
        (season name in uppercase or 'ANY', explicit years or None, corrected item)
    """
    if item.isdigit() or _RANGE_RE.match(item):
        hint = f"Did you mean '{previous}:{item}'? " if previous else ""
        raise ValueError(
            f"'{item}' is not a season. {hint}Years go after --year or after a colon, like winter:{item}"
        )

    name, sep, year_text = item.partition(":")
    if sep and (not name or not year_text or ":" in year_text):
        raise ValueError(f"Invalid season '{item}'. Use NAME or NAME:YEAR, like winter or winter:2025")

    corrected_name = name.lower()
    key = name.upper()
    key = ALIASES.get(key, key)
    if key not in (WILDCARD_ANY, WILDCARD_YEAR) and key not in SEASONS:
        valid = [s.lower() for s in SEASONS] + ["autumn", "any", "year"]
        close = fuzzy_match(name.lower(), valid)
        if not close:
            raise ValueError(f"Unknown season '{name}'. Valid: winter, spring, summer, fall (autumn), any, year")
        corrected_name = close
        key = ALIASES.get(corrected_name.upper(), corrected_name.upper())

    corrected_item = f"{corrected_name}:{year_text}" if sep else corrected_name
    return key, (parse_years(year_text) if sep else None), corrected_item


def parse_jobs(
    season_args: list[str] | None,
    year_args: list[str] | None,
    default_season: str,
    default_year: int,
) -> tuple[list[Job], list[str], tuple[str, str] | None]:
    """
    Turn --season and --year values into a list of jobs

    An item with its own year or range (winter:2025, winter:2023-2025) uses only
    those years. A bare season is combined with every year from --year (single
    years and ranges), or default_year if there is none. 'any' stands for all
    four seasons. 'year' stands for the whole year (all shows, including ones
    with no season). Duplicates are removed and the result is sorted oldest first.

    Args:
        season_args: Raw --season tokens, or None
        year_args: Raw --year tokens, or None
        default_season: Season used when --season is missing
        default_year: Year used when --year is missing

    Returns:
        (jobs, warnings, correction). correction is (raw, corrected) when a
        misspelled season was matched to the nearest one, otherwise None

    Raises:
        ValueError: On invalid input
    """
    warnings: list[str] = []

    year_items = _split(year_args)
    years: list[int] = []
    for text in year_items:
        for year in parse_years(text):
            if year not in years:
                years.append(year)
    if not years:
        years = [default_year]

    season_items = _split(season_args) or [default_season.lower()]

    jobs: set[Job] = set()
    used_year_list = False
    previous: str | None = None
    fixed_items: list[str] = []
    had_typo = False
    for item in season_items:
        key, explicit_years, corrected_item = _parse_season_item(item, previous)
        if corrected_item.lower() != item.lower():
            had_typo = True
        fixed_items.append(corrected_item)
        previous = corrected_item.partition(":")[0]

        if key == WILDCARD_ANY:
            seasons: tuple[str | None, ...] = SEASONS
        elif key == WILDCARD_YEAR:
            seasons = (None,)
        else:
            seasons = (key,)
        if explicit_years is None:
            used_year_list = True
            target_years = years
        else:
            target_years = explicit_years

        for season in seasons:
            for year in target_years:
                jobs.add(Job(season, year))

    if year_items and not used_year_list:
        warnings.append("--year was ignored because every season already has its own year")

    correction = (",".join(season_items), ",".join(fixed_items)) if had_typo else None
    return sorted(jobs, key=lambda job: job.sort_key), warnings, correction