import os
import requests
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHANNEL_ID = os.environ["TELEGRAM_CHANNEL_ID"]  # e.g. "@moviewarehouse_digest"

TELEGRAM_SEND_PHOTO_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
TELEGRAM_SEND_MESSAGE_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

CAPTION_MAX_LEN = 1024  # Telegram's hard limit for photo captions
OVERVIEW_SNIPPET_LEN = 160


def get_top_trending(conn, limit=5):
    """Top N movies by popularity on the most recent snapshot date,
    including poster path and overview for the #1 movie."""
    query = """
        WITH latest_date AS (
            SELECT MAX(snapshot_date) AS d FROM gold.fact_movie_snapshot
        )
        SELECT m.title, f.popularity, m.poster_path, m.overview
        FROM gold.fact_movie_snapshot f
        JOIN gold.dim_movie m ON f.movie_id = m.movie_id
        JOIN latest_date ld ON f.snapshot_date = ld.d
        ORDER BY f.popularity DESC
        LIMIT %s;
    """
    with conn.cursor() as cur:
        cur.execute(query, (limit,))
        return cur.fetchall()


def get_biggest_movers(conn, limit=3):
    """Movies with the largest rank improvement vs. the previous day."""
    query = """
        WITH ranked AS (
            SELECT
                f.movie_id,
                m.title,
                f.snapshot_date,
                RANK() OVER (PARTITION BY f.snapshot_date ORDER BY f.popularity DESC) AS daily_rank
            FROM gold.fact_movie_snapshot f
            JOIN gold.dim_movie m ON f.movie_id = m.movie_id
        ),
        with_change AS (
            SELECT
                movie_id,
                title,
                snapshot_date,
                daily_rank,
                LAG(daily_rank) OVER (PARTITION BY movie_id ORDER BY snapshot_date) - daily_rank AS rank_change
            FROM ranked
        )
        SELECT title, rank_change
        FROM with_change
        WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM gold.fact_movie_snapshot)
          AND rank_change IS NOT NULL
        ORDER BY rank_change DESC
        LIMIT %s;
    """
    with conn.cursor() as cur:
        cur.execute(query, (limit,))
        return cur.fetchall()


def get_top_genre(conn):
    """The single highest-average-popularity genre on the most recent date."""
    query = """
        WITH latest_date AS (
            SELECT MAX(snapshot_date) AS d FROM gold.fact_movie_snapshot
        )
        SELECT g.genre_name, ROUND(AVG(f.popularity), 1) AS avg_popularity
        FROM gold.fact_movie_snapshot f
        JOIN silver.movie_genre mg ON f.movie_id = mg.movie_id
        JOIN gold.dim_genre g ON mg.genre_id = g.genre_id
        JOIN latest_date ld ON f.snapshot_date = ld.d
        GROUP BY g.genre_name
        ORDER BY avg_popularity DESC
        LIMIT 1;
    """
    with conn.cursor() as cur:
        cur.execute(query)
        return cur.fetchone()


def truncate(text, max_len):
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + "…"


def build_caption(trending, movers, top_genre):
    top_title, top_popularity, _, top_overview = trending[0]

    lines = ["🎬 <b>Today's Movie Digest</b>\n"]
    lines.append(f"<b>#1 Trending:</b> {top_title}")
    if top_overview:
        lines.append(f"<i>{truncate(top_overview, OVERVIEW_SNIPPET_LEN)}</i>")

    lines.append("\n<b>🔥 Also Trending</b>")
    for i, (title, popularity, _, _) in enumerate(trending[1:], start=2):
        lines.append(f"{i}. {title} ({popularity:.1f})")

    if movers:
        lines.append("\n<b>📈 Biggest Movers</b>")
        for title, rank_change in movers:
            lines.append(f"• {title} (+{rank_change} spots)")

    if top_genre:
        genre_name, avg_pop = top_genre
        lines.append(f"\n<b>🏆 Top Genre Today:</b> {genre_name} (avg popularity {avg_pop})")

    caption = "\n".join(lines)
    return truncate(caption, CAPTION_MAX_LEN)


def send_photo_digest(caption, poster_path):
    photo_url = f"{TMDB_IMAGE_BASE}{poster_path}"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": "HTML",
    }
    response = requests.post(TELEGRAM_SEND_PHOTO_URL, json=payload, timeout=15)
    response.raise_for_status()
    return response.json()


def send_text_digest(caption):
    """Fallback if the #1 movie has no poster available."""
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "text": caption,
        "parse_mode": "HTML",
    }
    response = requests.post(TELEGRAM_SEND_MESSAGE_URL, json=payload, timeout=10)
    response.raise_for_status()
    return response.json()


def main():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        trending = get_top_trending(conn)
        movers = get_biggest_movers(conn)
        top_genre = get_top_genre(conn)
    finally:
        conn.close()

    caption = build_caption(trending, movers, top_genre)
    print(caption)  # also visible in the GitHub Actions log for debugging

    top_poster_path = trending[0][2]
    if top_poster_path:
        result = send_photo_digest(caption, top_poster_path)
    else:
        print("No poster available for #1 movie, falling back to text message")
        result = send_text_digest(caption)

    print(f"Sent to Telegram. Message ID: {result['result']['message_id']}")


if __name__ == "__main__":
    main()