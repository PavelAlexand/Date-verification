import os
import logging
import base64
import httpx
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update
from aiogram.enums import ParseMode

# 🔹 Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

# 🔹 Токены из переменных окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YANDEX_OCR_API_KEY = os.getenv("YANDEX_OCR_API_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не найден в переменных окружения")
if not YANDEX_OCR_API_KEY:
    raise ValueError("❌ YANDEX_OCR_API_KEY не найден в переменных окружения")

# 🔹 Основные объекты
bot = Bot(token=TELEGRAM_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(bot=bot)
app = FastAPI()

# 🔹 Webhook URL
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://date-verification.onrender.com/telegram/webhook")


# ---------- OCR через Яндекс ----------
async def ocr_image(image_bytes: bytes) -> str:
    url = "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze"
    encoded_image = base64.b64encode(image_bytes).decode("utf-8")

    headers = {
        "Authorization": f"Api-Key {YANDEX_OCR_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "folderId": os.getenv("YANDEX_FOLDER_ID", ""),  # если не задан, пусто
        "analyze_specs": [{
            "content": encoded_image,
            "features": [{"type": "TEXT_DETECTION"}]
        }]
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, headers=headers, json=payload)

    if response.status_code != 200:
        logger.error(f"Яндекс Vision ошибка {response.status_code}: {response.text}")
        return "⚠️ Ошибка OCR (не удалось распознать изображение)"

    try:
        data = response.json()
        text = " ".join([block["text"] for block in data["results"][0]["results"][0]["textDetection"]["pages"][0]["blocks"]])
        return text if text else "⚠️ Текст не найден"
    except Exception as e:
        logger.error(f"Ошибка разбора OCR: {e}")
        return "⚠️ Ошибка обработки ответа OCR"


# ---------- Хэндлер для фото ----------
@dp.message_handler(content_types=["photo"])
async def photo_handler(message: types.Message):
    try:
        Bot.set_current(bot)  # фикс контекста
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file.file_path}"

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(file_url)
            img_bytes = resp.content

        text = await ocr_image(img_bytes)
        await message.answer(f"📄 Распознанный текст:\n\n{text}")

    except Exception as e:
        logger.error(f"Ошибка при обработке фото: {e}")
        await message.answer("⚠️ Не удалось обработать фото")


# ---------- FastAPI endpoints ----------
@app.on_event("startup")
async def on_startup():
    webhook_url = WEBHOOK_URL
    await bot.set_webhook(webhook_url)
    logger.info(f"✅ Webhook установлен: {webhook_url}")


@app.on_event("shutdown")
async def on_shutdown():
    await bot.delete_webhook()
    await bot.session.close()
    logger.info("❌ Бот остановлен")


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        update = Update(**data)
        await dp.process_update(update)
        return {"ok": True}
    except Exception as e:
        logger.error(f"Ошибка при обработке апдейта: {e}")
        return {"ok": False}
