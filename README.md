# Movie Data Warehouse

A daily-refreshing, three-layer (Bronze/Silver/Gold) data warehouse built on the Inmon methodology, tracking trending movie data from TMDb — with a daily digest delivered straight to a public Telegram channel. Fully automated via GitHub Actions and running on a cloud-hosted PostgreSQL instance (Neon).

📲 https://t.me/WorldOfFrames — a daily 60-second look at what's trending in movies.

## Project Summary

This project ingests daily trending movie data from The Movie Database (TMDb) API, incrementally loads it into a raw staging layer, transforms it into a normalized enterprise data warehouse, and exposes it through a dimensionally-modeled reporting layer — then delivers a formatted daily digest (poster, trending list, biggest movers, genre spotlight) directly to a Telegram channel. The entire pipeline, from ingestion to end-user delivery, runs unattended on a daily schedule with zero local infrastructure.

## Architecture

```mermaid
flowchart LR
    A[TMDb API] -->|API calls| B[Extraction<br/>Python]
    B -->|Incremental Load| C[(Bronze<br/>Staging Layer)]
    C -->|Transform| D[(Silver<br/>EDW Layer)]
    D -->|Views| E[(Gold<br/>Data Marts Layer)]
    E --> F[Analytical SQL]
    E --> G[Telegram Digest<br/>Python]
    G -->|Daily Post| H[📲 Telegram Channel]

    style C fill:#e91e8c,color:#fff
    style D fill:#4a8c2a,color:#fff
    style E fill:#3d6ea5,color:#fff
    style H fill:#229ed9,color:#fff
```

This follows the **Inmon approach**: a normalized enterprise data warehouse (Silver) sits at the center as the single source of truth, with dimensional data marts (Gold) built on top of it for reporting — as opposed to Kimball's bus architecture, which builds conformed dimensional marts directly without a normalized center.

| Layer                 | Definition                              | Objective                 | Load Method               | Data Modeling    | Audience                 |
| --------------------- | --------------------------------------- | ------------------------- | ------------------------- | ---------------- | ------------------------ |
| **Bronze** (Staging)  | Raw, unprocessed data as-is from source | Traceability & debugging  | Incremental (append-only) | None             | Data Engineers           |
| **Silver** (EDW)      | Clean, standardized, normalized data    | Prepare data for analysis | Full rebuild from Bronze  | Normalized (3NF) | Data Engineers, Analysts |
| **Gold** (Data Marts) | Business-ready data                     | Reporting & analytics     | Views (no physical load)  | Star schema      | Data Analysts            |

## Entity-Relationship Diagrams

### Bronze Layer (Staging)

```mermaid
erDiagram
    MOVIE_RAW {
        bigserial id PK
        integer tmdb_id
        text source_endpoint
        integer page_number
        jsonb raw_payload
        timestamp pulled_at
    }
    GENRE_RAW {
        bigserial id PK
        jsonb raw_payload
        timestamp pulled_at
    }
```

Bronze is deliberately unstructured — the whole point is a faithful, traceable copy of what the API actually returned, not a cleaned shape.

### Silver Layer (Normalized EDW, 3NF)

```mermaid
erDiagram
    MOVIE {
        integer movie_id PK
        text title
        text original_title
        text original_language
        date release_date
        text overview
        text poster_path
    }
    GENRE {
        integer genre_id PK
        text genre_name
    }
    MOVIE_GENRE {
        integer movie_id FK
        integer genre_id FK
    }
    MOVIE_DAILY_STAT {
        integer movie_id FK
        date snapshot_date
        numeric popularity
        numeric vote_average
        integer vote_count
    }

    MOVIE ||--o{ MOVIE_GENRE : has
    GENRE ||--o{ MOVIE_GENRE : has
    MOVIE ||--o{ MOVIE_DAILY_STAT : tracked_daily
```

Movie attributes (what a movie _is_) are separated from daily stats (how it's _performing_) — this separation is what makes Silver genuinely 3NF rather than just "a cleaned table." The `MOVIE_GENRE` bridge table resolves the many-to-many relationship between movies and genres properly, instead of cramming a genre list into the movie row.

### Gold Layer (Star Schema, exposed as views)

```mermaid
erDiagram
    FACT_MOVIE_SNAPSHOT {
        integer movie_id FK
        date snapshot_date
        numeric popularity
        numeric vote_average
        integer vote_count
    }
    DIM_MOVIE {
        integer movie_id PK
        text title
        text original_title
        text original_language
        date release_date
        text overview
        text poster_path
    }
    DIM_GENRE {
        integer genre_id PK
        text genre_name
    }
    DIM_DATE {
        date date PK
        integer day_of_week
        integer month
        integer year
        boolean is_weekend
    }

    DIM_MOVIE ||--o{ FACT_MOVIE_SNAPSHOT : has
    DIM_DATE ||--o{ FACT_MOVIE_SNAPSHOT : occurs_on
```

Gold also includes `gold.movie_with_genres`, a flattened reporting view joining movies to an aggregated array of their genre names, for quick lookups without repeated joins.

## Tech Stack

- **Language:** Python (extraction + transformation + digest delivery)
- **Database:** PostgreSQL, hosted on [Neon](https://neon.tech) (serverless, no local infrastructure required)
- **Orchestration:** GitHub Actions (daily scheduled runs + manual trigger support)
- **Distribution:** Telegram Bot API — posts a daily digest (poster image + trending list + biggest movers + genre spotlight) to a public channel
- **Data Source:** [TMDb API](https://developer.themoviedb.org/docs) — `movie/popular` and `genre/movie/list` endpoints

## Repository Structure

```
Movie_Data_Warehouse/
├── extraction/
│   └── extract_load.py             # Bronze: pulls from TMDb, loads raw JSON
├── transformation/
│   └── transform_load.py           # Silver: normalizes Bronze into 3NF tables
├── telegram_bot/
│   └── daily_digest.py             # Distribution: posts daily digest to Telegram
├── sql/
│   ├── 01_bronze_ddl.sql
│   ├── 02_silver_ddl.sql
│   ├── 03_gold_views.sql
│   ├── 04_analytical_queries.sql
│   └── 05_migration_add_poster_path.sql
├── requirements.txt
├── LICENSE
└── .github/
    └── workflows/
        └── daily_extract.yaml      # Runs extraction + transformation + digest daily
```

## Setup & Running Locally

1. Clone the repo and install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Set required environment variables:
   ```bash
   export TMDB_API_KEY="your_tmdb_api_key"
   export DATABASE_URL="your_neon_postgres_connection_string"
   export TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
   export TELEGRAM_CHANNEL_ID="@your_channel_username"
   ```
3. Create the schema (run once in your Postgres SQL editor, in order):
   ```
   sql/01_bronze_ddl.sql
   sql/02_silver_ddl.sql
   sql/03_gold_views.sql
   ```
4. Run the pipeline manually:
   ```bash
   python extraction/extract_load.py
   python transformation/transform_load.py
   python telegram_bot/daily_digest.py
   ```

In production, all three scripts run automatically once a day via GitHub Actions (`.github/workflows/daily_extract.yaml`), using repository secrets for credentials — no manual steps required.

## Design Decisions

**Why Inmon over Kimball?** Choosing a normalized EDW (Silver) as the trusted center, with dimensional marts (Gold) built on top, gives a clear separation between "single source of truth" and "shaped for reporting." It also mirrors how many real enterprise warehouses are structured, which made it a more useful learning target than jumping straight to a single star schema.

**Why is Bronze incremental but Silver a full rebuild?** Bronze retains complete history via append-only inserts — nothing is ever overwritten, so it's safe to treat as the permanent record. Silver, by contrast, is a _derived_ clean state — since Bronze safely holds all history, Silver can be fully recomputed from it on every run without risk of losing data. This keeps the transform logic simple (`INSERT ... ON CONFLICT DO UPDATE`) while still being safely idempotent — re-running it never produces duplicates or inconsistent state.

**Why views for Gold instead of physical tables?** Since Gold's star schema is just a reshaped view of Silver, there's no need for a separate load step — Postgres computes it on query, so Gold is always current the moment Silver updates, with no additional pipeline stage required.

**Why deduplicate by calendar day in Silver?** The extraction script can be triggered manually in addition to its daily schedule (useful for testing), which could create multiple snapshots per movie on the same day. `movie_daily_stat` keeps only the latest snapshot per movie per day, so analytical queries always reflect one clean data point per day regardless of how many times the pipeline happened to run.

**Why a Telegram channel instead of a bot with individual subscribers?** The goal was one-way daily content delivery, not interactive on-demand queries — a channel fits that exactly, with Telegram handling all subscriber management. The bot only needs posting rights to the channel, not per-user tracking, which keeps the distribution layer as simple as the content it's delivering.

## Example Analytical Output

**Genre trend consistency** (from `gold_analytics.sql`, query 3) — average popularity and movie count per genre, tracked daily:

| Genre     | Date       | Avg Popularity | Movie Count |
| --------- | ---------- | -------------- | ----------- |
| Horror    | 2026-07-12 | 57.73          | 71          |
| Thriller  | 2026-07-12 | 49.04          | 112         |
| Animation | 2026-07-12 | 43.33          | 69          |
| Comedy    | 2026-07-12 | 41.59          | 120         |
| Western   | 2026-07-12 | 17.71          | 5           |

**Popularity volatility** (query 5) — movies with the widest swings in daily popularity so far:

| Movie          | Days Tracked | Avg Popularity | Std Dev |
| -------------- | ------------ | -------------- | ------- |
| Evil Dead Burn | 2            | 99.34          | 31.83   |
| Moana          | 2            | 188.33         | 30.72   |
| We Want Now    | 2            | 86.36          | 25.83   |

With only a few days of history so far, most movies still show low variance — this metric becomes more meaningful as daily history accumulates.

## Phase 2 — Telegram Distribution (Complete)

Every day, after Silver refreshes, `telegram_bot/daily_digest.py` queries the Gold layer and posts a formatted digest to a public Telegram channel: the #1 trending movie's poster and overview, a shortlist of other trending titles, the biggest rank movers of the day, and a genre spotlight. This turns the warehouse from a backend pipeline into an actual end-user-facing product, fully automated on the same daily schedule as the rest of the pipeline.

## What's Next (Phase 3)

An AI agent layer on top of the Gold data — using an LLM to write editorial commentary on daily trends, reason about which movie deserves to be featured (beyond just "highest popularity"), and potentially operate with direct tool access to the analytical queries rather than a fixed template. Scoped as a distinct future phase.
