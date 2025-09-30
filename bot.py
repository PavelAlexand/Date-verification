import os
import logging
import httpx
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update
from aiogram.utils.executor import Executor
from io import BytesIO

# ------------------ ЛОГИ ------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

# ------------------ ПЕРЕМЕННЫЕ ------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YANDEX_OCR_API_KEY = os.getenv("YANDEX_OCR_API_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не найден в переменных окружения")
if not YANDEX_OCR_API_KEY:
    raise ValueError("❌ YANDEX_OCR_API_KEY не найден в переменных окружения")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)

# ------------------ OCR ------------------
async def recognize_text(image_bytes: bytes) -> str:
    url = "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze"
    headers = {"Authorization": f"Api-Key {YANDEX_OCR_API_KEY}"}
    data = {
        "folderId": os.getenv("YANDEX_FOLDER_ID"),
        "analyze_specs": [{
            "content": image_bytes.decode("latin1"),
            "features": [{"type": "TEXT_DETECTION"}]
        }]
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=headers, json=data)
        resp.raise_for_status()
        result = resp.json()
        try:
            text = "\n".join([b["text"] for p in result["results"][0]["results"][0]["textDetection"]["pages"]
                              for b in p["blocks"]])
        except Exception:
            text = "⚠️ Не удалось распознать текст"
    return text

# ------------------ HANDLERS ------------------
@dp.message_handler(content_types=["photo"])
async def photo_handler(message: types.Message):
    try:
        photo = message.photo[-1]
        bio = BytesIO()
        await photo.download(destination_file=bio)
        bio.seek(0)

        text = await recognize_text(bio.getvalue())
        await message.answer(f"📅 Распознанный текст:\n{text}")

    except Exception as e:
        logger.error(f"Ошибка при обработке фото: {e}", exc_info=True)
        await message.answer(f"⚠️ Ошибка: {e}")

# ------------------ FASTAPI ------------------
app = FastAPI()

@app.get("/")
async def root():
    return {"status": "ok", "message": "bot is running"}

@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    try:
        update = Update(**await request.json())
        await dp.process_update(update)
    except Exception as e:
        logger.error(f"Ошибка при обработке апдейта: {e}", exc_info=True)
    return {"ok": True}

@app.on_event("startup")
async def on_startup():
    webhook_url = os.getenv("WEBHOOK_URL")
    if webhook_url:
        await bot.set_webhook(webhook_url + "/telegram/webhook")
        logger.info(f"✅ Webhook установлен: {webhook_url}/telegram/webhook")
    else:
        logger.warning("⚠️ WEBHOOK_URL не задан")

@app.on_event("shutdown")
async def on_shutdown():
    # Закрытие сессии
    try:
        await bot.get_session().close()
    except Exception:
        pass
    logger.info("❌ Бот остановлен")
