import os
import logging
import io
import httpx
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update

# 🔹 Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

# 🔹 Токены
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YANDEX_OCR_API_KEY = os.getenv("YANDEX_OCR_API_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не найден в переменных окружения")
if not YANDEX_OCR_API_KEY:
    raise ValueError("❌ YANDEX_OCR_API_KEY не найден в переменных окружения")

# 🔹 Основные объекты
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
app = FastAPI()

# URL вебхука
WEBHOOK_URL = "https://date-verification.onrender.com/telegram/webhook"


# ================== Обработчик фото ==================
@dp.message_handler(content_types=["photo"])
async def photo_handler(message: types.Message):
    try:
        # Получаем файл фото
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file.file_path}"

        # Скачиваем фото в память
        async with httpx.AsyncClient() as client:
            response = await client.get(file_url)
            image_bytes = response.content

        # Отправляем в Яндекс OCR
        ocr_url = "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze"
        headers = {"Authorization": f"Api-Key {YANDEX_OCR_API_KEY}"}
        data = {
            "analyze_specs": [{
                "content": image_bytes.decode("latin1"),  # base64 можно добавить при необходимости
                "features": [{"type": "TEXT_DETECTION", "text_detection_config": {"language_codes": ["*"]}}]
            }]
        }

        async with httpx.AsyncClient() as client:
            ocr_response = await client.post(ocr_url, headers=headers, json=data)

        if ocr_response.status_code != 200:
            await message.answer("⚠️ Ошибка OCR: API не вернул результат")
            return

        result_json = ocr_response.json()
        text = ""
        try:
            text = " ".join([b["text"] for b in result_json["results"][0]["results"][0]["textDetection"]["pages"][0]["blocks"]])
        except Exception:
            text = "❌ Текст не распознан"

        await message.answer(f"📅 Распознанный текст: {text}")

    except Exception as e:
        logger.error(f"Ошибка при обработке фото: {e}")
        await message.answer(f"⚠️ Ошибка: {e}")


# ================== FastAPI роуты ==================
@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    try:
        update = Update(**await request.json())
        await dp.process_update(update)
    except Exception as e:
        logger.error(f"Ошибка при обработке апдейта: {e}")
    return {"ok": True}


@app.on_event("startup")
async def on_startup():
    await bot.set_webhook(WEBHOOK_URL)
    logger.info(f"✅ Webhook установлен: {WEBHOOK_URL}")


@app.on_event("shutdown")
async def on_shutdown():
    session = await bot.get_session()
    await session.close()
    logger.info("❌ Бот остановлен")
