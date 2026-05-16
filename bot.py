import telebot
from flask import Flask, request
import os
import json
import requests
import threading
import time
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv
from google import genai
from PIL import Image

# =========================
# LOAD ENV
# =========================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# =========================
# CHECK ENV
# =========================
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
VIP_FILE = "vip_data.json"
USER_FILE = "users.json"
SIGNAL_FILE = "signals.json"

# =========================
# CREATE FILES IF MISSING
# =========================
for file in [VIP_FILE, USER_FILE, SIGNAL_FILE]:
    if not os.path.exists(file):
        with open(file, "w") as f:
            json.dump({}, f)

# =========================
# HELPERS
# =========================
def load(file):
    try:
        with open(file, "r") as f:
            return json.load(f)
    except:
        return {}

def save(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=4)

# =========================
# VIP SYSTEM
# =========================
def add_vip(user_id, days):
    data = load(VIP_FILE)

    expiry = (
        datetime.now() + timedelta(days=days)
    ).timestamp()

    data[str(user_id)] = expiry

    save(VIP_FILE, data)

def is_vip(user_id):
    data = load(VIP_FILE)

    uid = str(user_id)

    if uid not in data:
        return False

    expiry = data[uid]

    if datetime.now().timestamp() > expiry:
        del data[uid]
        save(VIP_FILE, data)
        return False

    return True

# =========================
# USERS
# =========================
def add_user(uid):
    data = load(USER_FILE)

    data[str(uid)] = {
        "joined": str(datetime.now())
    }

    save(USER_FILE, data)

# =========================
# RATE LIMIT
# =========================
last_time = {}

def rate_limit(uid):
    now = time.time()

    if uid in last_time:
        if now - last_time[uid] < 8:
            return False

    last_time[uid] = now
    return True

# =========================
# SIMPLE SMART MONEY ENGINE
# =========================
def smc_engine():
    structure = random.choice([
        "Bullish structure with higher highs",
        "Bearish structure with lower lows",
        "Sideways consolidation"
    ])

    liquidity = random.choice([
        "Liquidity resting above highs",
        "Liquidity resting below lows",
        "Balanced liquidity"
    ])

    return structure, liquidity

# =========================
# START
# =========================
@bot.message_handler(commands=['start'])
def start(m):

    add_user(m.chat.id)

    text = (
        "🚀 AMUDANCE FX BOT\n\n"
        "Commands:\n"
        "/pay 7\n"
        "/pay 30\n"
        "/pay 90\n"
        "/myvip\n\n"
        "Send chart screenshot for analysis 📊"
    )

    bot.reply_to(m, text)

# =========================
# VIP STATUS
# =========================
@bot.message_handler(commands=['myvip'])
def myvip(m):

    data = load(VIP_FILE)

    uid = str(m.chat.id)

    if uid not in data:
        return bot.reply_to(
            m,
            "❌ VIP inactive"
        )

    expiry = datetime.fromtimestamp(data[uid])

    bot.reply_to(
        m,
        f"💎 VIP ACTIVE\n\nExpires:\n{expiry}"
    )

# =========================
# PAYMENT SYSTEM
# =========================
@bot.message_handler(commands=['pay'])
def pay(m):

    try:

        parts = m.text.split()

        # VALIDATE COMMAND
        if len(parts) < 2:
            return bot.reply_to(
                m,
                "Usage:\n/pay 7\n/pay 30\n/pay 90"
            )

        # GET DAYS
        days = int(parts[1])

        # VALIDATE PLAN
        if days not in [7, 30, 90]:
            return bot.reply_to(
                m,
                "Available plans:\n7, 30, 90"
            )

        # PLAN PRICES
        if days == 7:
            amount = 2000

        elif days == 30:
            amount = 5000

        else:
            amount = 12000

        # PAYSTACK REQUEST
        url = "https://api.paystack.co/transaction/initialize"

        headers = {
            "Authorization": f"Bearer {PAYSTACK_SECRET}",
            "Content-Type": "application/json"
        }

        payload = {
            "email": f"user{m.chat.id}@mail.com",
            "amount": amount * 100,
            "metadata": {
                "user_id": m.chat.id,
                "days": days
            }
        }

        response = requests.post(
            url,
            json=payload,
            headers=headers
        )

        res = response.json()

        print("PAYSTACK RESPONSE:", res)

        # CHECK PAYSTACK SUCCESS
        if not res.get("status"):

            return bot.reply_to(
                m,
                f"❌ Paystack Error:\n{res.get('message')}"
            )

        pay_link = (
            res.get("data", {})
            .get("authorization_url")
        )

        # CHECK LINK
        if not pay_link:
            return bot.reply_to(
                m,
                "❌ Payment link not generated"
            )

        # SEND LINK
        bot.reply_to(
            m,
            f"💳 VIP PAYMENT\n\n"
            f"Plan: {days} days\n"
            f"Amount: ₦{amount}\n\n"
            f"Pay here:\n{pay_link}"
        )

    except Exception as e:

        print("PAY ERROR:", e)

        bot.reply_to(
            m,
            f"❌ ERROR:\n{e}"
        )

# =========================
# AI ANALYSIS
# =========================
@bot.message_handler(content_types=['photo', 'document'])
def analyze(m):

    try:

        if not rate_limit(m.chat.id):
            return bot.reply_to(
                m,
                "⛔ Slow down"
            )

        loading = bot.reply_to(
            m,
            "📊 Analyzing market..."
        )

        # DOWNLOAD IMAGE
        if m.photo:
            file_info = bot.get_file(
                m.photo[-1].file_id
            )
        else:
            file_info = bot.get_file(
                m.document.file_id
            )

        downloaded = bot.download_file(
            file_info.file_path
        )

        # SAVE IMAGE
        path = f"chart_{m.chat.id}.jpg"

        with open(path, "wb") as f:
            f.write(downloaded)

        image = Image.open(path)

        vip = is_vip(m.chat.id)

        structure, liquidity = smc_engine()

        confidence = (
            random.randint(85, 97)
            if vip
            else random.randint(60, 80)
        )

        prompt = f"""
You are a professional Smart Money Concepts trader.

Follow this structure:

Market Structure:
{structure}

Liquidity:
{liquidity}

Analyze chart and return:

📊 Trend
📉 Structure
💧 Liquidity
📍 Entry
🛑 Stop Loss
🎯 Take Profit
📈 Bias
⚠ Risk
🔥 Confidence: {confidence}%

If unclear, say:
"Uncertain market condition"

User:
{'VIP' if vip else 'FREE'}
"""

        # GEMINI ANALYSIS
        res = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt, image]
        )

        result = res.text

        # SAVE SIGNAL
        signals = load(SIGNAL_FILE)

        signals[str(time.time())] = result

        save(SIGNAL_FILE, signals)

        # SEND RESULT
        bot.edit_message_text(
            chat_id=m.chat.id,
            message_id=loading.message_id,
            text=result
        )

        # DELETE IMAGE
        os.remove(path)

    except Exception as e:

        print("ANALYSIS ERROR:", e)

        bot.reply_to(
            m,
            f"❌ ERROR:\n{e}"
        )

# =========================
# WEBHOOK
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():

    try:

        event = request.json

        print("WEBHOOK:", event)

        # PAYMENT SUCCESS
        if event["event"] == "charge.success":

            metadata = (
                event["data"]
                .get("metadata", {})
            )

            user_id = metadata.get("user_id")
            days = metadata.get("days")

            if user_id and days:

                add_vip(
                    int(user_id),
                    int(days)
                )

                bot.send_message(
                    user_id,
                    f"🎉 PAYMENT SUCCESSFUL\n\n"
                    f"VIP ACTIVE FOR {days} DAYS"
                )

                bot.send_message(
                    ADMIN_ID,
                    f"💰 NEW VIP USER\n\n"
                    f"User ID: {user_id}\n"
                    f"Days: {days}"
                )

        return "OK", 200

    except Exception as e:

        print("WEBHOOK ERROR:", e)

        return "ERROR", 500

# =========================
# HOME ROUTE
# =========================
@app.route("/")
def home():
    return "AMUDANCE FX BOT RUNNING"

# =========================
# BOT RUNNER
# =========================
def run_bot():

    while True:

        try:

            print("BOT STARTING...")

            bot.infinity_polling(
                timeout=60,
                long_polling_timeout=60,
                skip_pending=True
            )

        except Exception as e:

            print("BOT ERROR:", e)

            time.sleep(10)

# =========================
# START EVERYTHING
# =========================
if __name__ == "__main__":

    # START BOT THREAD
    bot_thread = threading.Thread(
        target=run_bot
    )

    bot_thread.daemon = True
    bot_thread.start()

    # START FLASK
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080))
    )