import os
import logging
import base64
import httpx
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update

# 🔹 Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

# 🔹 Чтение токенов из переменных окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YANDEX_OCR_API_KEY = os.getenv("YANDEX_OCR_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не найден в переменных окружения")
if not YANDEX_OCR_API_KEY:
    raise ValueError("❌ YANDEX_OCR_API_KEY не найден в переменных окружения")
if not YANDEX_FOLDER_ID:
    raise ValueError("❌ YANDEX_FOLDER_ID не найден в переменных окружения")

# 🔹 Инициализация бота и диспетчера
bot = Bot(token=TELEGRAM_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# 🔹 FastAPI приложение
app = FastAPI()


# ✅ Root endpoint для проверки
@app.get("/")
async def root():
    return {"status": "ok", "message": "🚀 Бот работает"}


# ✅ Яндекс Vision OCR
async def yandex_ocr(image_bytes: bytes) -> str:
    url = "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze"
    headers = {
        "Authorization": f"Api-Key {YANDEX_OCR_API_KEY}",
        "Content-Type": "application/json",
    }

    data = {
        "folderId": YANDEX_FOLDER_ID,
        "analyze_specs": [
            {
                "content": base64.b64encode(image_bytes).decode("utf-8"),
                "features": [{"type": "TEXT_DETECTION"}],
            }
        ],
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=data)

    if response.status_code != 200:
        logger.error(f"❌ Ошибка от Yandex API: {response.status_code} {response.text}")
        return "Ошибка распознавания текста"

    result = response.json()
    try:
        text = result["results"][0]["results"][0]["textDetection"]["pages"][0]["blocks"][0]["lines"][0]["words"][0]["text"]
    except Exception:
        text = "Дата не распознана"

    return text


# ✅ Обработчик фото
@dp.message_handler(content_types=["photo"])
async def photo_handler(message: types.Message):
    await bot.set_current(bot)  # фикс для контекста
    try:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        file_path = file.file_path

        # Скачиваем фото с серверов Telegram
        async with httpx.AsyncClient() as client:
            file_bytes = await client.get(
                f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
            )
        text = await yandex_ocr(file_bytes.content)
        await message.reply(f"📅 Распознанный текст: {text}")

    except Exception as e:
        logger.error(f"Ошибка при обработке фото: {e}")
        await message.reply("❌ Ошибка при обработке фото")


# ✅ Вебхук от Telegram
@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    update = Update(**await request.json())
    await dp.process_update(update)
    return {"ok": True}


# ✅ Установка вебхука при старте
@app.on_event("startup")
async def on_startup():
    webhook_url = "https://date-verification.onrender.com/telegram/webhook"
    await bot.set_webhook(webhook_url)
    logger.info(f"✅ Webhook установлен: {webhook_url}")


# ✅ Закрытие соединения при завершении
@app.on_event("shutdown")
async def on_shutdown():
    session = await bot.get_session()
    await session.close()
