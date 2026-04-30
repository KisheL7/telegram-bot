from google import genai
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
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

# ⚡ KRÓTSZY PROMPT (szybszy)
PROMPT = """
Jesteś asystentem segregacji odpadów w Polsce (5 frakcji).

Rozpoznaj odpad i podaj właściwy kosz.

Jeśli:
- człowiek/zwierzę → "To jest istota żywa..."
- niewyraźne → "Zdjęcie jest niewyraźne..."
- mieszanka → poproś o jeden typ odpadu

Frakcje:
ŻÓŁTY, NIEBIESKI, ZIELONY, BRĄZOWY, CZARNY, PSZOK

Dodaj emoji kosza:
🟡🗑️ 🔵🗑️ 🟢🗑️ 🟤🗑️ ⚫🗑️ 🏷️🗑️

Format:
Rozpoznano: ...
🟡🗑️ Śmietnik: ...
🌱 Dziękujemy za segregację

Max 5 linii.
"""

# 🔥 WARMUP (przy starcie – zmniejsza cold start API)
def warmup():
    try:
        client.models.generate_content(
            model="gemini-2.0-flash",
            contents="test"
        )
    except:
        pass

warmup()

# 📦 kompresja obrazu (szybsza)
def compress_image(image_bytes):
    img = Image.open(io.BytesIO(image_bytes))
    img.thumbnail((384, 384))  # mniejsze = szybciej
    if img.mode != "RGB":
        img = img.convert("RGB")
    output = io.BytesIO()
    img.save(output, format="JPEG", quality=60)
    return output.getvalue()

# 📊 limity
REQUEST_LIMIT = 20
request_count = 0

last_request = {}
user_points = {}

# ▶️ /start — kluczowe UX na demo
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Wyślij zdjęcie odpadu 📸")

# 📸 handler zdjęć
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global request_count, last_request, user_points

    user_id = update.message.from_user.id
    now = time.time()

    # 🚦 anti-spam
    if user_id in last_request and now - last_request[user_id] < 1:
        await update.message.reply_text("Za szybko 📸 poczekaj chwilę")
        return

    last_request[user_id] = now

    if user_id not in user_points:
        user_points[user_id] = 0

    if request_count >= REQUEST_LIMIT:
        await update.message.reply_text("Dzisiejszy limit zapytań osiągnięty 🚫")
        return

    request_count += 1

    # ⚡ natychmiastowy feedback (ważne UX)
    await update.message.reply_text("Analizuję zdjęcie... ♻️")

    try:
        # 📸 pobranie zdjęcia
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)

        img_bytes = await file.download_as_bytearray()
        compressed = compress_image(img_bytes)

        # ⚡ szybsze wywołanie (bez PIL -> Gemini)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                PROMPT,
                {"mime_type": "image/jpeg", "data": compressed}
            ]
        )

        text = response.text or "Brak odpowiedzi"

        # 🏆 punkty
        gained_points = 0

        if "PSZOK" in text:
            gained_points = 10
        elif any(x in text for x in ["ŻÓŁTY", "NIEBIESKI", "ZIELONY", "BRĄZOWY", "CZARNY"]):
            gained_points = 5

        user_points[user_id] += gained_points

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

# 💬 fallback tekst
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Wyślij zdjęcie odpadu 📸")

# 🚀 START APP
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

# 🔥 usuwa webhook (ważne na Render)
app.post_init = lambda app: app.bot.delete_webhook(drop_pending_updates=True)

# 📌 handlery
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(MessageHandler(filters.TEXT, handle_text))

print("Bot działa... wyślij zdjęcie 📸")

app.run_polling()
