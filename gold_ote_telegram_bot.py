import os
import time
import threading
from datetime import datetime
import io

from flask import Flask
import telebot
import yfinance as yf
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# --- CONFIG ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "") or os.environ.get("TELEGRAM_BOT_TOKEN", "") or os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "") or os.environ.get("TELEGRAM_CHAT_ID", "")

TIMEFRAMES = {"5m": "5m", "15m": "15m"}
SYMBOL = "GC=F"  # Gold Futures
OTE_LOW = 0.62
OTE_HIGH = 0.79

print("BOT_TOKEN:", "YES" if BOT_TOKEN else "NO", len(BOT_TOKEN))
print("CHAT_ID:", "YES" if CHAT_ID else "NO", str(CHAT_ID)[:6])

bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None
app = Flask(__name__)

@app.route('/')
@app.route('/health')
def health():
    return f"Bot GOLD OTE 0.70S Running - {datetime.now().isoformat()}"

def send_msg(text, parse_mode="Markdown"):
    if not bot or not CHAT_ID:
        print("No bot/chat")
        return
    try:
        chat = int(CHAT_ID) if str(CHAT_ID).lstrip('-').isdigit() else CHAT_ID
        bot.send_message(chat, text, parse_mode=parse_mode)
        print("Sent msg:", text[:80])
    except Exception as e:
        print("Send error:", e)
        try:
            bot.send_message(chat, text)
        except Exception as e2:
            print("Send error2:", e2)

def send_photo(img_bytes, caption=""):
    if not bot or not CHAT_ID:
        return
    try:
        chat = int(CHAT_ID) if str(CHAT_ID).lstrip('-').isdigit() else CHAT_ID
        bot.send_photo(chat, img_bytes, caption=caption, parse_mode="Markdown")
        print("Photo sent")
    except Exception as e:
        print("Photo error:", e)

def get_data(tf_yf, period="2d"):
    try:
        df = yf.download(SYMBOL, period=period, interval=tf_yf, auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.dropna()
        print(f"Data {tf_yf}: {len(df)} candles, last {df['Close'].iloc[-1] if len(df)>0 else 'none'}")
        return df
    except Exception as e:
        print(f"YF error {tf_yf}:", e)
        return pd.DataFrame()

def find_swing(df, lookback=50):
    if len(df) < lookback:
        return None
    recent = df.tail(lookback)
    high_idx = recent['High'].idxmax()
    low_idx = recent['Low'].idxmin()
    swing_high = float(recent.loc[high_idx, 'High'])
    swing_low = float(recent.loc[low_idx, 'Low'])
    is_bullish_leg = high_idx > low_idx
    return {
        "high": swing_high,
        "low": swing_low,
        "high_time": high_idx,
        "low_time": low_idx,
        "bullish": is_bullish_leg,
        "df": recent
    }

def compute_ote(swing):
    h = swing["high"]
    l = swing["low"]
    rng = h - l
    if swing["bullish"]:
        ote_top = h - rng * OTE_LOW
        ote_bot = h - rng * OTE_HIGH
    else:
        ote_top = l + rng * OTE_HIGH
        ote_bot = l + rng * OTE_LOW
    ote_top, ote_bot = max(ote_top, ote_bot), min(ote_top, ote_bot)
    lower = min(h - rng*OTE_LOW, h - rng*OTE_HIGH) if swing["bullish"] else min(l + rng*OTE_LOW, l + rng*OTE_HIGH)
    upper = max(h - rng*OTE_LOW, h - rng*OTE_HIGH) if swing["bullish"] else max(l + rng*OTE_LOW, l + rng*OTE_HIGH)
    return lower, upper, rng

def make_chart(df, swing, tf_label):
    lower, upper, rng = compute_ote(swing)
    last_price = float(df['Close'].iloc[-1])
    plt.figure(figsize=(10,5))
    plt.plot(df.index, df['Close'], label='GOLD Close', linewidth=1.2)
    plt.axhline(swing["high"], color='green', linestyle='--', alpha=0.6, label=f'Swing High {swing["high"]:.1f}')
    plt.axhline(swing["low"], color='red', linestyle='--', alpha=0.6, label=f'Swing Low {swing["low"]:.1f}')
    plt.axhspan(lower, upper, color='gold', alpha=0.35, label=f'OTE {OTE_LOW}-{OTE_HIGH}')
    plt.scatter([df.index[-1]], [last_price], color='black', zorder=5)
    plt.text(df.index[-1], last_price, f' {last_price:.1f}', fontsize=9, va='bottom')
    direction = "BULLISH LEG (retest long)" if swing["bullish"] else "BEARISH LEG (retest short)"
    plt.title(f'GOLD {tf_label} - {direction} | OTE {lower:.1f} - {upper:.1f}')
    plt.legend(fontsize=8)
    plt.grid(alpha=0.2)
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150)
    plt.close()
    buf.seek(0)
    return buf, lower, upper, last_price

def scan_tf(tf_key):
    tf_yf = TIMEFRAMES[tf_key]
    period = "1d" if tf_key=="5m" else "5d"
    df = get_data(tf_yf, period=period)
    if df.empty or len(df) < 40:
        print(f"{tf_key} not enough data")
        return
    swing = find_swing(df, lookback=50)
    if not swing:
        return
    buf, lower, upper, last = make_chart(swing["df"], swing, tf_key)
    in_ote = lower <= last <= upper
    direction = "BULLISH" if swing["bullish"] else "BEARISH"
    caption = (
        f"*{tf_key} | GOLD OTE 0.70S*\n"
        f"Leg: {direction} {swing['low']:.1f} -> {swing['high']:.1f}\n"
        f"OTE Zone: `{lower:.2f} - {upper:.2f}`\n"
        f"Price: `{last:.2f}` {'🟢 DANS OTE' if in_ote else '⚪ Hors OTE'}\n"
        f"Range: {swing['high']-swing['low']:.2f}\n"
        f"{datetime.now().strftime('%H:%M:%S')}"
    )
    if in_ote:
        caption = "🚨 *" + f"{tf_key} SIGNAL OTE" + "* 🚨\n" + caption
        send_photo(buf, caption)
    else:
        print(f"{tf_key} hors OTE {lower:.1f}-{upper:.1f} price {last:.1f}")
    buf.close()

def bot_loop():
    print("Bot GOLD OTE 0.70S 5m/15m + Graphique pret")
    time.sleep(3)
    send_msg("✅ *Bot GOLD OTE 0.70S demarre*\nScan 5m + 15m + Graphique\nSignal uniquement si prix dans OTE 0.62-0.79")
    last_full_send = 0
    while True:
        try:
            for tf in TIMEFRAMES:
                scan_tf(tf)
                time.sleep(3)
            if time.time() - last_full_send > 3600:
                try:
                    df5 = get_data("5m", period="1d")
                    if not df5.empty:
                        swing = find_swing(df5, 50)
                        if swing:
                            buf, lower, upper, last = make_chart(swing["df"], swing, "5m")
                            send_photo(buf, f"*Recap 5m* Prix {last:.1f} OTE {lower:.1f}-{upper:.1f} - Bot OK")
                            buf.close()
                except Exception as e:
                    print("Recap error", e)
                last_full_send = time.time()
            time.sleep(60)
        except Exception as e:
            print("Loop error:", e)
            time.sleep(30)

def start_bot():
    try:
        if bot:
            bot.remove_webhook()
            print("Webhook removed")
    except Exception as e:
        print("Webhook error", e)
    bot_loop()

if __name__ == "__main__":
    threading.Thread(target=start_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    print(f"Flask on port {port}")
    app.run(host="0.0.0.0", port=port)
