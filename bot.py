import os
import io
import base64
import logging
import httpx
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update

# 🔹 Логирование
logging.basicConfig(level=logging.INFO)

# 🔹 Переменные окружения (Render → Environment Variables)
BOT_TOKEN = os.getenv("BOT_TOKEN")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")

# Проверяем, чтобы всё было установлено
if not BOT_TOKEN or not YANDEX_API_KEY or not YANDEX_FOLDER_ID:
    raise RuntimeError("❌ Не заданы BOT_TOKEN, YANDEX_API_KEY или YANDEX_FOLDER_ID")

# 🔹 Telegram bot
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# 🔹 FastAPI для Webhook
app = FastAPI()


# ---- OCR через Yandex Vision API ----
async def yandex_ocr(image_bytes: bytes) -> str:
    url = "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze"

    headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}"}

    body = {
        "folderId": YANDEX_FOLDER_ID,
        "analyze_specs": [{
            "content": base64.b64encode(image_bytes).decode("utf-8"),
            "features": [{"type": "TEXT_DETECTION"}]
        }]
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(url, headers=headers, json=body)
        r.raise_for_status()
        result = r.json()

    # Достаём текст
    try:
        text = result["results"][0]["results"][0]["textDetection"]["pages"][0]["blocks"][0]["lines"][0]["text"]
    except Exception:
        text = "❌ Не удалось распознать текст"
    return text


# ---- Хендлер на фото ----
@dp.message_handler(content_types=["photo"])
async def photo_handler(message: types.Message):
    photo = message.photo[-1]  # Берем фото максимального размера
    bio = io.BytesIO()
    await photo.download(destination=bio)
    text = await yandex_ocr(bio.getvalue())
    await message.reply(f"📸 Распознанный текст:\n\n{text}")


# ---- Webhook ----
@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update(**data)
    await dp.process_update(update)
    return {"ok": True}


@app.on_event("startup")
async def on_startup():
    # Устанавливаем webhook
    webhook_url = os.getenv("RENDER_EXTERNAL_URL") + "/telegram/webhook"
    await bot.set_webhook(webhook_url)
    logging.info(f"✅ Webhook установлен: {webhook_url}")


@app.on_event("shutdown")
async def on_shutdown():
    await bot.session.close()
