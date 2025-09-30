import os
import logging
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.types import Update

# --- Настройка логов ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

# --- Токен и Webhook ---
API_TOKEN = os.getenv("TELEGRAM_TOKEN")  # теперь TELEGRAM_TOKEN
if not API_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не найден в переменных окружения")

WEBHOOK_PATH = "/telegram/webhook"
WEBHOOK_URL = f"https://date-verification.onrender.com{WEBHOOK_PATH}"

# --- Инициализация бота ---
bot = Bot(token=API_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# --- FastAPI ---
app = FastAPI()


# --- События запуска ---
@app.on_event("startup")
async def on_startup():
    await bot.set_webhook(WEBHOOK_URL)
    logger.info(f"✅ Webhook установлен: {WEBHOOK_URL}")


# --- События выключения ---
@app.on_event("shutdown")
async def on_shutdown():
    session = await bot.get_session()
    await session.close()
    logger.info("❌ Бот остановлен")


# --- Webhook endpoint ---
@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        update = Update.model_validate(data)
        await dp.feed_update(bot, update)
    except Exception as e:
        logger.error(f"Ошибка при обработке апдейта: {e}")
    return {"ok": True}


# --- Хендлеры ---
@dp.message()
async def echo_handler(message: types.Message):
    await message.answer("Привет 👋 Я бот, и я уже работаю через webhook 🚀")
