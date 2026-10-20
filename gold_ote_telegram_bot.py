1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
27
28
29
30
31
32
33
34
35
36
37
38
39
40
41
42
43
44
45
46
47
48
49
50
51
52
53
54
55
56
57
58
59
60
61
62
63
64
65
66
67
68
69
70
71
72
73
74
75
76
77
78
79
80
81
82
83
84
85
86
87
88
89
90
91
92
93
94
95
96
97
98
99
100
101
102
103
104
105
106
107
108
109
110
111
112
113
114
115
116
117
118
119
120
121
122
123
124
125
126
127
128
129
130
131
132
133
134
135
136
137
138
# GOLD OTE 0.705 - Version Render + UptimeRobot + Graphique
import time, os, yfinance as yf, pandas as pd, numpy as np, requests, io, threading
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime
from flask import Flask

TELEGRAM_BOT_TOKEN = "8860580363:AAERmQTJU9daLNc183_5TQvi3a6S4uC6VuI"
TELEGRAM_CHAT_ID = "1967933915"
SYMBOL_YF = "GC=F"
TIMEFRAMES = ["5m", "15m"]
SWING_LEN = 10
FIB705 = 0.705
EMA_LEN = 100
ATR_LEN = 14
ATR_SL_MULT = 1.5
ALERT_DISTANCE_PCT = 0.003
last_alert = {}

app = Flask(__name__)
@app.route('/')
def home(): return "Bot GOLD OTE 0.705 is running! ✅"
@app.route('/health')
def health(): return "OK", 200

def send_telegram(msg, parse_mode="Markdown"):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": parse_mode}, timeout=10)
    except: pass

def send_telegram_photo(fig, caption):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        buf = io.BytesIO(); fig.savefig(buf, format='png', dpi=150, bbox_inches='tight'); buf.seek(0); plt.close(fig)
        requests.post(url, files={'photo': ('chart.png', buf, 'image/png')}, data={'chat_id': TELEGRAM_CHAT_ID, 'caption': caption, 'parse_mode': 'Markdown'}, timeout=15)
    except: pass

def ema(s, p): return s.ewm(span=p, adjust=False).mean()
def atr(df, period):
    hl = df['High'] - df['Low']
    hc = (df['High'] - df['Close'].shift()).abs()
    lc = (df['Low'] - df['Close'].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def find_last_swings(df):
    lastHigh=None; lastHighIdx=-1; lastLow=None; lastLowIdx=-1
    for i in range(SWING_LEN, min(200, len(df)-SWING_LEN)):
        idx = len(df)-SWING_LEN-i-1
        if idx<0: break
        curH=float(df['High'].iloc[idx]); isHigh=True
        for j in range(1, SWING_LEN+1):
            if float(df['High'].iloc[idx+j])>curH or float(df['High'].iloc[idx-j])>=curH: isHigh=False; break
        if isHigh and lastHigh is None: lastHigh=curH; lastHighIdx=idx
        curL=float(df['Low'].iloc[idx]); isLow=True
        for j in range(1, SWING_LEN+1):
            if float(df['Low'].iloc[idx+j])<curL or float(df['Low'].iloc[idx-j])<=curL: isLow=False; break
        if isLow and lastLow is None: lastLow=curL; lastLowIdx=idx
        if lastHigh is not None and lastLow is not None: break
    return lastHigh, lastHighIdx, lastLow, lastLowIdx

def generate_chart(df, tf, lastHigh, lastLow, ote_level, sl, tp1, tp2, side, ema_val):
    df_plot=df.tail(100).copy()
    fig, ax=plt.subplots(figsize=(10,6))
    ax.plot(df_plot.index, df_plot['Close'], label='Close XAU', color='black', linewidth=1)
    ax.plot(df_plot.index, df_plot['EMA100'], label=f'EMA{EMA_LEN}', color='orange', linewidth=1.2)
    ax.axhline(lastHigh, color='gray', linestyle='--', alpha=0.7, label=f'Swing High {lastHigh:.2f}')
    ax.axhline(lastLow, color='gray', linestyle='--', alpha=0.7, label=f'Swing Low {lastLow:.2f}')
    ax.axhline(ote_level, color='blue', linestyle='-', linewidth=2, label=f'OTE 0.705 {ote_level:.2f}')
    ax.axhline(sl, color='red', linestyle='-', linewidth=1.5, label=f'SL {sl:.2f}')
    ax.axhline(tp1, color='green', linestyle='-', linewidth=1.2, label=f'TP1 {tp1:.2f}')
    ax.axhline(tp2, color='green', linestyle=':', linewidth=1.2, label=f'TP2 {tp2:.2f}')
    rng=abs(lastHigh-lastLow)
    ote62=lastLow+rng*0.62 if side=="LONG" else lastHigh-rng*0.62
    if side=="LONG": ax.axhspan(ote62, ote_level, color='blue', alpha=0.1, label='Zone OTE 0.62-0.705')
    else: ax.axhspan(ote_level, ote62, color='blue', alpha=0.1, label='Zone OTE 0.62-0.705')
    ax.set_title(f'GOLD {tf} - {side} OTE 0.705 - {datetime.now().strftime("%H:%M:%S")}', fontsize=12, fontweight='bold')
    ax.set_ylabel('Prix'); ax.legend(loc='best', fontsize=8); ax.grid(True, alpha=0.3); plt.xticks(rotation=20); plt.tight_layout(); return fig

def scan_tf(tf):
    try:
        df=yf.download(SYMBOL_YF, period="60d", interval=tf, progress=False, auto_adjust=True)
        if df.empty or len(df)<120: return
        if isinstance(df.columns, pd.MultiIndex): df.columns=df.columns.get_level_values(0)
        df=df.dropna(); df['EMA100']=ema(df['Close'], EMA_LEN); df['ATR']=atr(df, ATR_LEN)
        lastHigh, lastHighIdx, lastLow, lastLowIdx=find_last_swings(df)
        if lastHigh is None or lastLow is None: return
        rng=abs(lastHigh-lastLow); ote705_L=lastLow+rng*FIB705; ote705_S=lastHigh-rng*FIB705
        close=float(df['Close'].iloc[-1]); prevClose=float(df['Close'].iloc[-2]); ema_v=float(df['EMA100'].iloc[-1]); atr_val=float(df['ATR'].iloc[-1])
        bearLeg=lastLowIdx>lastHighIdx; bullLeg=lastHighIdx>lastLowIdx
        slLong=lastLow-atr_val*ATR_SL_MULT; tp1Long=lastHigh; tp2Long=lastHigh+rng*0.27
        slShort=lastHigh+atr_val*ATR_SL_MULT; tp1Short=lastLow; tp2Short=lastLow-rng*0.27
        key_base=f"{tf}_{lastHighIdx}_{lastLowIdx}"
        if bearLeg and close>ema_v:
            dist=abs(close-ote705_L)/close
            if dist<ALERT_DISTANCE_PCT and close>ote705_L:
                k=f"{key_base}_LONG_APPROACH"
                if k not in last_alert or time.time()-last_alert[k]>900:
                    send_telegram(f"⚠️ *GOLD {tf} - APPROCHE LONG OTE*\n\nNiveau 0.705: `{ote705_L:.2f}`\nActuel: `{close:.2f}`\nDistance: {dist*100:.2f}%\n\n👉 *Pose ton BUY LIMIT:*\nEntry: `{ote705_L:.2f}`\nSL: `{slLong:.2f}`\nTP1: `{tp1Long:.2f}` -> BE\nTP2: `{tp2Long:.2f}`")
                    fig=generate_chart(df, tf, lastHigh, lastLow, ote705_L, slLong, tp1Long, tp2Long, "LONG", ema_v)
                    send_telegram_photo(fig, f"📊 {tf} LONG Chart - Entry {ote705_L:.2f}"); last_alert[k]=time.time()
            if prevClose<=ote705_L and close>=ote705_L:
                k=f"{key_base}_LONG_ENTRY"
                if k not in last_alert or time.time()-last_alert[k]>1800:
                    send_telegram(f"🎯 *GOLD {tf} - LONG 0.705 TOUCHÉ* `{ote705_L:.2f}`\nSL `{slLong:.2f}` TP1 `{tp1Long:.2f}` TP2 `{tp2Long:.2f}`")
                    fig=generate_chart(df, tf, lastHigh, lastLow, ote705_L, slLong, tp1Long, tp2Long, "LONG", ema_v)
                    send_telegram_photo(fig, f"🎯 {tf} LONG TOUCHE - {ote705_L:.2f}"); last_alert[k]=time.time()
        if bullLeg and close<ema_v:
            dist=abs(close-ote705_S)/close
            if dist<ALERT_DISTANCE_PCT and close<ote705_S:
                k=f"{key_base}_SHORT_APPROACH"
                if k not in last_alert or time.time()-last_alert[k]>900:
                    send_telegram(f"⚠️ *GOLD {tf} - APPROCHE SHORT OTE*\n\nNiveau 0.705: `{ote705_S:.2f}`\nActuel: `{close:.2f}`\nDistance: {dist*100:.2f}%\n\n👉 *Pose ton SELL LIMIT:*\nEntry: `{ote705_S:.2f}`\nSL: `{slShort:.2f}`\nTP1: `{tp1Short:.2f}` -> BE\nTP2: `{tp2Short:.2f}`")
                    fig=generate_chart(df, tf, lastHigh, lastLow, ote705_S, slShort, tp1Short, tp2Short, "SHORT", ema_v)
                    send_telegram_photo(fig, f"📊 {tf} SHORT Chart - Entry {ote705_S:.2f}"); last_alert[k]=time.time()
            if prevClose>=ote705_S and close<=ote705_S:
                k=f"{key_base}_SHORT_ENTRY"
                if k not in last_alert or time.time()-last_alert[k]>1800:
                    send_telegram(f"🎯 *GOLD {tf} - SHORT 0.705 TOUCHÉ* `{ote705_S:.2f}`\nSL `{slShort:.2f}` TP1 `{tp1Short:.2f}` TP2 `{tp2Short:.2f}`")
                    fig=generate_chart(df, tf, lastHigh, lastLow, ote705_S, slShort, tp1Short, tp2Short, "SHORT", ema_v)
                    send_telegram_photo(fig, f"🎯 {tf} SHORT TOUCHE - {ote705_S:.2f}"); last_alert[k]=time.time()
    except Exception as e: print(f"Scan {tf} error: {e}")

def bot_loop():
    print("Bot GOLD OTE 0.705 5m/15m + Graphique démarré...")
    send_telegram("✅ *Bot GOLD OTE 0.705 démarré*\nScan 5m + 15m + Graphique - UptimeRobot ON")
    while True:
        try:
            for tf in TIMEFRAMES: scan_tf(tf); time.sleep(2)
            time.sleep(5)
        except Exception as e: print("Loop error:", e); time.sleep(10)

if __name__=="__main__":
    th
