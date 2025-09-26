import os
import io
import re
import base64
import logging
import httpx
from datetime import datetime
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update

# 🔹 Логирование
logging.basicConfig(level=logging.INFO)

# 🔹 Переменные окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")

if not BOT_TOKEN or not YANDEX_API_KEY or not YANDEX_FOLDER_ID:
    raise RuntimeError("❌ Не заданы BOT_TOKEN, YANDEX_API_KEY или YANDEX_FOLDER_ID")

# 🔹 Telegram bot
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# 🔹 FastAPI
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

    try:
        text = result["results"][0]["results"][0]["textDetection"]["pages"][0]["blocks"][0]["lines"][0]["text"]
    except Exception:
        text = "❌ Не удалось распознать текст"
    return text


# ---- Извлечение даты из текста ----
def extract_date(text: str) -> str:
    match = re.search(r"(\d{2}[.\-/]\d{2}[.\-/]\d{4})", text)
    if match:
        return match.group(1)
    return None


# ---- Хендлер фото ----
@dp.message_handler(content_types=["photo"])
async def photo_handler(message: types.Message):
    # Получаем file_id последнего фото
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)

    # Скачиваем файл напрямую
    file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(file_url)
        image_bytes = resp.content

    # Отправляем в OCR
    text = await yandex_ocr(image_bytes)

    # Проверка даты
    date_str = extract_date(text)
    if date_str:
        try:
            parsed_date = datetime.strptime(date_str, "%d.%m.%Y")
            today = datetime.today()
            if parsed_date >= today:
                result = f"✅ Дата актуальна: {date_str}"
            else:
                result = f"⚠️ Дата просрочена: {date_str}"
        except Exception:
            result = f"📸 Распознан текст, но дата в необычном формате:\n{text}"
    else:
        result = f"📸 Текст без даты:\n{text}"

    await message.reply(result)


# ---- Webhook ----
@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update(**data)
    await dp.process_update(update)
    return {"ok": True}


@app.on_event("startup")
async def on_startup():
    webhook_url = os.getenv("RENDER_EXTERNAL_URL") + "/telegram/webhook"
    await bot.set_webhook(webhook_url)
    logging.info(f"✅ Webhook установлен: {webhook_url}")


@app.on_event("shutdown")
async def on_shutdown():
    session = await bot.get_session()
    await session.close()
