import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

print(f"=== SWING SCAN 2026-07-01 14:32 UTC ===\n")

end = datetime.now()
start = end - timedelta(days=90)

candidates = ['AAPL','MSFT','NVDA','AMZN','GOOGL','META','TSLA','AVGO','ORCL',
              'AMD','ADBE','CRM','NFLX','COST','LIN','CSCO','INTU','AMAT','TXN','MU']

results = []
for sym in candidates:
    try:
        tk = yf.Ticker(sym)
        h = tk.history(start=start, end=end, interval='1d')
        if h.empty or len(h) < 30:
            continue
        cur = h['Close'].iloc[-1]
        prev = h['Close'].iloc[-2] if len(h) > 1 else cur
        chg1d = (cur - prev) / prev * 100
        chg5d = (cur - h['Close'].iloc[-6]) / h['Close'].iloc[-6] * 100 if len(h) > 5 else 0
        chg20d = (cur - h['Close'].iloc[-21]) / h['Close'].iloc[-21] * 100 if len(h) > 20 else 0

        sma20 = h['Close'].rolling(20).mean().iloc[-1]
        sma50 = h['Close'].rolling(50).mean().iloc[-1] if len(h) >= 50 else np.nan
        sma200 = h['Close'].rolling(200).mean().iloc[-1] if len(h) >= 200 else np.nan

        deltas = h['Close'].diff()
        gain = deltas.clip(lower=0).rolling(14).mean()
        loss = (-deltas.clip(upper=0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + gain / loss))
        rsi_val = rsi.iloc[-1]

        ema12 = h['Close'].ewm(span=12).mean().iloc[-1]
        ema26 = h['Close'].ewm(span=26).mean().iloc[-1]
        macd_line = ema12 - ema26
        macd_signal = pd.Series(ema12 - ema26).ewm(span=9).mean().iloc[-1]
        macd_hist = macd_line - macd_signal

        tr1 = h['High'] - h['Low']
        tr2 = abs(h['High'] - h['Close'].shift(1))
        tr3 = abs(h['Low'] - h['Close'].shift(1))
        atr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(14).mean().iloc[-1]

        vol_avg = h['Volume'].rolling(50).mean().iloc[-1]
        vol_today = h['Volume'].iloc[-1]
        vol_ratio = vol_today / vol_avg if vol_avg > 0 else 1

        score = 0
        if cur > sma20:
            score += 1
        if not np.isnan(sma50) and cur > sma50:
            score += 1
        if not np.isnan(sma200) and cur > sma200:
            score += 1
        if rsi_val >= 40 and rsi_val <= 68:
            score += 1
        if rsi_val < 35:
            score += 0.5
        if macd_hist > 0:
            score += 1
        if vol_ratio > 1.1:
            score += 1
        if chg5d > 3:
            score += 1
        if chg20d > 0:
            score += 1

        highs_20 = h['High'].iloc[-20:].max()
        near_high = (cur > 0.97 * highs_20)
        near_low = (cur < 1.03 * h['Low'].iloc[-20:].min())

        results.append({
            'SYM': sym,
            'Price': cur,
            '1d': chg1d,
            '5d': chg5d,
            '20d': chg20d,
            'RSI': rsi_val,
            'ATR': atr,
            'ATR_pct': atr / cur * 100,
            'VolR': vol_ratio,
            'Score': score,
            'SMA20': sma20,
            'SMA50': sma50,
            'SMA200': sma200,
            'Abv20': cur > sma20,
            'Abv50': not np.isnan(sma50) and cur > sma50,
            'Abv200': not np.isnan(sma200) and cur > sma200,
            'MACD_hist': macd_hist,
            'NearHigh': near_high,
            'NearLow': near_low,
        })
    except Exception as e:
        print(f"  ERROR {sym}: {e}")

df = pd.DataFrame(results)
if df.empty:
    print("No data retrieved.")
    exit()

df = df.sort_values('Score', ascending=False)

print("FULL RANKING:")
print(f"{'SYM':<6} {'Price':>8} {'1d%':>6} {'5d%':>6} {'20d%':>6} {'RSI':>5} {'ATR%':>5} {'VolR':>5} {'Score':>5} {'Abv20':>5} {'Abv50':>5} {'Abv200':>6} {'MACD':>6} {'NearH':>5}")
print("-" * 100)
for _, r in df.iterrows():
    print(f"{r['SYM']:<6} {r['Price']:>8.2f} {r['1d']:>6.2f} {r['5d']:>6.2f} {r['20d']:>6.2f} {r['RSI']:>5.1f} {r['ATR_pct']:>5.2f} {r['VolR']:>5.2f} {r['Score']:>5.1f} {str(r['Abv20']):>5} {str(r['Abv50']):>5} {str(r['Abv200']):>6} {r['MACD_hist']:>6.3f} {str(r['NearHigh']):>5}")

print()
print("=" * 80)
print("TOP 3 SWING TRADE SETUPS")
print("=" * 80)
for i, (_, r) in enumerate(df.head(3).iterrows()):
    stop = r['Price'] - r['ATR'] * 2
    t1 = r['Price'] + r['ATR']
    t2 = r['Price'] + r['ATR'] * 2
    rr1 = (t1 - r['Price']) / (r['Price'] - stop)
    rr2 = (t2 - r['Price']) / (r['Price'] - stop)
    risk_dollar = r['Price'] - stop
    print(f"\n--- SETUP #{i+1}: {r['SYM']} ---")
    print(f"  Score: {r['Score']:.1f}/9")
    print(f"  Price: ${r['Price']:.2f}")
    print(f"  1d={r['1d']:+.2f}%, 5d={r['5d']:+.2f}%, 20d={r['20d']:+.2f}%")
    print(f"  RSI(14)={r['RSI']:.1f}, MACD_hist={r['MACD_hist']:.3f} (bullish)" if r['MACD_hist'] > 0 else f"  RSI(14)={r['RSI']:.1f}, MACD_hist={r['MACD_hist']:.3f} (bearish)")
    print(f"  ATR(14): ${r['ATR']:.2f} ({r['ATR_pct']:.2f}%)")
    print(f"  SMA20: ${r['SMA20']:.2f}, SMA50: ${r['SMA50']:.2f}" if not np.isnan(r['SMA50']) else f"  SMA20: ${r['SMA20']:.2f}")
    print(f"  Above SMA20: {r['Abv20']}, Above SMA50: {r['Abv50']}, Above SMA200: {r['Abv200']}")
    print(f"  Vol ratio: {r['VolR']:.2f}x 50-day avg")
    print(f"  Near 20d High: {r['NearHigh']}")
    print(f"  --- LEVELS ---")
    print(f"  Stop Loss: ${stop:.2f} (Risk: ${risk_dollar:.2f}, {r['ATR_pct']*2:.2f}%)")
    print(f"  T1 (1x ATR): ${t1:.2f} | RR={rr1:.1f}:1")
    print(f"  T2 (2x ATR): ${t2:.2f} | RR={rr2:.1f}:1")
