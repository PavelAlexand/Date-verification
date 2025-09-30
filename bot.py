import os
import logging
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.types import Update

# === Логирование ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

# === Конфигурация ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://date-verification.onrender.com/telegram/webhook")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не найден в переменных окружения")

bot = Bot(token=TELEGRAM_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# === FastAPI ===
app = FastAPI()

# Health-check (чтобы Render не падал на / и /HEAD)
@app.get("/")
async def root():
    return {"status": "ok", "message": "🤖 Bot is running"}

@app.head("/")
async def root_head():
    return {"status": "ok"}


# === Webhook ===
@app.on_event("startup")
async def on_startup():
    await bot.set_webhook(WEBHOOK_URL)
    logger.info(f"✅ Webhook установлен: {WEBHOOK_URL}")

@app.on_event("shutdown")
async def on_shutdown():
    logger.info("♻️ Бот выключен")
    if not bot.session.closed:   # aiogram 3.x — session надо закрывать вручную
        await bot.session.close()


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        update = Update.model_validate(data)  # aiogram 3.x
        await dp.feed_update(bot, update)
        return {"ok": True}
    except Exception as e:
        logger.error(f"Ошибка в webhook: {e}")
        return {"ok": False}


# === Handlers ===
@dp.message()
async def handle_message(message: types.Message):
    if message.text:
        await message.answer(f"Ты написал: <b>{message.text}</b>")
    else:
        await message.answer("⚠️ Сообщение без текста")


@dp.message(content_types=["photo"])
async def handle_photo(message: types.Message):
    try:
        await message.answer("📷 Фото получено (OCR пока отключён)")
    except Exception as e:
        logger.error(f"Ошибка при обработке фото: {e}")
        await message.answer("⚠️ Ошибка обработки фото")
