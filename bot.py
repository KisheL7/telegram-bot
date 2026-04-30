from google import genai
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)
from PIL import Image
import io
import os
import time

# 🔑 ENV
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)

# 🧠 MAPA KOSZY
BINS = {
    "ŻÓŁTY": "🟡🗑️ Kosz ŻÓŁTY",
    "NIEBIESKI": "🔵🗑️ Kosz NIEBIESKI",
    "ZIELONY": "🟢🗑️ Kosz ZIELONY",
    "BRĄZOWY": "🟤🗑️ Kosz BRĄZOWY",
    "CZARNY": "⚫🗑️ Kosz CZARNY",
    "PSZOK": "🏷️🗑️ PSZOK"
}

FORCE_PSZOK = ["kapcie", "tekstyl", "bateria", "elektron", "flosser"]

# ⚡ PROMPT (lekki = szybki)
PROMPT = """
Zwróć tylko:
KOLOR | OPIS

Kolory:
ŻÓŁTY, NIEBIESKI, ZIELONY, BRĄZOWY, CZARNY, PSZOK

Jeśli niepewny → CZARNY
"""

# 📦 kompresja
def compress(img_bytes):
    img = Image.open(io.BytesIO(img_bytes))
    img.thumbnail((384, 384))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=60)
    return buf.getvalue()

# 🎨 keyboard
def main_keyboard():
    return ReplyKeyboardMarkup(
        [["📸 Zrób zdjęcie"]],
        resize_keyboard=True
    )

# ▶️ START (opcjonalny, UX only)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "♻️ Sortly\n\nZrób zdjęcie odpadu.",
        reply_markup=main_keyboard()
    )

# 🧠 parser
def parse(raw: str):
    raw_low = raw.lower()

    if any(x in raw_low for x in FORCE_PSZOK):
        return "PSZOK", raw

    try:
        color, desc = raw.split("|")
        return color.strip(), desc.strip()
    except:
        return "CZARNY", raw

# 📸 PHOTO
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Analizuję...")

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)

    img_bytes = await file.download_as_bytearray()
    compressed = compress(img_bytes)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents={
            "parts": [
                {"text": PROMPT},
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": compressed
                    }
                }
            ]
        }
    )

    raw = response.text or ""

    color, desc = parse(raw)
    emoji_text = BINS.get(color, "⚫🗑️ Kosz CZARNY")

    final = (
        "✅ Gotowe\n\n"
        f"{emoji_text}\n"
        f"({desc})\n\n"
        "🌱 Dziękujemy za segregację"
    )

    await msg.edit_text(final)

    # 🔁 follow-up UX
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("♻️ Sortuj dalej", callback_data="restart")]
    ])

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Sortujemy dalej?",
        reply_markup=keyboard
    )

# 🔁 RESTART FLOW
async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.message.reply_text(
        "♻️ Sortly\n\nZrób zdjęcie odpadu.",
        reply_markup=main_keyboard()
    )

# 💬 TEXT fallback (UX clean)
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Kliknij przycisk i wyślij zdjęcie")

# 🚀 APP
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

app.post_init = lambda app: app.bot.delete_webhook(drop_pending_updates=True)

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(MessageHandler(filters.TEXT, handle_text))
app.add_handler(CallbackQueryHandler(restart, pattern="restart"))

print("Bot działa 🚀")
app.run_polling()
