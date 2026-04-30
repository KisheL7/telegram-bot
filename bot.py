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

# 🧠 Gemini
client = genai.Client(api_key=GEMINI_API_KEY)

# ⚡ PROMPT (lekki + stabilny)
PROMPT = """
Rozpoznaj odpad i wskaż właściwy kosz (Polska).

Frakcje:
ŻÓŁTY, NIEBIESKI, ZIELONY, BRĄZOWY, CZARNY, PSZOK

Zasady:
- człowiek/zwierzę → "To jest istota żywa..."
- niewyraźne → "Zdjęcie jest niewyraźne..."
- mieszanka → poproś o jeden typ odpadu

Format:
Rozpoznano: ...
🟡🗑️ Śmietnik: ...
🌱 Dziękujemy za segregację

Max 5 linii.
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

# 📦 kompresja
def compress_image(image_bytes):
    img = Image.open(io.BytesIO(image_bytes))
    img.thumbnail((384, 384))
    if img.mode != "RGB":
        img = img.convert("RGB")
    output = io.BytesIO()
    img.save(output, format="JPEG", quality=60)
    return output.getvalue()

# 📊 stan
REQUEST_LIMIT = 20
request_count = 0

last_request = {}
user_points = {}

# 🎨 UI helpery
def main_keyboard():
    return ReplyKeyboardMarkup(
        [["📸 Zrób zdjęcie"]],
        resize_keyboard=True
    )

def welcome_text():
    return (
        "♻️ *Sortly*\n\n"
        "Zrób zdjęcie odpadu,\n"
        "a pokażę Ci gdzie go wyrzucić.\n\n"
        "👇 Zacznij poniżej"
    )

def processing_text():
    return (
        "🔍 *Analizuję zdjęcie...*\n"
        "_To zajmie chwilę_"
    )

def format_result(text, points, total):
    return (
        f"✅ *Gotowe*\n\n"
        f"{text}\n\n"
        f"🏆 +{points} pkt\n"
        f"📊 Razem: {total}"
    )

# ▶️ START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        welcome_text(),
        reply_markup=main_keyboard(),
        parse_mode="Markdown"
    )

# 📸 FOTO
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global request_count, last_request, user_points

    user_id = update.message.from_user.id
    now = time.time()

    if user_id in last_request and now - last_request[user_id] < 1:
        await update.message.reply_text("⏳ Spokojnie... sekunda 😄")
        return

    last_request[user_id] = now

    if user_id not in user_points:
        user_points[user_id] = 0

    if request_count >= REQUEST_LIMIT:
        await update.message.reply_text("🚫 Limit osiągnięty. Spróbuj później")
        return

    request_count += 1

    msg = await update.message.reply_text(
        processing_text(),
        parse_mode="Markdown"
    )

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

        text = response.text or "Brak odpowiedzi"

        gained = 0
        if "PSZOK" in text:
            gained = 10
        elif any(x in text for x in ["ŻÓŁTY", "NIEBIESKI", "ZIELONY", "BRĄZOWY", "CZARNY"]):
            gained = 5

        user_points[user_id] += gained

        await msg.edit_text(
            format_result(text, gained, user_points[user_id]),
            parse_mode="Markdown"
        )

    except Exception as e:
        await msg.edit_text(
            "⚠️ Coś poszło nie tak\nSpróbuj jeszcze raz",
            parse_mode="Markdown"
        )

# 💬 TEKST
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()

    if "zdjęcie" in text:
        await update.message.reply_text("📸 Super — wyślij zdjęcie odpadu")
    else:
        await start(update, context)

# 🚀 APP
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

app.post_init = lambda app: app.bot.delete_webhook(drop_pending_updates=True)

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(MessageHandler(filters.TEXT, handle_text))

print("Bot działa 🚀")

app.run_polling()
