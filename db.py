import asyncpg

CREATE_TABLES_QUERY = """
CREATE TABLE IF NOT EXISTS movies (
    id SERIAL PRIMARY KEY,
    title TEXT,
    year TEXT,
    imdb_rating TEXT,
    poster TEXT,
    watched BOOLEAN DEFAULT FALSE
);
"""

async def init_db(pool):
    async with pool.acquire() as conn:
        await conn.execute(CREATE_TABLES_QUERY)

async def add_movie(pool, title, year, imdb_rating, poster):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO movies (title, year, imdb_rating, poster) VALUES ($1, $2, $3, $4)",
            title, year, imdb_rating, poster
        )

async def get_movies(pool, watched=None):
    async with pool.acquire() as conn:
        if watched is None:
            return await conn.fetch("SELECT * FROM movies ORDER BY id DESC")
        return await conn.fetch("SELECT * FROM movies WHERE watched=$1 ORDER BY id DESC", watched)

async def mark_watched(pool, movie_id):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE movies SET watched=TRUE WHERE id=$1", movie_id)
