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
        # Берём последнее фото
        photo = message.photo[-1]

        # Получаем файл через bot
        file_info = await bot.get_file(photo.file_id)
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info.file_path}"

        async with httpx.AsyncClient() as client:
            response = await client.get(file_url)
            image_bytes = response.content

        # Отправляем в OCR
        text = await recognize_text(image_bytes)

        await bot.send_message(message.chat.id, f"📅 Распознанный текст: {text}")

    except Exception as e:
        logger.error(f"Ошибка при обработке фото: {e}", exc_info=True)
        await bot.send_message(message.chat.id, f"⚠️ Ошибка: {e}")


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
