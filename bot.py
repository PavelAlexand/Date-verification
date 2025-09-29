import os
import io
import httpx
import logging
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загружаем токены из переменных окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YANDEX_OCR_API_KEY = os.getenv("YANDEX_OCR_API_KEY")
FOLDER_ID = os.getenv("FOLDER_ID")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не найден в переменных окружения")
if not YANDEX_OCR_API_KEY:
    raise ValueError("❌ YANDEX_OCR_API_KEY не найден в переменных окружения")
if not FOLDER_ID:
    raise ValueError("❌ FOLDER_ID не найден в переменных окружения")

# Инициализация бота
bot = Bot(token=TELEGRAM_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# FastAPI
app = FastAPI()

# OCR функция
async def yandex_ocr(image_bytes: bytes) -> str:
    url = "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze"
    headers = {"Authorization": f"Api-Key {YANDEX_OCR_API_KEY}"}
    data = {
        "folderId": FOLDER_ID,
        "analyze_specs": [{
            "content": image_bytes.decode("latin1"),
            "features": [{"type": "TEXT_DETECTION", "text_detection_config": {"language_codes": ["*"]}}],
        }]
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()

    try:
        text = result["results"][0]["results"][0]["textDetection"]["pages"][0]["blocks"][0]["lines"][0]["words"][0]["text"]
        return text
    except Exception as e:
        logger.error(f"Ошибка парсинга ответа от Yandex OCR: {e}")
        return "❌ Не удалось распознать текст."

# Обработчик фото
@dp.message_handler(content_types=["photo"])
async def photo_handler(message: types.Message):
    photo = message.photo[-1]
    bio = io.BytesIO()
    await photo.download(destination_file=bio)
    text = await yandex_ocr(bio.getvalue())
    await message.reply(f"📄 Распознанный текст:\n{text}")

# Webhook
@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    update = Update(**await request.json())
    await dp.process_update(update)
    return {"ok": True}

# Проверочные эндпоинты
@app.get("/")
async def root_get():
    return {"status": "ok"}

@app.head("/")
async def root_head():
    return {}

# Запуск/остановка
@app.on_event("startup")
async def on_startup():
    webhook_url = os.getenv("WEBHOOK_URL")
    if webhook_url:
        await bot.set_webhook(f"{webhook_url}/telegram/webhook")
        logger.info(f"✅ Webhook установлен: {webhook_url}/telegram/webhook")

@app.on_event("shutdown")
async def on_shutdown():
    session = await bot.get_session()
    await session.close()
