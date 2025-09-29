import os
import base64
import logging
import httpx
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update

# ================== Настройки ==================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не найден в переменных окружения")
if not YANDEX_API_KEY:
    raise ValueError("❌ YANDEX_API_KEY не найден в переменных окружения")

bot = Bot(token=TELEGRAM_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

logging.basicConfig(level=logging.INFO)

app = FastAPI()


# ================== Яндекс OCR ==================
async def yandex_ocr(image_bytes: bytes) -> str:
    url = "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze"
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
    }
    data = {
        "analyze_specs": [{
            "content": base64.b64encode(image_bytes).decode("utf-8"),
            "features": [{
                "type": "TEXT_DETECTION",
                "text_detection_config": {"language_codes": ["*"]}
            }]
        }]
    }

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, headers=headers, json=data)
        r.raise_for_status()
        result = r.json()

    # 🔹 Логируем полный ответ Яндекса
    logging.info(f"📄 Yandex OCR raw response: {result}")

    # Пытаемся достать текст
    text_blocks = []
    try:
        for res in result["results"][0]["results"][0]["textDetection"]["pages"][0]["blocks"]:
            for line in res.get("lines", []):
                text_blocks.append(line.get("text", ""))
    except Exception as e:
        logging.error(f"Ошибка при разборе OCR ответа: {e}")

    full_text = "\n".join(text_blocks)
    logging.info(f"📄 Extracted text: {full_text}")

    return full_text or "Текст не распознан"


# ================== Хэндлеры ==================
@dp.message_handler(content_types=["photo"])
async def photo_handler(message: types.Message):
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file.file_path}"

    async with httpx.AsyncClient() as client:
        resp = await client.get(file_url)
        img_bytes = resp.content

    text = await yandex_ocr(img_bytes)

    # Логируем и отправляем пользователю
    logging.info(f"📩 Final recognized text: {text}")
    await message.reply(f"Распознанный текст:\n{text}")


@dp.message_handler(commands=["start"])
async def start_handler(message: types.Message):
    await message.reply("👋 Привет! Отправь мне фото, и я попробую распознать на нем дату.")


# ================== Webhook ==================
@app.on_event("startup")
async def on_startup():
    webhook_url = os.getenv("WEBHOOK_URL")
    if webhook_url:
        await bot.set_webhook(f"{webhook_url}/telegram/webhook")
        logging.info(f"✅ Webhook установлен: {webhook_url}/telegram/webhook")


@app.on_event("shutdown")
async def on_shutdown():
    await bot.delete_webhook()
    await bot.session.close()


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        update = Update(**data)
        await dp.process_update(update)
    except Exception as e:
        logging.error(f"Ошибка в webhook: {e}")
    return {"ok": True}


@app.get("/")
async def root():
    return {"status": "ok", "message": "Бот работает 🚀"}
