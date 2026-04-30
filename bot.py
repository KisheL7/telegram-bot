from google import genai
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes
from PIL import Image
import io
import os

# 🔑 ENV
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# 🧠 kosze
BINS = {
    "ŻÓŁTY": "🟡🗑️ Kosz ŻÓŁTY",
    "NIEBIESKI": "🔵🗑️ Kosz NIEBIESKI",
    "ZIELONY": "🟢🗑️ Kosz ZIELONY",
    "BRĄZOWY": "🟤🗑️ Kosz BRĄZOWY",
    "CZARNY": "⚫🗑️ Kosz CZARNY",
    "PSZOK": "🏷️🗑️ PSZOK"
}

PROMPT = """
Zwróć:
KOLOR | OPIS

Kolory:
ŻÓŁTY, NIEBIESKI, ZIELONY, BRĄZOWY, CZARNY, PSZOK

Jeśli niepewny → CZARNY
"""

# 📦 compress
def compress(img_bytes):
    img = Image.open(io.BytesIO(img_bytes))
    img.thumbnail((384, 384))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=60)
    return buf.getvalue()

# 🎨 keyboard (instrukcja zamiast pętli)
def photo_help_keyboard():
    return ReplyKeyboardMarkup(
        [["📸 Jak zrobić zdjęcie?"]],
        resize_keyboard=True
    )

# 🔁 inline restart (KLUCZ UX)
def restart_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("♻️ Sortuj dalej", callback_data="restart")]
    ])

# ▶️ START SCREEN
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "♻️ Sortly\n\nZrób zdjęcie odpadu.",
        reply_markup=photo_help_keyboard()
    )

# 📸 PHOTO
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Analizuję...")

    file = await context.bot.get_file(update.message.photo[-1].file_id)
    img = compress(await file.download_as_bytearray())

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents={
            "parts": [
                {"text": PROMPT},
                {"inline_data": {"mime_type": "image/jpeg", "data": img}}
            ]
        }
    )

    raw = response.text or ""

    try:
        color, desc = raw.split("|")
        color = color.strip()
        desc = desc.strip()
    except:
        color, desc = "CZARNY", raw

    final = (
        "✅ Gotowe\n\n"
        f"{BINS.get(color, '⚫🗑️ Kosz CZARNY')}\n"
        f"({desc})\n\n"
        "🌱 Dziękujemy za segregację"
    )

    await msg.edit_text(final, reply_markup=restart_keyboard())

# 🔁 callback restart (NOWY FLOW)
async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    await q.message.reply_text(
        "♻️ Sortly\n\nZrób zdjęcie odpadu.",
        reply_markup=photo_help_keyboard()
    )

# 💬 TEXT UX (bez pętli!)
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()

    if "jak zrobić" in text:
        await update.message.reply_text(
            "📸 Kliknij 📎 (agrafkę) → wybierz zdjęcie → wyślij",
            reply_markup=photo_help_keyboard()
        )
    else:
        await update.message.reply_text("📸 Kliknij przycisk poniżej")

# 🚀 APP
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(MessageHandler(filters.TEXT, handle_text))
app.add_handler(CallbackQueryHandler(restart, pattern="restart"))

async def on_startup(app):
    print("Bot działa 🚀")

app.post_init = on_startup
app.run_polling()
