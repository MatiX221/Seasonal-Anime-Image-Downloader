# Seasonal Anime Image Downloader

Your friendly neighborhood glorified image thief for seasonal anime 🎬

Download all anime cover images from any season to use with TierMaker or other tierlist creators!

## What This Does

Downloads anime cover images from AniList for a given season. Perfect for:

- Creating tierlists on TierMaker.com
- Building your own anime ranking tools
- Collecting seasonal anime artwork

## Features

- 🔍 Fetches seasonal or whole-year anime from the AniList API, across single or multiple seasons and year ranges
- 🔄 Includes anime continuing from the previous season (with a configurable grace period)
- 🎯 Filters by format and boolean genre expressions (`&`, `|`, `!`, parentheses), with custom sorting (`popularity`, `score`, `title`, `start`, `end`, `id`, `mal_id`)
- 🗂️ Optional `--merge` mode to combine multiple seasons or years into a single deduplicated folder
- 🧹 Every folder is kept in sync with the latest run, removing images that are no longer part of it (`--no-prune` to keep them)
- 💡 Suggests the closest match for misspelled option values
- 📥 Downloads cover images in parallel with retry logic
- 📊 Saves metadata JSON for reference
- ⚡ Global rate limiting, and automatic waiting and retrying when AniList rate limits you
- 🛡️ Safe writes, so interrupted downloads never leave broken images behind
- ⏭️ Skips already downloaded images

## Installation

```bash
# Clone the repository
git clone https://github.com/Daiya404/Seasonal-Anime-Image-Downloader.git
cd Seasonal-Anime-Image-Downloader

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Basic Usage (Auto-detect current season)

```bash
python -m src
```

### Specify Season and Year

```bash
python -m src -s Winter -y 2025
```

### Multiple Seasons and Years

```bash
# Several seasons and years (every combination, one folder each)
python -m src -s winter,spring -y 2025,2026

# Mix explicit years with a year list
python -m src -s winter:2024,spring -y 2025

# All four seasons of a year
python -m src -s any -y 2025

# A range of years
python -m src -s winter -y 2023-2025

# A whole year in one folder named after the year (includes shows with no season yet)
python -m src -s year:2027 -f tv -l 50

# Several whole years, one folder each
python -m src -s year -y 2025-2027

# One folder with everything from two seasons
python -m src -s winter,spring -y 2025 --merge

# The same, in a folder with a name of your choosing
python -m src -s winter,spring -y 2025 --merge "Winter and Spring 2025"
```

### Keeping Earlier Images

```bash
# Normally the folder ends up with exactly the 3 images of the latest run
python -m src -s fall -y 2025 -l 3

# With --no-prune, images from earlier runs stay
python -m src -s fall -y 2025 -l 3 --no-prune
```

### Sorting

```bash
# The 30 best-rated TV shows of a season
python -m src -s fall -f tv -S score -l 30

# Newest start date first, alphabetical among shows that started on the same day
python -m src -s fall -S start:desc,title
```

### Example: Filtered Seasonal Run

```bash
python -m src \
  --season fall \
  --year 2025 \
  --out ./output \
  --format TV,ONA \
  --limit 50 \
  --title-language english,native \
  --no-json
```

### Genre Filters

```bash
# Comedies without romance, plus any action show
python -m src -s fall -G "(comedy&!romance)|action"

# Everything except ecchi and horror
python -m src -s fall --exclude-genre "ecchi|horror"
```

## Arguments

| Argument           | Short | Description                                                                                                                                                                                                                                                       | Default        |
| ------------------ | ----- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------- |
| `--season`         | `-s`  | Season(s), comma separated: Winter/Spring/Summer/Fall (`autumn` also works), `any` for all four, or `year` for the whole year including shows with no season yet. Add `:year` or `:start-end` to give one its own years, e.g. `winter:2025` or `winter:2023-2025` | Current season |
| `--year`           | `-y`  | Year(s) or ranges, comma separated, e.g. `2025, 2023-2026`. Applies to seasons without their own year                                                                                                                                                             | Current year   |
| `--out`            | `-o`  | Output directory                                                                                                                                                                                                                                                  | `seasonal`     |
| `--workers`        | `-w`  | Number of parallel download workers                                                                                                                                                                                                                               | 8              |
| `--delay`          | `-d`  | Minimum delay between image requests, shared by all workers (milliseconds)                                                                                                                                                                                       | 50             |
| `--grace-days`     | `-g`  | Days into a season a previous-season show must still air to count as continuing (seasons only)                                                                                                                                                                    | 21             |
| `--no-continuing`  |       | Exclude anime continuing from the previous season (seasons only)                                                                                                                                                                                                  | False          |
| `--no-json`        |       | Skip metadata JSON output                                                                                                                                                                                                                                         | False          |
| `--include-adult`  |       | Include adult/hentai content                                                                                                                                                                                                                                      | False          |
| `--format`         | `-f`  | Only download the specified formats, comma separated; mutually exclusive with `--exclude-format`                                                                                                                                                                  | All formats    |
| `--exclude-format` |       | Skip the specified formats, comma separated; mutually exclusive with `--format`                                                                                                                                                                                   | None           |
| `--genre`          | `-G`  | Only keep shows whose genres match an expression: `&` both, `\|` either, `!` or `~` not, parentheses to group, e.g. `"(comedy&!romance)\|action"`. Names are case-insensitive and short forms work (`sol`, `scifi`, `magical girl`)                               | All            |
| `--exclude-genre`  |       | Drop shows whose genres match an expression (same syntax). Can be combined with `--genre`                                                                                                                                                                         | None           |
| `--limit`          | `-l`  | Keep only the top N titles per season (or in total with `--merge`), applied after format and genre filters and `--sort`                                                                                                                                           | All titles     |
| `--merge`          | `-m`  | Put everything into one folder (named `Merged`, or the name you give) instead of one per season. Duplicates are merged                                                                                                                                            | False          |
| `--sort`           | `-S`  | Sort by `popularity`, `score`, `title`, `start`, `end`, `id`, or `mal_id`; add `:asc` or `:desc`. Controls ranks and `--limit`; popularity and id are added as tie-breakers, and missing values go last                                                           | popularity     |
| `--title-language` | `-t`  | File-name title priority: `romaji`, `english`, `native`; `romaji` is always the final fallback                                                                                                                                                                    | `romaji`       |
| `--force`          |       | Re-download images even if they already exist                                                                                                                                                                                                                     | False          |
| `--no-prune`       |       | Keep images from earlier runs. By default each folder is kept in sync with the latest run                                                                                                                                                                         | False          |
| `--yes`            | `-Y`  | Skip confirmation prompts for large runs (more than 5 seasons' worth, a whole year counts as 4) and fuzzy-matched option typos                                                                                                                                    | False          |

### Genre Expression Notes

Genre expressions that use `&`, `|` or `!` must be quoted: double quotes in PowerShell and cmd, single quotes in bash (so `!` isn't expanded). A single genre doesn't need quotes. Genres are AniList's: Action, Adventure, Comedy, Drama, Ecchi, Fantasy, Hentai, Horror, Mahou Shoujo, Mecha, Music, Mystery, Psychological, Romance, Sci-Fi, Slice of Life, Sports, Supernatural, Thriller.

### Folder Cleanup

By default each output folder mirrors the latest run: images this tool downloaded earlier that are no longer part of it (for example after lowering `--limit` or changing filters) are removed. Only files named like the tool's own images (`rank - id - title.jpg`) and leftover `.part` files are touched, nothing is removed when a run finds no anime, and other files in the folder are left alone. Use `--no-prune` to keep everything. Don't give `--merge` the name of a folder you want to keep as it is.

### Title Languages

Title languages are tried in the order provided. For example, `-t english,native` uses English
titles first, then native titles, then romaji. Existing files are renamed when the selected
language changes; images are not downloaded again.

### Confirmation Prompts

Runs covering more than 5 seasons' worth of anime (a whole year counts as 4) ask for confirmation before downloading. Close typos in `--season`, `--sort`, `--genre`, `--exclude-genre`, `--title-language`, `--format` and `--exclude-format` also ask for confirmation (`Did you mean ...? (Y/n)`). Use `--yes` (`-Y`) to accept both automatically, including when running without a terminal.

## Output Structure

```
seasonal/
├── Winter 2025/
│   ├── 001 - 12345 - Anime Title 1.jpg
│   ├── 002 - 67890 - Anime Title 2.jpg
│   ├── ...
│   └── metadata.json
└── seasonal_downloader.log
```

File names are `rank - AniList ID - title`, and `metadata.json` lists the anime in the selected `--sort` order (popularity by default). Whole years use the year as the folder name (`2025`), and `--merge` uses `Merged` or the name you give.

## Using with TierMaker

1. Run the downloader for your desired season
2. Go to [TierMaker.com](https://tiermaker.com)
3. Click "Create a Tier List"
4. Upload all the downloaded images
5. Create your rankings!

## Requirements

- Python 3.10+
- requests
- tqdm

## License

MIT License - See [LICENSE](LICENSE) file for details

## Disclaimer

This tool downloads publicly available cover images from AniList for personal use. Please respect AniList's terms of service and rate limits.

## Contributing

Pull requests welcome! Please feel free to submit issues or improvements.

---

_Made with ❤️ for the anime community_
