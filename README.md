# YouTube Live Sentiment Pipeline

A data engineering project that ingests live YouTube chat data, preserves raw API responses, transforms events into analytics-ready datasets, and enriches messages with spam-related behavioral features.

The project is designed incrementally toward an end-to-end streaming analytics architecture for studying public reactions and narrative shifts during live news broadcasts.

## Current Architecture

```text
YouTube Live Stream
        │
        ▼
YouTube Data API v3
        │
        ▼
Python Ingestion Layer
        │
        ├── Video Metadata
        └── Live Chat Messages
        │
        ▼
Raw JSON Storage
        │
        ▼
Normalization
        │
        ▼
Feature Engineering
        │
        ├── Duplicate text count
        ├── Repeated character ratio
        └── Message cadence
        │
        ▼
Spam Classification
        │
        ▼
Silver Parquet Dataset
        │
        ▼
Author-Level Aggregations
        │
        ▼
Gold Analytics Dataset
```

## Data Layers

The pipeline follows a layered data model.

### Raw / Bronze

Original YouTube API responses are preserved as timestamped JSON files.

This layer acts as the source of truth and allows downstream datasets to be rebuilt without requesting the original events again.

### Silver

Raw chat events are normalized into a flat analytical schema and enriched with behavioral features.

Current fields include:

- `message_id`
- `author_channel_id`
- `author_name`
- `message`
- `published_at`
- `is_moderator`
- `is_owner`
- `is_verified`
- `duplicate_text_count`
- `repeated_character_ratio`
- `seconds_since_previous_message`
- `spam_score`
- `is_spam`

Silver data is stored in Apache Parquet.

### Gold

The Gold layer currently produces author-level analytics including:

- Total messages
- Spam messages
- Average spam score
- Spam rate

This layer is intended to serve downstream BI, dashboards, and analytical workloads.

## Spam Detection

The current spam classifier is heuristic and intentionally interpretable.

It combines multiple behavioral signals rather than relying on a single rule:

- Exact message repetition
- Short intervals between messages from the same author
- Repeated visual characters or symbols

These signals are converted into a `spam_score` between `0.0` and `1.0`.

Messages above the current threshold are marked with:

```text
is_spam = True
```

The classifier is an early-stage analytical component and will evolve as more real-world chat data is collected.

## Current Features

- YouTube Data API v3 integration
- Dynamic `liveChatId` discovery
- Live chat message ingestion
- Video and channel metadata extraction
- Timestamped raw API response preservation
- Raw-to-Silver normalization pipeline
- Apache Parquet output
- Unicode-aware repeated-character detection
- Message cadence analysis by author
- Duplicate-message feature engineering
- Rule-based spam scoring
- Author-level Gold aggregations
- Environment-based API key configuration
- Modular ingestion, storage, processing, feature, and classification layers
- Generated datasets excluded from version control

## Project Structure

```text
youtube-live-sentiment/
│
├── src/
│   ├── classification/
│   │   ├── __init__.py
│   │   └── spam_classifier.py
│   │
│   ├── config/
│   │   └── settings.py
│   │
│   ├── features/
│   │   └── spam_features.py
│   │
│   ├── ingestion/
│   │   └── youtube.py
│   │
│   ├── processing/
│   │   ├── __init__.py
│   │   ├── normalize_messages.py
│   │   ├── process_raw_files.py
│   │   └── build_gold.py
│   │
│   ├── storage/
│   │   ├── raw_writer.py
│   │   └── parquet_writer.py
│   │
│   ├── main.py
│   └── youtube_ingest.py
│
├── raw/
├── data/
│   ├── processed/
│   └── analytics/
│
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

Generated files under `raw/` and `data/` are excluded from version control.

## Tech Stack

### Currently Implemented

- Python
- YouTube Data API v3
- Requests
- Pandas
- Apache Arrow / PyArrow
- Apache Parquet
- Regex / Unicode grapheme processing
- Git / GitHub

## Running the Pipeline

### 1. Ingest Live YouTube Data

```bash
python3 src/youtube_ingest.py
```

### 2. Build the Silver Dataset

```bash
python3 -m src.processing.process_raw_files
```

Example output:

```text
Files processed: 4
Messages processed: 20
Spam messages: 3
Output: data/processed/youtube_messages.parquet
```

### 3. Build the Gold Analytics Dataset

```bash
python3 -m src.processing.build_gold
```

Example output:

```text
Authors summarized: 9
Output: data/analytics/author_summary.parquet
```

## Design Principles

The project currently follows several core data engineering principles:

- Preserve raw source data before transformation
- Treat processed datasets as reproducible derived state
- Keep ingestion, transformation, feature engineering, classification, and storage concerns separated
- Avoid exposing credentials in source code
- Keep generated datasets outside Git
- Prefer deterministic and inspectable transformations
- Preserve event-level data before performing analytical deduplication or aggregation

## Roadmap

The project is being developed incrementally toward a streaming architecture.

```text
YouTube Live
      │
      ▼
Python Producer
      │
      ▼
Apache Kafka
      │
      ▼
Streaming Processing
      │
      ├── Data Quality
      ├── Spam / Bot Detection
      ├── NLP
      ├── Entity Recognition
      └── Sentiment Analysis
      │
      ▼
Analytical Storage
      │
      ▼
API Layer
      │
      ▼
Real-Time Dashboard
```

Planned next steps include:

- DuckDB-based analytical querying
- Dockerized execution
- Automated pipeline orchestration
- Message-per-minute aggregations
- More robust bot and spam behavioral features
- Sentiment analysis
- Entity and topic extraction
- PostgreSQL or analytical database integration
- Backend API for serving analytics
- Interactive dashboard
- Apache Kafka for streaming ingestion

## Why This Project?

Most introductory data projects rely on static datasets.

This project focuses instead on continuously generated real-world events and the engineering challenges that come with them: API ingestion, raw data preservation, reproducible transformations, behavioral feature engineering, data quality, analytical storage, and eventually streaming analytics.

The long-term objective is to analyze how public sentiment, discussion topics, and coordinated behavior evolve during live news events while maintaining a reproducible and extensible data pipeline.
