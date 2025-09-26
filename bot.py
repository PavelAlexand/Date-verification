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

from aiohttp import web  # HTTP-заглушка для Render

# ========= Конфиг =========
TELEGRAM_TOKEN = os.getenv("TG_BOT_TOKEN")
TZ = pytz.timezone("Europe/Berlin")
REQUEST_INTERVAL_HOURS = 2
# ==========================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

registered_chats: set[int] = set()

DATE_REGEXES = [
    r'(?P<d>\b[0-3]?\d[.\-/][0-1]?\d[.\-/](?:20[0-9]{2}|19[0-9]{2}|\d{2})\b)',
    r'(?P<d>\b(?:20[0-9]{2}|19[0-9]{2})[.\-/][0-1]?\d[.\-/][0-3]?\d\b)',
    r'(?P<d>\b[0-3]?\d[ \-\/\.](?:янв|фев|мар|апр|май|июн|июл|авг|сен|oct|окт|ноя|дек|[A-Za-z]{3,9})[ \-\/\.][0-9]{2,4}\b)',
]

# ======= OCR (улучшенный) =======
def ocr_image_to_text(img_bytes: bytes) -> str:
    arr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Усиление контраста
    gray = cv2.equalizeHist(gray)

    # Инверсия (для светлой лазерной печати)
    gray = cv2.bitwise_not(gray)

    # Бинаризация (Otsu)
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # OCR только для цифр, точек и дефисов
    custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789./-'
    text = pytesseract.image_to_string(th, config=custom_config)

    return text

def extract_date_from_text(text: str):
    s = text.replace("\n", " ").lower()
    for rx in DATE_REGEXES:
        m = re.search(rx, s, flags=re.IGNORECASE)
        if m:
            try:
                return dateparser.parse(m.group("d"), dayfirst=True, fuzzy=True).date()
            except Exception:
                continue
    return None

# ======= Telegram handlers =======
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    registered_chats.add(update.effective_chat.id)
    await update.message.reply_text(
        "✅ Бот активен. Пришлите фото даты на банке — я сравню с сегодняшним числом."
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.photo:
        return
    file = await update.message.photo[-1].get_file()
    buf = BytesIO()
    await file.download_to_memory(buf)
    img_bytes = buf.getvalue()

    try:
        text = ocr_image_to_text(img_bytes)
        logger.info("OCR result: %s", text)  # логируем распознанный текст
        found_date =
        extract_date_from_text(text)
    except Exception as e:
        logger.exception("OCR error: %s", e)
        await update.message.reply_text("⚠️ Ошибка при распознавании. Попробуйте другое фото.")
        return

    today = datetime.now(TZ).date()

if not found_dates:
    await update.message.reply_text("⚠️ Не удалось распознать дату. Сделайте фото крупнее и без бликов.")
else:
    dates_str = ", ".join([d.isoformat() for d in found_dates])
    if today in found_dates:
        await update.message.reply_text(f"✅ Найдены даты: {dates_str}\nСегодня: {today} (совпадает)")
    else:
        await update.message.reply_text(f"❌ Найдены даты: {dates_str}\nСегодня: {today} (совпадений нет)")
        
# ======= HTTP-заглушка для Render =======
async def handle_root(request):
    return web.Response(text="OK")

def run_http_server():
    app = web.Application()
    app.add_routes([web.get("/", handle_root)])
    port = int(os.environ.get("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)

# ======= Entrypoint =======
if __name__ == "__main__":
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TG_BOT_TOKEN not set")

    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_photo))

    import threading
    threading.Thread(target=run_http_server, daemon=True).start()

    application.run_polling()
