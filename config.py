import os

# 🔑 Токен бота (вставь сюда свой или передай через переменные окружения)
BOT_TOKEN = os.getenv("BOT_TOKEN", "8438210114:AAGxLlAJQPhCVLCayy3ctnSucjQFyySShiY")

# 🔑 Ключ OMDb API (для рейтингов и постеров)
OMDB_API_KEY = os.getenv("OMDB_API_KEY", "79eef5a0")

# 🔗 PostgreSQL подключение (Render → DATABASE_URL)
DATABASE_URL = os.getenv("DATABASE_URL")
