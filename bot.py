from google import genai
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from PIL import Image
import io
import os
import time

# 🔑 ENV (Render)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("Brak TELEGRAM_TOKEN w ENV")

if not GEMINI_API_KEY:
    raise ValueError("Brak GEMINI_API_KEY w ENV")

# 🧠 Gemini client
client = genai.Client(api_key=GEMINI_API_KEY)

# 📝 PROMPT (Twój system – skrócony dla wydajności)
PROMPT = """
Rozpoznaj odpad na zdjęciu i przypisz do kosza w Polsce.

Odpowiedz:
Rozpoznano: ...
Śmietnik: ...
"""

# 📦 kompresja obrazu
def compress_image(image_bytes):
    img = Image.open(io.BytesIO(image_bytes))
    img.thumbnail((512, 512))
    if img.mode != "RGB":
        img = img.convert("RGB")
    output = io.BytesIO()
    img.save(output, format="JPEG", quality=70)
    return output.getvalue()

# 📊 system limitów
REQUEST_LIMIT = 20
request_count = 0

last_request = {}
user_points = {}

# 📸 handler zdjęć
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global request_count, last_request, user_points

    user_id = update.message.from_user.id
    now = time.time()

    # 🚦 anti-spam (1s per user)
    if user_id in last_request and now - last_request[user_id] < 1:
        await update.message.reply_text("Za szybko 📸 poczekaj chwilę")
        return

    last_request[user_id] = now

    # 🧠 init punktów
    if user_id not in user_points:
        user_points[user_id] = 0

    # 📊 limit dzienny
    if request_count >= REQUEST_LIMIT:
        await update.message.reply_text("Dzisiejszy limit zapytań osiągnięty 🚫")
        return

    request_count += 1

    try:
        # 📸 pobranie zdjęcia
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)

        img_bytes = await file.download_as_bytearray()
        compressed = compress_image(img_bytes)

        image = Image.open(io.BytesIO(compressed))

        # 🧠 Gemini request
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[PROMPT, image]
        )

        text = response.text or "Brak odpowiedzi"

        # 🏆 punkty
        gained_points = 0

        if "PSZOK" in text:
            gained_points = 10
        elif any(x in text for x in ["ŻÓŁTY", "NIEBIESKI", "ZIELONY", "BRĄZOWY", "CZARNY"]):
            gained_points = 5

        user_points[user_id] += gained_points

        # 💬 odpowiedź
        final_message = (
            f"{text}\n\n"
            f"🏆 Punkty za zdjęcie: +{gained_points}\n"
            f"📊 Suma: {user_points[user_id]}"
        )

        MAX_LENGTH = 4000
        for i in range(0, len(final_message), MAX_LENGTH):
            await update.message.reply_text(final_message[i:i+MAX_LENGTH])

    except Exception as e:
        error_msg = str(e)

        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
            await update.message.reply_text("Limit API osiągnięty ⏳ Spróbuj za chwilę")
        else:
            await update.message.reply_text(f"Błąd: {error_msg[:1000]}")

# 💬 tekst fallback
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Wyślij zdjęcie odpadu 📸")

# 🚀 START APP (Render-safe)
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

# 🔥 usuwa webhook (naprawia conflict)
app.post_init = lambda app: app.bot.delete_webhook(drop_pending_updates=True)

app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(MessageHandler(filters.TEXT, handle_text))

print("Bot działa... wyślij zdjęcie 📸")

app.run_polling()
