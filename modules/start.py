import os
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

# ============ SEMUA KREDENSIAL & KONFIG DARI .ENV ============
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY")
BOT_NAME = os.getenv("BOT_NAME", "Vantra AI")
OWNER_ID = os.getenv("OWNER_ID")
OWNER_USERNAME = os.getenv("OWNER_USERNAME")
UPDATE_CHANNEL = os.getenv("UPDATE_CHANNEL", "https://t.me/your_channel")
CURRENT_MODEL = os.getenv("CURRENT_MODEL", "openai/gpt-4o-mini")
BOT_USERNAME = os.getenv("BOT_USERNAME", "VantraAIBot")  # buat link tambah ke grup
# ================================================================

# ------------------------------------------------------------------
# Penyimpanan preferensi bahasa user.
# SEMENTARA pakai dict in-memory dulu (reset kalau bot restart).
# TODO: ganti ke Neon (Postgres) begitu koneksi DB siap:
#   - kolom `lang` di tabel users, default 'id'
#   - get_user_lang(user_id) -> query DB
#   - set_user_lang(user_id, lang) -> update DB
# ------------------------------------------------------------------
user_lang: dict[int, str] = {}

DEFAULT_LANG = "id"


def get_user_lang(user_id: int) -> str:
    return user_lang.get(user_id, DEFAULT_LANG)


def set_user_lang(user_id: int, lang: str) -> None:
    user_lang[user_id] = lang


# ============ TEKS DUA BAHASA ============
TEXTS = {
    "id": {
        "welcome": (
            "Hai <b>{first_name}</b>, Saya Adalah <b>{bot_name}</b>, "
            "Sebuah Bot Chat LLM Berbasis Kecerdasan Buatan Yang Ditenagai "
            "Oleh <b>{model}</b>. Saya Bisa:\n\n"
            "• Membantu Menjawab Pertanyaan\n"
            "• Menemukan Ide\n"
            "• Tanya Jawab Sederhana\n"
            "• Dan Lain Lain\n\n"
            "Pantau Perkembangan Saya Di Channel Dibawah Ini Atau Tambahkan "
            "Saya Ke Grup Untuk Menggunakan Saya Di Grup."
        ),
        "btn_add_group": "➕ Tambahkan ke Grup",
        "btn_update_channel": "📢 Saluran Pembaruan",
        "btn_lang": "🌐 Bahasa",
        "lang_prompt": "Silakan pilih bahasa yang ingin Anda gunakan:",
        "lang_set": "✅ Bahasa telah diubah ke <b>Bahasa Indonesia</b>.",
    },
    "en": {
        "welcome": (
            "Hi <b>{first_name}</b>, I Am <b>{bot_name}</b>, "
            "An AI-Powered LLM Chat Bot Powered By <b>{model}</b>. "
            "I Can:\n\n"
            "• Help Answer Questions\n"
            "• Find Ideas\n"
            "• Simple Q&A\n"
            "• And Much More\n\n"
            "Follow My Updates On The Channel Below Or Add Me "
            "To A Group To Use Me There."
        ),
        "btn_add_group": "➕ Add to Group",
        "btn_update_channel": "📢 Update Channel",
        "btn_lang": "🌐 Language",
        "lang_prompt": "Please choose the language you want to use:",
        "lang_set": "✅ Language switched to <b>English</b>.",
    },
}


def t(user_id: int, key: str) -> str:
    """Ambil teks sesuai bahasa pilihan user."""
    lang = get_user_lang(user_id)
    return TEXTS.get(lang, TEXTS[DEFAULT_LANG])[key]


def main_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Keyboard yang muncul di pesan /start: add to group, channel, ganti bahasa."""
    add_group_url = f"https://t.me/{BOT_USERNAME}?startgroup=true"

    buttons = [
        [InlineKeyboardButton(t(user_id, "btn_add_group"), url=add_group_url)],
        [InlineKeyboardButton(t(user_id, "btn_update_channel"), url=UPDATE_CHANNEL)],
        [InlineKeyboardButton(t(user_id, "btn_lang"), callback_data="open_lang_menu")],
    ]
    return InlineKeyboardMarkup(buttons)


def lang_selection_keyboard() -> InlineKeyboardMarkup:
    """Keyboard buat command /lang: pilih Indonesia atau English."""
    buttons = [
        [
            InlineKeyboardButton("🇮🇩 Indonesia", callback_data="set_lang_id"),
            InlineKeyboardButton("🇬🇧 English", callback_data="set_lang_en"),
        ]
    ]
    return InlineKeyboardMarkup(buttons)


# ============ HANDLERS ============

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler buat /start — kirim sambutan + tombol menu utama."""
    user = update.effective_user
    text = t(user.id, "welcome").format(
        first_name=user.first_name,
        bot_name=BOT_NAME,
        model=CURRENT_MODEL,
    )

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_keyboard(user.id),
        disable_web_page_preview=True,
    )


async def lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler buat /lang — tampilkan pilihan bahasa."""
    user = update.effective_user
    await update.message.reply_text(
        t(user.id, "lang_prompt"),
        reply_markup=lang_selection_keyboard(),
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler buat semua tombol inline (callback_query) di modul ini."""
    query = update.callback_query
    user = query.from_user
    await query.answer()

    data = query.data

    if data == "open_lang_menu":
        await query.edit_message_text(
            t(user.id, "lang_prompt"),
            reply_markup=lang_selection_keyboard(),
        )
        return

    if data == "set_lang_id":
        set_user_lang(user.id, "id")
        await query.edit_message_text(
            t(user.id, "lang_set"),
            parse_mode=ParseMode.HTML,
        )
        return

    if data == "set_lang_en":
        set_user_lang(user.id, "en")
        await query.edit_message_text(
            t(user.id, "lang_set"),
            parse_mode=ParseMode.HTML,
        )
        return


def register_handlers(app) -> None:
    """
    Panggil ini dari main.py buat daftarin semua handler di modul start.py:

        from modules.start import register_handlers
        register_handlers(app)
    """
    from telegram.ext import CommandHandler, CallbackQueryHandler

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("lang", lang_command))
    app.add_handler(
        CallbackQueryHandler(
            button_callback,
            pattern="^(open_lang_menu|set_lang_id|set_lang_en)$",
        )
    )
