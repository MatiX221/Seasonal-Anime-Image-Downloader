# src/main.py

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
from . import __version__
from .config import (
    DEFAULT_WORKERS,
    DEFAULT_DELAY,
    DEFAULT_OUT_DIR,
    DEFAULT_MERGE_NAME,
    DEFAULT_GRACE_DAYS,
    DEFAULT_TITLE_LANGUAGES,
    DEFAULT_LOG_FORMAT,
    CONFIRM_ABOVE,
    YEAR_WEIGHT,
    VALID_FORMATS,
    VALID_TITLE_LANGUAGES,
)
from .anilist import get_seasonal_anime, get_yearly_anime, filter_by_format
from .downloader import Downloader
from .genres import GenreMatcher, parse_genre_expression
from .seasons import SEASONS, Job, parse_jobs
from .sorting import SortKey, describe_sort, parse_sort, sort_anime
from .utils import (
    get_current_season,
    normalize_season,
    parse_choices,
    sanitize_filename,
)


def setup_logging(logfile: Path):
    """Configure logging to both file and console"""
    logging.basicConfig(
        level=logging.INFO,
        format=DEFAULT_LOG_FORMAT,
        handlers=[
            logging.FileHandler(logfile, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be 1 or greater")
    return number


def describe_jobs(jobs: list[Job], keep: int = 3) -> str:
    """Comma separated job names, shortened when there are many."""
    names = [job.label for job in jobs]
    if len(names) <= keep * 2 + 2:
        return ", ".join(names)
    hidden = len(names) - keep * 2
    return f"{', '.join(names[:keep])}, ... {hidden} more ..., {', '.join(names[-keep:])}"


def confirm_corrections(corrections: list[tuple[str, str, str]], assume_yes: bool) -> bool:
    """Ask the user to confirm fuzzy-matched CLI arguments, defaulting to yes."""
    if not corrections:
        return True
    for option, raw, fixed in corrections:
        if assume_yes:
            print(f'Assuming {option} "{fixed}" (from "{raw}")')
            continue
        if not sys.stdin.isatty():
            sys.exit(f'Unknown value "{raw}" for {option}. Did you mean "{fixed}"? Pass --yes (-Y) to accept automatically.')
        try:
            answer = input(f'For {option}, did you mean "{fixed}"? (Y/n) ')
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        if answer.strip().lower() not in ("", "y", "yes"):
            return False
    return True


def confirm_large_run(jobs: list[Job], assume_yes: bool) -> bool:
    """Ask before a large run, returning whether it may proceed."""
    weight = sum(job.weight for job in jobs)
    if assume_yes or weight <= CONFIRM_ABOVE:
        return True

    summary = (
        f"This run covers {weight} seasons' worth of anime (a whole year counts as {YEAR_WEIGHT}):\n"
        f"  {describe_jobs(jobs)}"
    )
    if not sys.stdin.isatty():
        sys.exit(f"{summary}\nThis needs confirmation, but there is no terminal to ask on. Pass --yes (-Y) to run it anyway.")

    print(summary)
    try:
        answer = input("Do you want to continue? (y/N) ")
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer.strip().lower() in ("y", "yes")


@dataclass
class JobOutcome:
    """Result of one season: either an error, or download counts"""
    name: str
    error: str | None = None
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0


@dataclass
class Selection:
    """What to keep from a fetched list, and in which order"""
    include_formats: list[str] | None
    exclude_formats: list[str] | None
    sort_keys: list[SortKey]
    genre: GenreMatcher | None = None
    exclude_genre: GenreMatcher | None = None


def log_section(text: str):
    logging.info("=" * 60)
    logging.info(text)
    logging.info("=" * 60)


def fetch_job(job: Job, args: argparse.Namespace) -> list[dict]:
    """Fetch one season or whole year from AniList"""
    if job.season is None:
        anime_list = get_yearly_anime(job.year, include_adult=args.include_adult)
    else:
        anime_list = get_seasonal_anime(
            job.season,
            job.year,
            include_adult=args.include_adult,
            include_continuing=not args.no_continuing,
            grace_days=args.grace_days
        )
    logging.info(f"Successfully fetched {len(anime_list)} anime titles")
    return anime_list


def select_and_download(
    label: str,
    folder_name: str,
    anime_list: list[dict],
    args: argparse.Namespace,
    selection: Selection,
    dl: Downloader,
    extra_metadata: dict | None = None,
) -> tuple[JobOutcome, list[dict]]:
    """Filter, sort, limit and download a list into one folder."""
    if selection.include_formats or selection.exclude_formats:
        before = len(anime_list)
        anime_list = filter_by_format(anime_list, selection.include_formats, selection.exclude_formats)
        logging.info(f"Format filter kept {len(anime_list)} of {before} titles")

    genre = selection.genre
    if genre is not None:
        before = len(anime_list)
        anime_list = [anime for anime in anime_list if genre(anime.get("genres"))]
        logging.info(f"Genre filter kept {len(anime_list)} of {before} titles")

    exclude_genre = selection.exclude_genre
    if exclude_genre is not None:
        before = len(anime_list)
        anime_list = [anime for anime in anime_list if not exclude_genre(anime.get("genres"))]
        logging.info(f"Exclude-genre filter kept {len(anime_list)} of {before} titles")
        if before and not anime_list:
            if genre is not None:
                logging.warning("--exclude-genre removed every title that --genre kept, check that the two expressions don't contradict each other")
            else:
                logging.warning("--exclude-genre removed every title")

    anime_list = sort_anime(anime_list, selection.sort_keys, dl.title_languages)
    logging.info(f"Sorted by {describe_sort(selection.sort_keys)}")

    if args.limit is not None and len(anime_list) > args.limit:
        anime_list = anime_list[:args.limit]
        logging.info(f"Limited to the top {args.limit} titles")

    if not anime_list:
        logging.warning(f"No anime found for {label}")
        return JobOutcome(label), []

    results = dl.download_all(
        anime_list,
        folder_name,
        write_json=not args.no_json,
        extra_metadata=extra_metadata,
    )
    outcome = JobOutcome(
        label,
        downloaded=sum(1 for result in results if result.get("status") == "ok"),
        skipped=sum(1 for result in results if result.get("status") == "skipped"),
        failed=sum(1 for result in results if result.get("status") == "failed"),
    )
    logging.info(f"Download complete: {outcome.downloaded} downloaded, {outcome.skipped} skipped, {outcome.failed} failed")
    if not args.no_json:
        logging.info(f"Metadata saved to {dl.out_dir / folder_name / 'metadata.json'}")
    if getattr(args, "no_prune", False):
        logging.info("Keeping files from earlier runs (--no-prune)")
    else:
        removed = dl.prune(folder_name, {anime["id"] for anime in anime_list})
        if removed:
            logging.info(f"Removed {len(removed)} files that are not part of this run from {folder_name}")
    return outcome, anime_list


def process_job(
    job: Job,
    args: argparse.Namespace,
    selection: Selection,
    dl: Downloader,
) -> JobOutcome:
    """Fetch, filter and download one season (or one whole year) into its own folder."""
    log_section(f"Processing {job.label}")
    anime_list = fetch_job(job, args)
    outcome, _ = select_and_download(
        job.label,
        job.name,
        anime_list,
        args,
        selection,
        dl,
    )
    return outcome


def run_merged(
    jobs: list[Job],
    folder_name: str,
    args: argparse.Namespace,
    selection: Selection,
    dl: Downloader,
) -> JobOutcome:
    """Fetch every job, merge it, download once, and prune stale owned files."""
    merged: dict[int, dict] = {}
    for job in jobs:
        log_section(f"Fetching {job.label}")
        try:
            anime_list = fetch_job(job, args)
        except Exception as e:
            raise RuntimeError(
                f"fetching {job.label} failed ({e}), so nothing was merged and the folder was left untouched"
            ) from e
        for anime in anime_list:
            merged.setdefault(anime["id"], anime)

    log_section(f"Merging into {folder_name}")
    logging.info(f"{len(merged)} unique titles from {len(jobs)} seasons/years")

    outcome, _ = select_and_download(
        folder_name,
        folder_name,
        list(merged.values()),
        args,
        selection,
        dl,
        extra_metadata={"seasons": [job.label for job in jobs]},
    )

    return outcome


def needs_year_tip(jobs: list[Job]) -> bool:
    """True if a current or future year is requested as all four seasons."""
    now_year = datetime.now().year
    for year in {job.year for job in jobs if job.year >= now_year}:
        seasons = {job.season for job in jobs if job.year == year}
        if None not in seasons and seasons >= set(SEASONS):
            return True
    return False


class SmartHelpFormatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter):
    """Clean help formatter that respects descriptions/epilog newlines and suppresses redundant defaults."""

    def __init__(self, prog):
        super().__init__(prog, max_help_position=32)

    def _get_help_string(self, action):
        help_text = action.help or ""
        if action.default in (None, False, argparse.SUPPRESS) or "%(default)" in help_text or "default:" in help_text.lower():
            return help_text
        return help_text + " (default: %(default)s)"


def main():
    parser = argparse.ArgumentParser(
        prog="anime-downloader",
        description="Seasonal Anime Cover Downloader - glorified image thief\nDownload anime cover images from AniList for any season to use with TierMaker or ranking tools.",
        formatter_class=SmartHelpFormatter,
        add_help=False,
        epilog="""examples:
  anime-downloader                            Auto-detect and download current season
  anime-downloader -s Winter -y 2025          Download specific season and year
  anime-downloader -s fall -S score -l 30     Top 30 rated shows of Fall
  anime-downloader -s year:2025 -f tv -l 50   Top 50 TV shows across all of 2025
  anime-downloader -s winter,spring --merge   Combine multiple seasons into one folder
  anime-downloader -G "(comedy&!romance)"     Filter using boolean genre expression"""
    )

    gen_group = parser.add_argument_group("General Options")
    gen_group.add_argument(
        "-h",
        "--help",
        action="help",
        help="Show this help message and exit"
    )
    gen_group.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show program's version number and exit"
    )

    target_group = parser.add_argument_group("Season & Target Selection")
    target_group.add_argument(
        "-s",
        "--season",
        nargs="+",
        metavar="SEASON",
        help="Season(s), comma separated: winter, spring, summer, fall (autumn works), any (all four) or year (the whole year, including shows with no season yet). Add :YEAR (or :START-END) to give one its own years, e.g. winter:2025 or year:2023-2025. Defaults to current season"
    )
    target_group.add_argument(
        "-y",
        "--year",
        nargs="+",
        metavar="YEAR",
        help="Year(s) or ranges, comma separated, e.g. 2025, 2023-2026. Applies to seasons without their own year. Defaults to current year"
    )
    target_group.add_argument(
        "-g",
        "--grace-days",
        type=int,
        default=DEFAULT_GRACE_DAYS,
        metavar="DAYS",
        help="Days into a season a previous-season show must still air to count as continuing"
    )
    target_group.add_argument(
        "--no-continuing",
        action="store_true",
        help="Exclude anime continuing from previous season"
    )

    filter_group = parser.add_argument_group("Filters & Sorting")
    format_group = filter_group.add_mutually_exclusive_group()
    format_group.add_argument(
        "-f",
        "--format",
        nargs="+",
        metavar="FORMAT",
        help="Only download these formats, comma separated (whitelist): TV, TV_SHORT, MOVIE, SPECIAL, OVA, ONA, MUSIC"
    )
    format_group.add_argument(
        "--exclude-format",
        nargs="+",
        metavar="FORMAT",
        help="Skip these formats, comma separated (blacklist). Can't be combined with --format"
    )
    filter_group.add_argument(
        "-G",
        "--genre",
        nargs="+",
        metavar="EXPR",
        help='Only keep shows whose genres match an expression: & both, | either, ! or ~ not, parentheses to group, e.g. "(comedy&!romance)|action". Quote it if it uses operators. Names are case-insensitive, and short forms like sol, scifi and "magical girl" work'
    )
    filter_group.add_argument(
        "--exclude-genre",
        nargs="+",
        metavar="EXPR",
        help="Drop shows whose genres match an expression (same syntax as --genre). Can be combined with --genre"
    )
    filter_group.add_argument(
        "--include-adult",
        action="store_true",
        help="Include adult / hentai content"
    )
    filter_group.add_argument(
        "-S",
        "--sort",
        nargs="+",
        metavar="KEY",
        help="Sort order, comma separated keys: popularity, score, title, start, end, id, mal_id. Add :asc or :desc to a key, e.g. score,title:desc. popularity and id are always added as tie-breakers. Decides rank numbers and what --limit keeps (default: popularity)"
    )
    filter_group.add_argument(
        "-l",
        "--limit",
        type=positive_int,
        metavar="N",
        help="Only keep top N titles per season, or in total with --merge (applied after format and genre filters and --sort)"
    )

    out_group = parser.add_argument_group("Output & File Management")
    out_group.add_argument(
        "-o",
        "--out",
        type=str,
        default=DEFAULT_OUT_DIR,
        metavar="DIR",
        help="Base output directory for downloaded covers"
    )
    out_group.add_argument(
        "-m",
        "--merge",
        nargs="?",
        const=DEFAULT_MERGE_NAME,
        metavar="NAME",
        help=f"Put everything into one folder (default name: {DEFAULT_MERGE_NAME}) instead of one per season. Duplicates are merged"
    )
    out_group.add_argument(
        "-t",
        "--title-language",
        nargs="+",
        metavar="LANG",
        default=list(DEFAULT_TITLE_LANGUAGES),
        help="Title language for file names: romaji, english, native. Comma separated in priority order; romaji is always the final fallback"
    )
    out_group.add_argument(
        "--no-json",
        action="store_true",
        help="Do not output metadata JSON"
    )
    out_group.add_argument(
        "--no-prune",
        action="store_true",
        help="Keep images from earlier runs instead of removing ones no longer part of current run"
    )
    out_group.add_argument(
        "-Y",
        "--yes",
        action="store_true",
        help=f"Skip confirmation prompts for large runs (more than {CONFIRM_ABOVE} seasons' worth, a whole year counts as {YEAR_WEIGHT}) and fuzzy-matched typos"
    )

    dl_group = parser.add_argument_group("Download & Network")
    dl_group.add_argument(
        "-w",
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        metavar="N",
        help="Number of parallel download workers"
    )
    dl_group.add_argument(
        "-d",
        "--delay",
        type=int,
        default=DEFAULT_DELAY,
        metavar="MS",
        help="Minimum delay between image requests, shared by all workers (milliseconds)"
    )
    dl_group.add_argument(
        "--force",
        action="store_true",
        help="Re-download images even if they already exist"
    )

    args = parser.parse_args()

    corrections: list[tuple[str, str, str]] = []

    try:
        include_formats, format_correction = (
            parse_choices(args.format, VALID_FORMATS, "--format", fuzzy=True) if args.format else (None, None)
        )
        if format_correction:
            corrections.append(("--format", *format_correction))

        exclude_formats, exclude_format_correction = (
            parse_choices(args.exclude_format, VALID_FORMATS, "--exclude-format", fuzzy=True) if args.exclude_format else (None, None)
        )
        if exclude_format_correction:
            corrections.append(("--exclude-format", *exclude_format_correction))

        title_languages, title_correction = parse_choices(
            args.title_language,
            VALID_TITLE_LANGUAGES,
            "--title-language",
            fuzzy=True,
        )
        if title_correction:
            corrections.append(("--title-language", *title_correction))

        sort_keys, sort_correction = parse_sort(args.sort)
        if sort_correction:
            corrections.append(("--sort", *sort_correction))

        genre, genre_correction = parse_genre_expression(" ".join(args.genre), "--genre") if args.genre else (None, None)
        if genre_correction:
            corrections.append(("--genre", *genre_correction))

        exclude_genre, exclude_genre_correction = parse_genre_expression(" ".join(args.exclude_genre), "--exclude-genre") if args.exclude_genre else (None, None)
        if exclude_genre_correction:
            corrections.append(("--exclude-genre", *exclude_genre_correction))

        jobs, warnings, season_correction = parse_jobs(
            args.season,
            args.year,
            default_season=normalize_season(get_current_season()),
            default_year=datetime.now().year,
        )
        if season_correction:
            corrections.append(("--season", *season_correction))
    except ValueError as e:
        parser.error(str(e))
    if "romaji" not in title_languages:
        title_languages.append("romaji")

    if not confirm_corrections(corrections, args.yes):
        print("Cancelled, nothing was downloaded.")
        return 1

    selection = Selection(include_formats, exclude_formats, sort_keys, genre, exclude_genre)

    merge_name = sanitize_filename(args.merge.strip() or DEFAULT_MERGE_NAME) if args.merge is not None else None

    if not confirm_large_run(jobs, args.yes):
        print("Cancelled, nothing was downloaded.")
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(out_dir / "seasonal_downloader.log")

    logging.info("=" * 60)
    logging.info("Seasonal Anime Image Downloader")
    logging.info("=" * 60)
    for warning in warnings:
        logging.warning(warning)
    logging.info(f"To process ({len(jobs)}): {', '.join(job.label for job in jobs)}")
    if needs_year_tip(jobs):
        logging.info("Tip: shows without an assigned season are not in season folders, use -s year to include them")
    if not args.include_adult:
        logging.info("Filtering out adult content (use --include-adult to disable)")
    if not args.no_continuing and any(job.season is not None for job in jobs):
        logging.info("Including anime continuing from previous season (use --no-continuing to disable)")
    if merge_name is not None:
        logging.info(f"Merging everything into one folder: {merge_name}")

    logging.info(f"Using {args.workers} download workers")
    dl = Downloader(
        out_dir=out_dir,
        max_workers=args.workers,
        delay=args.delay,
        title_languages=title_languages,
        force=args.force
    )

    outcomes: list[JobOutcome] = []
    if merge_name is not None:
        try:
            outcomes.append(run_merged(jobs, merge_name, args, selection, dl))
        except Exception as e:
            logging.error(f"Merge failed: {e}")
            outcomes.append(JobOutcome(merge_name, error=str(e)))
    else:
        for job in jobs:
            try:
                outcomes.append(process_job(job, args, selection, dl))
            except Exception as e:
                logging.error(f"{job.label} failed: {e}")
                outcomes.append(JobOutcome(job.label, error=str(e)))

    logging.info("=" * 60)
    logging.info("Summary")
    for outcome in outcomes:
        if outcome.error:
            logging.error(f"  {outcome.name}: FAILED ({outcome.error})")
        else:
            logging.info(f"  {outcome.name}: {outcome.downloaded} downloaded, {outcome.skipped} skipped, {outcome.failed} failed")
    logging.info(f"Images saved to: {out_dir}")
    logging.info("Upload them to TierMaker.com to create your tierlist!")
    logging.info("=" * 60)

    return 1 if any(outcome.error or outcome.failed for outcome in outcomes) else 0


if __name__ == '__main__':
    exit(main())