import os
import logging
import httpx
from io import BytesIO
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

# Токены из переменных окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YANDEX_OCR_API_KEY = os.getenv("YANDEX_OCR_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не найден в переменных окружения")
if not YANDEX_OCR_API_KEY:
    raise ValueError("❌ YANDEX_OCR_API_KEY не найден в переменных окружения")
if not YANDEX_FOLDER_ID:
    raise ValueError("❌ YANDEX_FOLDER_ID не найден в переменных окружения")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)

app = FastAPI()

YANDEX_VISION_URL = "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze"


async def recognize_text(image_bytes: bytes) -> str:
    headers = {
        "Authorization": f"Api-Key {YANDEX_OCR_API_KEY}",
        "Content-Type": "application/json",
    }
    data = {
        "folderId": YANDEX_FOLDER_ID,
        "analyze_specs": [{
            "content": image_bytes.decode("latin1"),
            "features": [{"type": "TEXT_DETECTION", "text_detection_config": {"language_codes": ["*"]}}],
        }]
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(YANDEX_VISION_URL, headers=headers, json=data)

    # Логируем полный ответ Яндекса
    logger.info(f"📩 Yandex Vision raw response: {response.text}")

    if response.status_code != 200:
        return f"Ошибка Vision API: {response.text}"

    try:
        result = response.json()
        text = result["results"][0]["results"][0]["textDetection"]["pages"][0]["blocks"][0]["lines"][0]["text"]
        return text
    except Exception as e:
        logger.error(f"Ошибка парсинга ответа Vision API: {e}")
        return "Дата не распознана"


@dp.message_handler(content_types=["photo"])
async def photo_handler(message: types.Message):
    try:
        bot.set_current(bot)  # фикс контекста
        photo = message.photo[-1]
        bio = BytesIO()
        await photo.download(destination_file=bio)
        bio.seek(0)

        text = await recognize_text(bio.getvalue())
        await message.reply(f"📅 Распознанный текст: {text}")

    except Exception as e:
        logger.error(f"Ошибка при обработке фото: {e}", exc_info=True)
        await message.reply(f"⚠️ Ошибка: {e}")


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update(**data)
    await dp.process_update(update)
    return {"ok": True}


@app.on_event("startup")
async def on_startup():
    webhook_url = "https://date-verification.onrender.com/telegram/webhook"
    await bot.set_webhook(webhook_url)
    logger.info(f"✅ Webhook установлен: {webhook_url}")


@app.on_event("shutdown")
async def on_shutdown():
    await bot.delete_webhook()
    await bot.session.close()
    logger.info("❌ Бот остановлен")
