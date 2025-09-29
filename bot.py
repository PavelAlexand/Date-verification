import os
import logging
import httpx
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update
from aiogram.utils.executor import start_webhook

# =============================
# 🔧 Логирование
# =============================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

# =============================
# 🔧 Переменные окружения
# =============================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YANDEX_OCR_API_KEY = os.getenv("YANDEX_OCR_API_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не найден в переменных окружения")

if not YANDEX_OCR_API_KEY:
    raise ValueError("❌ YANDEX_OCR_API_KEY не найден в переменных окружения")

# =============================
# 🔧 Настройки бота и webhook
# =============================
WEBHOOK_PATH = "/telegram/webhook"
WEBHOOK_URL = f"https://date-verification.onrender.com{WEBHOOK_PATH}"

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)

# =============================
# 🔧 FastAPI
# =============================
app = FastAPI()

# =============================
# 📷 Обработчик фото
# =============================
@dp.message_handler(content_types=["photo"])
async def photo_handler(message: types.Message):
    try:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        file_path = file.file_path

        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"

        # =============================
        # Отправка в Yandex Vision API
        # =============================
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze",
                headers={
                    "Authorization": f"Api-Key {YANDEX_OCR_API_KEY}",
                },
                json={
                    "folderId": os.getenv("YANDEX_FOLDER_ID"),
                    "analyze_specs": [{
                        "content": (await client.get(file_url)).content.decode("latin1"),
                        "features": [{"type": "TEXT_DETECTION"}]
                    }]
                }
            )

        result = response.json()
        logger.info(f"Yandex OCR response: {result}")

        # Извлекаем текст
        text = ""
        try:
            text = result["results"][0]["results"][0]["textDetection"]["pages"][0]["blocks"][0]["lines"][0]["words"][0]["text"]
        except Exception:
            text = "❌ Дата не распознана"

        # Отправляем результат пользователю
        await bot.send_message(message.chat.id, f"📅 Распознанный текст: {text}")

    except Exception as e:
        logger.error(f"Ошибка при обработке фото: {e}")
        await bot.send_message(message.chat.id, "⚠️ Ошибка при обработке изображения. Попробуйте ещё раз.")


# =============================
# 🔧 Webhook endpoint
# =============================
@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    update = Update(**await request.json())
    await dp.process_update(update)
    return {"ok": True}


# =============================
# 🔧 Установка webhook при старте
# =============================
@app.on_event("startup")
async def on_startup():
    await bot.set_webhook(WEBHOOK_URL)
    logger.info(f"✅ Webhook установлен: {WEBHOOK_URL}")


@app.on_event("shutdown")
async def on_shutdown():
    session = await bot.get_session()
    await session.close()
