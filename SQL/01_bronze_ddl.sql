-- ============================================================
-- Bronze Layer (Staging) — DDL
-- Raw, unprocessed data as-is from the source. No transformation,
-- no deduplication. Load method: incremental (append-only).
-- ============================================================

CREATE SCHEMA IF NOT EXISTS bronze;

-- Raw movie snapshots pulled from TMDb's /movie/popular endpoint
CREATE TABLE IF NOT EXISTS bronze.movie_raw (
    id BIGSERIAL PRIMARY KEY,
    tmdb_id INTEGER NOT NULL,
    source_endpoint TEXT NOT NULL,
    page_number INTEGER,
    raw_payload JSONB NOT NULL,
    pulled_at TIMESTAMP NOT NULL DEFAULT now()
);

-- Raw genre reference list pulled from TMDb's /genre/movie/list endpoint
CREATE TABLE IF NOT EXISTS bronze.genre_raw (
    id BIGSERIAL PRIMARY KEY,
    raw_payload JSONB NOT NULL,
    pulled_at TIMESTAMP NOT NULL DEFAULT now()
);
