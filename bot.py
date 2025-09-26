import os
import logging
import re
from datetime import datetime
import pytz
import cv2
import numpy as np
import pytesseract
from dateutil import parser as dateparser

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

from aiohttp import web  # HTTP-заглушка для Render

# ========= Конфиг =========
TELEGRAM_TOKEN = os.getenv("TG_BOT_TOKEN")
TZ = pytz.timezone("Europe/Berlin")
REQUEST_INTERVAL_HOURS = 2
# ==========================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(_name_)

registered_chats = set()

DATE_REGEXES = [
    r'(?P<d>\b[0-3]?\d[.\-/][0-1]?\d[.\-/](?:20[0-9]{2}|19[0-9]{2}|\d{2})\b)',
    r'(?P<d>\b(?:20[0-9]{2}|19[0-9]{2})[.\-/][0-1]?\d[.\-/][0-3]?\d\b)',
    r'(?P<d>\b[0-3]?\d[ \-\/\.](?:янв|фев|мар|апр|май|июн|июл|авг|сен|oct|окт|ноя|дек|[A-Za-z]{3,9})[ \-\/\.][0-9]{2,4}\b)',
]

def preprocess_image_for_ocr(img_bytes: bytes):
    arr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if min(gray.shape) < 500:
        gray = cv2.resize(gray, (gray.shape[1]*2, gray.shape[0]*2))
    return cv2.medianBlur(gray, 3)

def ocr_image_to_text(img_bytes: bytes) -> str:
    processed = preprocess_image_for_ocr(img_bytes)
    return pytesseract.image_to_string(processed, lang='rus+eng', config='--oem 3 --psm 6')

def extract_date_from_text(text: str):
    text = text.replace("\n", " ").lower()
    for rx in DATE_REGEXES:
        m = re.search(rx, text)
        if m:
            try:
                return dateparser.parse(m.group("d"), dayfirst=True, fuzzy=True).date()
            except Exception:
                continue
    return None

# === Telegram handlers ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    registered_chats.add(update.effective_chat.id)
    await update.message.reply_text("✅ Бот активен. Я буду запрашивать фото каждые 2 часа.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.photo[-1].get_file()
    img_bytes = await file.download_as_bytearray()
    text = ocr_image_to_text(bytes(img_bytes))
    found_date = extract_date_from_text(text)
    today = datetime.now(TZ).date()
    if found_date == today:
        await update.message.reply_text(f"✅ Дата совпадает: {found_date}")
    else:
        await update.message.reply_text(f"❌ Дата не совпадает. Найдена: {found_date}, сегодня: {today}")

# === Планировщик ===
scheduler = BackgroundScheduler(timezone=TZ)
def tick(bot):
    for chat_id in registered_chats:
        bot.send_message(chat_id, "⏰ Пожалуйста, пришлите фото даты.")

# === HTTP-заглушка для Render ===
async def handle_root(request):
    return web.Response(text="OK")

def run_http_server():
    app = web.Application()
    app.add_routes([web.get("/", handle_root)])
    port = int(os.environ.get("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)

# === Main ===
if _name_ == "__main__":
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TG_BOT_TOKEN not set")

    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # планировщик (каждые 2 часа запрос фото)
    scheduler.add_job(lambda: tick(application.bot),
                     trigger=IntervalTrigger(hours=REQUEST_INTERVAL_HOURS))
    scheduler.start()

    # Запускаем HTTP-заглушку параллельно
    import threading
    threading.Thread(target=run_http_server, daemon=True).start()

    # Синхронный запуск — без asyncio.run()
    application.run_polling()
