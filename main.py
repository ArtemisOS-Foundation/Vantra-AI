import os
import logging

from dotenv import load_dotenv
from telegram.ext import Application

from modules.start import register_handlers as register_start_handlers
from modules.chatbot import (
    register_handlers as register_chatbot_handlers,
    init_db,
    close_db,
)
from modules.premium import (
    register_handlers as register_premium_handlers,
    init_premium_db,
)

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")


async def post_init(app: Application) -> None:
    """Dijalankan sekali setelah bot nyambung ke Telegram, sebelum mulai polling."""
    await init_db()
    await init_premium_db()
    logger.info("Bot siap jalan.")


async def post_shutdown(app: Application) -> None:
    """Dijalankan pas bot dimatikan, biar koneksi DB ditutup rapi."""
    await close_db()


def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN belum di-set di .env")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    register_start_handlers(app)
    register_premium_handlers(app)
    register_chatbot_handlers(app)  # daftar paling akhir: dia yang nangkep teks bebas

    logger.info("Bot jalan, polling dimulai...")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
