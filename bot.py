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

if not TELEGRAM_TOKEN:
    raise ValueError("Brak TELEGRAM_TOKEN w ENV")

if not GEMINI_API_KEY:
    raise ValueError("Brak GEMINI_API_KEY w ENV")

# 🧠 AI client
client = genai.Client(api_key=GEMINI_API_KEY)

# 🎯 MAPA UI (KOD decyduje o kolorze, nie AI)
EMOJI_MAP = {
    "ŻÓŁTY": "🟡🗑️",
    "NIEBIESKI": "🔵🗑️",
    "ZIELONY": "🟢🗑️",
    "BRĄZOWY": "🟤🗑️",
    "CZARNY": "⚫🗑️",
    "PSZOK": "🏷️🗑️"
}

# 🚨 twarde reguły override (deterministyczne bezpieczeństwo)
FORCE_PSZOK = ["kapcie", "tekstyl", "bateria", "elektron", "flosser", "lek", "igła"]

# ⚡ PROMPT (AI tylko sugeruje, NIE decyduje UI)
PROMPT = """
Jesteś klasyfikatorem odpadów.

Zwracasz TYLKO:

FRACJA: jedna z [ŻÓŁTY, NIEBIESKI, ZIELONY, BRĄZOWY, CZARNY, PSZOK]
UZASADNIENIE: jedna linia

Zasady:
- niepewne = CZARNY
- tekstylia i elektronika = PSZOK
- nie zgadujesz poza listą
"""

# 🔥 warmup
def warmup():
    try:
        client.models.generate_content(
            model="gemini-2.5-flash",
            contents="test"
        )
    except:
        pass

warmup()

# 📦 image compress
def compress_image(image_bytes):
    img = Image.open(io.BytesIO(image_bytes))
    img.thumbnail((384, 384))
    if img.mode != "RGB":
        img = img.convert("RGB")
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=60)
    return out.getvalue()

# 📊 state
REQUEST_LIMIT = 20
request_count = 0

last_request = {}
user_points = {}

# 🎨 UI
def keyboard():
    return ReplyKeyboardMarkup(
        [["📸 Zrób zdjęcie"]],
        resize_keyboard=True
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "♻️ *Sortly*\n\nZrób zdjęcie odpadu, a powiem gdzie go wyrzucić.",
        reply_markup=keyboard(),
        parse_mode="Markdown"
    )

# 🧠 parsing AI → deterministic override
def parse_result(raw: str):
    raw_lower = raw.lower()

    # FORCE PSZOK override
    if any(x in raw_lower for x in FORCE_PSZOK):
        return "PSZOK", raw

    # extract frakcja
    for key in EMOJI_MAP.keys():
        if key in raw:
            return key, raw

    return "CZARNY", raw

# 📸 handler
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global request_count, last_request, user_points

    user_id = update.message.from_user.id
    now = time.time()

    if user_id in last_request and now - last_request[user_id] < 1:
        await update.message.reply_text("⏳ chwila...")
        return

    last_request[user_id] = now

    if user_id not in user_points:
        user_points[user_id] = 0

    if request_count >= REQUEST_LIMIT:
        await update.message.reply_text("🚫 limit osiągnięty")
        return

    request_count += 1

    msg = await update.message.reply_text("🔍 Analizuję...")

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

        raw = response.text or ""

        frakcja, raw_text = parse_result(raw)
        emoji = EMOJI_MAP[frakcja]

        gained = 10 if frakcja == "PSZOK" else 5

        user_points[user_id] += gained

        final = (
            f"{emoji} FRACJA: {frakcja}\n\n"
            f"{raw_text}\n\n"
            f"🏆 +{gained} pkt | 📊 {user_points[user_id]}"
        )

        await msg.edit_text(final)

    except Exception:
        await msg.edit_text("⚠️ błąd analizy")

# 💬 fallback (usuwa potrzebę /start UX-wise)
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
