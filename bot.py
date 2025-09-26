import os
import re
import logging
from datetime import datetime
import pytz
import tempfile
import cv2
import numpy as np
import pytesseract
from dateutil import parser as dateparser

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

from aiohttp import web  # для фиктивного HTTP-сервера

# ========= Конфиг =========
TELEGRAM_TOKEN = os.getenv("TG_BOT_TOKEN")
TZ = pytz.timezone("Europe/Berlin")
REQUEST_INTERVAL_HOURS = 2
# ==========================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(_name_)

registered_chats = set()
last_status = {}

DATE_REGEXES = [
    r'(?P<d>\b[0-3]?\d[.\-/][0-1]?\d[.\-/](?:20[0-9]{2}|19[0-9]{2}|\d{2})\b)',
    r'(?P<d>\b(?:20[0-9]{2}|19[0-9]{2})[.\-/][0-1]?\d[.\-/][0-3]?\d\b)',
    r'(?P<d>\b[0-3]?\d[ \-\/\.](?:янв|фев|мар|апр|май|июн|июл|авг|сен|oct|окт|ноя|дек|[A-Za-z]{3,9})[ \-\/\.][0-9]{2,4}\b)',
]

def preprocess_image_for_ocr(img_bytes: bytes) -> np.ndarray:
    arr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Не удалось прочитать изображение")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if min(gray.shape) < 500:
        gray = cv2.resize(gray, (gray.shape[1]*2, gray.shape[0]*2), interpolation=cv2.INTER_LINEAR)
    gray = cv2.medianBlur(gray, 3)
    th = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY, 31, 11)
    return th

def ocr_image_to_text(img_bytes: bytes) -> str:
    processed = preprocess_image_for_ocr(img_bytes)
    return pytesseract.image_to_string(processed, lang='rus+eng', config='--oem 3 --psm 6')

def extract_date_from_text(text: str):
    text = text.replace('\n', ' ').lower()
    for rx in DATE_REGEXES:
        m = re.search(rx, text, flags=re.IGNORECASE)
        if m:
            try:
                return dateparser.parse(m.group('d'), dayfirst=True, fuzzy=True).date()
            except Exception:
                continue
    return None

# === Telegram handlers ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    registered_chats.add(chat_id)
    last_status[chat_id] = {"last_checked": None, "last_result": None}
    await update.message.reply_text("✅ Бот активен. Я буду запрашивать фото каждые 2 часа.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    file = await update.message.photo[-1].get_file()
    with tempfile.NamedTemporaryFile(suffix=".jpg") as tmp:
        await file.download_to_drive(tmp.name)
        img_bytes = open(tmp.name, "rb").read()
    text = ocr_image_to_text(img_bytes)
    found_date = extract_date_from_text(text)
    now_date = datetime.now(TZ).date()
    if found_date == now_date:
        await update.message.reply_text(f"✅ Дата совпадает: {found_date}")
    else:
        await update.message.reply_text(f"❌ Дата не совпадает. Найдена: {found_date}, сегодня: {now_date}")

# === Scheduler ===
scheduler = AsyncIOScheduler(timezone=TZ)
async def start_scheduler(app):
    scheduler.remove_all_jobs()
    async def tick():
        for chat_id in list(registered_chats):
            await app.bot.send_message(chat_id, "⏰ Пожалуйста, пришлите фото даты.")
    scheduler.add_job(tick, trigger=IntervalTrigger(hours=REQUEST_INTERVAL_HOURS))
    scheduler.start()

# === HTTP-заглушка для Render ===
async def handle_root(request):
    return web.Response(text="OK")

async def run_web():
    app = web.Application()
    app.add_routes([web.get("/", handle_root)])
    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

# === Main ===
async def main():
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TG_BOT_TOKEN not set")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    await start_scheduler(app)

    # Запускаем и бота, и http-заглушку
    await run_web()
    await app.run_polling()

if _name_ == "_main_":
    import
