import os
import logging
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update
import httpx
import io

# ==============================
# Логирование
# ==============================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

# ==============================
# Токены и ключи
# ==============================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YANDEX_OCR_API_KEY = os.getenv("YANDEX_OCR_API_KEY")
FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не найден в переменных окружения")
if not YANDEX_OCR_API_KEY:
    raise ValueError("❌ YANDEX_OCR_API_KEY не найден в переменных окружения")
if not FOLDER_ID:
    raise ValueError("❌ YANDEX_FOLDER_ID не найден в переменных окружения")

# ==============================
# Инициализация бота
# ==============================
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)

# ==============================
# FastAPI
# ==============================
app = FastAPI()

@app.on_event("startup")
async def on_startup():
    webhook_url = os.getenv("RENDER_EXTERNAL_URL", "") + "/telegram/webhook"
    await bot.set_webhook(webhook_url)
    logger.info(f"✅ Webhook установлен: {webhook_url}")

@app.on_event("shutdown")
async def on_shutdown():
    session = await bot.get_session()
    await session.close()
    logger.info("❌ Бот остановлен")

# ==============================
# Корневой эндпоинт для Render
# ==============================
@app.get("/")
async def root():
    return {"status": "ok", "message": "Бот работает ✅"}

# ==============================
# Эндпоинт для Telegram
# ==============================
@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update(**data)
    await dp.process_update(update)
    return {"ok": True}

# ==============================
# Хендлер для фото
# ==============================
@dp.message_handler(content_types=["photo"])
async def photo_handler(message: types.Message):
    try:
        # Скачиваем фото вручную через bot
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        file_path = file.file_path

        # Получаем файл из Telegram
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
        async with httpx.AsyncClient() as client:
            response = await client.get(file_url)
            image_bytes = response.content

        # Отправляем в Яндекс OCR
        headers = {
            "Authorization": f"Api-Key {YANDEX_OCR_API_KEY}",
            "Content-Type": "application/json"
        }
        body = {
            "folderId": FOLDER_ID,
            "analyze_specs": [{
                "content": image_bytes.decode("latin1"),  # лучше base64
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
            await bot.send_message(message.chat.id, "⚠️ Ошибка при обращении к Yandex OCR API")
            return

        result = ocr_response.json()
        text = result["results"][0]["results"][0]["textDetection"]["pages"][0]["blocks"][0]["lines"][0]["text"]

        await bot.send_message(message.chat.id, f"📅 Распознанный текст: {text}")

    except Exception as e:
        logger.error("Ошибка при обработке фото", exc_info=True)
        await bot.send_message(message.chat.id, f"⚠️ Ошибка: {e}")
