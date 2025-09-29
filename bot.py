import os
import logging
import httpx
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update
from aiogram.dispatcher.filters import CommandStart
from aiogram.utils.executor import start_webhook

# ==============================
# 🔹 Логирование
# ==============================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

# ==============================
# 🔹 Переменные окружения
# ==============================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YANDEX_OCR_API_KEY = os.getenv("YANDEX_OCR_API_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не найден в переменных окружения")
if not YANDEX_OCR_API_KEY:
    raise ValueError("❌ YANDEX_OCR_API_KEY не найден в переменных окружения")

# ==============================
# 🔹 Инициализация
# ==============================
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)
app = FastAPI()

WEBHOOK_URL = "https://date-verification.onrender.com/telegram/webhook"

# ==============================
# 🔹 Старт
# ==============================
@dp.message_handler(CommandStart())
async def start_handler(message: types.Message):
    await bot.send_message(message.chat.id, "👋 Отправь фото с датой — я её распознаю!")

# ==============================
# 🔹 Обработка фото
# ==============================
@dp.message_handler(content_types=["photo"])
async def photo_handler(message: types.Message):
    try:
        # Скачиваем фото
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        file_path = file.file_path
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"

        async with httpx.AsyncClient() as client:
            img_bytes = await client.get(file_url)

            # Запрос в Яндекс Vision
            ocr_url = "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze"
            headers = {"Authorization": f"Api-Key {YANDEX_OCR_API_KEY}"}
            payload = {
                "folderId": "<YOUR_FOLDER_ID>",
                "analyze_specs": [{
                    "content": img_bytes.content.decode("latin1"),
                    "features": [{"type": "TEXT_DETECTION"}]
                }]
            }

            response = await client.post(ocr_url, headers=headers, json=payload)

        if response.status_code != 200:
            await bot.send_message(message.chat.id, f"⚠️ Ошибка OCR API: {response.text}")
            return

        data = response.json()
        text = data["results"][0]["results"][0]["textDetection"]["pages"][0]["blocks"][0]["lines"][0]["text"]

        await bot.send_message(message.chat.id, f"📅 Распознанный текст: {text}")

    except Exception as e:
        logger.exception("Ошибка при обработке фото")
        await bot.send_message(message.chat.id, f"⚠️ Ошибка: {e}")

# ==============================
# 🔹 Webhook
# ==============================
@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    update = Update(**await request.json())

    # 📌 Устанавливаем контекст один раз
    from aiogram import Bot, Dispatcher
    Bot.set_current(bot)
    Dispatcher.set_current(dp)

    await dp.process_update(update)
    return {"ok": True}

# ==============================
# 🔹 При старте приложения
# ==============================
@app.on_event("startup")
async def on_startup():
    await bot.set_webhook(WEBHOOK_URL)
    logger.info(f"✅ Webhook установлен: {WEBHOOK_URL}")

# ==============================
# 🔹 При завершении
# ==============================
@app.on_event("shutdown")
async def on_shutdown():
    await bot.delete_webhook()
    await bot.session.close()
    logger.info("❌ Бот остановлен")
