import os
import psycopg2
from psycopg2.extras import execute_values

DATABASE_URL = os.environ["DATABASE_URL"]


def fetch_bronze_movies(conn):
    """Pull every raw movie snapshot ever loaded, oldest to newest."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT tmdb_id, raw_payload, pulled_at
            FROM bronze.movie_raw
            ORDER BY pulled_at ASC
        """)
        return cur.fetchall()


def fetch_latest_genre_payload(conn):
    """Genres barely change, so we just need the most recent pull."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT raw_payload
            FROM bronze.genre_raw
            ORDER BY pulled_at DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        return row[0] if row else {"genres": []}


def build_movie_master(bronze_rows):
    """
    One row per movie, keeping the LATEST payload seen for each tmdb_id.
    Since bronze_rows is ordered oldest -> newest, later iterations
    naturally overwrite earlier ones in the dict.
    """
    movie_master = {}
    for tmdb_id, payload, pulled_at in bronze_rows:
        movie_master[tmdb_id] = payload
    return movie_master


def build_daily_stats(bronze_rows):
    """
    One row per (movie, date) - if a movie was pulled more than once on
    the same day, keep the LATEST snapshot from that day only.
    """
    daily_stats = {}
    for tmdb_id, payload, pulled_at in bronze_rows:
        snapshot_date = pulled_at.date()
        key = (tmdb_id, snapshot_date)
        daily_stats[key] = payload  # later rows overwrite earlier same-day rows
    return daily_stats


def upsert_genres(conn, genre_payload):
    genres = genre_payload.get("genres", [])
    rows = [(g["id"], g["name"]) for g in genres]
    if not rows:
        return 0
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO silver.genre (genre_id, genre_name)
            VALUES %s
            ON CONFLICT (genre_id) DO UPDATE
                SET genre_name = EXCLUDED.genre_name
            """,
            rows,
        )
    conn.commit()
    return len(rows)


def upsert_movies(conn, movie_master):
    rows = []
    for tmdb_id, payload in movie_master.items():
        release_date = payload.get("release_date") or None
        if release_date == "":
            release_date = None
        rows.append((
            tmdb_id,
            payload.get("title"),
            payload.get("original_title"),
            payload.get("original_language"),
            release_date,
            payload.get("overview"),
        ))
    if not rows:
        return 0
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO silver.movie
                (movie_id, title, original_title, original_language, release_date, overview)
            VALUES %s
            ON CONFLICT (movie_id) DO UPDATE
                SET title = EXCLUDED.title,
                    original_title = EXCLUDED.original_title,
                    original_language = EXCLUDED.original_language,
                    release_date = EXCLUDED.release_date,
                    overview = EXCLUDED.overview
            """,
            rows,
        )
    conn.commit()
    return len(rows)


def upsert_movie_genres(conn, movie_master):
    pairs = set()
    for tmdb_id, payload in movie_master.items():
        for genre_id in payload.get("genre_ids", []):
            pairs.add((tmdb_id, genre_id))
    rows = list(pairs)
    if not rows:
        return 0
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO silver.movie_genre (movie_id, genre_id)
            VALUES %s
            ON CONFLICT (movie_id, genre_id) DO NOTHING
            """,
            rows,
        )
    conn.commit()
    return len(rows)


def upsert_daily_stats(conn, daily_stats):
    rows = []
    for (tmdb_id, snapshot_date), payload in daily_stats.items():
        rows.append((
            tmdb_id,
            snapshot_date,
            payload.get("popularity"),
            payload.get("vote_average"),
            payload.get("vote_count"),
        ))
    if not rows:
        return 0
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO silver.movie_daily_stat
                (movie_id, snapshot_date, popularity, vote_average, vote_count)
            VALUES %s
            ON CONFLICT (movie_id, snapshot_date) DO UPDATE
                SET popularity = EXCLUDED.popularity,
                    vote_average = EXCLUDED.vote_average,
                    vote_count = EXCLUDED.vote_count
            """,
            rows,
        )
    conn.commit()
    return len(rows)


def main():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        bronze_rows = fetch_bronze_movies(conn)
        print(f"Read {len(bronze_rows)} raw rows from bronze.movie_raw")

        genre_payload = fetch_latest_genre_payload(conn)

        movie_master = build_movie_master(bronze_rows)
        daily_stats = build_daily_stats(bronze_rows)

        genre_count = upsert_genres(conn, genre_payload)
        print(f"Upserted {genre_count} rows into silver.genre")

        movie_count = upsert_movies(conn, movie_master)
        print(f"Upserted {movie_count} rows into silver.movie")

        movie_genre_count = upsert_movie_genres(conn, movie_master)
        print(f"Upserted {movie_genre_count} rows into silver.movie_genre")

        stat_count = upsert_daily_stats(conn, daily_stats)
        print(f"Upserted {stat_count} rows into silver.movie_daily_stat")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
