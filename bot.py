import telebot
from telebot import types
from flask import Flask, request
import os
import json
import requests
import threading
import time
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from PIL import Image

# =========================
# ENV
# =========================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

if not BOT_TOKEN:
    raise Exception("BOT_TOKEN missing")
if not GEMINI_API_KEY:
    raise Exception("GEMINI_API_KEY missing")
if not PAYSTACK_SECRET:
    raise Exception("PAYSTACK_SECRET_KEY missing")

# =========================
# INIT
# =========================
bot = telebot.TeleBot(BOT_TOKEN)
client = genai.Client(api_key=GEMINI_API_KEY)
app = Flask(__name__)

# =========================
# FILES
# =========================
USER_FILE = "users.json"
SIGNAL_FILE = "signals.json"
CREDIT_FILE = "credits.json"
FREE_FILE = "free_trial.json"
WHITELIST_FILE = "whitelist.json"

for f in [USER_FILE, SIGNAL_FILE, CREDIT_FILE, FREE_FILE, WHITELIST_FILE]:
    if not os.path.exists(f):
        with open(f, "w") as x:
            json.dump({}, x)

# =========================
# HELPERS
# =========================
def load(f):
    try:
        return json.load(open(f))
    except:
        return {}

def save(f, d):
    with open(f, "w") as x:
        json.dump(d, x, indent=4)

# =========================
# USER
# =========================
def add_user(uid):
    d = load(USER_FILE)
    if str(uid) not in d:
        d[str(uid)] = {"joined": str(datetime.now())}
        save(USER_FILE, d)

# =========================
# CREDIT SYSTEM
# =========================
def get_credit(uid):
    return load(CREDIT_FILE).get(str(uid), 0)

def add_credit(uid, amt):
    d = load(CREDIT_FILE)
    d[str(uid)] = d.get(str(uid), 0) + amt
    save(CREDIT_FILE, d)

def remove_credit(uid, amt=1):
    d = load(CREDIT_FILE)
    if d.get(str(uid), 0) >= amt:
        d[str(uid)] -= amt
        save(CREDIT_FILE, d)
        return True
    return False

# =========================
# FREE SYSTEM
# =========================
FREE_LIMIT = 2

def get_free_used(uid):
    return load(FREE_FILE).get(str(uid), 0)

def use_free(uid):
    d = load(FREE_FILE)
    d[str(uid)] = d.get(str(uid), 0) + 1
    save(FREE_FILE, d)

def free_left(uid):
    return max(0, FREE_LIMIT - get_free_used(uid))

# =========================
# WHITELIST SYSTEM
# =========================
def is_whitelisted(uid):
    return str(uid) in load(WHITELIST_FILE)

# =========================
# RATE LIMIT
# =========================
last_time = {}

def rate_limit(uid):
    now = time.time()
    if uid in last_time and now - last_time[uid] < 8:
        return False
    last_time[uid] = now
    return True

# =========================
# START
# =========================
@bot.message_handler(commands=['start'])
def start(m):
    add_user(m.chat.id)

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📊 Analyze Market", "💳 Buy Credit")
    markup.add("💰 My Balance", "📞 Support")

    bot.send_message(
        m.chat.id,
        f"🚀 AMUDANCE FX BOT\n\n🎁 Free: {free_left(m.chat.id)}\n💎 Credits: {get_credit(m.chat.id)}",
        reply_markup=markup
    )

# =========================
# BUY CREDIT
# =========================
@bot.message_handler(func=lambda m: m.text == "💳 Buy Credit")
def buy(m):
    markup = types.InlineKeyboardMarkup()

    plans = [
        (500, 1),
        (1000, 2),
        (2000, 4),
        (3000, 6),
        (5000, 10),
        (10000, 20),
    ]

    for price, credits in plans:
        markup.add(
            types.InlineKeyboardButton(
                f"₦{price} = {credits} Credit(s)",
                callback_data=f"buy_{price}_{credits}"
            )
        )

    bot.send_message(m.chat.id, "Choose package:", reply_markup=markup)

# =========================
# PAYSTACK
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("buy_"))
def pay(c):
    _, amount, credits = c.data.split("_")

    res = requests.post(
        "https://api.paystack.co/transaction/initialize",
        headers={"Authorization": f"Bearer {PAYSTACK_SECRET}"},
        json={
            "email": f"user{c.message.chat.id}@mail.com",
            "amount": int(amount) * 100,
            "metadata": {
                "user_id": c.message.chat.id,
                "credits": int(credits)
            }
        }
    ).json()

    url = res.get("data", {}).get("authorization_url")

    if not url:
        return bot.answer_callback_query(c.id, "Payment failed")

    bot.send_message(
        c.message.chat.id,
        f"Pay ₦{amount} for {credits} credits",
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("PAY NOW", url=url)
        )
    )

# =========================
# BALANCE
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 My Balance")
def bal(m):
    bot.reply_to(
        m,
        f"💎 Credits: {get_credit(m.chat.id)}\n🎁 Free: {free_left(m.chat.id)}"
    )

# =========================
# SUPPORT
# =========================
@bot.message_handler(func=lambda m: m.text == "📞 Support")
def sup(m):
    bot.reply_to(m, "Contact: @yourusername")

# =========================
# ANALYZE BUTTON
# =========================
@bot.message_handler(func=lambda m: m.text == "📊 Analyze Market")
def ask(m):
    bot.reply_to(m, "Send chart screenshot 📸")

# =========================
# AI ANALYSIS (IMPROVED PROMPT + WHITELIST)
# =========================
@bot.message_handler(content_types=['photo', 'document'])
def analyze(m):

    try:
        if not rate_limit(m.chat.id):
            return bot.reply_to(m, "⛔ Slow down")

        owner = (m.chat.id == ADMIN_ID)
        whitelist = is_whitelisted(m.chat.id)

        free = free_left(m.chat.id)
        using_free = False

        # ACCESS CONTROL
        if not owner and not whitelist:
            if free > 0:
                using_free = True
            elif get_credit(m.chat.id) < 1:
                return bot.reply_to(m, "❌ No credits")

        loading = bot.reply_to(m, "📊 Analyzing chart...")

        file = bot.get_file(m.photo[-1].file_id if m.photo else m.document.file_id)
        img = bot.download_file(file.file_path)

        path = f"chart_{m.chat.id}.jpg"
        open(path, "wb").write(img)

        image = Image.open(path)

        confidence = 90

        # =========================
        # IMPROVED AI PROMPT
        # =========================
        prompt = """
You are a PROFESSIONAL Smart Money Concepts (SMC) forex analyst.

Analyze ONLY from the chart:

Focus strictly on:
- Market Structure (HH, HL, LH, LL)
- Liquidity zones (buy-side / sell-side)
- Break of Structure (BOS)
- Change of Character (CHoCH)
- Order blocks (if visible)
- Trend direction

RULES:
- Do NOT guess randomly
- If unclear, say: No clean setup detected
- Be precise and institutional-level accurate

OUTPUT FORMAT:

📊 Pair:
⏰ Timeframe:

📈 Market Structure:
💧 Liquidity:
🔁 Market Phase:
📉 Key Level:

📍 Entry:
🛑 Stop Loss:
🎯 Take Profit 1:
🎯 Take Profit 2:
🎯 Take Profit 3:

📈 Bias: BUY or SELL only
⚠ Risk Level:
🔥 Confidence:
"""

        res = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt, image]
        )

        result = res.text

        # =========================
        # ACCESS RESULT LOGIC
        # =========================
        if owner or whitelist:
            result += "\n\n👑 PREMIUM ACCESS"
        elif using_free:
            use_free(m.chat.id)
            result += f"\n\n🎁 Free left: {free_left(m.chat.id)}"
        else:
            remove_credit(m.chat.id, 1)
            result += f"\n\n💎 Credits: {get_credit(m.chat.id)}"

        save(SIGNAL_FILE, {str(time.time()): result})

        bot.edit_message_text(
            result,
            chat_id=m.chat.id,
            message_id=loading.message_id
        )

        os.remove(path)

    except Exception as e:
        bot.reply_to(m, f"Error: {e}")

# =========================
# WEBHOOK
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    if data["event"] == "charge.success":
        meta = data["data"]["metadata"]

        add_credit(meta["user_id"], meta["credits"])

        bot.send_message(
            meta["user_id"],
            f"✅ Payment successful +{meta['credits']} credits"
        )

    return "OK"

@app.route("/")
def home():
    return "BOT RUNNING"

# =========================
# RUN
# =========================
def run():
    bot.infinity_polling(skip_pending=True)

if __name__ == "__main__":
    threading.Thread(target=run).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
