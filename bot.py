import telebot
from telebot import types
from flask import Flask
import os
import json
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
ADMIN_ID = int(os.getenv("ADMIN_ID"))

if not BOT_TOKEN:
    raise Exception("BOT_TOKEN missing")

if not GEMINI_API_KEY:
    raise Exception("GEMINI_API_KEY missing")

# =========================
# BANK DETAILS
# =========================
BANK_NAME = "OPay"
ACCOUNT_NUMBER = "7048508048"
ACCOUNT_NAME = "AMUJO TIMILEHIN 📊"

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
PENDING_FILE = "pending_payments.json"

for f in [USER_FILE, SIGNAL_FILE, CREDIT_FILE, FREE_FILE, PENDING_FILE]:
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
def add_user(user):
    d = load(USER_FILE)

    uid = str(user.id)

    if uid not in d:
        d[uid] = {
            "username": user.username,
            "name": user.first_name,
            "joined": str(datetime.now())
        }

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

    add_user(m.from_user)

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)

    markup.add("📊 Analyze Market", "💳 Buy Credit")
    markup.add("💰 My Balance", "📞 Support")

    bot.send_message(
        m.chat.id,
        f"""
🚀 AMUDANCE FX BOT

🎁 Free Analysis Left: {free_left(m.chat.id)}
💎 Credits: {get_credit(m.chat.id)}

Send chart screenshots and get AI market analysis.
""",
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

    bot.send_message(
        m.chat.id,
        "Choose credit package:",
        reply_markup=markup
    )

# =========================
# PACKAGE SELECT
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("buy_"))
def buy_callback(c):

    _, amount, credits = c.data.split("_")

    pending = load(PENDING_FILE)

    pending[str(c.message.chat.id)] = {
        "amount": int(amount),
        "credits": int(credits),
        "username": c.from_user.username,
        "time": str(datetime.now())
    }

    save(PENDING_FILE, pending)

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("✅ I Paid")

    bot.send_message(
        c.message.chat.id,
        f"""
💳 PAYMENT DETAILS

🏦 Bank: {BANK_NAME}
🔢 Account Number: {ACCOUNT_NUMBER}
👤 Account Name: {ACCOUNT_NAME}

💰 Amount: ₦{amount}
💎 Credits: {credits}

After payment click:
✅ I Paid
""",
        reply_markup=markup
    )

# =========================
# USER CLICKED I PAID
# =========================
@bot.message_handler(func=lambda m: m.text == "✅ I Paid")
def paid(m):

    pending = load(PENDING_FILE)

    if str(m.chat.id) not in pending:
        return bot.reply_to(m, "❌ No pending payment")

    bot.send_message(
        m.chat.id,
        "📸 Send payment screenshot now"
    )

# =========================
# PAYMENT SCREENSHOT
# =========================
@bot.message_handler(content_types=['photo'])
def handle_photo(m):

    pending = load(PENDING_FILE)

    # =====================
    # PAYMENT SCREENSHOT
    # =====================
    if str(m.chat.id) in pending:

        data = pending[str(m.chat.id)]

        amount = data["amount"]
        credits = data["credits"]

        caption = f"""
💰 NEW PAYMENT

👤 User: @{m.from_user.username}
🆔 ID: {m.chat.id}

💵 Amount: ₦{amount}
💎 Credits: {credits}

Approve payment below:
"""

        markup = types.InlineKeyboardMarkup()

        markup.add(
            types.InlineKeyboardButton(
                "✅ APPROVE",
                callback_data=f"approve_{m.chat.id}_{credits}"
            ),

            types.InlineKeyboardButton(
                "❌ REJECT",
                callback_data=f"reject_{m.chat.id}"
            )
        )

        bot.send_photo(
            ADMIN_ID,
            m.photo[-1].file_id,
            caption=caption,
            reply_markup=markup
        )

        return bot.reply_to(
            m,
            "✅ Screenshot submitted\n⏳ Waiting for admin approval"
        )

    # =====================
    # MARKET ANALYSIS
    # =====================
    analyze_market(m)

# =========================
# APPROVE PAYMENT
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("approve_"))
def approve(c):

    _, user_id, credits = c.data.split("_")

    user_id = int(user_id)
    credits = int(credits)

    add_credit(user_id, credits)

    pending = load(PENDING_FILE)

    if str(user_id) in pending:
        del pending[str(user_id)]

    save(PENDING_FILE, pending)

    bot.send_message(
        user_id,
        f"""
✅ PAYMENT APPROVED

💎 {credits} Credit(s) Added

Use:
📊 Analyze Market
to start analysis.
"""
    )

    bot.answer_callback_query(c.id, "Approved")

    bot.edit_message_caption(
        caption=c.message.caption + "\n\n✅ APPROVED",
        chat_id=c.message.chat.id,
        message_id=c.message.message_id
    )

# =========================
# REJECT PAYMENT
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("reject_"))
def reject(c):

    _, user_id = c.data.split("_")

    user_id = int(user_id)

    pending = load(PENDING_FILE)

    if str(user_id) in pending:
        del pending[str(user_id)]

    save(PENDING_FILE, pending)

    bot.send_message(
        user_id,
        "❌ Payment rejected\nContact support if this is a mistake."
    )

    bot.answer_callback_query(c.id, "Rejected")

    bot.edit_message_caption(
        caption=c.message.caption + "\n\n❌ REJECTED",
        chat_id=c.message.chat.id,
        message_id=c.message.message_id
    )

# =========================
# BALANCE
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 My Balance")
def bal(m):

    bot.reply_to(
        m,
        f"""
💎 Credits: {get_credit(m.chat.id)}
🎁 Free Left: {free_left(m.chat.id)}
"""
    )

# =========================
# SUPPORT
# =========================
@bot.message_handler(func=lambda m: m.text == "📞 Support")
def support(m):

    bot.reply_to(
        m,
        "Contact Admin: @yourusername"
    )

# =========================
# ANALYZE BUTTON
# =========================
@bot.message_handler(func=lambda m: m.text == "📊 Analyze Market")
def ask(m):

    bot.reply_to(
        m,
        "📸 Send chart screenshot"
    )

# =========================
# MARKET ANALYSIS
# =========================
def analyze_market(m):

    try:

        if not rate_limit(m.chat.id):
            return bot.reply_to(m, "⛔ Slow down")

        owner = (m.chat.id == ADMIN_ID)

        free = free_left(m.chat.id)

        using_free = False

        if not owner:

            if free > 0:
                using_free = True

            elif get_credit(m.chat.id) < 1:
                return bot.reply_to(
                    m,
                    "❌ No credits left\nBuy credits to continue."
                )

        loading = bot.reply_to(
            m,
            "📊 Analyzing chart..."
        )

        file = bot.get_file(m.photo[-1].file_id)

        img = bot.download_file(file.file_path)

        path = f"chart_{m.chat.id}_{int(time.time())}.jpg"

        open(path, "wb").write(img)

        image = Image.open(path)

        prompt = """
You are a professional Smart Money Concepts trader.

Analyze ONLY real market structure:

- Market Structure (HH HL LH LL)
- Liquidity zones
- Break of Structure (BOS)
- Change of Character (CHoCH)
- Order blocks if visible

If unclear:
No clean setup detected

OUTPUT:

📊 Pair:
⏰ Timeframe:
📈 Market Structure:
💧 Liquidity:
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

        if owner:

            result += "\n\n👑 OWNER MODE"

        elif using_free:

            use_free(m.chat.id)

            result += f"\n\n🎁 Free Left: {free_left(m.chat.id)}"

        else:

            remove_credit(m.chat.id, 1)

            result += f"\n\n💎 Credits Left: {get_credit(m.chat.id)}"

        signals = load(SIGNAL_FILE)

        signals[str(time.time())] = result

        save(SIGNAL_FILE, signals)

        bot.edit_message_text(
            result,
            chat_id=m.chat.id,
            message_id=loading.message_id
        )

        os.remove(path)

    except Exception as e:

        bot.reply_to(
            m,
            f"❌ Error:\n{e}"
        )

# =========================
# HOME
# =========================
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

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080))
        )
