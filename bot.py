import os
import logging
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.enums.parse_mode import ParseMode
from aiogram.types import Update
import httpx

# 🔹 Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

# 🔹 Переменные окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YANDEX_OCR_API_KEY = os.getenv("YANDEX_OCR_API_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не найден в переменных окружения")
if not YANDEX_OCR_API_KEY:
    raise ValueError("❌ YANDEX_OCR_API_KEY не найден в переменных окружения")

WEBHOOK_PATH = "/telegram/webhook"
WEBHOOK_URL = f"https://date-verification.onrender.com{WEBHOOK_PATH}"

# 🔹 Инициализация бота
bot = Bot(token=TELEGRAM_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# 🔹 FastAPI
app = FastAPI()


# Health-check
@app.get("/")
async def root():
    return {"status": "ok", "message": "🤖 Bot is running"}


# Webhook для Telegram
@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.model_validate(data)
    await dp.feed_update(bot, update)
    return {"status": "ok"}


# Обработчик фото
@dp.message(lambda m: m.content_type == "photo")
async def photo_handler(message: types.Message):
    try:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file.file_path}"

        # 🔹 Запрос в Яндекс Vision
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze",
                headers={
                    "Authorization": f"Api-Key {YANDEX_OCR_API_KEY}",
                },
                json={
                    "folderId": os.getenv("YANDEX_FOLDER_ID"),
                    "analyze_specs": [
                        {
                            "content": (await client.get(file_url)).content.decode("latin1"),
                            "features": [{"type": "TEXT_DETECTION"}],
                        }
                    ],
                },
            )

        if response.status_code != 200:
            await message.answer("⚠️ Ошибка при запросе в Яндекс Vision API")
            return

        result = response.json()
        text = result["results"][0]["results"][0]["textDetection"]["pages"][0]["blocks"][0]["lines"][0]["words"][0]["text"]

        await message.answer(f"📅 Распознанный текст: <b>{text}</b>")

    except Exception as e:
        logger.error(f"Ошибка при обработке фото: {e}")
        await message.answer("⚠️ Ошибка при обработке фото")


# Установка webhook при старте
@app.on_event("startup")
async def on_startup():
    await bot.set_webhook(WEBHOOK_URL)
    logger.info(f"✅ Webhook установлен: {WEBHOOK_URL}")


# Очистка при завершении
@app.on_event("shutdown")
async def on_shutdown():
    await bot.delete_webhook()
    await bot.session.close()
    logger.info("❌ Бот остановлен")
