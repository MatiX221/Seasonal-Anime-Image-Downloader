# src/config.py

"""
Central configuration defaults and constants for Seasonal Anime Image Downloader.
"""

from typing import Sequence

# --- Download & Concurrency Defaults ---
DEFAULT_WORKERS: int = 8
DEFAULT_DELAY: int = 50  # Minimum milliseconds between requests across all workers
DOWNLOAD_RETRIES: int = 2
DOWNLOAD_BACKOFF: float = 1.0  # Backoff multiplier in seconds

# --- Output & Storage Defaults ---
DEFAULT_OUT_DIR: str = "seasonal"
DEFAULT_MERGE_NAME: str = "Merged"
DEFAULT_TITLE_LANGUAGES: Sequence[str] = ("romaji",)
DEFAULT_LOG_FORMAT: str = "%(asctime)s - %(levelname)s - %(message)s"

# --- Season & Year Defaults ---
DEFAULT_GRACE_DAYS: int = 21  # Days into a season a previous-season anime must air to count as continuing
MIN_YEAR: int = 1950
YEAR_WEIGHT: int = 4  # Weight of a full year (4 seasons) for confirmation checks
CONFIRM_ABOVE: int = 5  # Prompt confirmation if jobs exceed this number of seasons

SEASON_START_MONTH: dict[str, int] = {
    "WINTER": 1,
    "SPRING": 4,
    "SUMMER": 7,
    "FALL": 10,
}
SEASONS: tuple[str, ...] = tuple(SEASON_START_MONTH.keys())
SEASON_ORDER: list[str] = ["WINTER", "SPRING", "SUMMER", "FALL"]
SEASON_ALIASES: dict[str, str] = {"AUTUMN": "FALL"}

# --- Formats & Languages ---
VALID_FORMATS: tuple[str, ...] = ("TV", "TV_SHORT", "MOVIE", "SPECIAL", "OVA", "ONA", "MUSIC")
VALID_TITLE_LANGUAGES: tuple[str, ...] = ("romaji", "english", "native")

# --- AniList API Settings ---
ANILIST_API_URL: str = "https://graphql.anilist.co"
ANILIST_API_TIMEOUT: int = 30  # seconds
ANILIST_PER_PAGE: int = 50  # AniList GraphQL max results per page
ANILIST_API_RETRIES: int = 3

