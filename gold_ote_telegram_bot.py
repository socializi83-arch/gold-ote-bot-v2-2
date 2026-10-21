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
    plt.title(f'GOLD
