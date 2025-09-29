import os
import logging
import base64
import httpx
from io import BytesIO

from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

# Переменные окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YANDEX_OCR_API_KEY = os.getenv("YANDEX_OCR_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не найден в переменных окружения")
if not YANDEX_OCR_API_KEY:
    raise ValueError("❌ YANDEX_OCR_API_KEY не найден в переменных окружения")
if not YANDEX_FOLDER_ID:
    raise ValueError("❌ YANDEX_FOLDER_ID не найден в переменных окружения")

# Инициализация
bot = Bot(token=TELEGRAM_TOKEN)
dispatcher = Dispatcher(bot)
app = FastAPI()


# ====== OCR ======
async def process_image_with_yandex(image_bytes: bytes) -> str:
    url = "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze"
    headers = {"Authorization": f"Api-Key {YANDEX_OCR_API_KEY}"}
    data = {
        "folderId": YANDEX_FOLDER_ID,
        "analyze_specs": [
            {
                "content": base64.b64encode(image_bytes).decode("utf-8"),
                "features": [
                    {"type": "TEXT_DETECTION", "text_detection_config": {"language_codes": ["*"]}}
                ],
            }
        ],
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=data)
        resp.raise_for_status()
        result = resp.json()

    try:
        texts = []
        for page in result["results"][0]["results"][0]["textDetection"]["pages"]:
            for block in page["blocks"]:
                for line in block["lines"]:
                    line_text = " ".join([word["text"] for word in line["words"]])
                    texts.append(line_text)

        full_text = "\n".join(texts)
        return full_text if full_text.strip() else "❌ Текст не распознан"
    except Exception as e:
        logger.error(f"Ошибка парсинга OCR: {e}")
        return "⚠️ Ошибка при обработке текста"


# ====== Обработчики ======
@dispatcher.message_handler(content_types=["photo"])
async def photo_handler(message: types.Message):
    try:
        Bot.set_current(bot)  # фикс для контекста
        photo = message.photo[-1]
        bio = BytesIO()
        await photo.download(destination_file=bio)
        bio.seek(0)

        text = await process_image_with_yandex(bio.read())
        await message.answer(f"📄 Распознанный текст:\n{text}")

    except Exception as e:
        logger.error(f"Ошибка при обработке фото: {e}")
        await message.answer(f"⚠️ Ошибка: {e}")


# ====== Webhook ======
@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    Bot.set_current(bot)  # фикс для aiogram
    update = Update(**await request.json())
    await dispatcher.process_update(update)
    return {"ok": True}


@app.on_event("startup")
async def on_startup():
    webhook_url = os.getenv("WEBHOOK_URL", "https://date-verification.onrender.com/telegram/webhook")
    await bot.set_webhook(webhook_url)
    logger.info(f"✅ Webhook установлен: {webhook_url}")


@app.on_event("shutdown")
async def on_shutdown():
    session = await bot.get_session()
    await session.close()
    logger.info("♻️ Бот выключен")
