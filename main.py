import logging, random, requests, asyncio, asyncpg
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from config import BOT_TOKEN, OMDB_API_KEY, DATABASE_URL
import db

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

async def get_pool():
    return await asyncpg.create_pool(DATABASE_URL)

@dp.message_handler(commands=['start', 'help'])
async def start_cmd(message: types.Message):
    text = (
        "🎬 Привет! Я — *Кинодневник*.\n\n"
        "В общем чате можно:\n"
        "➕ /add — добавить фильм\n"
        "📋 /list — список фильмов\n"
        "✅ /watched — отметить просмотр\n"
        "🎲 /random — случайная рекомендация"
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message_handler(commands=['add'])
async def add_movie_cmd(message: types.Message):
    await message.answer("Введи название фильма или сериала:")
    dp.register_message_handler(process_add_movie, state=None)

async def process_add_movie(message: types.Message):
    title = message.text.strip()
    url = f"http://www.omdbapi.com/?t={title}&apikey={OMDB_API_KEY}&plot=short"
    res = requests.get(url).json()
    pool = await get_pool()
    await db.init_db(pool)

    if res.get("Response") == "True":
        name = res.get("Title")
        year = res.get("Year")
        rating = res.get("imdbRating")
        poster = res.get("Poster") if res.get("Poster") != "N/A" else None
        await db.add_movie(pool, name, year, rating, poster)
        caption = f"🎞 *{name}* ({year})\n⭐ IMDb: {rating}"
        if poster:
            await message.answer_photo(photo=poster, caption=caption, parse_mode="Markdown")
        else:
            await message.answer(caption, parse_mode="Markdown")
    else:
        await message.answer("Фильм не найден 😔")

    await pool.close()

@dp.message_handler(commands=['list'])
async def list_movies(message: types.Message):
    pool = await get_pool()
    await db.init_db(pool)
    movies = await db.get_movies(pool)
    await pool.close()

    if not movies:
        await message.answer("Список фильмов пуст 🎬")
        return

    text = ""
    for m in movies:
        check = "✅" if m["watched"] else "❌"
        text += f"{check} {m['title']} ({m['year']}) — IMDb {m['imdb_rating']}\n"
    await message.answer(text)

@dp.message_handler(commands=['watched'])
async def watched_cmd(message: types.Message):
    pool = await get_pool()
    await db.init_db(pool)
    movies = await db.get_movies(pool, watched=False)
    if not movies:
        await message.answer("Нет непросмотренных фильмов 🎉")
        await pool.close()
        return
    kb = types.InlineKeyboardMarkup()
    for m in movies:
        kb.add(types.InlineKeyboardButton(m['title'], callback_data=f"watched_{m['id']}"))
    await message.answer("Выбери фильм, который ты посмотрел:", reply_markup=kb)
    await pool.close()

@dp.callback_query_handler(lambda c: c.data.startswith("watched_"))
async def watched_callback(callback_query: types.CallbackQuery):
    movie_id = int(callback_query.data.split("_")[1])
    pool = await get_pool()
    await db.mark_watched(pool, movie_id)
    await pool.close()
    await callback_query.answer("Отмечено ✅")
    await callback_query.message.edit_text("Фильм отмечен как просмотренный.")

@dp.message_handler(commands=['random'])
async def random_cmd(message: types.Message):
    pool = await get_pool()
    movies = await db.get_movies(pool, watched=False)
    await pool.close()
    if not movies:
        await message.answer("Все фильмы уже просмотрены 😎")
        return
    movie = random.choice(movies)
    caption = f"🎬 *{movie['title']}* ({movie['year']})\n⭐ IMDb: {movie['imdb_rating']}"
    if movie['poster']:
        await message.answer_photo(movie['poster'], caption=caption, parse_mode="Markdown")
    else:
        await message.answer(caption, parse_mode="Markdown")

async def on_startup(_):
    pool = await get_pool()
    await db.init_db(pool)
    await pool.close()
    logging.info("База данных инициализирована.")

if __name__ == "__main__":
    executor.start_polling(dp, on_startup=on_startup, skip_updates=True)

import threading
from aiohttp import web

async def healthcheck(request):
    return web.Response(text="Bot is running!")

def start_web_server():
    app = web.Application()
    app.router.add_get("/", healthcheck)
    web.run_app(app, host="0.0.0.0", port=8080)

# Запуск маленького web-сервера в фоне
threading.Thread(target=start_web_server, daemon=True).start()


