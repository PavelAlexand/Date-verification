import os
import io
import logging
import httpx
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update

# -------------------------------------------------
# 🔧 Настройка логов
# -------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(_name_)

# -------------------------------------------------
# 🔑 Переменные окружения
# -------------------------------------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")  # API-ключ для Vision

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не найден в переменных окружения")
if not YANDEX_FOLDER_ID:
    raise ValueError("❌ YANDEX_FOLDER_ID не найден в переменных окружения")
if not YANDEX_API_KEY:
    raise ValueError("❌ YANDEX_API_KEY не найден в переменных окружения")

# -------------------------------------------------
# 🤖 Инициализация бота
# -------------------------------------------------
bot = Bot(token=TELEGRAM_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)
Bot.set_current(bot)  # фикс ошибки RuntimeError: Can't get bot instance

# -------------------------------------------------
# 🌐 FastAPI
# -------------------------------------------------
app = FastAPI()

@app.get("/")
async def root():
    return {"status": "ok", "message": "Bot is running 🚀"}

# -------------------------------------------------
# 📝 Функция OCR (Яндекс Vision)
# -------------------------------------------------
async def yandex_ocr(image_bytes: bytes) -> str:
    url = "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze"
    headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}"}
    data = {
        "folderId": YANDEX_FOLDER_ID,
        "analyze_specs": [{
            "content": image_bytes.decode("latin1"),  # передаем байты как строку
            "features": [{"type": "TEXT_DETECTION"}]
        }]
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()

    try:
        text = result["results"][0]["results"][0]["textDetection"]["pages"][0]["blocks"][0]["lines"][0]["words"][0]["text"]
    except Exception:
        text = "⚠️ Дата не распознана"
    return text

# -------------------------------------------------
# 📷 Обработка фото
# -------------------------------------------------
@dp.message_handler(content_types=["photo"])
async def photo_handler(message: types.Message):
    photo = message.photo[-1]
    bio = io.BytesIO()
    await photo.download(destination_file=bio)
    text = await yandex_ocr(bio.getvalue())
    await message.reply(f"📅 Распознанный текст: {text}")

# -------------------------------------------------
# 📩 Вебхук
# -------------------------------------------------
@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    update = Update(**await request.json())
    await dp.process_update(update)
    return {"ok": True}

# -------------------------------------------------
# 🚀 Установка вебхука при запуске
# -------------------------------------------------
@app.on_event("startup")
async def on_startup():
    webhook_url = f"{os.getenv('RENDER_EXTERNAL_URL')}/telegram/webhook"
    await bot.set_webhook(webhook_url)
    logger.info(f"✅ Webhook установлен: {webhook_url}")

@app.on_event("shutdown")
async def on_shutdown():
    session = await bot.get_session()
    await session.close()
