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

BOT_TOKEN = os.environ.get("BOT_TOKEN", "") or os.environ.get("TELEGRAM_BOT_TOKEN", "") or os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "") or os.environ.get("TELEGRAM_CHAT_ID", "")
TIMEFRAMES = {"5m": "5m", "15m": "15m"}
SYMBOL = "GC=F"
OTE_LOW = 0.62
OTE_HIGH = 0.79

bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None
app = Flask(__name__)
active_trades = {}
last_signals = {}

@app.route('/')
@app.route('/health')
def health():
    return f"Bot GOLD OTE BUY/SELL+BE Running - {datetime.now().isoformat()}"

def send_msg(text, parse_mode="Markdown"):
    if not bot or not CHAT_ID:
        return
    try:
        chat = int(CHAT_ID) if str(CHAT_ID).lstrip('-').isdigit() else CHAT_ID
        bot.send_message(chat, text, parse_mode=parse_mode)
    except Exception as e:
        print("Send error:", e)

def send_photo(img_bytes, caption=""):
    if not bot or not CHAT_ID:
        return
    try:
        chat = int(CHAT_ID) if str(CHAT_ID).lstrip('-').isdigit() else CHAT_ID
        bot.send_photo(chat, img_bytes, caption=caption, parse_mode="Markdown")
    except Exception as e:
        print("Photo error:", e)

def get_data(tf_yf, period="2d"):
    try:
        df = yf.download(SYMBOL, period=period, interval=tf_yf, auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.dropna()
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
    return {"high": swing_high, "low": swing_low, "bullish": is_bullish_leg, "df": recent}

def compute_ote(swing):
    h = swing["high"]; l = swing["low"]; rng = h - l
    lower = min(h - rng*OTE_LOW, h - rng*OTE_HIGH) if swing["bullish"] else min(l + rng*OTE_LOW, l + rng*OTE_HIGH)
    upper = max(h - rng*OTE_LOW, h - rng*OTE_HIGH) if swing["bullish"] else max(l + rng*OTE_LOW, l + rng*OTE_HIGH)
    return lower, upper, rng

def calc_levels(swing):
    h = swing["high"]; l = swing["low"]; rng = h - l
    lower, upper, _ = compute_ote(swing)
    entry = (lower + upper) / 2
    if swing["bullish"]:
        sl = l - rng * 0.15
        tp1 = h
        tp2 = h + rng * 0.62
        tp3 = h + rng * 1.0
    else:
        sl = h + rng * 0.15
        tp1 = l
        tp2 = l - rng * 0.62
        tp3 = l - rng * 1.0
    return lower, upper, entry, sl, tp1, tp2, tp3, rng

def make_chart(df, swing, tf_label, entry, sl, tp1, tp2):
    lower, upper, rng = compute_ote(swing)
    last_price = float(df['Close'].iloc[-1])
    plt.figure(figsize=(11,5.5))
    plt.plot(df.index, df['Close'], label='GOLD', linewidth=1.3)
    plt.axhline(swing["high"], color='green', linestyle='--', alpha=0.5)
    plt.axhline(swing["low"], color='red', linestyle='--', alpha=0.5)
    plt.axhspan(lower, upper, color='gold', alpha=0.35, label=f'OTE {OTE_LOW}-{OTE_HIGH}')
    plt.axhline(entry, color='blue', linestyle='-', linewidth=1.5, label=f'ENTRY {entry:.1f}')
    plt.axhline(sl, color='red', linestyle='-', linewidth=1.2, label=f'SL {sl:.1f}')
    plt.axhline(tp1, color='limegreen', linestyle='-', linewidth=1.2, label=f'TP1 {tp1:.1f}')
    plt.axhline(tp2, color='darkgreen', linestyle='-', alpha=0.7, label=f'TP2 {tp2:.1f}')
    plt.scatter([df.index[-1]], [last_price], color='black', zorder=5)
    direction = "LONG BUY" if swing["bullish"] else "SHORT SELL"
    plt.title(f'GOLD {tf_label} - {direction} | OTE {lower:.1f}-{upper:.1f} Entry {entry:.1f}')
    plt.legend(fontsize=7)
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
        return
    swing = find_swing(df, lookback=50)
    if not swing:
        return
    lower, upper, entry, sl, tp1, tp2, tp3, rng = calc_levels(swing)
    buf, _, _, last = make_chart(swing["df"], swing, tf_key, entry, sl, tp1, tp2)
    in_ote = lower <= last <= upper
    if swing["bullish"]:
        direction = "LONG 📈 BUY"
        order_type = "🟢 BUY / LONG - ACHAT"
        action = "BUY"
    else:
        direction = "SHORT 📉 SELL"
        order_type = "🔴 SELL / SHORT - VENTE"
        action = "SELL"
    rr1 = abs(tp1-entry)/abs(entry-sl) if abs(entry-sl)>0 else 0
    rr2 = abs(tp2-entry)/abs(entry-sl) if abs(entry-sl)>0 else 0

    if tf_key in active_trades:
        tr = active_trades[tf_key]
        is_long = tr["bullish"]
        tp1_hit = (last >= tr["tp1"]) if is_long else (last <= tr["tp1"])
        if tp1_hit and not tr.get("be_done"):
            be_msg = (
                f"✅ *TP1 TOUCHÉ {tf_key} - PASSE EN BE* ✅\n\n"
                f"Direction: {tr['direction']}\n"
                f"Entrée: `{tr['entry']:.2f}`\n"
                f"TP1 `{tr['tp1']:.2f}` validé 🟢\n\n"
                f"👉 *ACTION:*\n"
                f"SL: `{tr['sl']:.2f}` ➡️ `{tr['entry']:.2f}`\n\n"
                f"`{tr['entry']:.2f}`\n"
                f"☝️ COPIE CE CHIFFRE DANS SL\n\n"
                f"Objectif TP2: `{tr['tp2']:.2f}`"
            )
            send_msg(be_msg)
            tr["be_done"] = True
            active_trades[tf_key] = tr
        tp2_hit = (last >= tr["tp2"]) if is_long else (last <= tr["tp2"])
        if tp2_hit and tr.get("be_done") and not tr.get("tp2_done"):
            tp2_msg = (
                f"🔥 *TP2 TOUCHÉ {tf_key} - SECURISE BE+* 🔥\n\n"
                f"`{tr['entry']:.2f}` -> `{tr['tp2']:.2f}`\n"
                f"TP2 validé\n\n"
                f"👉 Passe SL en BE+: `{tr['tp1']:.2f}`\n\n"
                f"`{tr['tp1']:.2f}`\n"
                f"☝️ COPIE POUR TP3 `{tr['tp3']:.2f}`"
            )
            send_msg(tp2_msg)
            tr["tp2_done"] = True
            active_trades[tf_key] = tr

    caption = (
        f"🚨 *{tf_key} SIGNAL OTE {direction}* 🚨\n"
        f"{order_type}\n\n"
        f"Leg: {swing['low']:.1f} -> {swing['high']:.1f} (Range {rng:.1f}$)\n"
        f"OTE: `{lower:.2f} - {upper:.2f}` | Prix: `{last:.2f}` {'🟢 DANS OTE' if in_ote else '⚪ Hors OTE'}\n\n"
        f"🎯 *PLAN ICT:*\n"
        f"➡️ ORDRE: *{action}*\n"
        f"➡️ ENTRÉE: `{entry:.2f}` (0.705S)\n"
        f"🛑 SL: `{sl:.2f}` ({abs(entry-sl):.1f}$)\n"
        f"✅ TP1: `{tp1:.2f}` (Swing) RR {rr1:.1f}R\n"
        f"✅ TP2: `{tp2:.2f}` RR {rr2:.1f}R\n"
        f"✅ TP3: `{tp3:.2f}` (Ext 1.0)\n"
        f"_{datetime.now().strftime('%H:%M:%S')}_"
    )
    if in_ote:
        now = time.time()
        prev = last_signals.get(tf_key)
        if prev and abs(prev["entry"] - entry) < 2.0 and (now - prev["time"]) < 900:
            print(f"{tf_key} déjà signalé il y a {(now-prev['time'])/60:.1f}min - skip")
            buf.close()
            return
        send_photo(buf, caption)
        last_signals[tf_key] = {"entry": entry, "time": now}
        if tf_key not in active_trades or abs(active_trades[tf_key]["entry"] - entry) > 2.0:
            active_trades[tf_key] = {
                "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3,
                "direction": direction, "bullish": swing["bullish"],
                "be_done": False, "tp2_done": False
            }
    else:
        print(f"{tf_key} hors OTE")
    buf.close()

def bot_loop():
    print("Bot GOLD OTE BUY/SELL + BE pret")
    time.sleep(2)
   
