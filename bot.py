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

# Подписанные чаты
registered_chats: set[int] = set()

# Регулярки для поиска даты
DATE_REGEXES = [
    r'(?P<d>\b[0-3]?\d[.\-/][0-1]?\d[.\-/](?:20[0-9]{2}|19[0-9]{2}|\d{2})\b)',
    r'(?P<d>\b(?:20[0-9]{2}|19[0-9]{2})[.\-/][0-1]?\d[.\-/][0-3]?\d\b)',
    r'(?P<d>\b[0-3]?\d[ \-\/\.](?:янв|фев|мар|апр|май|июн|июл|авг|сен|oct|окт|ноя|дек|[A-Za-z]{3,9})[ \-\/\.][0-9]{2,4}\b)',
]

# ======= OCR helpers =======
def preprocess_image_for_ocr(img_bytes: bytes) -> np.ndarray:
    arr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Не удалось прочитать изображение")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    if min(h, w) < 500:
        gray = cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_LINEAR)
    return cv2.medianBlur(gray, 3)

def ocr_image_to_text(img_bytes: bytes) -> str:
    processed = preprocess_image_for_ocr(img_bytes)
    return pytesseract.image_to_string(
        processed, lang="rus+eng", config="--oem 3 --psm 6"
    )

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
        "✅ Бот активен. Я буду запрашивать фото каждые 2 часа."
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
        found_date = extract_date_from_text(text)
    except Exception:
        await update.message.reply_text("⚠️ Ошибка при распознавании. Пришлите фото чётче.")
        return

    today = datetime.now(TZ).date()
    if found_date == today:
        await update.message.reply_text(f"✅ Дата совпадает: {found_date.isoformat()}")
    elif found_date is None:
        await update.message.reply_text("⚠️ Не удалось распознать дату. Сделайте фото крупнее.")
    else:
        await update.message.reply_text(
            f"❌ Дата НЕ совпадает. Найдено: {found_date}, сегодня: {today}"
        )

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

    # Поднимаем HTTP-заглушку в отдельном потоке
    import threading
    threading.Thread(target=run_http_server, daemon=True).start()

    # Запускаем бота
    application.run_polling()
