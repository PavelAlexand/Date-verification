import os
import logging
import base64
import httpx
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, Update
from aiogram.enums import ParseMode

# ==== Конфиг ====
API_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://date-verification.onrender.com/telegram/webhook")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")  # токен для Vision API
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")  # id каталога в Yandex Cloud

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==== Telegram Bot ====
bot = Bot(token=API_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

app = FastAPI()


# ==== Обработчик фото ====
@dp.message(F.photo)
async def photo_handler(message: Message):
    try:
        # Берём лучшее качество фото
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        file_url = f"https://api.telegram.org/file/bot{API_TOKEN}/{file.file_path}"

        # Скачиваем фото
        async with httpx.AsyncClient() as client:
            resp = await client.get(file_url)
            resp.raise_for_status()
            image_bytes = resp.content

        # Кодируем в base64
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        # Отправляем в Yandex Vision
        vision_url = "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze"
        headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}"}
        body = {
            "folderId": YANDEX_FOLDER_ID,
            "analyze_specs": [{
                "content": image_b64,
                "features": [{"type": "TEXT_DETECTION"}]
            }]
        }

        async with httpx.AsyncClient() as client:
            vision_resp = await client.post(vision_url, headers=headers, json=body)
            vision_resp.raise_for_status()
            result = vision_resp.json()

        # Достаём текст
        text = ""
        try:
            pages = result["results"][0]["results"][0]["textDetection"]["pages"]
            for page in pages:
                for block in page["blocks"]:
                    for line in block["lines"]:
                        line_text = " ".join([word["text"] for word in line["words"]])
                        text += line_text + "\n"
        except Exception:
            text = "❌ Текст не найден"

        await message.answer(f"📄 Распознанный текст:\n\n{text}")

    except Exception as e:
        logger.error(f"Ошибка при обработке фото: {e}", exc_info=True)
        await message.answer("⚠️ Ошибка при обработке фото")


# ==== Webhook ====
@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.model_validate(data)
    await dp.feed_update(bot, update)
    return {"ok": True}


# ==== Тестовый GET ====
@app.get("/")
async def home():
    return {"status": "ok", "message": "Бот работает 🚀"}
