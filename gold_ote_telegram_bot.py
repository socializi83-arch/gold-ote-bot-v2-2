import os
import time
import threading
from flask import Flask
import telebot

# Support both names: BOT_TOKEN / TELEGRAM_BOT_TOKEN
BOT_TOKEN = os.environ.get("BOT_TOKEN", "") or os.environ.get("TELEGRAM_BOT_TOKEN", "") or os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "") or os.environ.get("TELEGRAM_CHAT_ID", "")

print("BOT_TOKEN found:", "YES" if BOT_TOKEN else "NO", "len", len(BOT_TOKEN))
print("CHAT_ID found:", "YES" if CHAT_ID else "NO", CHAT_ID)

TIMEFRAMES = ["5m", "15m"]

bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None
app = Flask(__name__)

def send_telegram(msg):
    if bot and CHAT_ID:
        try:
            bot.send_message(CHAT_ID, msg, parse_mode="Markdown")
            print("Telegram sent")
        except Exception as e:
            print("Telegram error:", e)

def scan_tf(tf):
    print("Scan", tf)

@app.route('/health')
def health_check():
    return "Bot GOLD OTE 0.70S Running"

def bot_loop():
    print("Bot GOLD OTE 0.70S 5m/15m ready")
    try:
        send_telegram("Bot GOLD OTE 0.70S operationnel")
    except Exception as e:
        print("Send error:", e)
    while True:
        try:
            for tf in TIMEFRAMES:
                scan_tf(tf)
                time.sleep(2)
            time.sleep(5)
        except Exception as e:
            print("Loop error", e)
            time.sleep(10)

def start_bot():
    try:
        if bot:
            bot.remove_webhook()
    except:
        pass
    bot_loop()

if __name__ == "__main__":
    threading.Thread(target=start_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    print("Flask on port", port)
    app.run(host="0.0.0.0", port=port)
