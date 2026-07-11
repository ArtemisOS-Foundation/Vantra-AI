import os
import logging
import secrets
import string
from datetime import datetime, timedelta, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from modules.chatbot import get_pool
from modules.start import get_user_lang

logger = logging.getLogger(__name__)

# ============ KREDENSIAL & KONFIG DARI .ENV ============
OWNER_ID = os.getenv("OWNER_ID")
# ==========================================================

CODE_LENGTH = 8
CODE_ALPHABET = string.ascii_uppercase + string.digits

# Pilihan durasi yang muncul di tombol /createcode -> (label_id, label_en, jumlah_hari)
DURATION_OPTIONS = [
    ("7 Hari", "7 Days", 7),
    ("1 Bulan", "1 Month", 30),
    ("1 Tahun", "1 Year", 365),
]


# ============ DATABASE ============

async def init_premium_db() -> None:
    """
    Panggil setelah chatbot.init_db() di main.py, supaya connection pool sudah ada.
    Bikin tabel redeem_codes + pastikan kolom premium_until ada di tabel users.
    """
    pool = get_pool()
    if pool is None:
        logger.warning("DB belum terkonfigurasi, fitur premium/redeem code nonaktif.")
        return

    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS redeem_codes (
                code TEXT PRIMARY KEY,
                duration_days INT NOT NULL,
                created_by BIGINT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                is_used BOOLEAN NOT NULL DEFAULT FALSE,
                used_by BIGINT,
                used_at TIMESTAMPTZ
            );
            """
        )
        # Jaga-jaga kalau tabel users belum ada / belum punya kolom premium_until
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                chat_count INT NOT NULL DEFAULT 0,
                last_reset DATE NOT NULL DEFAULT CURRENT_DATE
            );
            """
        )
        await conn.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS premium_until TIMESTAMPTZ;"
        )
    logger.info("Tabel 'redeem_codes' & kolom 'premium_until' siap dipakai.")


def _generate_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


async def _create_unique_code(pool, duration_days: int, owner_id: int) -> str:
    """Generate kode acak 8 karakter, retry kalau ternyata udah ada (sangat jarang)."""
    async with pool.acquire() as conn:
        for _ in range(5):
            code = _generate_code()
            exists = await conn.fetchval(
                "SELECT 1 FROM redeem_codes WHERE code = $1", code
            )
            if not exists:
                await conn.execute(
                    """
                    INSERT INTO redeem_codes (code, duration_days, created_by)
                    VALUES ($1, $2, $3)
                    """,
                    code,
                    duration_days,
                    owner_id,
                )
                return code
    raise RuntimeError("Gagal generate kode unik setelah beberapa percobaan.")


async def redeem_code(user_id: int, code: str) -> tuple[bool, str, datetime | None]:
    """
    Coba redeem kode.
    Return (berhasil: bool, alasan_gagal: str, premium_until: datetime | None)
    alasan_gagal salah satu dari: "", "not_found", "already_used", "no_db"
    """
    pool = get_pool()
    if pool is None:
        return False, "no_db", None

    code = code.strip().upper()

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT duration_days, is_used FROM redeem_codes WHERE code = $1 FOR UPDATE",
                code,
            )

            if row is None:
                return False, "not_found", None

            if row["is_used"]:
                return False, "already_used", None

            duration_days = row["duration_days"]
            now = datetime.now(timezone.utc)

            # Kalau user masih punya sisa premium aktif, tambahin dari situ.
            # Kalau enggak, mulai dari sekarang.
            user_row = await conn.fetchrow(
                "SELECT premium_until FROM users WHERE user_id = $1", user_id
            )
            current_until = user_row["premium_until"] if user_row else None
            base_time = current_until if (current_until and current_until > now) else now
            new_until = base_time + timedelta(days=duration_days)

            await conn.execute(
                """
                INSERT INTO users (user_id, premium_until)
                VALUES ($1, $2)
                ON CONFLICT (user_id) DO UPDATE SET premium_until = $2
                """,
                user_id,
                new_until,
            )
            await conn.execute(
                """
                UPDATE redeem_codes
                SET is_used = TRUE, used_by = $2, used_at = $3
                WHERE code = $1
                """,
                code,
                user_id,
                now,
            )

            return True, "", new_until


async def is_premium(user_id: int) -> bool:
    """Cek apakah user masih punya premium aktif. Dipakai nanti buat bypass limit di chatbot.py."""
    pool = get_pool()
    if pool is None:
        return False

    async with pool.acquire() as conn:
        until = await conn.fetchval(
            "SELECT premium_until FROM users WHERE user_id = $1", user_id
        )

    if until is None:
        return False
    return until > datetime.now(timezone.utc)


# ============ TEKS DUA BAHASA ============

TEXTS = {
    "id": {
        "not_owner": "⛔ Perintah ini hanya bisa digunakan oleh pemilik bot.",
        "choose_duration": "Pilih masa berlaku kode premium yang ingin dibuat:",
        "code_created": (
            "✅ Kode berhasil dibuat!\n\n"
            "Kode: <code>{code}</code>\n"
            "Masa berlaku: <b>{duration_label}</b>\n\n"
            "Berikan kode ini kepada pembeli. Kode hanya bisa digunakan satu kali."
        ),
        "redeem_usage": "Gunakan format:\n<code>/redeem KODE_ANDA</code>",
        "redeem_success": (
            "🎉 Kode berhasil digunakan!\n\n"
            "Status premium Anda aktif hingga: <b>{expiry}</b>"
        ),
        "redeem_not_found": "❌ Kode tidak ditemukan atau tidak valid.",
        "redeem_used": "❌ Kode ini sudah pernah digunakan.",
        "redeem_no_db": "⚠️ Sistem premium sedang tidak tersedia. Coba lagi nanti.",
    },
    "en": {
        "not_owner": "⛔ This command can only be used by the bot owner.",
        "choose_duration": "Choose the validity period for the premium code:",
        "code_created": (
            "✅ Code successfully created!\n\n"
            "Code: <code>{code}</code>\n"
            "Validity: <b>{duration_label}</b>\n\n"
            "Give this code to the buyer. The code can only be used once."
        ),
        "redeem_usage": "Use this format:\n<code>/redeem YOUR_CODE</code>",
        "redeem_success": (
            "🎉 Code redeemed successfully!\n\n"
            "Your premium status is active until: <b>{expiry}</b>"
        ),
        "redeem_not_found": "❌ Code not found or invalid.",
        "redeem_used": "❌ This code has already been used.",
        "redeem_no_db": "⚠️ The premium system is currently unavailable. Please try again later.",
    },
}


def t(user_id: int, key: str) -> str:
    lang = get_user_lang(user_id)
    return TEXTS.get(lang, TEXTS["id"])[key]


def duration_keyboard(user_id: int) -> InlineKeyboardMarkup:
    lang = get_user_lang(user_id)
    buttons = []
    for label_id, label_en, days in DURATION_OPTIONS:
        label = label_id if lang == "id" else label_en
        buttons.append(
            [InlineKeyboardButton(label, callback_data=f"createcode_{days}")]
        )
    return InlineKeyboardMarkup(buttons)


def _format_duration_label(user_id: int, days: int) -> str:
    lang = get_user_lang(user_id)
    for label_id, label_en, d in DURATION_OPTIONS:
        if d == days:
            return label_id if lang == "id" else label_en
    return f"{days} hari" if lang == "id" else f"{days} days"


# ============ HANDLERS ============

async def createcode_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/createcode - hanya owner, munculin pilihan durasi via tombol."""
    user = update.effective_user

    if not OWNER_ID or str(user.id) != str(OWNER_ID):
        await update.effective_message.reply_text(t(user.id, "not_owner"))
        return

    await update.effective_message.reply_text(
        t(user.id, "choose_duration"),
        reply_markup=duration_keyboard(user.id),
    )


async def createcode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler tombol pilihan durasi di /createcode."""
    query = update.callback_query
    user = query.from_user
    await query.answer()

    if not OWNER_ID or str(user.id) != str(OWNER_ID):
        await query.edit_message_text(t(user.id, "not_owner"))
        return

    days = int(query.data.split("_")[1])
    pool = get_pool()

    if pool is None:
        await query.edit_message_text(t(user.id, "redeem_no_db"))
        return

    code = await _create_unique_code(pool, days, user.id)
    duration_label = _format_duration_label(user.id, days)

    await query.edit_message_text(
        t(user.id, "code_created").format(code=code, duration_label=duration_label),
        parse_mode=ParseMode.HTML,
    )


async def redeem_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/redeem KODE - siapa aja bisa pakai buat klaim premium."""
    user = update.effective_user

    if not context.args:
        await update.effective_message.reply_text(
            t(user.id, "redeem_usage"), parse_mode=ParseMode.HTML
        )
        return

    code = context.args[0]
    success, reason, premium_until = await redeem_code(user.id, code)

    if success:
        expiry_str = premium_until.strftime("%d %B %Y, %H:%M UTC")
        await update.effective_message.reply_text(
            t(user.id, "redeem_success").format(expiry=expiry_str),
            parse_mode=ParseMode.HTML,
        )
        return

    if reason == "not_found":
        await update.effective_message.reply_text(t(user.id, "redeem_not_found"))
    elif reason == "already_used":
        await update.effective_message.reply_text(t(user.id, "redeem_used"))
    else:
        await update.effective_message.reply_text(t(user.id, "redeem_no_db"))


def register_handlers(app) -> None:
    """
    Panggil ini dari main.py:

        from modules.premium import register_handlers
        register_handlers(app)
    """
    app.add_handler(CommandHandler("createcode", createcode_command))
    app.add_handler(CommandHandler("redeem", redeem_command))
    app.add_handler(
        CallbackQueryHandler(createcode_callback, pattern=r"^createcode_\d+$")
    )
