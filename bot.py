from google import genai
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
from PIL import Image
import io
import os
import time

# 🔑 ENV
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)

# 🧠 MAPA KOSZY (UI)
BINS = {
    "ŻÓŁTY": "🟡🗑️ Kosz ŻÓŁTY",
    "NIEBIESKI": "🔵🗑️ Kosz NIEBIESKI",
    "ZIELONY": "🟢🗑️ Kosz ZIELONY",
    "BRĄZOWY": "🟤🗑️ Kosz BRĄZOWY",
    "CZARNY": "⚫🗑️ Kosz CZARNY",
    "PSZOK": "🏷️🗑️ PSZOK"
}

FORCE_PSZOK = ["kapcie", "tekstyl", "bateria", "elektron", "flosser"]

# ⏱️ sesje (symulacja „uśpienia”)
SESSION_TIMEOUT = 900  # 15 min
last_activity = {}

# ⚡ PROMPT (AI tylko klasyfikuje)
PROMPT = """
Zwróć:
KOSZ: [ŻÓŁTY/NIEBIESKI/ZIELONY/BRĄZOWY/CZARNY/PSZOK]
OPIS: krótko co to jest

Zasady:
- niepewne = CZARNY
- tekstylia/elektronika = PSZOK
"""

# 📦 image compress
def compress_image(image_bytes):
    img = Image.open(io.BytesIO(image_bytes))
    img.thumbnail((384, 384))
    if img.mode != "RGB":
        img = img.convert("RGB")
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=60)
    return out.getvalue()

# 🎨 UI
def keyboard():
    return ReplyKeyboardMarkup(
        [["📸 Zrób zdjęcie"]],
        resize_keyboard=True
    )

# 🟢 START SCREEN (premium UX)
def start_screen():
    return (
        "♻️ *Sortly*\n\n"
        "Zrób zdjęcie odpadu,\n"
        "a powiem Ci gdzie go wyrzucić.\n\n"
        "👇 Kliknij przycisk poniżej"
    )

# 🔁 reset sesji
def reset_if_needed(user_id):
    now = time.time()
    if user_id in last_activity:
        if now - last_activity[user_id] > SESSION_TIMEOUT:
            return True
    return False

# ▶️ START / RESET UX
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    last_activity[user_id] = time.time()

    await update.message.reply_text(
        start_screen(),
        reply_markup=keyboard(),
        parse_mode="Markdown"
    )

# 🧠 parse AI → final UI
def parse_ai(raw: str):
    raw_lower = raw.lower()

    if any(x in raw_lower for x in FORCE_PSZOK):
        return "PSZOK", raw

    for k in BINS.keys():
        if k in raw:
            return k, raw

    return "CZARNY", raw

# 📸 PHOTO HANDLER
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    last_activity[user_id] = time.time()

    msg = await update.message.reply_text("🔍 Analizuję zdjęcie...")

    try:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)

        img_bytes = await file.download_as_bytearray()
        compressed = compress_image(img_bytes)

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

        kosz, opis = parse_ai(response.text or "")

        # 🧠 clean UX (bez FRACJA, bez śmieci)
        result = (
            "✅ Gotowe\n\n"
            f"{BINS[kosz]}\n"
            f"{opis}\n\n"
            "🌱 Dziękujemy za segregację"
        )

        await msg.edit_text(result)

    except Exception:
        await msg.edit_text("⚠️ Nie udało się rozpoznać odpadu")

# 💬 TEXT → działa jak start (UX fix)
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

# 🚀 APP
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

app.post_init = lambda app: app.bot.delete_webhook(drop_pending_updates=True)

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(MessageHandler(filters.TEXT, handle_text))

print("Bot działa 🚀")
app.run_polling()
