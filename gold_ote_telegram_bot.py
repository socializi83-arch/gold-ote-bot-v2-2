import os
import time
import threading
from flask import Flask
import telebot

# --- CONFIG ---
# Supporte BOT_TOKEN et TELEGRAM_BOT_TOKEN et TELEGRAM_TOKEN
BOT_TOKEN = (
    os.environ.get("BOT_TOKEN", "") or 
    os.environ.get("TELEGRAM_BOT_TOKEN", "") or 
    os.environ.get("TELEGRAM_TOKEN", "") or
    os.environ.get("TELE_BOT_TOKEN", "")
)
# Supporte CHAT_ID et TELEGRAM_CHAT_ID
CHAT_ID = (
    os.environ.get("CHAT_ID", "") or 
    os.environ.get("TELEGRAM_CHAT_ID", "") or
    os.environ.get("TELEGRAM_CHAT", "") or
    os.environ.get("TELE_CHAT_ID", "")
)
TIMEFRAMES = ["5m", "15m"]

print(f"🔑 BOT_TOKEN trouvé: {'OUI' if BOT_TOKEN else 'NON'} (longueur {len(BOT_TOKEN)})")
print(f"🔑 CHAT_ID trouvé: {'OUI' if CHAT_ID else 'NON'} ({CHAT_ID[:4]}...)" if CHAT_ID else "🔑 CHAT_ID NON")

bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None
app = Flask(__name__)

def send_telegram(msg):
    if bot and CHAT_ID:
        bot.send_message(CHAT_ID, msg, parse_mode="Markdown")

def scan_tf(tf):
    # TODO: ta logique OTE ici
    print(f"Scan {tf}")
    pass

@app.route('/health')
def health_check():
    return "Bot GOLD OTE 0.70S Running ✅"

def bot_loop():
    print("Bot GOLD OTE 0.70S 5m/15m + Graphique prêt ✅")
    try:
        send_telegram("✅ *Bot GOLD OTE 0.70S opérationnel*")
    except:
        pass
    while True:
        try:
            for tf in TIMEFRAMES:
                scan_tf(tf)
                time.sleep(2)
            time.sleep(5)
        except Exception as e:
            print(f"Loop error: {e
