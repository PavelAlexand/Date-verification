import os
import logging
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types, F
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# --- Настройки ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = f"https://date-verification.onrender.com/telegram/webhook"

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

# Инициализация
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# --- Хэндлер для фото ---
@dp.message(F.photo)
async def photo_handler(message: types.Message):
    await message.reply("✅ Фото получено! Но пока обрабатываем только текст 😉")

# --- Хэндлер для текста ---
@dp.message(F.text)
async def text_handler(message: types.Message):
    await message.reply(f"Ты написал: {message.text}")

# --- FastAPI ---
app = FastAPI()

@app.on_event("startup")
async def on_startup():
    await bot.set_webhook(WEBHOOK_URL)
    logger.info(f"✅ Webhook установлен: {WEBHOOK_URL}")

@app.on_event("shutdown")
async def on_shutdown():
    await bot.delete_webhook()
    await bot.session.close()
    logger.info("❌ Бот остановлен")

@app.get("/")
async def root():
    return {"status": "ok", "message": "Бот работает!"}

# Подключаем aiogram к FastAPI
SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/telegram/webhook")
setup_application(app, dp, bot=bot)
