import os
import logging
import base64
import httpx
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types

# 🔹 Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

# 🔹 Переменные окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YANDEX_OCR_API_KEY = os.getenv("YANDEX_OCR_API_KEY")
FOLDER_ID = os.getenv("FOLDER_ID")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не найден в переменных окружения")
if not YANDEX_OCR_API_KEY:
    raise ValueError("❌ YANDEX_OCR_API_KEY не найден в переменных окружения")
if not FOLDER_ID:
    raise ValueError("❌ FOLDER_ID не найден в переменных окружения")
if not WEBHOOK_URL:
    raise ValueError("❌ WEBHOOK_URL не найден в переменных окружения")

# 🔹 Telegram bot
bot = Bot(token=TELEGRAM_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# 🔹 FastAPI app
app = FastAPI()

@app.on_event("startup")
async def on_startup():
    # Используем URL из переменной окружения без добавления хвоста
    await bot.set_webhook(WEBHOOK_URL)
    logger.info(f"✅ Webhook установлен: {WEBHOOK_URL}")

@app.on_event("shutdown")
async def on_shutdown():
    session = await bot.get_session()
    await session.close()

@app.get("/")
async def root():
    return {"status": "ok", "message": "Bot is running 🚀"}

@app.head("/")
async def root_head():
    return {}

# 🔹 OCR через Yandex Vision API
async def yandex_ocr(image_bytes: bytes) -> str:
    url = "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze"
    headers = {"Authorization": f"Api-Key {YANDEX_OCR_API_KEY}"}
    data = {
        "folderId": FOLDER_ID,
        "analyze_specs": [
            {
                "content": base64.b64encode(image_bytes).decode("utf-8"),
                "features": [{"type": "TEXT_DETECTION"}],
            }
        ],
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()

    try:
        text = result["results"][0]["results"][0]["textDetection"]["pages"][0]["blocks"][0]["lines"][0]["words"][0]["text"]
        return text
    except Exception:
        return "Дата не распознана"

# 🔹 Обработчик фото
@dp.message_handler(content_types=["photo"])
async def photo_handler(message: types.Message):
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file.file_path}"

    async with httpx.AsyncClient(timeout=30) as client:
        file_response = await client.get(file_url)
        file_response.raise_for_status()
        image_bytes = file_response.content

    text = await yandex_ocr(image_bytes)
    await message.reply(f"📅 Распознанный текст: {text}")

# 🔹 Webhook endpoint
@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = types.Update(**data)
    await dp.process_update(update)
    return {"ok": True}
