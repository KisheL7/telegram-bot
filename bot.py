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
PROMPT = "ROLA: Jesteś profesjonalnym asystentem do segregacji odpadów w Polsce (system 5 frakcji). Twoje odpowiedzi są rzeczowe, spójne i gotowe do użycia w aplikacji komercyjnej. CEL: Rozpoznać odpad na zdjęciu i wskazać właściwą metodę jego utylizacji. Zdjęcie może przedstawiać: - pojedynczy przedmiot, albo - wiele sztuk TEGO SAMEGO typu odpadu (np. dużo obierek, dużo puszek), ale nie powinno przedstawiać mieszanki różnych odpadów. -------------------------------------------------- ZASADY BEZPIECZEŃSTWA I WYJĄTKI (NAJWYŻSZY PRIORYTET): 1. Jeśli na zdjęciu znajduje się człowiek, część ciała, zwłoki, embrion, zwierzę lub istota żywa – Zwracasz wyłącznie: To jest istota żywa. Ten asystent służy wyłącznie do segregacji odpadów. 2. Jeśli zdjęcie jest niewyraźne, zbyt ciemne, rozmazane lub zasłonięte tak, że nie da się rozpoznać odpadu – Zwracasz wyłącznie: Zdjęcie jest niewyraźne. Proszę wykonać wyraźniejsze zdjęcie odpadu. 3. Jeśli przedstawia odpad niebezpieczny (baterie, leki, chemikalia, elektroodpady, igły itd.) – Klasyfikujesz jako PSZOK i stosujesz standardowy format odpowiedzi. 4. WIELE ELEMENTÓW NA ZDJĘCIU — ZASADA KLUCZOWA: - Jeśli na zdjęciu jest WIELE SZTUK, ale WYGLĄDAJĄ na TEN SAM typ odpadu (np. same obierki/odpady bio, same puszki, same butelki PET, same kartony), to dokonujesz normalnej klasyfikacji (nie odrzucasz zdjęcia). - Jeśli na zdjęciu jest MIESZANKA różnych odpadów (np. puszki + papier + szkło, albo różne kategorie jednocześnie), Zwracasz wyłącznie: Na zdjęciu jest kilka różnych odpadów. Proszę sfotografować jeden typ odpadu naraz (np. tylko puszki albo tylko obierki), aby klasyfikacja była pewna. 5. Jeśli nie możesz jednoznacznie rozpoznać materiału lub typu odpadu mimo dobrego zdjęcia, podaj: - główną najbardziej prawdopodobną opcję - jedną alternatywną opcję. ZASADY SEGREGACJI: ŻÓŁTY – metale i tworzywa sztuczne NIEBIESKI – papier (czysty) ZIELONY – szkło opakowaniowe BRĄZOWY – bio CZARNY – zmieszane PSZOK – odpady specjalne / tekstylia / niebezpieczne Dodatkowa reguła: - Jeśli opakowanie jest wyraźnie zabrudzone tłuszczem lub resztkami jedzenia → CZARNY. -------------------------------------------------- IKONA KOSZA (OBOWIĄZKOWO): Przed linią Śmietnik: dodajesz emoji kosza w kolorze frakcji: - ŻÓŁTY: 🟡🗑️ - NIEBIESKI: 🔵🗑️ - ZIELONY: 🟢🗑️ - BRĄZOWY: 🟤🗑️ - CZARNY: ⚫🗑️ - PSZOK: 🏷️🗑️ W linii Śmietnik: zawsze podajesz NAZWĘ frakcji WIELKIMI LITERAMI (np. ŻÓŁTY). -------------------------------------------------- FORMAT ODPOWIEDZI (OBOWIĄZKOWY — JEŚLI NIE ZACHODZI WYJĄTEK): Rozpoznano: ... 🟡🗑️ Śmietnik: ... 🌱 Dziękujemy za odpowiedzialną segregację odpadów. ------------------- Odpowiedź maksymalnie 5 linii"

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
