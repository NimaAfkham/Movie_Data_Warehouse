-- ============================================================
-- Movie Data Warehouse — Gold Layer Analytical Queries
-- All queries run against gold.* views (star schema)
-- ============================================================


-- 1. Rolling 7-day average popularity per movie
-- Technique: window function with a frame (ROWS BETWEEN)
-- Use case: smooths out day-to-day noise to see real popularity trends
SELECT
    f.movie_id,
    m.title,
    f.snapshot_date,
    f.popularity,
    ROUND(
        AVG(f.popularity) OVER (
            PARTITION BY f.movie_id
            ORDER BY f.snapshot_date
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ), 2
    ) AS rolling_7day_avg_popularity
FROM gold.fact_movie_snapshot f
JOIN gold.dim_movie m ON f.movie_id = m.movie_id
ORDER BY f.movie_id, f.snapshot_date;


-- 2. Daily popularity rank + rank change day-over-day
-- Technique: RANK() window function + LAG() to compare against the previous day
-- Use case: which movies are climbing or falling in relative popularity
WITH ranked AS (
    SELECT
        f.movie_id,
        m.title,
        f.snapshot_date,
        f.popularity,
        RANK() OVER (PARTITION BY f.snapshot_date ORDER BY f.popularity DESC) AS daily_rank
    FROM gold.fact_movie_snapshot f
    JOIN gold.dim_movie m ON f.movie_id = m.movie_id
)
SELECT
    movie_id,
    title,
    snapshot_date,
    daily_rank,
    LAG(daily_rank) OVER (PARTITION BY movie_id ORDER BY snapshot_date) AS previous_day_rank,
    LAG(daily_rank) OVER (PARTITION BY movie_id ORDER BY snapshot_date) - daily_rank AS rank_change
FROM ranked
ORDER BY snapshot_date DESC, daily_rank ASC;


-- 3. Which genres trend most consistently over the tracking period
-- Technique: join through the movie_genre bridge, aggregate average popularity per genre per day
-- Use case: spot genres with sustained high popularity vs. genres that spike occasionally
SELECT
    g.genre_name,
    f.snapshot_date,
    ROUND(AVG(f.popularity), 2) AS avg_popularity,
    COUNT(DISTINCT f.movie_id) AS movie_count
FROM gold.fact_movie_snapshot f
JOIN silver.movie_genre mg ON f.movie_id = mg.movie_id
JOIN gold.dim_genre g ON mg.genre_id = g.genre_id
GROUP BY g.genre_name, f.snapshot_date
ORDER BY f.snapshot_date DESC, avg_popularity DESC;


-- 4. Correlation between vote count and vote average
-- Technique: built-in Postgres CORR() aggregate function
-- Use case: do more-watched movies actually rate higher, or is there no real relationship?
SELECT
    ROUND(CORR(vote_count, vote_average)::numeric, 4) AS vote_count_vs_avg_correlation
FROM gold.fact_movie_snapshot;


-- 5. Popularity volatility per movie (spikes vs. sustained popularity)
-- Technique: STDDEV() aggregate, only meaningful once a movie has multiple days of history
-- Use case: separates "briefly trending" movies from "consistently popular" ones
SELECT
    f.movie_id,
    m.title,
    COUNT(*) AS days_tracked,
    ROUND(AVG(f.popularity), 2) AS avg_popularity,
    ROUND(STDDEV(f.popularity), 2) AS popularity_stddev
FROM gold.fact_movie_snapshot f
JOIN gold.dim_movie m ON f.movie_id = m.movie_id
GROUP BY f.movie_id, m.title
HAVING COUNT(*) > 1
ORDER BY popularity_stddev DESC NULLS LAST;


-- ============================================================
-- Bonus queries
-- ============================================================


-- 6. Newly appeared movies per day
-- Technique: anti-join (NOT EXISTS) between today's snapshot and all prior days
-- Use case: track churn in the popular list — how many new movies enter each day
SELECT
    f.snapshot_date,
    COUNT(*) AS new_movies_today
FROM gold.fact_movie_snapshot f
WHERE NOT EXISTS (
    SELECT 1
    FROM gold.fact_movie_snapshot earlier
    WHERE earlier.movie_id = f.movie_id
      AND earlier.snapshot_date < f.snapshot_date
)
GROUP BY f.snapshot_date
ORDER BY f.snapshot_date;


-- 7. Highest-rated movies by decade
-- Technique: EXTRACT on release_date to bucket into decades, then aggregate
-- Use case: a completely different analytical angle — historical rating patterns, not just recent trends
SELECT
    (EXTRACT(YEAR FROM m.release_date)::int / 10) * 10 AS decade,
    COUNT(DISTINCT m.movie_id) AS movie_count,
    ROUND(AVG(f.vote_average), 2) AS avg_rating
FROM gold.dim_movie m
JOIN gold.fact_movie_snapshot f ON m.movie_id = f.movie_id
WHERE m.release_date IS NOT NULL
GROUP BY decade
ORDER BY decade DESC;


-- 8. "Hidden gems" — high rating, comparatively low vote count
-- Technique: NTILE() to bucket movies into quartiles by vote_count, then filter
-- Use case: a genuinely interesting business question, not just a technical exercise —
-- surfaces well-rated movies that haven't been widely voted on yet
WITH latest_snapshot AS (
    SELECT DISTINCT ON (movie_id)
        movie_id, vote_average, vote_count, snapshot_date
    FROM gold.fact_movie_snapshot
    ORDER BY movie_id, snapshot_date DESC
),
bucketed AS (
    SELECT
        *,
        NTILE(4) OVER (ORDER BY vote_count ASC) AS vote_count_quartile
    FROM latest_snapshot
)
SELECT
    m.title,
    b.vote_average,
    b.vote_count
FROM bucketed b
JOIN gold.dim_movie m ON b.movie_id = m.movie_id
WHERE b.vote_count_quartile = 1   -- lowest quartile of vote counts
  AND b.vote_average >= 7.0
ORDER BY b.vote_average DESC;
