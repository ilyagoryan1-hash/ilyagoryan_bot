import os
import asyncpg
import requests
import random
import hashlib
from urllib.parse import quote
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineQuery, InlineQueryResultArticle, InputTextMessageContent, CallbackQuery
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
KINOPOSK_API_KEY = os.getenv("KINOPOSK_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# --- Создание таблицы ---
async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS movies (
        id SERIAL PRIMARY KEY,
        title TEXT,
        year TEXT,
        rating TEXT,
        poster TEXT,
        comment TEXT
    );
    """)
    await conn.close()

# --- Главное меню ---
def main_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("🎬 Добавить"), KeyboardButton("📋 Список"))
    kb.row(KeyboardButton("🎲 Случайный фильм"), KeyboardButton("💡 Рекомендую"))
    return kb

# --- Команда /start ---
@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await init_db()
    await message.answer(
        "🎥 *Кинодневник* — твой личный каталог фильмов.\n\n"
        "Добавляй, отмечай просмотренные и ищи новые идеи.",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

# --- Добавление фильма ---
@dp.message_handler(lambda m: m.text in ["🎬 Добавить", "/add"])
async def add_movie_start(message: types.Message):
    await message.answer("Введи название фильма или сериала:")
    dp.register_message_handler(process_add_movie, state="adding_movie")

async def process_add_movie(message: types.Message):
    title = message.text.strip()
    query = quote(title)
    url = f"https://api.kinopoisk.dev/v1.4/movie/search?page=1&limit=1&query={query}"
    headers = {"X-API-KEY": KINOPOSK_API_KEY}
    response = requests.get(url, headers=headers).json()

    if "docs" not in response or not response["docs"]:
        await message.answer("Фильм не найден 😔", reply_markup=main_keyboard())
        return

    film = response["docs"][0]
    title = film.get("name", "Без названия")
    year = str(film.get("year", "—"))
    rating = str(film.get("rating", {}).get("imdb", "—"))
    poster = film.get("poster", {}).get("url", "")

    async with asyncpg.create_pool(DATABASE_URL) as pool:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO movies (title, year, rating, poster) VALUES ($1,$2,$3,$4);",
                title, year, rating, poster
            )

    text = f"🎬 *{title}* ({year})\n⭐ IMDb: {rating}"
    if poster:
        await message.answer_photo(photo=poster, caption=text, parse_mode="Markdown")
    else:
        await message.answer(text, parse_mode="Markdown")

    await message.answer("✅ Фильм добавлен!", reply_markup=main_keyboard())
    dp.unregister_message_handler(process_add_movie, state="adding_movie")

# --- Список фильмов ---
@dp.message_handler(lambda m: m.text in ["📋 Список", "/list"])
async def list_movies(message: types.Message):
    async with asyncpg.create_pool(DATABASE_URL) as pool:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM movies ORDER BY id;")

    if not rows:
        await message.answer("📭 Список фильмов пуст.", reply_markup=main_keyboard())
        return

    for row in rows:
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("✅ Просмотрено", callback_data=f"watched_{row['id']}"),
            InlineKeyboardButton("❌ Удалить", callback_data=f"delete_{row['id']}")
        )
        text = f"🎬 *{row['title']}* ({row['year']})\n⭐ IMDb: {row['rating'] or '—'}"
        if row["comment"] == "Просмотрено":
            text += "\n✅ Уже просмотрено!"
        await message.answer(text, reply_markup=kb, parse_mode="Markdown")

# --- Случайный фильм ---
@dp.message_handler(lambda m: m.text in ["🎲 Случайный фильм", "/random"])
async def random_movie(message: types.Message):
    async with asyncpg.create_pool(DATABASE_URL) as pool:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM movies;")

    if not rows:
        await message.answer("Список фильмов пуст 😔", reply_markup=main_keyboard())
        return

    row = random.choice(rows)
    text = f"🎲 *{row['title']}* ({row['year']})\n⭐ IMDb: {row['rating'] or '—'}"
    if row["poster"]:
        await message.answer_photo(photo=row["poster"], caption=text, parse_mode="Markdown")
    else:
        await message.answer(text, parse_mode="Markdown")

# --- Рекомендую ---
@dp.message_handler(lambda m: m.text in ["💡 Рекомендую", "/recommend"])
async def recommend(message: types.Message):
    async with asyncpg.create_pool(DATABASE_URL) as pool:
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT title, year, rating FROM movies
                WHERE rating ~ '^[0-9]' AND CAST(rating AS FLOAT) >= 7
                ORDER BY rating DESC;
            """)

    if not rows:
        await message.answer("Пока нечего рекомендовать 😅", reply_markup=main_keyboard())
        return

    text = "💡 *Моя подборка рекомендуемого:*\n\n"
    for row in rows:
        text += f"🎬 *{row['title']}* ({row['year']}) — ⭐ {row['rating']}\n"
    await message.answer(text, parse_mode="Markdown", reply_markup=main_keyboard())

# --- Inline-поиск ---
@dp.inline_handler()
async def inline_search(query: InlineQuery):
    if not query.query:
        await query.answer([], cache_time=1)
        return

    text = query.query.strip()
    url = f"https://api.kinopoisk.dev/v1.4/movie/search?page=1&limit=10&query={quote(text)}"
    headers = {"X-API-KEY": KINOPOSK_API_KEY}
    response = requests.get(url, headers=headers).json()
    results = []

    if "docs" in response:
        for film in response["docs"]:
            title = film.get("name", "Без названия")
            year = str(film.get("year", "—"))
            rating = str(film.get("rating", {}).get("imdb", "—"))
            poster = film.get("poster", {}).get("url", "")
            desc = film.get("description", "Нет описания.")
            uid = hashlib.md5((title + year).encode()).hexdigest()

            results.append(
                InlineQueryResultArticle(
                    id=uid,
                    title=f"{title} ({year}) ⭐ {rating}",
                    description=desc[:80] + ("..." if len(desc) > 80 else ""),
                    thumb_url=poster or None,
                    input_message_content=InputTextMessageContent(
                        message_text=f"🎬 *{title}* ({year})\n⭐ IMDb: {rating}\n\n{desc}",
                        parse_mode="Markdown"
                    )
                )
            )

    await query.answer(results, cache_time=1, is_personal=True)

# --- Сохранение из inline ---
@dp.message_handler(lambda m: m.text.startswith("🎬 "))
async def save_from_inline(message: types.Message):
    lines = message.text.split("\n")
    title_line = lines[0].replace("🎬 ", "")
    if "(" in title_line:
        title = title_line.split("(")[0].strip()
        year = title_line.split("(")[1].split(")")[0]
    else:
        title = title_line
        year = "—"
    rating = "—"
    for l in lines:
        if "IMDb:" in l:
            rating = l.split("IMDb:")[1].strip()
            break
    async with asyncpg.create_pool(DATABASE_URL) as pool:
        async with pool.acquire() as conn:
            exists = await conn.fetchval("SELECT id FROM movies WHERE title=$1;", title)
            if not exists:
                await conn.execute(
                    "INSERT INTO movies (title, year, rating) VALUES ($1,$2,$3);",
                    title, year, rating
                )
    await message.reply("✅ Добавлено в кинодневник!", reply_markup=main_keyboard())

# --- Кнопки удаления и отметки ---
@dp.callback_query_handler(lambda c: c.data.startswith("delete_"))
async def delete_movie(callback: CallbackQuery):
    movie_id = int(callback.data.split("_")[1])
    async with asyncpg.create_pool(DATABASE_URL) as pool:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM movies WHERE id=$1;", movie_id)
    await callback.answer("Удалено ❌")
    await callback.message.edit_text("❌ Фильм удалён.")

@dp.callback_query_handler(lambda c: c.data.startswith("watched_"))
async def mark_watched(callback: CallbackQuery):
    movie_id = int(callback.data.split("_")[1])
    async with asyncpg.create_pool(DATABASE_URL) as pool:
        async with pool.acquire() as conn:
            await conn.execute("UPDATE movies SET comment='Просмотрено' WHERE id=$1;", movie_id)
    await callback.answer("✅ Просмотрено")
    await callback.message.edit_text("✅ Фильм отмечен как просмотренный.")

# --- Запуск ---
if __name__ == "__main__":
    import asyncio
    asyncio.run(init_db())
    
    import asyncio
asyncio.set_event_loop(asyncio.new_event_loop())
    executor.start_polling(dp, skip_updates=True)
