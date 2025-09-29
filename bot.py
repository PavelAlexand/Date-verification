import os
import base64
import logging
from io import BytesIO

import httpx
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

# Читаем переменные окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YANDEX_OCR_API_KEY = os.getenv("YANDEX_OCR_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не найден в переменных окружения")
if not YANDEX_OCR_API_KEY:
    raise ValueError("❌ YANDEX_OCR_API_KEY не найден в переменных окружения")
if not YANDEX_FOLDER_ID:
    raise ValueError("❌ YANDEX_FOLDER_ID не найден в переменных окружения")

# Telegram
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)

# FastAPI
app = FastAPI()


async def recognize_text(image_bytes: bytes) -> str:
    """Отправка картинки в Yandex OCR API"""
    img_base64 = base64.b64encode(image_bytes).decode("utf-8")

    url = "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze"
    headers = {"Authorization": f"Api-Key {YANDEX_OCR_API_KEY}"}

    json_data = {
        "folderId": YANDEX_FOLDER_ID,
        "analyze_specs": [
            {
                "content": img_base64,
                "features": [{"type": "TEXT_DETECTION"}],
            }
        ],
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=headers, json=json_data)

    logger.info(f"⬅️ Ответ от Yandex OCR: {response.status_code} {response.text}")

    if response.status_code != 200:
        return f"⚠️ Ошибка Yandex OCR: {response.status_code} {response.text}"

    try:
        result = response.json()
        text = ""
        for page in result["results"][0]["results"]:
            for block in page["textDetection"]["pages"][0]["blocks"]:
                for line in block["lines"]:
                    for word in line["words"]:
                        text += word["text"] + " "
        return text.strip() if text else "❌ Текст не распознан"
    except Exception as e:
        logger.error(f"Ошибка обработки JSON: {e}")
        return "⚠️ Ошибка при разборе ответа OCR"


# Обработка фото
@dp.message_handler(content_types=["photo"])
async def photo_handler(message: types.Message):
    try:
        photo = message.photo[-1]
        bio = BytesIO()
        await photo.download(destination_file=bio)
        text = await recognize_text(bio.getvalue())
        await message.reply(f"📅 Распознанный текст: {text}")
    except Exception as e:
        logger.exception("Ошибка при обработке фото")
        await message.reply(f"⚠️ Ошибка: {e}")


# Webhook
@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.to_object(data)
    await dp.process_update(update)
    return {"ok": True}


@app.on_event("startup")
async def on_startup():
    webhook_url = os.getenv("WEBHOOK_URL", "https://date-verification.onrender.com/telegram/webhook")
    await bot.set_webhook(webhook_url)
    logger.info(f"✅ Webhook установлен: {webhook_url}")


@app.on_event("shutdown")
async def on_shutdown():
    await bot.delete_webhook()
    session = await bot.get_session()
    await session.close()
    logger.info("🛑 Бот остановлен")
