-- ============================================================
-- Gold Layer (Data Marts) — Views
-- Business-ready, dimensionally modeled (star schema) data.
-- No physical load step — views compute on query, always
-- reflecting the current state of Silver.
-- ============================================================

CREATE SCHEMA IF NOT EXISTS gold;

-- ---- Dimensions ----

CREATE OR REPLACE VIEW gold.dim_movie AS
SELECT
    movie_id,
    title,
    original_title,
    original_language,
    release_date,
    overview
FROM silver.movie;

CREATE OR REPLACE VIEW gold.dim_genre AS
SELECT
    genre_id,
    genre_name
FROM silver.genre;

CREATE OR REPLACE VIEW gold.dim_date AS
SELECT DISTINCT
    snapshot_date AS date,
    EXTRACT(ISODOW FROM snapshot_date) AS day_of_week,      -- 1=Mon ... 7=Sun
    EXTRACT(MONTH FROM snapshot_date) AS month,
    EXTRACT(YEAR FROM snapshot_date) AS year,
    (EXTRACT(ISODOW FROM snapshot_date) IN (6, 7)) AS is_weekend
FROM silver.movie_daily_stat;

-- ---- Fact ----

CREATE OR REPLACE VIEW gold.fact_movie_snapshot AS
SELECT
    movie_id,
    snapshot_date,
    popularity,
    vote_average,
    vote_count
FROM silver.movie_daily_stat;

-- ---- Flattened reporting view ----
-- Movie + aggregated genre names in one row, for quick lookups
-- without repeated joins

CREATE OR REPLACE VIEW gold.movie_with_genres AS
SELECT
    m.movie_id,
    m.title,
    m.release_date,
    array_agg(g.genre_name ORDER BY g.genre_name) AS genres
FROM silver.movie m
LEFT JOIN silver.movie_genre mg ON m.movie_id = mg.movie_id
LEFT JOIN silver.genre g ON mg.genre_id = g.genre_id
GROUP BY m.movie_id, m.title, m.release_date;
