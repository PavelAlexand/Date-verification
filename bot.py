import os
import logging
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

# Токен из переменных окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не найден в переменных окружения")

# Настройка бота
bot = Bot(token=TELEGRAM_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# Создаём FastAPI
app = FastAPI()

WEBHOOK_PATH = "/telegram/webhook"
WEBHOOK_URL = f"https://date-verification.onrender.com{WEBHOOK_PATH}"


# ========= ОБРАБОТЧИКИ =========

@dp.message()
async def handle_message(message: types.Message):
    if message.text:
        await message.answer(f"Ты написал: <b>{message.text}</b>")
    else:
        await message.answer("⚠️ Сообщение без текста")


@dp.message(F.photo)  # ✅ aiogram 3.x
async def handle_photo(message: types.Message):
    try:
        await message.answer("📷 Фото получено (OCR пока отключён)")
    except Exception as e:
        logger.error(f"Ошибка при обработке фото: {e}")
        await message.answer("⚠️ Ошибка обработки фото")


# ========= FASTAPI =========

@app.on_event("startup")
async def on_startup():
    await bot.set_webhook(WEBHOOK_URL)
    logger.info(f"✅ Webhook установлен: {WEBHOOK_URL}")


@app.on_event("shutdown")
async def on_shutdown():
    await bot.delete_webhook()
    await bot.session.close()
    logger.info("❌ Бот остановлен")


@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    update = types.Update(**await request.json())
    await dp.feed_update(bot, update)
    return {"ok": True}


@app.get("/")
async def root():
    return {"status": "ok", "message": "Бот работает 🚀"}
