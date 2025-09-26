import os
import re
import logging
from datetime import datetime, timezone
import pytz
import tempfile
from io import BytesIO

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

import cv2
import numpy as np
import pytesseract
from dateutil import parser as dateparser

TELEGRAM_TOKEN = os.getenv("TG_BOT_TOKEN")
TZ = pytz.timezone("Europe/Berlin")
REQUEST_INTERVAL_HOURS = 2

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    h, w = gray.shape
    if min(h, w) < 500:
        gray = cv2.resize(gray, (int(w*2), int(h*2)), interpolation=cv2.INTER_LINEAR)
    gray = cv2.medianBlur(gray, 3)
    th = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY, 31, 11)
    kernel = np.ones((1, 1), np.uint8)
    processed = cv2.dilate(th, kernel, iterations=1)
    return processed

def ocr_image_to_text(img_bytes: bytes) -> str:
    processed = preprocess_image_for_ocr(img_bytes)
    custom_oem_psm = r'--oem 3 --psm 6'
    text = pytesseract.image_to_string(processed, lang='rus+eng', config=custom_oem_psm)
    return text

def extract_date_from_text(text: str):
    text = text.replace('\n', ' ').lower()
    for rx in DATE_REGEXES:
        m = re.search(rx, text, flags=re.IGNORECASE)
        if m:
            date_str = m.group('d')
            try:
                dt = dateparser.parse(date_str, dayfirst=True, fuzzy=True)
                if dt:
                    return dt.date()
            except Exception:
                continue
    tokens = re.findall(r'\d{1,4}[.\-/]\d{1,2}[.\-/]\d{1,4}', text)
    for t in tokens:
        try:
            dt = dateparser.parse(t, dayfirst=True, fuzzy=True)
            if dt:
                return dt.date()
        except Exception:
            pass
    try:
        dt = dateparser.parse(text, dayfirst=True, fuzzy=True)
        if dt:
            return dt.date()
    except Exception:
        pass
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    registered_chats.add(chat_id)
    last_status[chat_id] = {"last_checked": None, "last_result": None}
    await update.message.reply_text(
        "Бот зарегистрировал этот чат. Я буду присылать запрос фото каждые 2 часа.\n"
        "Команды: /stop, /checknow, /status"
    )

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in registered_chats:
        registered_chats.remove(chat_id)
        last_status.pop(chat_id, None)
        await update.message.reply_text("Вы отписаны от запросов.")
    else:
        await update.message.reply_text("Вы не были подписаны.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    st = last_status.get(chat_id)
    if not st:
        await update.message.reply_text("Нет данных — вы не зарегистрированы.")
    else:
        await update.message.reply_text(f"Последняя проверка: {st.get('last_checked')}\nРезультат: {st.get('last_result')}")

async def checknow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in registered_chats:
        await update.message.reply_text("Вы не зарегистрированы. Отправьте /start.")
        return
    await context.bot.send_message(chat_id=chat_id, text="Пришлите фото маркировки даты.")

async def request_photo_job(bot: Bot, chat_id: int):
    try:
        if chat_id in registered_chats:
            await bot.send_message(chat_id=chat_id, text="⏰ Пожалуйста, пришлите фото маркировки даты (банки).")
    except Exception as e:
        logger.exception("Failed to send scheduled request: %s", e)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat_id = update.effective_chat.id
    if chat_id not in registered_chats:
        await message.reply_text("Вы не зарегистрированы. Отправьте /start.")
        return
    photo = message.photo
    if not photo:
        await message.reply_text("Пришлите фото.")
        return
    file = await photo[-1].get_file()
    with tempfile.NamedTemporaryFile(suffix=".jpg") as tmp:
        await file.download_to_drive(tmp.name)
        with open(tmp.name, "rb") as f:
            img_bytes = f.read()
    try:
        text = ocr_image_to_text(img_bytes)
        found_date = extract_date_from_text(text)
    except Exception as e:
        await message.reply_text("Ошибка обработки изображения.")
        last_status[chat_id] = {"last_checked": datetime.now(TZ).isoformat(), "last_result": "OCR error"}
        return
    now_date = datetime.now(TZ).date()
    last_status[chat_id] = {"last_checked": datetime.now(TZ).isoformat(), "last_result": None}
    if found_date is None:
        await message.reply_text("Не удалось распознать дату. Попробуйте другое фото.")
        last_status[chat_id]["last_result"] = "Дата не распознана"
        return
    if found_date == now_date:
        await message.reply_text(f"✅ Дата совпадает: {found_date.isoformat()}")
        last_status[chat_id]["last_result"] = f"OK ({found_date.isoformat()})"
    else:
        await message.reply_text(f"❌ Дата НЕ совпадает. Найдена: {found_date.isoformat()}, сегодня: {now_date.isoformat()}")
        last_status[chat_id]["last_result"] = f"Mismatch ({found_date.isoformat()})"

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Неизвестная команда. Используйте /start /stop /checknow /status.")

scheduler = AsyncIOScheduler(timezone=TZ)
async def start_scheduler(app):
    scheduler.remove_all_jobs()
    async def tick():
        for chat_id in list(registered_chats):
            await request_photo_job(app.bot, chat_id)
    scheduler.add_job(tick, trigger=IntervalTrigger(hours=REQUEST_INTERVAL_HOURS))
    scheduler.start()

async def main():
    if not TELEGRAM_TOKEN:
        raise RuntimeError("Set TG_BOT_TOKEN environment variable")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("checknow", checknow))
    app.add_handler(MessageHandler(filters.PHOTO & (~filters.COMMAND), handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), unknown))
    await start_scheduler(app)
    await app.run_polling()

if _name_ == "_main_":
    import asyncio

    try:
        asyncio.run(main())
    except RuntimeError as e:
        # если цикл уже запущен (как на Render) — используем существующий
        loop = asyncio.get_event_loop()
        loop.create_task(main())
        loop.run_forever()
