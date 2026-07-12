-- ============================================================
-- Silver Layer (EDW) — DDL
-- Clean, standardized, normalized (3NF) data. Single source of
-- truth. Load method: full rebuild from Bronze on each run
-- (safe because Bronze retains complete incremental history).
-- ============================================================

CREATE SCHEMA IF NOT EXISTS silver;

-- Movie master data — deduplicated, one row per movie,
-- holding only attributes that don't change day to day
CREATE TABLE IF NOT EXISTS silver.movie (
    movie_id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    original_title TEXT,
    original_language TEXT,
    release_date DATE,
    overview TEXT
);

-- Genre lookup
CREATE TABLE IF NOT EXISTS silver.genre (
    genre_id INTEGER PRIMARY KEY,
    genre_name TEXT NOT NULL
);

-- Many-to-many resolution between movies and genres
CREATE TABLE IF NOT EXISTS silver.movie_genre (
    movie_id INTEGER NOT NULL REFERENCES silver.movie(movie_id),
    genre_id INTEGER NOT NULL REFERENCES silver.genre(genre_id),
    PRIMARY KEY (movie_id, genre_id)
);

-- Daily normalized stats — one row per movie per calendar day,
-- holding only attributes that change over time
CREATE TABLE IF NOT EXISTS silver.movie_daily_stat (
    movie_id INTEGER NOT NULL REFERENCES silver.movie(movie_id),
    snapshot_date DATE NOT NULL,
    popularity NUMERIC,
    vote_average NUMERIC,
    vote_count INTEGER,
    PRIMARY KEY (movie_id, snapshot_date)
);
