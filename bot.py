import os
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://date-verification.onrender.com/telegram/webhook")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(_name_)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()


@dp.message(F.text)
async def echo_handler(message: Message):
    await message.answer(f"Ты написал: {message.text}")


async def on_startup(app: web.Application):
    await bot.set_webhook(WEBHOOK_URL)
    logger.info(f"✅ Webhook установлен: {WEBHOOK_URL}")


async def on_shutdown(app: web.Application):
    await bot.delete_webhook()
    await bot.session.close()
    logger.info("❌ Бот остановлен")


def main():
    app = web.Application()
    # регистрируем хэндлер aiogram
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/telegram/webhook")
    # вешаем события
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    return app


if _name_ == "_main_":
    web.run_app(main(), host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
