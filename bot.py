import os
import logging
import re
import base64
import datetime
import httpx

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiohttp import web
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://date-verification.onrender.com/telegram/webhook")
YANDEX_API_KEY = os.getenv("YANDEX_OCR_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")
CHAT_ID = os.getenv("CHAT_ID")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# ---------------- OCR ----------------
async def process_ocr(image_url: str) -> str | None:
    """
    Отправляем фото в Yandex OCR и возвращаем распознанный текст
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(image_url)
        if resp.status_code != 200:
            return None

        img_data = base64.b64encode(resp.content).decode("utf-8")

        body = {
            "folderId": YANDEX_FOLDER_ID,
            "analyze_specs": [
                {
                    "content": img_data,
                    "features": [
                        {
                            "type": "TEXT_DETECTION",
                            "text_detection_config": {
                                "language_codes": ["*"],
                                "model": "page"
                            }
                        }
                    ]
                }
            ]
        }

        headers = {
            "Authorization": f"Api-Key {YANDEX_API_KEY}"
        }

        ocr_resp = await client.post(
            "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze",
            headers=headers,
            json=body
        )

        if ocr_resp.status_code != 200:
            logger.error(f"OCR error: {ocr_resp.text}")
            return None

        data = ocr_resp.json()

        texts = []
        try:
            annotation = (
                data["results"][0]["results"][0].get("textDetection")
                or data["results"][0]["results"][0].get("textAnnotation")
            )

            if not annotation:
                logger.error(f"Не найдено textDetection/textAnnotation в ответе: {data}")
                return None

            for page in annotation.get("pages", []):
                for block in page.get("blocks", []):
                    for line in block.get("lines", []):
                        line_text = " ".join([word["text"] for word in line.get("words", [])])
                        texts.append(line_text)

            if not texts:
                logger.warning(f"OCR не нашёл текст: {data}")
                return None

            return " ".join(texts)

        except Exception as e:
            logger.error(f"Ошибка разбора OCR ответа: {e}, ответ: {data}")
            return None

# ---------------- Хэндлеры ----------------
@dp.message(F.text == "/start")
async def cmd_start(message: Message):
    await message.answer("✅ Бот запущен. Буду напоминать присылать фото каждые 2 часа.")
    logger.info(f"Chat ID для напоминаний: {message.chat.id}")

@dp.message(F.photo)
async def handle_photo(message: Message):
    try:
        file = await bot.get_file(message.photo[-1].file_id)
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file.file_path}"

        text = await process_ocr(file_url)

        if not text:
            await message.answer("❌ Не удалось распознать текст на фото")
            return

        await message.answer(f"📝 Распознанный текст:\n{text}")

        # Расширенный поиск даты
        patterns = [
            r"\d{2}\.\d{2}\.\d{4}",  # 16.07.2025
            r"\d{2}\.\d{2}\.\d{2}",  # 16.07.25
            r"\d{2}/\d{2}/\d{2,4}",    # 16/07/25 или 16/07/2025
            r"\d{6}"                     # 160725
        ]

        date_str = None
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                raw = match.group()
                if len(raw) == 6 and raw.isdigit():
                    # Преобразуем 160725 → 16.07.2025
                    date_str = f"{raw[0:2]}.{raw[2:4]}.20{raw[4:6]}"
                else:
                    date_str = raw
                break

        if not date_str:
            await message.answer("❌ Дата не найдена в тексте")
            return

        prod_date = datetime.datetime.strptime(date_str, "%d.%m.%Y").date()
        today = datetime.date.today()

        if prod_date == today:
            await message.answer(f"✅ Дата совпадает ({date_str})")
        elif prod_date < today:
            await message.answer(f"⚠️ Дата на банке ({date_str}) устарела. Сегодня: {today}")
        else:
            await message.answer(f"ℹ️ Дата на банке ({date_str}) ещё не наступила. Сегодня: {today}")

    except Exception as e:
        logger.error(f"Ошибка обработки фото: {e}")
        await message.answer("⚠️ Произошла ошибка при обработке фото")

# ---------------- Напоминание ----------------
async def remind_handler(request):
    if CHAT_ID:
        await bot.send_message(CHAT_ID, "⏰ Пора загрузить фото банки для проверки!")
        return web.Response(text="Reminder sent")
    else:
        return web.Response(text="CHAT_ID not set", status=400)

# ---------------- Запуск ----------------
async def on_startup(app: web.Application):
    await bot.set_webhook(WEBHOOK_URL)
    logger.info(f"✅ Webhook установлен: {WEBHOOK_URL}")

async def on_shutdown(app: web.Application):
    await bot.delete_webhook()
    await bot.session.close()
    logger.info("❌ Бот остановлен")

def main():
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/telegram/webhook")
    app.router.add_get("/remind_photo", remind_handler)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    return app

app = main()

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
