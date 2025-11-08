import os
import logging
import random
import asyncio
import asyncpg
import requests

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

# === Настройка логирования ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Переменные окружения ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
KINOPOSK_API_KEY = os.getenv("KINOPOSK_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost/movies")

# === Инициализация бота и базы ===
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)


# === Инициализация базы данных ===
async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS movies (
        id SERIAL PRIMARY KEY,
        title TEXT,
        year TEXT,
        rating REAL,
        poster TEXT,
        comment TEXT
    );
    """)
    await conn.close()
    logger.info("База данных инициализирована.")


# === Добавление фильма ===
@dp.message_handler(commands=["add"])
async def add_movie(message: types.Message):
    await message.answer("Введи название фильма или сериала:")
    await MovieStates.waiting_for_title.set()


from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
storage = MemoryStorage()
dp.storage = storage


class MovieStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_comment = State()


@dp.message_handler(state=MovieStates.waiting_for_title)
async def process_title(message: types.Message, state):
    title = message.text.strip()

    headers = {"X-API-KEY": KINOPOSK_API_KEY}
    url = f"https://api.kinopoisk.dev/v1.4/movie/search?page=1&limit=1&query={title}"

    response = requests.get(url, headers=headers).json()

    if not response.get("docs"):
        await message.answer("Фильм не найден 😔")
        await state.finish()
        return

    movie = response["docs"][0]
    name = movie.get("name")
    year = movie.get("year")
    rating = movie.get("rating", {}).get("kp")
    poster = movie.get("poster", {}).get("url")

    text = f"🎬 {name} ({year})\n⭐️ Рейтинг: {rating or '—'}"

    if poster:
        await message.answer_photo(poster, caption=text)
    else:
        await message.answer(text)

    # Сохраняем во временное состояние
    await state.update_data(movie={
        "title": name,
        "year": year,
        "rating": rating,
        "poster": poster
    })
    await message.answer("Хочешь добавить комментарий? Напиши его или '-' чтобы пропустить.")
    await MovieStates.waiting_for_comment.set()


@dp.message_handler(state=MovieStates.waiting_for_comment)
async def process_comment(message: types.Message, state):
    user_data = await state.get_data()
    movie = user_data["movie"]
    comment = message.text if message.text != "-" else None

    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
        INSERT INTO movies (title, year, rating, poster, comment)
        VALUES ($1, $2, $3, $4, $5)
    """, movie["title"], movie["year"], movie["rating"], movie["poster"], comment)
    await conn.close()

    await message.answer("Фильм добавлен в список! ✅")
    await state.finish()


# === Список фильмов ===
@dp.message_handler(commands=["list"])
async def list_movies(message: types.Message):
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("SELECT title, year, rating FROM movies")
    await conn.close()

    if not rows:
        await message.answer("Список фильмов пуст 🎬")
        return

    text = "\n".join([f"• {r['title']} ({r['year']}) — ⭐️ {r['rating'] or '—'}" for r in rows])
    await message.answer(text)


# === Случайная рекомендация ===
@dp.message_handler(commands=["random"])
async def random_movie(message: types.Message):
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("SELECT title, year, rating, poster FROM movies")
    await conn.close()

    if not rows:
        await message.answer("Список фильмов пуст 🎬")
        return

    movie = random.choice(rows)
    caption = f"🎲 {movie['title']} ({movie['year']})\n⭐️ {movie['rating'] or '—'}"

    if movie["poster"]:
        await message.answer_photo(movie["poster"], caption=caption)
    else:
        await message.answer(caption)


# === Команда старт ===
@dp.message_handler(commands=["start", "help"])
async def start_command(message: types.Message):
    text = (
        "🎬 Добро пожаловать в КИНОДНЕВНИК!\n\n"
        "Команды:\n"
        "/add — добавить фильм или сериал\n"
        "/list — показать список\n"
        "/random — случайная рекомендация\n"
    )
    await message.answer(text)


# === Health-check для Render ===
from aiohttp import web
import threading

async def healthcheck(request):
    return web.Response(text="Bot is running!")

def start_web_server():
    app = web.Application()
    app.router.add_get("/", healthcheck)
    web.run_app(app, host="0.0.0.0", port=8080)

threading.Thread(target=start_web_server, daemon=True).start()


# === Основной запуск ===
async def main():
    await init_db()
    await dp.start_polling()


if __name__ == "__main__":
    asyncio.run(main())
