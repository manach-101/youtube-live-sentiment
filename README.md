# YouTube Live Sentiment Pipeline

A batch data-engineering pipeline that ingests YouTube live chat through the YouTube Data API v3, keeps the raw API responses as a Bronze layer, builds a deduplicated Silver dataset with spam features, and produces Gold author-level analytics. Everything is stored as local JSON and Parquet files and queried with DuckDB.

The long-term goal is to study public reactions during live news broadcasts. Sentiment analysis is **not implemented yet**; see [Roadmap](#roadmap).

## Architecture

```text
YouTube Data API v3
  videos.list ──────────────► activeLiveChatId
  liveChatMessages.list ─────► paginated polling (nextPageToken, pollingIntervalMillis,
        │                       retry/backoff, checkpoint/resume)
        ▼
Bronze  raw/youtube_comments_<UTC timestamp>.json      unmodified API pages
        raw/youtube_video_<UTC timestamp>.json          video metadata
        raw/_state/<liveChatId>.json                    page-token checkpoint
        │   python -m src.processing.process_raw_files
        ▼
Silver  data/processed/youtube_messages.parquet         1 row per unique message_id
        normalize → dedupe → features → heuristic spam score
        │   python -m src.processing.build_gold
        ▼
Gold    data/analytics/author_summary.parquet           1 row per author_channel_id
        │
        ▼
DuckDB  src/analytics/queries.py                        ad-hoc SQL over Silver
```

`python -m src.pipeline` runs Silver and Gold in one step. Every layer after Bronze is derived state, so it can be deleted and rebuilt at any time without calling the API again.

## Quick start (fresh machine)

Requirements: **Python 3.12 or newer** (the pinned numpy 2.5 needs it) and `git`. `make` is optional.

```bash
git clone https://github.com/manach-101/youtube-live-sentiment.git
cd youtube-live-sentiment
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Check the install offline (no API key needed):

```bash
python -m pytest -q
python -m src.pipeline --raw-dir tests/fixtures/raw --data-dir data/demo
```

If you have `make`: `make setup`, `make test` and `make demo` do the same things.

### Freshly formatted Mac

macOS ships without a suitable Python. Install the Xcode Command Line Tools (which provide `git` and `make`) and Homebrew, then Python 3.12:

```bash
xcode-select --install
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install python@3.12
```

Then clone the repo and run the setup, tests and demo, using Homebrew's Python explicitly:

```bash
git clone https://github.com/manach-101/youtube-live-sentiment.git && cd youtube-live-sentiment
make setup PYTHON=python3.12
make test
make demo
cp .env.example .env    # then edit .env and set YOUTUBE_API_KEY
```

## Configuration

```bash
cp .env.example .env
```

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `YOUTUBE_API_KEY` | ingestion only | none | API key with YouTube Data API v3 enabled |
| `YOUTUBE_VIDEO_ID` | no | none | Default for `--video-id` |
| `RAW_DIR` | no | `raw` | Bronze directory |
| `SILVER_PATH` | no | `data/processed/youtube_messages.parquet` | Silver output |
| `GOLD_PATH` | no | `data/analytics/author_summary.parquet` | Gold output |

`.env`, `raw/` and `data/` are git-ignored. Only ingestion needs the API key; processing, analytics and tests run without it.

## Running

### 1. Ingest a live chat (needs API key and a currently live stream)

```bash
python -m src.youtube_ingest --video-id <VIDEO_ID> --duration 600
```

| Option | Meaning |
|---|---|
| `--duration SECONDS` / `--max-polls N` | Stop after a time limit or number of polls. Without either, it runs until the chat ends or you press Ctrl+C. |
| `--max-results N` | Messages per page, 200–2000 (default 2000). Values outside the range are rejected before any API call (exit code 2). |
| `--no-resume` | Ignore the saved page-token checkpoint. |
| `--raw-dir DIR` | Where to write Bronze files. |
| `-v` | Debug logging. |

Exit codes: `0` success, `1` API or video error (for example no active chat or quota exhausted), `2` configuration or argument error (missing key or video ID, invalid `--max-results`).

How ingestion behaves:

- **Pagination**: follows `nextPageToken` and waits the API's `pollingIntervalMillis` (at least 1 s) between polls.
- **Retries**: network errors, HTTP 429/5xx, `rateLimitExceeded`, and HTTP 200 responses whose body is not a JSON object (for example a truncated transfer or a proxy page, reported as `invalidJson`) are retried with exponential backoff plus jitter, up to 5 retries. `Retry-After` is honored. Permanent errors such as `quotaExceeded`, an invalid key, or a chat that has ended are not retried.
- **Stops cleanly** on `offlineAt`, `liveChatEnded`/`liveChatNotFound`/`liveChatDisabled`, the duration or poll limit, or Ctrl+C.
- **Safe persistence**: each non-empty page is written atomically (temp file then rename) with a microsecond timestamp and never overwrites an existing file. The page token is checkpointed after every page, so a restart resumes where it stopped. The checkpoint is reset only when the API rejects the page token itself (HTTP 400 with reason `invalidPageToken` or `pageTokenInvalid`); ingestion then restarts from the current head of the chat. Any other error leaves the checkpoint intact so a later run can resume.
- **Duplicates**: Bronze keeps API pages unchanged. Overlapping messages are counted in the logs and removed in Silver by `message_id`.
- **Secrets**: the API key is redacted from error messages, and `urllib3` request-URL logging is silenced.

### 2. Build Silver and Gold

```bash
python -m src.pipeline                      # raw/ -> data/
# or step by step:
python -m src.processing.process_raw_files  # --raw-dir, --output
python -m src.processing.build_gold         # --silver-path, --output
```

### 3. Query with DuckDB

```python
from src.analytics.queries import (
    get_messages_per_minute, get_spam_summary, get_stream_summary, get_top_authors,
)

print(get_spam_summary())
print(get_top_authors(limit=5))
print(get_messages_per_minute())
print(get_stream_summary())          # one row per live_chat_id

# Every query takes an optional silver_path=; all except get_stream_summary
# also take live_chat_id= to restrict results to one stream.
print(get_messages_per_minute(live_chat_id="<LIVE_CHAT_ID>"))
```

## Data contracts

**Bronze**: `raw/youtube_comments_*.json` files hold the `liveChatMessages.list` response unchanged (`items[].id`, `items[].snippet`, `items[].authorDetails`).

**Silver**: `youtube_messages.parquet` has one row per unique `message_id` for viewer messages only, with a fixed schema.

Only items whose `snippet.type` is `textMessageEvent` or `superChatEvent` reach Silver. Moderation and system events such as `messageDeletedEvent` and `userBannedEvent` stay in Bronze but are excluded, and the Silver step reports how many of each type it excluded. Items with no `snippet.type` (which the API does not produce) are kept.

| Column | Type | Notes |
|---|---|---|
| `message_id` | string | unique |
| `author_channel_id` | string | |
| `author_name` | string | display name (not unique) |
| `message` | string | `displayMessage`; null if absent |
| `published_at` | string | ISO-8601 exactly as returned by the API |
| `is_moderator`, `is_owner`, `is_verified` | bool | |
| `duplicate_text_count` | int64 | occurrences of the identical text **within the same `live_chat_id`** |
| `repeated_character_ratio` | float64 | share of adjacent identical graphemes (Unicode-aware) |
| `seconds_since_previous_message` | float64 | gap from the same author's previous message **in the same `live_chat_id`**; null for their first |
| `spam_score` | float64 | 0.0–1.0 |
| `is_spam` | bool | `spam_score >= 0.7` |
| `live_chat_id` | string | stream the message belongs to (`snippet.liveChatId`); null if absent. Added as the last column. |

Spam features are computed per stream, so activity in one live chat never changes the duplicate counts, posting gaps or spam flags of another. Messages with a null `live_chat_id` are treated as one stream.

**Gold**: `author_summary.parquet` has one row per `author_channel_id` across all streams (unchanged contract), with columns `author_channel_id`, `author_name` (latest display name), `total_messages`, `spam_messages`, `average_spam_score` and `spam_rate`. Rows are sorted by `total_messages` descending. The spam flags it aggregates were computed per stream; for per-stream totals use `get_stream_summary()` or the `live_chat_id=` filter on the DuckDB queries.

### Spam heuristic

The score is a simple, interpretable rule-based heuristic, not a trained model. It adds up three signals:

| Signal | Points |
|---|---|
| `duplicate_text_count >= 3` | +0.4 |
| `seconds_since_previous_message < 15` | +0.4 |
| `repeated_character_ratio > 0.10` | +0.2 |

A message needs at least two signals, one of which must be duplicate text or fast posting, to reach the 0.7 spam threshold. The thresholds have not been calibrated against labelled data.

## Tests

```bash
python -m pytest -q
```

There are 76 offline tests:

| File | Covers |
|---|---|
| `test_pipeline_end_to_end.py` | Bronze → Silver → Gold on fixtures: expected counts, schemas, dedup, event filtering, stream isolation, Bronze unchanged, idempotency, corrupt or unrelated files, empty input, DuckDB queries (overall and per stream) |
| `test_youtube_client.py` | Request parameters, retry/backoff, `Retry-After`, non-retryable errors, retry limit, key redaction, `liveChatId` extraction |
| `test_live_chat_poller.py` | Page tokens, polling interval, checkpoint/resume, stale tokens, stop conditions, Ctrl+C, overlap counting |
| `test_spam_features.py`, `test_spam_classifier.py`, `test_normalize_messages.py` | Feature and classifier logic, Unicode graphemes, mixed timestamp formats |
| `test_storage_and_cli.py` | Atomic, non-overwriting raw writes; CLI exit codes; full CLI run against a fake HTTP session |
| `test_review_regressions.py` | Regressions for review findings: moderation events excluded (H1), per-stream features (H2), checkpoint reset only for invalid tokens and `--max-results` range (M1), malformed JSON in HTTP 200 (M2) |

The fixtures in `tests/fixtures/raw/` are **synthetic**. They follow the documented API response shape but no data in them was captured from YouTube. See `tests/fixtures/README.md` for the edge cases they contain.

## Verified results

These were checked on 2026-11-21 with `pip install -r requirements.txt` in a new virtualenv. GitHub Actions runs the same suite on every pull request.

- Python 3.12 and 3.13: install succeeds and **76 passed**.
- Python 3.11: install **fails** because numpy 2.5.2 requires Python 3.12 or newer, hence the 3.12+ requirement.
- Demo on the synthetic fixtures (`python -m src.pipeline --raw-dir tests/fixtures/raw --data-dir data/demo`):

```text
Files processed: 5
Duplicate messages dropped: 1
Non-text events excluded: 2 (messageDeletedEvent=1, userBannedEvent=1)
Messages processed: 13
Spam messages: 2
Authors summarized: 6
```

**Not verified:** ingestion against the real YouTube API. No API key or live stream was available while reviving the project. The HTTP client and polling loop are tested only against fakes that follow the documented API behaviour.

## Limitations

- **Live API untested in this revision.** The first real run should be short, for example `--max-polls 3`, followed by a check of the raw files.
- **Quota.** Every poll uses YouTube API quota. Long sessions can exhaust the daily quota, and ingestion then stops with `quotaExceeded`.
- **Batch, not streaming.** Silver and Gold are full rebuilds from Bronze. That is simple and idempotent, but cost grows with the size of `raw/`.
- **Duplicate detection spans all authors within a stream.** `duplicate_text_count` counts identical text from anyone in the same live chat, so common short messages ("hi", "🔥") from many people raise the count. Combined with the cadence signal this can flag enthusiastic but legitimate users.
- **Polling resumes but may skip messages.** If a checkpoint token is rejected, ingestion restarts from the current head of the chat and messages posted in between are not fetched.
- **Event filtering uses an allowlist.** Only `textMessageEvent` and `superChatEvent` reach Silver; other types (memberships, Super Stickers, polls, ...) are excluded and counted. Super Chat amounts are not parsed.
- **Page-token error reasons are unverified.** `invalidPageToken` and `pageTokenInvalid` come from the API documentation and have not been observed against the live API. If YouTube uses another reason, the run stops with exit code 1 and keeps the checkpoint; `--no-resume` then starts from the chat head.
- **A network outage of about 30 seconds ends the run.** Retries are bounded; restart the command and it resumes from the checkpoint.
- **No sentiment or NLP** yet, despite the project name.

## Changes in this revision

- Silver deduplicates by `message_id`. Overlapping polls previously created duplicate rows, a fake 0-second cadence and inflated duplicate counts, which made false spam positives likely.
- Gold groups by `author_channel_id` instead of `author_name`. Different channels with the same display name were previously merged. **Contract change:** a new `author_channel_id` column was added, and the existing columns are unchanged.
- Cadence is ordered by parsed timestamps. String ordering mis-sorted mixed formats (`…18Z` vs `…18.7+00:00`) and produced negative intervals.
- An empty `raw/` previously crashed Gold. Silver and Gold now have explicit Parquet schemas and are written atomically.
- `settings.py` no longer raises on import, so processing and tests run without a key.
- Ingestion was rewritten from a one-shot script with a hardcoded video ID and `maxResults=5` into a CLI with polling, retries, a checkpoint and logging.
- Raw files use microsecond timestamps and never overwrite each other. Before, two saves in the same second clobbered each other.
- The `src/main.py` placeholder was removed.
- Review fixes:
  - Moderation events no longer appear in Silver as messages.
  - **Contract change (additive):** Silver gains a `live_chat_id` column, and spam features are computed per stream.
  - The checkpoint is reset only for invalid-page-token errors, and `--max-results` is validated.
  - A malformed JSON body in an HTTP 200 response is retried instead of crashing.

## Project structure

```text
src/
  config/settings.py              env-based configuration
  ingestion/youtube.py            API client (retry/backoff, errors)
  ingestion/live_chat_poller.py   pagination, checkpoint, stop conditions
  storage/raw_writer.py           atomic raw JSON writes
  storage/parquet_writer.py       atomic Parquet writes with schema
  processing/normalize_messages.py
  processing/process_raw_files.py Bronze -> Silver
  processing/build_gold.py        Silver -> Gold
  features/spam_features.py
  classification/spam_classifier.py
  analytics/queries.py            DuckDB queries
  pipeline.py                     Silver + Gold runner
  youtube_ingest.py               ingestion CLI
tests/
  fixtures/raw/                   synthetic API pages
Makefile  requirements.txt  .env.example  .python-version
```

## Roadmap

These are **not implemented**:

- Sentiment analysis, entity and topic extraction
- Calibrating the spam heuristic against labelled data; per-author duplicate features
- Incremental Silver builds, partitioned by stream or date
- Scheduling or orchestration (cron is likely enough) and Docker packaging
- A dashboard or API over Gold
- Streaming (for example Kafka), only if volume justifies it

## Why this project?

Most introductory data projects use static datasets. This one works with continuously generated real-world events and the problems that come with them: API ingestion, raw data preservation, reproducible transformations, behavioral feature engineering and data quality.
