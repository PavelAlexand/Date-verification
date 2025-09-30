import os
import logging
from io import BytesIO

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
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не найден в переменных окружения")
if not YANDEX_OCR_API_KEY:
    raise ValueError("❌ YANDEX_OCR_API_KEY не найден в переменных окружения")
if not YANDEX_FOLDER_ID:
    raise ValueError("❌ YANDEX_FOLDER_ID не найден в переменных окружения")

# === Инициализация ===
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)
app = FastAPI()


# === Healthcheck для Render ===
@app.get("/")
async def root():
    return {"status": "ok", "message": "🤖 Bot is running"}


# === Обработчик фото ===
@dp.message_handler(content_types=["photo"])
async def photo_handler(message: types.Message):
    try:
        photo = message.photo[-1]
        bio = BytesIO()
        await photo.download(destination_file=bio, bot=bot)  # передаем bot
        bio.seek(0)

        # Запрос в Yandex Vision
        ocr_url = "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze"
        headers = {"Authorization": f"Api-Key {YANDEX_OCR_API_KEY}"}
        data = {
            "folderId": YANDEX_FOLDER_ID,
            "analyze_specs": [{
                "content": bio.getvalue().decode("latin1"),
                "features": [{"type": "TEXT_DETECTION"}]
            }]
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(ocr_url, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()

        # Достаем текст
        text = ""
        for res in result["results"][0]["results"]:
            if "textDetection" in res:
                for page in res["textDetection"]["pages"]:
                    for block in page["blocks"]:
                        for line in block["lines"]:
                            for word in line["words"]:
                                text += word["text"] + " "

        if not text.strip():
            text = "⚠️ Дата не распознана"

        await message.reply(f"📅 Распознанный текст: {text}")

    except Exception as e:
        logger.error("Ошибка при обработке фото", exc_info=True)
        await message.reply(f"⚠️ Ошибка: {e}")


# === Webhook ===
@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    try:
        update = Update(**await request.json())
        await dp.process_update(update)
    except Exception as e:
        logger.error(f"Ошибка при обработке апдейта: {e}")
    return {"ok": True}


# === Startup / Shutdown ===
@app.on_event("startup")
async def on_startup():
    webhook_url = os.getenv("RENDER_EXTERNAL_URL", "") + "/telegram/webhook"
    if webhook_url:
        await bot.set_webhook(webhook_url)
        logger.info(f"✅ Webhook установлен: {webhook_url}")


@app.on_event("shutdown")
async def on_shutdown():
    await bot.session.close()
    logger.info("❌ Бот остановлен")
