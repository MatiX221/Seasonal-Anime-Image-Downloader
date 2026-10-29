# src/anilist.py

import calendar
import time
import requests
import logging
from datetime import date, timedelta
from .config import (
    ANILIST_API_URL,
    ANILIST_API_TIMEOUT,
    ANILIST_API_RETRIES,
    ANILIST_PER_PAGE,
    DEFAULT_GRACE_DAYS,
    SEASON_ORDER,
    SEASON_START_MONTH,
)
from .utils import format_season_name

API_URL = ANILIST_API_URL

# Fetched seasons, so consecutive seasons don't download the same data twice
_season_cache: dict[tuple[str, int, bool], list[dict]] = {}


_QUERY_TEMPLATE = """
query (__VARIABLE_DEFS__) {
    Page(page: $page, perPage: $perPage) {
        pageInfo {
            total
            perPage
            currentPage
            lastPage
            hasNextPage
        }
        media(__MEDIA_ARGS__) {
            id
            idMal
            popularity
            title {
                romaji
                english
                native
            }
            coverImage {
                large
                extraLarge
            }
            siteUrl
            format
            episodes
            averageScore
            isAdult
            genres
            seasonYear
            startDate {
                year
                month
                day
            }
            endDate {
                year
                month
                day
            }
            status
        }
    }
}
"""


def _build_query(variables: str, media_args: str) -> str:
    """Build a query from the shared template, adding paging and adult filtering."""
    variable_defs = ", ".join(filter(None, [variables, "$page: Int", "$perPage: Int", "$isAdult: Boolean"]))
    args = ", ".join(filter(None, [media_args, "type: ANIME", "sort: POPULARITY_DESC", "isAdult: $isAdult"]))
    return _QUERY_TEMPLATE.replace("__VARIABLE_DEFS__", variable_defs).replace("__MEDIA_ARGS__", args)


SEASON_QUERY = _build_query("$season: MediaSeason, $year: Int", "season: $season, seasonYear: $year")
YEAR_SEASON_QUERY = _build_query("$year: Int", "seasonYear: $year")


def _year_date_query(year: int) -> str:
    """Query for shows whose start date falls in year."""
    return _build_query("", f"startDate_greater: {year - 1}1231, startDate_lesser: {year + 1}0000")


def filter_by_format(
    anime_list: list[dict],
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> list[dict]:
    """Keep only formats in include, or drop formats in exclude."""
    if include:
        return [anime for anime in anime_list if anime.get("format") in include]
    if exclude:
        return [anime for anime in anime_list if anime.get("format") not in exclude]
    return anime_list


def _is_continuing(anime, season, year, grace_days):
    end = anime.get("endDate") or {}
    if not end.get("year"):
        return True  # no end date known, assume still running
    end_year = end["year"]
    end_month = min(max(end.get("month") or 12, 1), 12)
    max_day = calendar.monthrange(end_year, end_month)[1]
    end_day = min(max(end.get("day") or max_day, 1), max_day)
    end_date = date(end_year, end_month, end_day)
    season_start = date(year, SEASON_START_MONTH[season.upper()], 1)
    return end_date > season_start + timedelta(days=grace_days)


def get_previous_season(season: str, year: int):
    """
    Get the previous season and year
    
    Args:
        season: Current season (WINTER, SPRING, SUMMER, FALL)
        year: Current year
    
    Returns:
        Tuple of (previous_season, previous_year)
    """
    season_upper = season.upper()
    current_idx = SEASON_ORDER.index(season_upper)
    
    if current_idx == 0:  # Winter > previous Fall
        return SEASON_ORDER[-1], year - 1
    else:
        return SEASON_ORDER[current_idx - 1], year


def get_seasonal_anime(season: str, year: int, per_page: int = ANILIST_PER_PAGE, include_adult: bool = False, include_continuing: bool = True, grace_days: int = DEFAULT_GRACE_DAYS):
    """
    Fetch seasonal anime from AniList API, including continuing anime from previous season

    Args:
        season: Season name (WINTER, SPRING, SUMMER, FALL)
        year: Year (e.g., 2025)
        per_page: Results per page (max 50)
        include_adult: Whether to include adult/hentai content (default: False)
        include_continuing: Whether to include anime continuing from previous season (default: True)
        grace_days: Days into the new season a previous-season anime must still be
            airing to count as continuing (default: 21)

    Returns:
        List of anime dictionaries (all fields from the query), sorted by popularity (highest first)
    """
    # Current season
    logging.info(f"Fetching {format_season_name(season, year)} anime...")
    current_season_anime = _fetch_season(season, year, per_page, include_adult)
    
    results = current_season_anime.copy()
    current_ids = {anime['id'] for anime in current_season_anime}
    
    # Continuing anime from last season
    if include_continuing:
        prev_season, prev_year = get_previous_season(season, year)
        logging.info(f"Fetching continuing anime from {format_season_name(prev_season, prev_year)}...")
        
        prev_season_anime = _fetch_season(prev_season, prev_year, per_page, include_adult)
        
        # Filter for anime that are still airing/continuing
        continuing_anime = [
            a for a in prev_season_anime
            if a["id"] not in current_ids and _is_continuing(a, season, year, grace_days)
        ]
        
        if continuing_anime:
            logging.info(f"Found {len(continuing_anime)} continuing anime from previous season")
            results.extend(continuing_anime)
        else:
            logging.info("No continuing anime found from previous season")

    results.sort(key=lambda a: a.get("popularity") or 0, reverse=True)
    return results


def get_yearly_anime(year: int, per_page: int = ANILIST_PER_PAGE, include_adult: bool = False) -> list[dict]:
    """
    Fetch every anime of a calendar year, including upcoming shows with no season yet.

    Shows are collected by season year and by start date, then deduplicated. A
    show assigned to another season year belongs to that year rather than its
    start-date year.
    """
    logging.info(f"Fetching {year} anime by season...")
    by_season = _fetch_all(YEAR_SEASON_QUERY, {"year": year}, per_page, include_adult)

    logging.info(f"Fetching {year} anime by start date...")
    by_date = _fetch_all(_year_date_query(year), {}, per_page, include_adult)

    results: dict[int, dict] = {anime["id"]: anime for anime in by_season}
    added = 0
    for anime in by_date:
        if anime.get("seasonYear") not in (None, year):
            continue
        if anime["id"] not in results:
            results[anime["id"]] = anime
            added += 1

    logging.info(f"Found {len(by_season)} anime by season and {added} more by start date")
    return sorted(results.values(), key=lambda anime: anime.get("popularity") or 0, reverse=True)


def _post(query: str, variables: dict, retries: int = ANILIST_API_RETRIES) -> dict:
    """POST to AniList, retrying rate limits and transient failures."""
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(
                API_URL,
                json={"query": query, "variables": variables},
                timeout=ANILIST_API_TIMEOUT
            )
        except requests.RequestException as error:
            if attempt == retries:
                raise
            logging.warning(f"Request to AniList failed ({error}), retrying ({attempt}/{retries})...")
            time.sleep(2 * attempt)
            continue

        if resp.status_code == 429:
            if attempt == retries:
                break
            try:
                wait = max(0, int(float(resp.headers.get("Retry-After", 60))))
            except (TypeError, ValueError):
                wait = 60
            logging.warning(f"Rate limited by AniList, sleeping {wait}s")
            time.sleep(wait)
            continue
        if resp.status_code in (500, 502, 503, 504) and attempt < retries:
            logging.warning(f"AniList returned HTTP {resp.status_code}, retrying ({attempt}/{retries})...")
            time.sleep(2 * attempt)
            continue
        if not resp.ok:
            raise requests.HTTPError(f"HTTP {resp.status_code} from AniList: {resp.text[:300]}", response=resp)
        return resp.json()
    raise RuntimeError("AniList rate limit: retries exhausted")


def _fetch_pages(query: str, variables: dict, per_page: int, is_adult: bool) -> list[dict]:
    """Fetch every page of a query using AniList's strict adult filter."""
    results = []
    page = 1

    while True:
        data = _post(query, {**variables, "page": page, "perPage": per_page, "isAdult": is_adult})

        if "errors" in data:
            raise RuntimeError(f"AniList GraphQL errors on page {page}: {data['errors']}")

        page_data = (data.get("data") or {}).get("Page") or {}
        page_media = page_data.get("media", [])
        if not page_media:
            break

        results.extend(page_media)
        if not page_data.get("pageInfo", {}).get("hasNextPage", False):
            break
        page += 1

    return results


def _fetch_all(query: str, variables: dict, per_page: int, include_adult: bool) -> list[dict]:
    """Fetch non-adult media, optionally add adult media, then deduplicate and sort."""
    flags = [False, True] if include_adult else [False]
    results, seen = [], set()
    for flag in flags:
        for anime in _fetch_pages(query, variables, per_page, flag):
            if anime["id"] not in seen:
                seen.add(anime["id"])
                results.append(anime)
    results.sort(key=lambda anime: anime.get("popularity") or 0, reverse=True)
    return results


def _fetch_season(season: str, year: int, per_page: int, include_adult: bool) -> list[dict]:
    """Fetch one season, cached for the rest of the run."""
    key = (season.upper(), year, include_adult)
    if key in _season_cache:
        logging.info(f"Using already fetched {format_season_name(season, year)}")
        return list(_season_cache[key])

    results = _fetch_all(SEASON_QUERY, {"season": season.upper(), "year": year}, per_page, include_adult)
    _season_cache[key] = results
    return list(results)