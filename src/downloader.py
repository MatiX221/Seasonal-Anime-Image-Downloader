# src/downloader.py

import os
import json
import re
import time
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import threading
from tqdm import tqdm
from typing import List, Sequence
from .config import (
    DEFAULT_WORKERS,
    DEFAULT_DELAY,
    DOWNLOAD_RETRIES,
    DOWNLOAD_BACKOFF,
    DEFAULT_TITLE_LANGUAGES,
)
from .utils import sanitize_filename, pick_title


# Names this tool gives its own files: 'rank - AniList id - title.jpg'
_IMAGE_NAME_RE = re.compile(r"^\d+ - (\d+) - .*\.jpg$")
_PART_NAME_RE = re.compile(r"^\d+ - \d+ - .*\.jpg\.part$")


class Downloader:
    def __init__(
        self,
        out_dir: str | Path,
        max_workers: int = DEFAULT_WORKERS,
        delay: int = DEFAULT_DELAY,
        retries: int = DOWNLOAD_RETRIES,
        backoff: float = DOWNLOAD_BACKOFF,
        title_languages: Sequence[str] = DEFAULT_TITLE_LANGUAGES,
        force: bool = False,
    ):
        self.out_dir = Path(out_dir)
        self.max_workers = max_workers
        self.delay = delay
        self.retries = retries
        self.backoff = backoff
        self.title_languages = tuple(title_languages)
        self.force = force
        self._local = threading.local()
        self._rate_lock = threading.Lock()
        self._next_slot = 0.0

    def _get_session(self) -> requests.Session:
        if not hasattr(self._local, "session"):
            self._local.session = requests.Session()
        return self._local.session

    def _throttle(self):
        """Global spacing between requests, shared by all workers"""
        delay_sec = self.delay / 1000.0
        with self._rate_lock:
            now = time.monotonic()
            wait = self._next_slot - now
            self._next_slot = max(now, self._next_slot) + delay_sec
        if wait > 0:
            time.sleep(wait)

    def _download_one(self, item, index, season_folder: Path):
        title = sanitize_filename(pick_title(item, self.title_languages))
        cover = item.get("coverImage") or {}
        url = cover.get("extraLarge") or cover.get("large")
        
        if not url:
            logging.warning(f"No cover image URL for {title}")
            return {"status": "failed", "file": None, "title": title}
        
        filename = f"{index:03d} - {item['id']} - {title}.jpg"
        filepath = season_folder / filename

        existing = next(season_folder.glob(f"* - {item['id']} - *.jpg"), None)
        if not self.force and existing and existing.stat().st_size > 1024:
            if existing != filepath:
                existing.replace(filepath)  # rank changed, fix the number
            logging.info(f"Skipping existing {filename}")
            return {"status": "skipped", "file": str(filepath), "title": title}

        attempt = 0
        while attempt <= self.retries:
            try:
                self._throttle()
                resp = self._get_session().get(url, timeout=30)
                resp.raise_for_status()
                tmp = filepath.with_name(filepath.name + ".part")
                with open(tmp, "wb") as f:
                    f.write(resp.content)
                os.replace(tmp, filepath)
                if existing and existing != filepath:
                    existing.unlink(missing_ok=True)  # old name or corrupt leftover
                return {"status": "ok", "file": str(filepath), "title": title}
            except Exception as e:
                attempt += 1
                logging.warning(f"Attempt {attempt} failed for {title}: {e}")
                if attempt <= self.retries:
                    time.sleep(self.backoff * attempt)
        
        return {"status": "failed", "file": str(filepath), "title": title}

    def download_all(
        self,
        anime_list: List[dict],
        season_name: str,
        write_json: bool = True,
        extra_metadata: dict | None = None,
    ) -> List[dict]:
        season_folder = self.out_dir / season_name
        season_folder.mkdir(parents=True, exist_ok=True)

        with ThreadPoolExecutor(max_workers=self.max_workers) as exc:
            futures = [
                exc.submit(self._download_one, item, idx + 1, season_folder)
                for idx, item in enumerate(anime_list)
            ]

            for _ in tqdm(as_completed(futures), total=len(futures), desc="Downloading", unit="img"):
                pass

        results: List[dict] = []
        for fut, item in zip(futures, anime_list):
            try:
                results.append(fut.result())
            except Exception as e:
                logging.exception(f"A future failed outright: {e}")
                results.append({"status": "failed", "file": None, "title": str(item.get("id"))})

        if write_json:
            meta_path = season_folder / "metadata.json"
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump({"season": season_name, **(extra_metadata or {}), "items": results}, f, ensure_ascii=False, indent=2)

        return results

    def prune(self, folder_name: str, keep_ids: set[int]) -> list[str]:
        """
        Remove tool-owned images not in keep_ids and leftover partial files.

        Other files and subfolders are left untouched.
        """
        folder = self.out_dir / folder_name
        removed: list[str] = []
        if not folder.is_dir():
            return removed

        for path in sorted(folder.iterdir()):
            if not path.is_file():
                continue
            match = _IMAGE_NAME_RE.match(path.name)
            stale_image = match is not None and int(match.group(1)) not in keep_ids
            if stale_image or _PART_NAME_RE.match(path.name):
                path.unlink()
                removed.append(path.name)
                logging.info(f"Removed {path.name}")
        return removed