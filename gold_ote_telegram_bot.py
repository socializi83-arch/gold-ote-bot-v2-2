import os
import time
import threading
from datetime import datetime, timezone
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
# V5.0 ICT PRO : OTE precise 70.5%
OTE_LOW = 0.68
OTE_HIGH = 0.73
OTE_ENTRY = 0.705
CAPITAL = 1000.0
RISK_PCT = 1.0
MAX_SL_DOLLARS = 20.0
MIN_RR = 1.8
MAX_LOT = 0.20
MIN_LOT = 0.10

bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None
app = Flask(__name__)
active_trades = {}
last_signals = {}
last_heartbeat = 0
scan_count = 0

@app.route('/')
@app.route('/health')
def health():
    return f"Bot GOLD OTE V5.0 ICT PRO 1000E - {datetime.now().isoformat()} - Last:{last_signals} - Scans:{scan_count}"

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

def get_htf_trend():
    try:
        df_1h = get_data("60m", period="5d")
        if df_1h.empty or len(df_1h) < 50:
            return "NEUTRAL", "No HTF"
        df_1h['EMA50'] = df_1h['Close'].ewm(span=50).mean()
        df_1h['EMA200'] = df_1h['Close'].ewm(span=200).mean()
        last = df_1h.iloc[-1]
        bullish_ema = last['EMA50'] > last['EMA200'] and last['Close'] > last['EMA50']
        bearish_ema = last['EMA50'] < last['EMA200'] and last['Close'] < last['EMA50']
        recent_high = df_1h['High'].tail(20).max()
        recent_low = df_1h['Low'].tail(20).min()
        bos_up = last['Close'] > recent_high
        bos_down = last['Close'] < recent_low
        if bullish_ema or bos_up:
            trend = "BULLISH"
        elif bearish_ema or bos_down:
            trend = "BEARISH"
        else:
            trend = "NEUTRAL"
        return trend, f"1H EMA50 {last['EMA50']:.1f} EMA200 {last['EMA200']:.1f} Close {last['Close']:.1f}"
    except Exception as e:
        return "NEUTRAL", f"HTF error {e}"

def is_in_killzone():
    try:
        now_utc = datetime.now(timezone.utc)
        hour = now_utc.hour
        london = 7 <= hour <= 11
        ny = 12 <= hour <= 16
        overlap = 12 <= hour <= 14
        if overlap:
            return True, f"KILLZONE OVERLAP LONDON+NY {hour}h UTC (BEST)"
        if london or ny:
            return True, f"KILLZONE {'LONDON' if london else 'NY'} {hour}h UTC"
        return False, f"HORS KILLZONE {hour}h UTC (risque + bruit)"
    except:
        return True, "Killzone check skip"

def has_fvg(df):
    try:
        if len(df) < 10:
            return False, "No FVG check"
        for i in range(len(df)-10, len(df)-1):
            if i < 2:
                continue
            c = df.iloc[i]
            c2 = df.iloc[i-2]
            if c2['High'] < c['Low'] and (c['Low'] - c2['High']) > 1.0:
                return True, f"FVG BULL {c2['High']:.1f}->{c['Low']:.1f} gap {c['Low']-c2['High']:.1f}$"
            if c['High'] < c2['Low'] and (c2['Low'] - c['High']) > 1.0:
                return True, f"FVG BEAR {c['High']:.1f}->{c2['Low']:.1f} gap {c2['Low']-c['High']:.1f}$"
        return False, "Pas de FVG recent"
    except Exception as e:
        return False, f"FVG err {e}"

def find_swing(df, lookback=80):
    if len(df) < lookback:
        return None
    recent = df.tail(lookback)
    high_idx = recent['High'].idxmax()
    low_idx = recent['Low'].idxmin()
    swing_high = float(recent.loc[high_idx, 'High'])
    swing_low = float(recent.loc[low_idx, 'Low'])
    is_bullish_leg = high_idx > low_idx
    return {"high": swing_high, "low": swing_low, "bullish": is_bullish_leg, "df": recent, "high_idx": high_idx, "low_idx": low_idx}

def compute_ote(swing):
    h = swing["high"]
    l = swing["low"]
    rng = h - l
    if swing["bullish"]:
        lower = h - rng*OTE_HIGH
        upper = h - rng*OTE_LOW
        entry = h - rng*OTE_ENTRY
    else:
        lower = l + rng*OTE_LOW
        upper = l + rng*OTE_HIGH
        entry = l + rng*OTE_ENTRY
        if lower > upper:
            lower, upper = upper, lower
    return lower, upper, entry, rng

def calc_levels(swing):
    h = swing["high"]
    l = swing["low"]
    rng = h - l
    lower, upper, entry, _ = compute_ote(swing)
    if swing["bullish"]:
        sl = l - rng * 0.12
        tp1 = h
        tp2 = h + rng * 0.72
        tp3 = h + rng * 1.15
    else:
        sl = h + rng * 0.12
        tp1 = l
        tp2 = l - rng * 0.72
        tp3 = l - rng * 1.15
    return lower, upper, entry, sl, tp1, tp2, tp3, rng

def calc_lot(entry, sl):
    sl_dist = abs(entry - sl)
    if sl_dist > 12:
        return 0.10
    elif sl_dist > 8:
        return 0.15
    else:
        return 0.20

def make_chart(df, swing, tf_label, entry, sl, tp1, tp2, lot, mt5_type, htf_info, kz_info, fvg_info):
    lower, upper, _, rng = compute_ote(swing)
    last_price = float(df['Close'].iloc[-1])
    plt.figure(figsize=(12,6))
    plt.plot(df.index, df['Close'], label='GOLD', linewidth=1.4)
    plt.axhline(swing["high"], color='green', linestyle='--', alpha=0.6, label=f"SWING HIGH {swing['high']:.1f}")
    plt.axhline(swing["low"], color='red', linestyle='--', alpha=0.6, label=f"SWING LOW {swing['low']:.1f}")
    plt.axhspan(lower, upper, color='gold', alpha=0.4, label=f'OTE {OTE_LOW}-{OTE_HIGH} (70.5%={entry:.1f})')
    plt.axhline(entry, color='blue', linestyle='-', linewidth=2, label=f'ENTRY 70.5% {entry:.1f} {mt5_type}')
    plt.axhline(sl, color='red', linestyle='-', linewidth=1.5, label=f'SL {sl:.1f}')
    plt.axhline(tp1, color='limegreen', linestyle='-', linewidth=1.5, label=f'TP1 {tp1:.1f}')
    plt.axhline(tp2, color='darkgreen', linestyle='-', linewidth=1.2, label=f'TP2 {tp2:.1f}')
    plt.scatter([df.index[-1]], [last_price], color='black', zorder=5)
    direction = "LONG BUY" if swing["bullish"] else "SHORT SELL"
    plt.title(f"GOLD {tf_label} {direction} | V5 ICT PRO | LOT {lot} | {htf_info[:40]}")
    plt.legend(fontsize=6.5, loc='upper left')
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
        return
    rr1 = abs(tp1-entry)/abs(entry-sl) if abs(entry-sl)>0 else 0
    rr2 = abs(tp2-entry)/abs(entry-sl) if abs(entry-sl)>0 else 0
    if rr1 < MIN_RR:
        return

    htf_trend, htf_detail = get_htf_trend()
    in_kz, kz_detail = is_in_killzone()
    fvg_ok, fvg_detail = has_fvg(swing["df"])

    if swing["bullish"] and htf_trend == "BEARISH" and rr1 < 2.0:
        return
    if not swing["bullish"] and htf_trend == "BULLISH" and rr1 < 2.0:
        return

    lot = calc_lot(entry, sl)

    if swing["bullish"]:
        direction = "LONG BUY"
        order_type = "BUY / LONG - ACHAT"
        mt5_type = "Buy Limit"
    else:
        direction = "SHORT SELL"
        order_type = "SELL / SHORT - VENTE"
        mt5_type = "Sell Limit"

    buf, _, _, last = make_chart(swing["df"], swing, tf_key, entry, sl, tp1, tp2, lot, mt5_type, htf_detail, kz_detail, fvg_detail)
    in_ote = lower <= last <= upper

    if tf_key in active_trades:
        tr = active_trades[tf_key]
        is_long = tr["bullish"]
        tp1_hit = (last >= tr["tp1"]) if is_long else (last <= tr["tp1"])
        if tp1_hit and not tr.get("be_done"):
            be_msg = f"TP1 TOUCHE {tf_key} V5 PRO - PASSE EN BE\nEntree {tr['entry']:.2f} Lot {tr['lot']}\nTP1 {tr['tp1']:.2f} valide RR {tr.get('rr1',0):.1f}R\nSL {tr['sl']:.2f} -> {tr['entry']:.2f} (BE)\nSplit: 0.10 encaisse, 0.10 runner TP2 {tr['tp2']:.2f}"
            send_msg(be_msg)
            tr["be_done"] = True
            active_trades[tf_key] = tr
        tp2_hit = (last >= tr["tp2"]) if is_long else (last <= tr["tp2"])
        if tp2_hit and tr.get("be_done") and not tr.get("tp2_done"):
            tp2_msg = f"TP2 TOUCHE {tf_key} V5 PRO - SECURISE BE+\n{tr['entry']:.2f} -> {tr['tp2']:.2f} Lot {tr['lot']} RR {tr.get('rr2',0):.1f}R\nPasse SL en BE+: {tr['tp1']:.2f}\nTP3 runner {tr['tp3']:.2f}"
            send_msg(tp2_msg)
            tr["tp2_done"] = True
            active_trades[tf_key] = tr

    ote_status = "DANS OTE 70.5%" if in_ote else "Hors OTE"
    score = 0
    if htf_trend != "NEUTRAL" and ((swing["bullish"] and htf_trend=="BULLISH") or (not swing["bullish"] and htf_trend=="BEARISH")):
        score += 30
    if fvg_ok:
        score += 20
    if in_kz:
        score += 20
    if rr1 >= 2.0:
        score += 20
    if sl_dist <= 12:
        score += 10
    grade = "C"
    if score >= 80:
        grade = "A+ SETUP ICT PRO"
    elif score >= 60:
        grade = "A SETUP"
    elif score >= 40:
        grade = "B SETUP"

    caption = (
        f"{tf_key} SIGNAL OTE V5 ICT PRO {direction} {grade}\n"
        f"{order_type} -> {mt5_type} @ 70.5%\n\n"
        f"Leg: {swing['low']:.1f} -> {swing['high']:.1f} (Range {rng:.1f}$)\n"
        f"OTE PRO: {lower:.2f} - {upper:.2f} | ENTRY 70.5% {entry:.2f} | Prix {last:.2f} {ote_status}\n\n"
        f"=== FILTRES ICT PRO ===\n"
        f"HTF 1H: {htf_trend} | {htf_detail}\n"
        f"Killzone: {kz_detail}\n"
        f"FVG: {fvg_detail}\n"
        f"Score ICT: {score}/100 -> {grade}\n\n"
        f"1000 EUR SAFE V5 PRO:\n"
        f"Lot: {lot} | Risque {RISK_PCT}% = 10E | SL {sl_dist:.1f}$\n\n"
        f"PLAN ICT PRO:\n"
        f"ORDRE: {mt5_type} @ {entry:.2f}\n"
        f"ENTREE PRECISE 70.5%: {entry:.2f}\n"
        f"SL: {sl:.2f} ({sl_dist:.1f}$)\n"
        f"TP1: {tp1:.2f} RR {rr1:.1f}R (50% lot)\n"
        f"TP2: {tp2:.2f} RR {rr2:.1f}R (50% lot runner)\n"
        f"TP3: {tp3:.2f}\n\n"
        f"STRATEGIE: Split 0.10 TP1 -> BE -> 0.10 TP2 runner\n"
        f"{datetime.now().strftime('%H:%M:%S')} UTC"
    )

    if in_ote:
        now = time.time()
        prev = last_signals.get(tf_key)
        if prev:
            same_dir = prev.get("bullish") == swing["bullish"]
            entry_close = abs(prev["entry"] - entry) < 3.0
            time_close = (now - prev["time"]) < 3600
            if same_dir and entry_close and time_close:
                buf.close()
                return
        if score < 30 and rr1 < 1.8:
            buf.close()
            return
        send_photo(buf, caption)
        last_signals[tf_key] = {"entry": entry, "time": now, "bullish": swing["bullish"], "score": score}
        if tf_key not in active_trades or abs(active_trades[tf_key]["entry"] - entry) > 3.0 or active_trades[tf_key]["bullish"] != swing["bullish"]:
            active_trades[tf_key] = {
                "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3, "lot": lot, "rr1": rr1, "rr2": rr2,
                "direction": direction, "bullish": swing["bullish"],
                "be_done": False, "tp2_done": False
            }
    buf.close()

def bot_loop():
    global last_heartbeat, scan_count
    print("Bot GOLD OTE V5.0 ICT PRO 1000E pret")
    time.sleep(2)
    send_msg(f"Bot V5.0 ICT PRO 1000E demarre - CAPITAL {CAPITAL}E - OTE 70.5% PRECISE - HTF 1H + BOS + FVG + Killzone - SL max {MAX_SL_DOLLARS}$ RR min {MIN_RR} Lot {MIN_LOT}-{MAX_LOT} - Winrate vise 75-82%")
    last_heartbeat = time.time()
    while True:
        try:
            for tf in TIMEFRAMES:
                scan_tf(tf)
                scan_count += 1
                time.sleep(5)
            if time.time() - last_heartbeat > 21600:
                df_check = get_data("5m", period="1d")
                price = float(df_check['Close'].iloc[-1]) if not df_check.empty else 0
                htf, htf_d = get_htf_trend()
                hb_msg = (
                    f"HEARTBEAT V5.0 ICT PRO OK - {datetime.now().strftime('%d/%m %H:%M')}\n"
                    f"Gold: {price:.2f}$ | HTF {htf} | Scans {scan_count}\n"
                    f"V5 PRO: OTE 70.5% {OTE_LOW}-{OTE_HIGH} | SL {MAX_SL_DOLLARS}$ RR {MIN_RR} Lot {MIN_LOT}-{MAX_LOT}\n"
                    f"Filtres: HTF 1H + FVG + Killzone + Score ICT\n"
                    f"Bot en vie - winrate vise 75-82% meme nombre trades qualite A"
                )
                send_msg(hb_msg)
                last_heartbeat = time.time()
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
