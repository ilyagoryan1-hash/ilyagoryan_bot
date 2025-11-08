import asyncio
import logging
import requests
import asyncpg
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor

# -------------------
# 🔧 НАСТРОЙКИ
# -------------------
API_TOKEN = "ТВОЙ_ТОКЕН_БОТА"
OMDB_API_KEY = "79eef5a0"
DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/movies"  # Замени на свой

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# -------------------
# 📦 БАЗА ДАННЫХ
# -------------------
async def create_db():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            title TEXT,
            year TEXT,
            poster TEXT
        );
    """)
    await conn.close()

# -------------------
# 🎛 КНОПКИ
# -------------------
def get_main_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(
        KeyboardButton("🎥 Добавить фильм"),
        KeyboardButton("📋 Мой список"),
    ).add(
        KeyboardButton("❌ Удалить фильм")
    )
    return kb

# -------------------
# 🔎 ПОИСК ФИЛЬМА
# -------------------
def search_movie(title):
    try:
        url = f"https://www.omdbapi.com/?t={title}&apikey={OMDB_API_KEY}&r=json"
        response = requests.get(url)
        data = response.json()
        if data.get("Response") == "True":
            return {
                "title": data["Title"],
                "year": data["Year"],
                "poster": data.get("Poster", "")
            }
    except Exception as e:
        logging.error(e)
    return None

# -------------------
# 🚀 ХЕНДЛЕРЫ
# -------------------
@dp.message_handler(commands=['start'])
async def start_cmd(message: types.Message):
    await message.answer("Привет! Это твой 🎬 *Кинодневник*.\n"
                         "Добавляй фильмы, смотри список и управляй ими!",
                         parse_mode="Markdown", reply_markup=get_main_keyboard())

@dp.message_handler(lambda msg: msg.text == "🎥 Добавить фильм")
async def add_movie_prompt(message: types.Message):
    await message.answer("Введи название фильма или сериала:")
    dp.register_message_handler(add_movie_process, content_types=['text'], state=None)

async def add_movie_process(message: types.Message):
    movie = search_movie(message.text)
    if movie:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute(
            "INSERT INTO movies (user_id, title, year, poster) VALUES ($1, $2, $3, $4)",
            message.from_user.id, movie['title'], movie['year'], movie['poster']
        )
        await conn.close()
        await message.answer(
            f"✅ Добавлено: *{movie['title']}* ({movie['year']})",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
    else:
        await message.answer("Фильм не найден 😔 Попробуй другое название.", reply_markup=get_main_keyboard())

@dp.message_handler(lambda msg: msg.text == "📋 Мой список")
async def show_list(message: types.Message):
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("SELECT title, year, poster FROM movies WHERE user_id = $1", message.from_user.id)
    await conn.close()
    if not rows:
        await message.answer("Список фильмов пуст 🎬", reply_markup=get_main_keyboard())
        return

    text = "🎞 *Твой список фильмов:*\n\n"
    for row in rows:
        text += f"• {row['title']} ({row['year']})\n"
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_keyboard())

@dp.message_handler(lambda msg: msg.text == "❌ Удалить фильм")
async def delete_movie_prompt(message: types.Message):
    await message.answer("Введи точное название фильма, который хочешь удалить:")
    dp.register_message_handler(delete_movie_process, content_types=['text'], state=None)

async def delete_movie_process(message: types.Message):
    conn = await asyncpg.connect(DATABASE_URL)
    result = await conn.execute(
        "DELETE FROM movies WHERE user_id=$1 AND title ILIKE $2",
        message.from_user.id, message.text
    )
    await conn.close()
    if "DELETE 0" in result:
        await message.answer("⚠️ Фильм не найден в списке.", reply_markup=get_main_keyboard())
    else:
        await message.answer("🗑 Фильм успешно удалён!", reply_markup=get_main_keyboard())

# -------------------
# ⚙️ ЗАПУСК
# -------------------
if __name__ == "__main__":
    import asyncio
    asyncio.set_event_loop(asyncio.new_event_loop())

    async def on_startup():
        await create_db()
        print("База данных инициализирована ✅")

    loop = asyncio.get_event_loop()
    loop.run_until_complete(on_startup())

    executor.start_polling(dp, skip_updates=True)
