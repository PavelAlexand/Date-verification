import os
import logging
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update
from aiogram.utils.executor import set_webhook
import httpx
import io

# ================== НАСТРОЙКА ЛОГОВ ==================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

# ================== НАСТРОЙКА ПЕРЕМЕННЫХ ==================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YANDEX_OCR_API_KEY = os.getenv("YANDEX_OCR_API_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не найден в переменных окружения")
if not YANDEX_OCR_API_KEY:
    raise ValueError("❌ YANDEX_OCR_API_KEY не найден в переменных окружения")

WEBHOOK_PATH = "/telegram/webhook"
WEBHOOK_URL = f"https://date-verification.onrender.com{WEBHOOK_PATH}"

# ================== ИНИЦИАЛИЗАЦИЯ ==================
bot = Bot(token=TELEGRAM_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)
app = FastAPI()

# ================== ОБРАБОТЧИК ФОТО ==================
@dp.message_handler(content_types=["photo"])
async def photo_handler(message: types.Message):
    try:
        bot.set_current(bot)  # фикс контекста

        photo = message.photo[-1]
        bio = io.BytesIO()
        await photo.download(destination_file=bio)
        bio.seek(0)

        # Отправка фото в Yandex Vision
        files = {"file": bio}
        headers = {"Authorization": f"Api-Key {YANDEX_OCR_API_KEY}"}

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze",
                headers=headers,
                files=files,
            )

        if response.status_code != 200:
            await message.reply(f"⚠️ Ошибка OCR API: {response.text}")
            return

        result = response.json()
        logger.info(f"📄 Ответ от Yandex Vision: {result}")

        try:
            text = result["results"][0]["results"][0]["textDetection"]["pages"][0]["blocks"][0]["lines"][0]["words"][0]["text"]
        except Exception:
            text = "❌ Дата не распознана"

        await message.reply(f"📅 Распознанный текст: {text}")

    except Exception as e:
        logger.error("Ошибка при обработке фото", exc_info=True)
        await message.answer(f"⚠️ Ошибка: {e}")

# ================== ВЕБХУК ==================
@app.on_event("startup")
async def on_startup():
    await set_webhook(bot=bot, dispatcher=dp, url=WEBHOOK_URL)
    logger.info(f"✅ Webhook установлен: {WEBHOOK_URL}")

@app.on_event("shutdown")
async def on_shutdown():
    session = await bot.get_session()
    await session.close()
    logger.info("❌ Бот остановлен")

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    update = Update(**await request.json())
    await dp.process_update(update)
    return {"ok": True}

@app.get("/")
async def root():
    return {"status": "ok"}
