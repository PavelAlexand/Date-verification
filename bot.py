import os
import logging
import re
from datetime import datetime
from io import BytesIO

import pytz
import cv2
import numpy as np
import pytesseract
from dateutil import parser as dateparser

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from aiohttp import web  # HTTP stub for Render


# ========= Config =========
TELEGRAM_TOKEN = os.getenv("TG_BOT_TOKEN")
TZ = pytz.timezone("Europe/Berlin")
REQUEST_INTERVAL_HOURS = 2
# ==========================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Track subscribed chats
registered_chats: set[int] = set()

# Regex patterns to extract date text
DATE_REGEXES = [
    r'(?P<d>\b[0-3]?\d[.\-/][0-1]?\d[.\-/](?:20[0-9]{2}|19[0-9]{2}|\d{2})\b)',
    r'(?P<d>\b(?:20[0-9]{2}|19[0-9]{2})[.\-/][0-1]?\d[.\-/][0-3]?\d\b)',
    r'(?P<d>\b[0-3]?\d[ \-\/\.](?:янв|фев|мар|апр|май|июн|июл|авг|сен|oct|окт|ноя|дек|[A-Za-z]{3,9})[ \-\/\.][0-9]{2,4}\b)',
]


# ======= OCR helpers =======
def preprocess_image_for_ocr(img_bytes: bytes) -> np.ndarray:
    """Basic denoise + scale for OCR"""
    arr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Не удалось прочитать изображение (imdecode вернул None)")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    if min(h, w) < 500:
        gray = cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_LINEAR)
    gray = cv2.medianBlur(gray, 3)
    th = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY, 31, 11)
    return th


def ocr_image_to_text(img_bytes: bytes) -> str:
    processed = preprocess_image_for_ocr(img_bytes)
    text = pytesseract.image_to_string(processed, lang='rus+eng', config='--oem 3 --psm 6')
    return text


def extract_date_from_text(text: str):
    s = text.replace('\n', ' ').lower()
    for rx in DATE_REGEXES:
        m = re.search(rx, s, flags=re.IGNORECASE)
        if m:
            try:
                return dateparser.parse(m.group('d'), dayfirst=True, fuzzy=True).date()
            except Exception:
                continue
    # fallback
    return None


# ======= Telegram handlers =======
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in registered_chats:
        registered_chats.add(chat_id)
    # schedule (via JobQueue) per chat — every 2 hours
    # cancel previous with same name to avoid duplicates
    job_name = f"request_{chat_id}"
    for j in context.job_queue.get_jobs_by_name(job_name):
        j.schedule_removal()
    context.job_queue.run_repeating(
        send_request_job,
        interval=REQUEST_INTERVAL_HOURS * 3600,
        first=0,
        chat_id=chat_id,
        name=job_name,
    )
    await update.message.reply_text(
        "✅ Бот активен. Я буду запрашивать фото маркировки каждые 2 часа.\n"
        "Пришлите фото крупно и без бликов."
    )


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    registered_chats.discard(chat_id)
    # remove scheduled job
    job_name = f"request_{chat_id}"
    for j in context.job_queue.get_jobs_by_name(job_name):
        j.schedule_removal()
    await update.message.reply_text("🛑 Запросы отключены. Для повторного запуска — /start")


async def cmd_checknow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Пожалуйста, пришлите фото даты маркировки.")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.photo:
        return
    file = await update.message.photo[-1].get_file()
    buf = BytesIO()
    await file.download_to_memory(buf)
    img_bytes = buf.getvalue()

    try:
        text = ocr_image_to_text(img_bytes)
        found_date = extract_date_from_text(text)
    except Exception as e:
        logger.exception("OCR error: %s", e)
        await update.message.reply_text("Ошибка при обработке изображения. Сделайте фото чётче и повторите.")
        return

    today = datetime.now(TZ).date()
    if found_date == today:
        await update.message.reply_text(f"✅ Дата совпадает: {found_date.isoformat()}")
    elif found_date is None:
        await update.message.reply_text("⚠️ Не удалось распознать дату. Пришлите фото крупнее и без бликов.")
    else:
        await update.message.reply_text(
            f"❌ Дата НЕ совпадает. Найдено: {found_date}, сегодня: {today}"
        )


# ======= JobQueue callback =======
async def send_request_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    try:
        await context.bot.send_message(chat_id, "⏰ Пожалуйста, пришлите фото маркировки даты (банки).")
    except Exception as e:
        logger.warning("Failed to send scheduled message to %s: %s", chat_id, e)


# ======= HTTP stub for Render (keeps service 'live') =======
async def handle_root(request):
    return web.Response(text="OK")


def run_http_server():
    app = web.Application()
    app.add_routes([web.get("/", handle_root)])
    port = int(os.environ.get("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)


# ======= Entrypoint =======
if _name_ == "_main_":
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TG_BOT_TOKEN not set")

    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("stop", cmd_stop))
    application.add_handler(CommandHandler("checknow", cmd_checknow))
    application.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_photo))

    # run small HTTP server in parallel thread
    import threading
    threading.Thread(target=run_http_server, daemon=True).start()

    # IMPORTANT: synchronous run to avoid event loop conflicts on Render
    application.run_polling()
