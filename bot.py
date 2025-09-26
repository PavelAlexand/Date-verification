import io
import re
import base64
import httpx
import os
from datetime import datetime
import pytz

from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage

BOT_TOKEN = os.getenv("BOT_TOKEN")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "secret")
BASE_URL = os.getenv("BASE_URL")
TZ = os.getenv("TZ", "Europe/Moscow")

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot, storage=MemoryStorage())
app = FastAPI()

YANDEX_URL = "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze"
DATE_REGEX = r"(\d{2}[.\-/]\d{2}[.\-/]\d{2,4})|(\d{6})"

async def yandex_ocr(img_bytes: bytes) -> str:
    img_b64 = base64.b64encode(img_bytes).decode()
    payload = {
        "analyze_specs": [{
            "content": img_b64,
            "features": [{"type": "TEXT_DETECTION"}]
        }]
    }
    headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}"}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(YANDEX_URL, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
    texts = []
    try:
        for p in data["results"][0]["results"][0]["textDetection"]["pages"]:
            for b in p["blocks"]:
                for l in b["lines"]:
                    texts.append(" ".join([w["text"] for w in l["words"]]))
    except Exception:
        return ""
    return " ".join(texts)

def parse_date(text: str):
    match = re.search(DATE_REGEX, text)
    if not match:
        return None
    raw = match.group(0)
    try:
        if len(raw) == 6:  # YYMMDD
            return datetime.strptime(raw, "%y%m%d")
        elif len(raw.split(".")) == 3:
            return datetime.strptime(raw, "%d.%m.%y")
    except Exception:
        try:
            return datetime.strptime(raw, "%d.%m.%Y")
        except Exception:
            return None

def compare_with_today(dt: datetime):
    now = datetime.now(pytz.timezone(TZ)).date()
    diff = (dt.date() - now).days
    if diff < 0:
        return f"📅 {dt.date()} — срок <b>истёк</b> {abs(diff)} дн. назад."
    elif diff == 0:
        return f"📅 {dt.date()} — <b>сегодня</b>."
    else:
        return f"📅 {dt.date()} — осталось <b>{diff}</b> дн."

@dp.message_handler(commands=["start"])
async def start_cmd(msg: types.Message):
    await msg.answer("Привет 👋 Отправь фото банки, я распознаю дату и сравню с текущей.")

@dp.message_handler(content_types=["photo"])
async def photo_handler(msg: types.Message):
    photo = msg.photo[-1]
    bio = io.BytesIO()
    await photo.download(destination=bio)
    text = await yandex_ocr(bio.getvalue())
    if not text:
        await msg.answer("❌ Не удалось распознать текст.")
        return
    dt = parse_date(text)
    if not dt:
        await msg.answer(f"Текст: <code>{text}</code>\nДата не найдена.")
        return
    await msg.answer(compare_with_today(dt))

@app.on_event("startup")
async def on_startup():
    if BASE_URL:
        await bot.set_webhook(f"{BASE_URL}/telegram/{WEBHOOK_SECRET}")

@app.post("/telegram/{secret}")
async def telegram_webhook(secret: str, request: Request):
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")
    update = types.Update(**await request.json())
    await dp.process_update(update)
    return {"ok": True}

@app.get("/health")
async def health():
    return {"status": "ok"}
