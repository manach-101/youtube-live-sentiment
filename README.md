# YouTube Live Sentiment Pipeline

A real-time data engineering project that collects live chat events from YouTube streams and preserves raw API responses for downstream analytics, NLP, and sentiment analysis.

The goal is to build an end-to-end pipeline capable of analyzing public reactions and narrative shifts during live news broadcasts using continuously generated data instead of static datasets.

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
```

## Current Features

* YouTube Data API integration
* Dynamic `liveChatId` discovery from active broadcasts
* Live chat message ingestion
* Video and channel metadata extraction
* Raw API response preservation as timestamped JSON files
* Environment-based API key configuration
* Modular separation between ingestion and storage
* Generated raw data excluded from version control

## Project Structure

```text
youtube-live-sentiment/
│
├── src/
│   ├── config/
│   │   └── settings.py
│   ├── ingestion/
│   │   └── youtube.py
│   ├── storage/
│   │   └── raw_writer.py
│   ├── main.py
│   └── youtube_ingest.py
│
├── raw/
├── logs/
├── analysis/
├── docs/
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## Tech Stack

**Currently implemented**

* Python
* YouTube Data API v3
* Requests
* JSON
* Git / GitHub

## Roadmap

The project is being developed incrementally toward a streaming data architecture.

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
Processing / Data Quality
      │
      ├── Message normalization
      ├── Duplicate detection
      ├── Spam filtering
      ├── Entity recognition
      └── Sentiment analysis
      │
      ▼
PostgreSQL
      │
      ▼
Analytics Layer
      │
      ▼
Real-Time Dashboard
```

Planned technologies include:

* Apache Kafka
* PostgreSQL
* Docker
* NLP / sentiment analysis
* Data quality and spam detection
* Interactive analytics dashboard

## Why This Project?

Most introductory data projects operate on static datasets.

This project instead focuses on continuously generated, real-world data and the engineering challenges that come with it: API ingestion, raw data preservation, duplicate and spam handling, streaming architectures, storage, processing, and eventually real-time analytics.

The long-term objective is to analyze how public sentiment and discussion topics evolve during live news events while maintaining a reproducible data pipeline.
