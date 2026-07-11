# Vantra AI — Telegram AI Chatbot

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white" alt="Python Version">
  <img src="https://img.shields.io/badge/python--telegram--bot-21.4-2CA5E0?logo=telegram&logoColor=white" alt="python-telegram-bot">
  <img src="https://img.shields.io/badge/database-Neon%20Postgres-00E599?logo=postgresql&logoColor=white" alt="Neon Postgres">
  <img src="https://img.shields.io/badge/AI-OpenRouter-8A2BE2" alt="OpenRouter">
  <img src="https://img.shields.io/badge/license-MIT-lightgrey" alt="License">
</p>

<p align="center">
  A multilingual, LLM-powered Telegram chatbot with clean HTML formatting,
  per-user daily limits, and a built-in premium code redemption system.
</p>

---

## ✨ Features

- 🤖 **AI-powered conversations** via [OpenRouter](https://openrouter.ai), compatible with any model available on the platform (GPT, Gemini, Claude, Llama, and more)
- 🧹 **Clean message formatting** — Markdown output from the LLM is automatically sanitized and converted to Telegram-native HTML (bold, italic, code blocks, links, lists) with no leftover `**` or `_` symbols
- 🌐 **Bilingual support** — Indonesian and English, switchable anytime with `/lang`
- 👥 **Group support** — invite the bot to any group and interact with it using `/vantra <question>`
- 🔐 **Daily usage limit** — configurable per-user message quota per day, backed by Postgres
- 💎 **Premium code system** — the bot owner can generate one-time redeemable codes (7 days / 1 month / 1 year) via `/createcode`; users redeem them with `/redeem`
- ☁️ **Serverless-friendly database** — built on [Neon](https://neon.tech) Postgres, fully async via `asyncpg`
- 🧩 **Modular architecture** — each feature lives in its own file under `modules/`, making it easy to extend

---

## 📁 Project Structure

```
vantra-ai/
├── main.py                # Entry point — wires up all modules and starts polling
├── requirements.txt        # Python dependencies
├── .env.example             # Environment variable template
├── .gitignore
└── modules/
    ├── __init__.py
    ├── start.py             # /start, /lang, welcome message, language selection
    ├── chatbot.py           # Core AI logic, Markdown→HTML sanitizer, daily limit
    └── premium.py           # /createcode, /redeem, premium code system
```

---

## 🛠️ Requirements

- Python **3.11** or newer
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- An [OpenRouter](https://openrouter.ai/keys) API key
- A [Neon](https://neon.tech) Postgres database (free tier is sufficient to start)

---

## 🚀 Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/your-username/vantra-ai.git
cd vantra-ai
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv venv
source venv/bin/activate      # Linux/macOS
venv\Scripts\activate         # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

> Running on Termux? See the [Termux notes](#-running-on-termux) below.

### 4. Configure environment variables

Copy the example file and fill in your own values:

```bash
cp .env.example .env
```

| Variable          | Description                                                              | Example                                              |
| ------------------ | ------------------------------------------------------------------------ | ----------------------------------------------------- |
| `BOT_TOKEN`        | Telegram bot token from BotFather                                        | `123456:ABC-DEF...`                                    |
| `BOT_USERNAME`     | Bot's username, without `@` (used for the "Add to Group" deep link)      | `VantraAIBot`                                          |
| `BOT_NAME`         | Display name shown in the welcome message                                | `Vantra AI`                                            |
| `OWNER_ID`         | Your numeric Telegram user ID — grants access to owner-only commands     | `123456789`                                            |
| `OWNER_USERNAME`   | Your Telegram username, without `@`                                      | `yourusername`                                         |
| `OPENROUTER_KEY`   | API key from OpenRouter                                                  | `sk-or-v1-xxxxxxxx`                                     |
| `CURRENT_MODEL`    | OpenRouter model identifier the bot will use                             | `openai/gpt-4o-mini`                                    |
| `SITE_URL`         | Your site URL, used for OpenRouter's optional ranking headers            | `https://example.com`                                   |
| `UPDATE_CHANNEL`   | Telegram channel link shown as a button in `/start`                      | `https://t.me/your_channel`                              |
| `POSTGRESQL_URI`   | Neon Postgres connection string                                          | `postgresql://user:pass@host/db?sslmode=require`         |
| `DAILY_LIMIT`      | Number of messages a non-premium user can send per day                   | `5`                                                     |

> Don't know your Telegram user ID? Message [@userinfobot](https://t.me/userinfobot) and it will reply with it.

### 5. Run the bot

```bash
python main.py
```

If everything is configured correctly, you should see:

```
INFO - Koneksi Neon Postgres berhasil, tabel 'users' siap dipakai.
INFO - Tabel 'redeem_codes' & kolom 'premium_until' siap dipakai.
INFO - Bot siap jalan.
INFO - Bot jalan, polling dimulai...
```

---

## 📱 Running on Termux

```bash
pkg update && pkg upgrade
pkg install python rust binutils clang libffi openssl
pip install -r requirements.txt
python main.py
```

---

## 🤖 Bot Commands

| Command       | Description                              | Access      |
| ------------- | ----------------------------------------- | ----------- |
| `/start`      | Show the welcome message and main menu    | Everyone    |
| `/lang`       | Change the bot's language                 | Everyone    |
| `/vantra`     | Ask the AI a question inside a group      | Everyone    |
| `/redeem`     | Redeem a premium code                     | Everyone    |
| `/createcode` | Generate a new premium redeem code        | Owner only  |

To register these with BotFather, send `/setcommands` and paste:

```
start - Mulai bot & lihat menu utama
lang - Ganti bahasa (Indonesia/English)
vantra - Tanya AI di dalam grup
redeem - Klaim kode premium
createcode - Buat kode premium (owner only)
```

---

## 🗄️ Database Schema

The bot automatically creates the required tables on startup. No manual migration needed.

**`users`**

| Column          | Type          | Description                                  |
| ---------------- | ------------- | ---------------------------------------------- |
| `user_id`        | `BIGINT`      | Telegram user ID (primary key)                 |
| `chat_count`      | `INT`         | Messages sent today                            |
| `last_reset`     | `DATE`        | Date the counter was last reset                |
| `premium_until`  | `TIMESTAMPTZ` | Premium expiry timestamp, if any               |

**`redeem_codes`**

| Column           | Type          | Description                          |
| ----------------- | ------------- | --------------------------------------- |
| `code`            | `TEXT`        | 8-character redeem code (primary key)   |
| `duration_days`    | `INT`         | Premium duration granted upon redemption |
| `created_by`      | `BIGINT`      | Owner ID who generated the code         |
| `created_at`      | `TIMESTAMPTZ` | Creation timestamp                      |
| `is_used`         | `BOOLEAN`     | Whether the code has been redeemed      |
| `used_by`         | `BIGINT`      | User ID who redeemed it                 |
| `used_at`         | `TIMESTAMPTZ` | Redemption timestamp                    |

---

## 🌐 Deployment

This bot uses long-polling, so it needs to run as a **long-lived process** rather than a serverless function. It has been tested with:

- [Wispbyte](https://wispbyte.com)
- Any VPS running Python 3.11+ (with `screen`, `tmux`, `pm2`, or `systemd` to keep it alive)
- Termux (for local testing/development)

---

## 🔒 Security Notes

- Never commit your `.env` file. It's already excluded via `.gitignore`.
- Rotate your `BOT_TOKEN` and `OPENROUTER_KEY` immediately if they are ever exposed publicly.
- `OWNER_ID` gates access to `/createcode` — double-check it matches your own numeric Telegram ID.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

## 🙌 Acknowledgements

- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- [OpenRouter](https://openrouter.ai)
- [Neon](https://neon.tech)
