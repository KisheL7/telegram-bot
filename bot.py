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
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

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

# 🎨 keyboard (Twoje UX)
def photo_help_keyboard():
    return ReplyKeyboardMarkup(
        [["🙀 Jak zrobić zdjęcie?"]],
        resize_keyboard=True
    )

def restart_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("♻️ Sortujemy dalej?", callback_data="restart")]
    ])

# 🧠 typing / thinking UX
async def thinking(update: Update, context: ContextTypes.DEFAULT_TYPE, stage=""):
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )

    if stage == "scan":
        await asyncio.sleep(0.6)
    elif stage == "analyze":
        await asyncio.sleep(0.9)
    else:
        await asyncio.sleep(0.5)

# ▶️ START SCREEN
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "♻️ Sortly\n\nZrób zdjęcie odpadu.",
        reply_markup=photo_help_keyboard()
    )

# 📸 PHOTO HANDLER
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Analizuję...")

    await thinking(update, context, "scan")
    await msg.edit_text("🧠 Rozpoznaję materiał...")

    await thinking(update, context, "analyze")
    await msg.edit_text("♻️ Dobieram odpowiedni kosz...")

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

# 🔁 restart flow
async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    await q.message.reply_text(
        "♻️ Sortly\n\nZrób zdjęcie odpadu.",
        reply_markup=photo_help_keyboard()
    )

# 💬 TEXT UX
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()

    if "jak zrobić" in text:
        await update.message.reply_text(
            "😺 Kliknij 📎 agrafkę i wyślij zdjęcie odpadu",
            reply_markup=photo_help_keyboard()
        )
    else:
        await update.message.reply_text("📸 Kliknij przycisk poniżej")

# 🚀 HEALTH CHECK (Render)
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health():
    server = HTTPServer(("0.0.0.0", 10000), Handler)
    server.serve_forever()

threading.Thread(target=run_health, daemon=True).start()

# 🚀 START LOG
async def on_startup(app):
    print("Bot działa 🚀")

# 🚀 APP
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(MessageHandler(filters.TEXT, handle_text))
app.add_handler(CallbackQueryHandler(restart, pattern="restart"))

app.post_init = on_startup

app.run_polling()
