import os, time, threading
from flask import Flask
import telebot
import yfinance as yf
import matplotlib.pyplot as plt

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")
TIMEFRAMES = {"5m": "5m", "15m": "15m"}

bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None
app = Flask(__name__)

def send_telegram(msg, chart_path=None):
    if not bot or not CHAT_ID:
        print(msg)
        return
    try:
        if chart_path and os.path.exists(chart_path):
            with open(chart_path, 'rb') as photo:
                bot.send_photo(CHAT_ID, photo, caption=msg, parse_mode="Markdown")
        else:
            bot.send_message(CHAT_ID, msg, parse_mode="Markdown")
    except Exception as e:
        print(f"Telegram error: {e}")

def scan_tf(tf_name):
    tf = TIMEFRAMES[tf_name]
    print(f"🔍 Scan GOLD {tf_name}...")
    try:
        # Récupère GOLD
        data = yf.download("GC=F", period="2d", interval=tf, progress=False)
        if len(data) < 50: return
        
        high = data['High'].max()
        low = data['Low'].min()
        price = float(data['Close'].iloc[-1])
        
        # Calcul OTE 0.70S
        range_ = high - low
        ote_top = low + range_ * 0.79
        ote_bottom = low + range_ * 0.62
        ote_70 = low + range_ * 0.70
        
        print(f"Price {price:.2f} | OTE [{ote_bottom:.2f} - {ote_top:.2f}]")
        
        # Condition OTE
        if ote_bottom <= price <= ote_top:
            # Graphique
            plt.figure(figsize=(8,4))
            plt.plot(data['Close'].tail(100))
            plt.axhspan(ote_bottom, ote_top, color='gold', alpha=0.3, label='OTE 0.62-0.79')
            plt.axhline(ote_70, color='red', linestyle='--', label='0.70S')
            plt.title(f"GOLD OTE Signal {tf_name} - {price:.2f}")
            plt.legend()
            plt.tight_layout()
            chart = f"/tmp/gold_{tf_name}.png"
            plt.savefig(chart)
            plt.close()
            
            msg = f"🚨 *GOLD OTE 0.70S {tf_name}*\nPrix: {price:.2f}\nOTE: {ote_bottom:.2f} - {ote_top:.2f}\nZone optimale touchée ✅"
            send_telegram(msg, chart)
            
    except Exception as e:
        print(f"Scan {tf_name} error: {e}")

@app.route('/')
@app.route('/health')
def health_check():
    return "Bot GOLD OTE 0.70S Running ✅ - https://gold-ote-bot-v2-2.onrender.com"

def bot_loop():
    print("Bot GOLD OTE 0.70S 5m/15m + Graphique prêt ✅")
    try:
        send_telegram("✅ *Bot GOLD OTE 0.70S opérationnel*\nScan 5m/15m actif")
    except:
        pass
    while True:
        try:
            for tf in TIMEFRAMES:
                scan_tf(tf)
                time.sleep(2)
            time.sleep(60) # scan toutes les 1 min
        except Exception as e:
            print(f"Loop error: {e}")
            time.sleep(10)

def start_bot():
    try:
        if bot: bot.remove_webhook()
    except: pass
    bot_loop()

if __name__ == "__main__":
    threading.Thread(target=start_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Flask sur port {port}")
    app.run(host="0.0.0.0", port=port)
