from google import genai
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from PIL import Image
import requests
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

# 🧠 klient Gemini
client = genai.Client(api_key=GEMINI_API_KEY)

# 🧹 webhook cleaner
async def clear_webhook(app):
    await app.bot.delete_webhook(drop_pending_updates=True)

PROMPT = "ROLA: Jesteś profesjonalnym asystentem do segregacji odpadów w Polsce (system 5 frakcji)..."

# 📦 kompresja obrazu
def compress_image(image_bytes):
    img = Image.open(io.BytesIO(image_bytes))
    img.thumbnail((512, 512))

    if img.mode != "RGB":
        img = img.convert("RGB")

    output = io.BytesIO()
    img.save(output, format="JPEG", quality=70)
    return output.getvalue()

# 📊 LIMITY
REQUEST_LIMIT = 20
request_count = 0

last_request = {}
user_points = {}

# 📸 obsługa zdjęcia
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global request_count, last_request, user_points

    user_id = update.message.from_user.id
    now = time.time()

    # 🚦 RATE LIMIT
    if user_id in last_request and now - last_request[user_id] < 1:
        await update.message.reply_text("Za szybko 📸 poczekaj chwilę")
        return

    last_request[user_id] = now

    # 🧠 INIT POINTS
    if user_id not in user_points:
        user_points[user_id] = 0

    # 📊 DAILY LIMIT
    if request_count >= REQUEST_LIMIT:
        await update.message.reply_text("Dzisiejszy limit zapytań osiągnięty 🚫")
        return

    request_count += 1

    try:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)

        img_bytes = await file.download_as_bytearray()
        compressed = compress_image(img_bytes)

        # 🧠 GEMINI
        response = client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=[
                PROMPT,
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": compressed
                    }
                }
            ]
        )

        text = response.text or "Brak odpowiedzi"

        # 🏆 PUNKTY (najpierw licz, potem wyświetl razem)
        gained_points = 0

        if "PSZOK" in text:
            gained_points = 10
        elif any(x in text for x in ["ŻÓŁTY", "NIEBIESKI", "ZIELONY", "BRĄZOWY", "CZARNY"]):
            gained_points = 5

        user_points[user_id] += gained_points

        # 💬 JEDNA WIADOMOŚĆ (lepsze UX)
        final_message = f"{text}\n\n🏆 Punkty za to zdjęcie: +{gained_points}\nSuma: {user_points[user_id]}"

        MAX_LENGTH = 4000
        for i in range(0, len(final_message), MAX_LENGTH):
            await update.message.reply_text(final_message[i:i+MAX_LENGTH])

    except Exception as e:
        error_msg = str(e)

        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
            await update.message.reply_text("Limit API osiągnięty ⏳")
        else:
            await update.message.reply_text(f"Błąd: {error_msg[:1000]}")

# 💬 fallback
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Wyślij zdjęcie odpadu 📸")

# ▶️ start bota (TYLKO RAZ!)
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

app.post_init = clear_webhook

app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(MessageHandler(filters.TEXT, handle_text))

print("Bot działa... wyślij zdjęcie na Telegramie 📸")

app.run_polling()
