import os
import logging
import base64
import httpx
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update

# === Логирование ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

# === Переменные окружения ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YANDEX_OCR_API_KEY = os.getenv("YANDEX_OCR_API_KEY")
FOLDER_ID = os.getenv("FOLDER_ID")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не найден в переменных окружения")
if not YANDEX_OCR_API_KEY:
    raise ValueError("❌ YANDEX_OCR_API_KEY не найден в переменных окружения")
if not FOLDER_ID:
    raise ValueError("❌ FOLDER_ID не найден в переменных окружения")

# === Telegram Bot ===
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)

# === FastAPI ===
app = FastAPI()


# === Хэндлер фото ===
@dp.message_handler(content_types=["photo"])
async def photo_handler(message: types.Message):
    try:
        # Берем самое большое фото
        photo = message.photo[-1]

        # Получаем file_path через API Telegram
        file = await bot.get_file(photo.file_id)
        file_path = file.file_path

        # Скачиваем фото напрямую
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
        async with httpx.AsyncClient() as client:
            response = await client.get(file_url)
            image_bytes = response.content

        # Конвертируем в base64
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        # Запрос в Yandex Vision
        headers = {
            "Authorization": f"Api-Key {YANDEX_OCR_API_KEY}",
            "Content-Type": "application/json"
        }
        body = {
            "folderId": FOLDER_ID,
            "analyze_specs": [{
                "content": image_base64,
                "features": [{"type": "TEXT_DETECTION"}]
            }]
        }

        async with httpx.AsyncClient() as client:
            ocr_response = await client.post(
                "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze",
                headers=headers,
                json=body
            )

        if ocr_response.status_code != 200:
            await bot.send_message(
                message.chat.id,
                f"⚠️ Ошибка от Yandex: {ocr_response.text}"
            )
            return

        result = ocr_response.json()
        # Достаём первый блок текста
        text = result["results"][0]["results"][0]["textDetection"]["pages"][0]["blocks"][0]["lines"][0]["text"]

        await bot.send_message(message.chat.id, f"📅 Распознанный текст: {text}")

    except Exception as e:
        logger.error("Ошибка при обработке фото", exc_info=True)
        await bot.send_message(message.chat.id, f"⚠️ Ошибка: {e}")


# === Webhook ===
@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    try:
        update = Update(**await request.json())
        await dp.process_update(update)
    except Exception as e:
        logger.error(f"Ошибка в webhook: {e}", exc_info=True)
    return {"ok": True}


# === Старт приложения ===
@app.on_event("startup")
async def on_startup():
    webhook_url = os.getenv("RENDER_EXTERNAL_URL", "https://date-verification.onrender.com") + "/telegram/webhook"
    await bot.set_webhook(webhook_url)
    logger.info(f"✅ Webhook установлен: {webhook_url}")


@app.on_event("shutdown")
async def on_shutdown():
    await bot.delete_webhook()
    logger.info("♻️ Бот выключен")
