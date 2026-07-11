import os
import time
import requests
import psycopg2
from psycopg2.extras import execute_values, Json

DATABASE_URL = os.environ["DATABASE_URL"]
TMDB_API_KEY = os.environ["TMDB_API_KEY"]
BASE_URL = "https://api.themoviedb.org/3"

NUM_PAGES = 25  # 25 pages x 20 movies/page = ~500 movies per run


def fetch_page(endpoint, page):
    url = f"{BASE_URL}/{endpoint}"
    params = {"api_key": TMDB_API_KEY, "page": page}
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    return response.json()


def fetch_all_pages(endpoint, num_pages):
    all_movies = []
    for page in range(1, num_pages + 1):
        data = fetch_page(endpoint, page)
        results = data.get("results", [])
        for movie in results:
            all_movies.append((movie, page))
        print(f"Fetched page {page}/{num_pages} - {len(results)} movies")
        time.sleep(0.3)  # be polite to the API, avoid rate limiting
    return all_movies


def load_to_bronze(conn, endpoint, movies_with_pages):
    with conn.cursor() as cur:
        rows = [
            (movie["id"], endpoint, page, Json(movie))
            for movie, page in movies_with_pages
        ]
        execute_values(
            cur,
            """
            INSERT INTO bronze.movie_raw (tmdb_id, source_endpoint, page_number, raw_payload)
            VALUES %s
            """,
            rows,
        )
    conn.commit()


def main():
    endpoint = "movie/popular"
    movies_with_pages = fetch_all_pages(endpoint, NUM_PAGES)
    print(f"Total movies fetched: {len(movies_with_pages)}")

    conn = psycopg2.connect(DATABASE_URL)
    try:
        load_to_bronze(conn, endpoint, movies_with_pages)
        print(f"Loaded {len(movies_with_pages)} rows into bronze.movie_raw")
    finally:
        conn.close()


if __name__ == "__main__":
    main()