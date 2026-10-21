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
SYMBOL = "XAUUSD=X"
OTE_LOW = 0.62
OTE_HIGH = 0.79
CAPITAL = 100.0
RISK_PCT = 1.0
MAX_SL_DOLLARS = 12.0
MIN_RR = 1.3
MAX_LOT = 0.02
MIN_LOT = 0.01

bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None
app = Flask(__name__)
active_trades = {}
last_signals = {}

@app.route('/')
@app.route('/health')
def health():
    return f"Bot GOLD OTE V3.3 NOVICE SAFE - {datetime.now().isoformat()} - Last:{last_signals}"

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

def get_data(tf_yf, period="5d"):
    try:
        df = yf.download(SYMBOL, period=period, interval=tf_yf, auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.dropna()
        return df
    except Exception as e:
        print(f"YF error {tf_yf}:", e)
        return pd.DataFrame()

def find_swing(df, lookback=80):
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
    h = swing["high"]
    l = swing["low"]
    rng = h - l
    if swing["bullish"]:
        lower = h - rng*OTE_HIGH
        upper = h - rng*OTE_LOW
    else:
        lower = l + rng*OTE_LOW
        upper = l + rng*OTE_HIGH
        if lower > upper:
            lower, upper = upper, lower
    return lower, upper, rng

def calc_levels(swing):
    h = swing["high"]
    l = swing["low"]
    rng = h - l
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

def calc_lot(entry, sl):
    sl_dist = abs(entry - sl)
    if sl_dist > 5:
        return 0.01
    return 0.02

def make_chart(df, swing, tf_label, entry, sl, tp1, tp2, lot, mt5_type):
    lower, upper, rng = compute_ote(swing)
    last_price = float(df['Close'].iloc[-1])
    plt.figure(figsize=(11,5.5))
    plt.plot(df.index, df['Close'], label='GOLD', linewidth=1.3)
    plt.axhline(swing["high"], color='green', linestyle='--', alpha=0.5)
    plt.axhline(swing["low"], color='red', linestyle='--', alpha=0.5)
    plt.axhspan(lower, upper, color='gold', alpha=0.35, label=f'OTE {OTE_LOW}-{OTE_HIGH}')
    plt.axhline(entry, color='blue', linestyle='-', linewidth=1.5, label=f'ENTRY {entry:.1f} {mt5_type}')
    plt.axhline(sl, color='red', linestyle='-', linewidth=1.2, label=f'SL {sl:.1f}')
    plt.axhline(tp1, color='limegreen', linestyle='-', linewidth=1.2, label=f'TP1 {tp1:.1f}')
    plt.axhline(tp2, color='darkgreen', linestyle='-', alpha=0.7, label=f'TP2 {tp2:.1f}')
    plt.scatter([df.index[-1]], [last_price], color='black', zorder=5)
    direction = "LONG BUY" if swing["bullish"] else "SHORT SELL"
    plt.title(f"GOLD {tf_label} {direction} | {mt5_type} {entry:.1f} LOT {lot}")
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
    df = get_data(tf_yf, period="5d")
    if df.empty or len(df) < 80:
        return
    swing = find_swing(df, lookback=80)
    if not swing:
        return
    lower, upper, entry, sl, tp1, tp2, tp3, rng = calc_levels(swing)
    sl_dist = abs(entry - sl)
    if sl_dist > MAX_SL_DOLLARS:
        print(f"{tf_key} SKIP SL trop large {sl_dist:.1f}$")
        return
    rr1 = abs(tp1-entry)/abs(entry-sl) if abs(entry-sl)>0 else 0
    rr2 = abs(tp2-entry)/abs(entry-sl) if abs(entry-sl)>0 else 0
    if rr1 < MIN_RR:
        print(f"{tf_key} SKIP RR {rr1:.1f}")
        return
    lot = calc_lot(entry, sl)

    if swing["bullish"]:
        direction = "LONG BUY"
        order_type = "BUY / LONG - ACHAT"
        mt5_type = "Buy Limit"
        novice_help = "Dans MT5 choisis: Buy Limit | Prix = ENTREE"
    else:
        direction = "SHORT SELL"
        order_type = "SELL / SHORT - VENTE"
        mt5_type = "Sell Limit"
        novice_help = "Dans MT5 choisis: Sell Limit | Prix = ENTREE"

    buf, _, _, last = make_chart(swing["df"], swing, tf_key, entry, sl, tp1, tp2, lot, mt5_type)
    in_ote = lower <= last <= upper

    if in_ote:
        novice_help = novice_help + " | Si DANS OTE, Execution marche possible"

    if tf_key in active_trades:
        tr = active_trades[tf_key]
        is_long = tr["bullish"]
        tp1_hit = (last >= tr["tp1"]) if is_long else (last <= tr["tp1"])
        if tp1_hit and not tr.get("be_done"):
            be_msg = f"TP1 TOUCHE {tf_key} - PASSE EN BE\nEntree {tr['entry']:.2f} Lot {tr['lot']}\nTP1 {tr['tp1']:.2f} valide\nSL {tr['sl']:.2f} -> {tr['entry']:.2f}\n{tr['entry']:.2f} COPIE DANS SL - TP2 {tr['tp2']:.2f}"
            send_msg(be_msg)
            tr["be_done"] = True
            active_trades[tf_key] = tr
        tp2_hit = (last >= tr["tp2"]) if is_long else (last <= tr["tp2"])
        if tp2_hit and tr.get("be_done") and not tr.get("tp2_done"):
            tp2_msg = f"TP2 TOUCHE {tf_key} - SECURISE BE+\n{tr['entry']:.2f} -> {tr['tp2']:.2f} Lot {tr['lot']}\nPasse SL en BE+: {tr['tp1']:.2f}\n{tr['tp1']:.2f} COPIE POUR TP3 {tr['tp3']:.2f}"
            send_msg(tp2_msg)
            tr["tp2_done"] = True
            active_trades[tf_key] = tr

    ote_status = "DANS OTE" if in_ote else "Hors OTE"
    caption = (
        f"{tf_key} SIGNAL OTE {direction}\n"
        f"{order_type} -> {mt5_type}\n\n"
        f"Leg: {swing['low']:.1f} -> {swing['high']:.1f} (Range {rng:.1f}$)\n"
        f"OTE: {lower:.2f} - {upper:.2f} | Prix: {last:.2f} {ote_status}\n\n"
        f"100 EUR SAFE levier 1/100:\n"
        f"Lot: {lot} | Risque {RISK_PCT}% = 1E | MAX 0.02\n\n"
        f"PLAN ICT:\n"
        f"ORDRE MT5 A CHOISIR: {mt5_type} @ {entry:.2f}\n"
        f"ENTREE: {entry:.2f} (0.705S)\n"
        f"SL: {sl:.2f} ({sl_dist:.1f}$)\n"
        f"TP1: {tp1:.2f} RR {rr1:.1f}R\n"
        f"TP2: {tp2:.2f} RR {rr2:.1f}R\n"
        f"TP3: {tp3:.2f}\n\n"
        f"POUR NOVICE:\n"
        f"{novice_help}\n"
        f"NE PAS choisir Buy Stop / Sell Stop pour OTE!\n"
        f"Buy Stop = achat breakout, Sell Limit = vente rebond\n\n"
        f"{datetime.now().strftime('%H:%M:%S')}"
    )

    if in_ote:
        now = time.time()
        prev = last_signals.get(tf_key)
        if prev:
            same_dir = prev.get("bullish") == swing["bullish"]
            entry_close = abs(prev["entry"] - entry) < 3.0
            time_close = (now - prev["time"]) < 3600
            if same_dir and entry_close and time_close:
                print(f"{tf_key} SKIP meme swing {prev['entry']:.1f}")
                buf.close()
                return
            if tf_key in active_trades and same_dir and entry_close:
                if not active_trades[tf_key].get("be_done"):
                    print(f"{tf_key} SKIP trade actif")
                    buf.close()
                    return
        send_photo(buf, caption)
        last_signals[tf_key] = {"entry": entry, "time": now, "bullish": swing["bullish"]}
        if tf_key not in active_trades or abs(active_trades[tf_key]["entry"] - entry) > 3.0 or active_trades[tf_key]["bullish"] != swing["bullish"]:
            active_trades[tf_key] = {
                "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3, "lot": lot,
                "direction": direction, "bullish": swing["bullish"],
                "be_done": False, "tp2_done": False
            }
    else:
        print(f"{tf_key} hors OTE {last:.1f}")
    buf.close()

def bot_loop():
    print("Bot GOLD OTE V3.3 NOVICE SAFE pret")
    time.sleep(2)
    send_msg(f"Bot V3.3 NOVICE SAFE demarre - Capital {CAPITAL} EUR Risque {RISK_PCT}% - Symbole {SYMBOL} - Meme strategie OTE + BE + TP1/TP2/TP3 - Lot auto + Guide Buy Limit / Sell Limit")
    while True:
        try:
            for tf in TIMEFRAMES:
                scan_tf(tf)
                time.sleep(5)
            time.sleep(90)
        except Exception as e:
            print("Loop error:", e)
            time.sleep(30)

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
    app.run(host="0.0.0.0", port=port)
