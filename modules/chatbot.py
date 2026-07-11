import os
import re
import json
import logging
from datetime import date

import asyncpg
import httpx

from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters

from modules.start import get_user_lang

logger = logging.getLogger(__name__)

# ============ SEMUA KREDENSIAL & KONFIG DARI .ENV ============
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY")
CURRENT_MODEL = os.getenv("CURRENT_MODEL", "openai/gpt-4o-mini")
POSTGRESQL_URI = os.getenv("POSTGRESQL_URI")
OWNER_ID = os.getenv("OWNER_ID")
SITE_URL = os.getenv("SITE_URL", "https://example.com")
BOT_NAME = os.getenv("BOT_NAME", "Vantra AI")
DAILY_LIMIT = int(os.getenv("DAILY_LIMIT", "5"))
# ================================================================

_db_pool: asyncpg.Pool | None = None


# ============ DATABASE (Neon Postgres) ============

async def init_db() -> None:
    """Panggil sekali saat bot start (lihat main.py) buat siapin connection pool + tabel."""
    global _db_pool

    if not POSTGRESQL_URI:
        logger.warning("POSTGRESQL_URI belum di-set, fitur limit harian nonaktif (fail-open).")
        return

    _db_pool = await asyncpg.create_pool(dsn=POSTGRESQL_URI, ssl="require")
    async with _db_pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                chat_count INT NOT NULL DEFAULT 0,
                last_reset DATE NOT NULL DEFAULT CURRENT_DATE
            );
            """
        )
    logger.info("Koneksi Neon Postgres berhasil, tabel 'users' siap dipakai.")


async def close_db() -> None:
    """Panggil saat bot shutdown biar koneksi ditutup rapi."""
    if _db_pool is not None:
        await _db_pool.close()


def get_pool() -> asyncpg.Pool | None:
    """Expose connection pool biar bisa dipakai bareng oleh modul lain (mis. premium.py)."""
    return _db_pool


async def check_and_increment_limit(user_id: int) -> tuple[bool, int]:
    """
    Cek & tambah jumlah chat user hari ini.
    Return (boleh_lanjut: bool, sisa_limit: int).

    - Owner (OWNER_ID) tidak kena limit.
    - Kalau DB belum terkonfigurasi, selalu izinkan (fail-open) supaya bot
      tetap jalan meski POSTGRESQL_URI belum diisi saat development.
    """
    if OWNER_ID and str(user_id) == str(OWNER_ID):
        return True, DAILY_LIMIT

    if _db_pool is None:
        return True, DAILY_LIMIT

    today = date.today()

    async with _db_pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT chat_count, last_reset FROM users WHERE user_id = $1 FOR UPDATE",
                user_id,
            )

            if row is None:
                await conn.execute(
                    "INSERT INTO users (user_id, chat_count, last_reset) VALUES ($1, 1, $2)",
                    user_id,
                    today,
                )
                return True, DAILY_LIMIT - 1

            chat_count = row["chat_count"]
            last_reset = row["last_reset"]

            # Reset otomatis kalau udah ganti hari
            if last_reset != today:
                chat_count = 0

            if chat_count >= DAILY_LIMIT:
                await conn.execute(
                    "UPDATE users SET last_reset = $2 WHERE user_id = $1",
                    user_id,
                    today,
                )
                return False, 0

            chat_count += 1
            await conn.execute(
                "UPDATE users SET chat_count = $2, last_reset = $3 WHERE user_id = $1",
                user_id,
                chat_count,
                today,
            )
            return True, DAILY_LIMIT - chat_count


# ============ OPENROUTER ============

async def call_openrouter(prompt: str) -> str:
    """Kirim prompt ke OpenRouter secara async, return teks balasan (masih format Markdown)."""
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_KEY}",
                    "HTTP-Referer": SITE_URL,
                    "X-Title": BOT_NAME,
                    "Content-Type": "application/json",
                },
                content=json.dumps(
                    {
                        "model": CURRENT_MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                    }
                ),
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

    except httpx.HTTPError as e:
        logger.error(f"OpenRouter request error: {e}")
        return "__ERROR_CONNECTION__"
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        logger.error(f"OpenRouter response parsing error: {e}")
        return "__ERROR_PARSING__"


# ============ SANITIZE MARKDOWN -> TELEGRAM HTML ============

def markdown_to_telegram_html(text: str) -> str:
    """
    Convert Markdown standar (yang biasa dipakai LLM) ke HTML yang didukung
    Telegram, supaya **, _, #, ``` gak nongol mentah di chat.
    """
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    code_blocks = []

    def stash_code_block(match):
        code_blocks.append(match.group(1).strip("\n"))
        return f"\x00CODEBLOCK{len(code_blocks) - 1}\x00"

    text = re.sub(r"```(?:\w+\n)?(.*?)```", stash_code_block, text, flags=re.DOTALL)
    text = re.sub(r"`([^`\n]+?)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", r"<i>\1</i>", text)
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"^#{1,6}\s*(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*]\s+", "• ", text, flags=re.MULTILINE)

    for i, code in enumerate(code_blocks):
        text = text.replace(f"\x00CODEBLOCK{i}\x00", f"<pre>{code}</pre>")

    return text.strip()


# ============ TEKS DUA BAHASA (error & limit) ============

REPLY_TEXTS = {
    "id": {
        "connection_error": "Maaf, terjadi kendala saat menghubungi AI. Silakan coba lagi sebentar lagi.",
        "parsing_error": "Maaf, respons dari AI tidak dapat diproses. Silakan coba lagi.",
        "limit_reached": (
            "⛔ Anda telah mencapai batas <b>{limit} pesan</b> untuk hari ini.\n"
            "Silakan coba kembali besok."
        ),
        "empty_question_group": "Silakan tulis pertanyaan setelah perintah, contoh:\n/vantra apa itu kecerdasan buatan?",
    },
    "en": {
        "connection_error": "Sorry, there was an issue reaching the AI. Please try again shortly.",
        "parsing_error": "Sorry, the AI's response could not be processed. Please try again.",
        "limit_reached": (
            "⛔ You have reached the <b>{limit} message</b> limit for today.\n"
            "Please try again tomorrow."
        ),
        "empty_question_group": "Please write a question after the command, e.g.:\n/vantra what is artificial intelligence?",
    },
}


def rt(user_id: int, key: str) -> str:
    lang = get_user_lang(user_id)
    return REPLY_TEXTS.get(lang, REPLY_TEXTS["id"])[key]


# ============ CORE: PROSES PERTANYAAN & KIRIM JAWABAN ============

async def process_question(update: Update, user_id: int, question: str) -> None:
    """Logic inti: cek limit -> call AI -> sanitize -> kirim balasan."""
    allowed, _remaining = await check_and_increment_limit(user_id)

    if not allowed:
        await update.effective_message.reply_text(
            rt(user_id, "limit_reached").format(limit=DAILY_LIMIT),
            parse_mode=ParseMode.HTML,
        )
        return

    await update.effective_chat.send_action(action=ChatAction.TYPING)

    ai_reply_markdown = await call_openrouter(question)

    if ai_reply_markdown == "__ERROR_CONNECTION__":
        await update.effective_message.reply_text(rt(user_id, "connection_error"))
        return
    if ai_reply_markdown == "__ERROR_PARSING__":
        await update.effective_message.reply_text(rt(user_id, "parsing_error"))
        return

    ai_reply_html = markdown_to_telegram_html(ai_reply_markdown)

    try:
        await update.effective_message.reply_text(
            ai_reply_html,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception as e:
        # fallback: kalau HTML-nya somehow invalid, kirim plain text aja
        logger.error(f"Gagal kirim dengan parse_mode HTML: {e}")
        plain_text = re.sub(r"<[^>]+>", "", ai_reply_html)
        await update.effective_message.reply_text(plain_text)


# ============ HANDLERS ============

async def handle_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Chat pribadi: semua teks (bukan command) langsung dianggap pertanyaan."""
    user = update.effective_user
    question = update.effective_message.text
    await process_question(update, user.id, question)


async def vantra_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Di grup: bot cuma merespons kalau dipanggil lewat /vantra <pertanyaan>."""
    user = update.effective_user
    question = " ".join(context.args).strip() if context.args else ""

    if not question:
        await update.effective_message.reply_text(
            rt(user.id, "empty_question_group")
        )
        return

    await process_question(update, user.id, question)


def register_handlers(app) -> None:
    """
    Panggil ini dari main.py buat daftarin semua handler di modul chatbot.py:

        from modules.chatbot import register_handlers
        register_handlers(app)
    """
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
            handle_private_message,
        )
    )
    app.add_handler(
        CommandHandler("vantra", vantra_command, filters=filters.ChatType.GROUPS)
    )
