import yfinance as yf, pandas as pd, numpy as np
from datetime import datetime, timedelta

targets = ['TSLA','AMD','META']
for sym in targets:
    tk = yf.Ticker(sym)
    h = tk.history(start=datetime.now()-timedelta(days=120), interval='1d')
    cur = h['Close'].iloc[-1]

    sma20 = h['Close'].rolling(20).mean().iloc[-1]
    sma50 = h['Close'].rolling(50).mean().iloc[-1] if len(h)>=50 else np.nan
    sma200 = h['Close'].rolling(200).mean().iloc[-1] if len(h)>=200 else np.nan

    ema12 = h['Close'].ewm(span=12, adjust=False).mean()
    ema26 = h['Close'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal

    d = h['Close'].diff()
    g = d.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rsi = 100 - (100/(1+g/l))

    tr1 = h['High'] - h['Low']
    tr2 = abs(h['High'] - h['Close'].shift(1))
    tr3 = abs(h['Low'] - h['Close'].shift(1))
    atr = pd.concat([tr1,tr2,tr3],axis=1).max(axis=1).rolling(14).mean().iloc[-1]

    vol_avg = h['Volume'].rolling(20).mean().iloc[-1]
    vol_today = h['Volume'].iloc[-1]

    highs = h['High'].iloc[-20:].max()
    lows = h['Low'].iloc[-20:].min()

    pivot = (h['High'].iloc[-1] + h['Low'].iloc[-1] + cur) / 3
    r1 = 2*pivot - h['Low'].iloc[-1]
    s1 = 2*pivot - h['High'].iloc[-1]

    fib_382 = lows + 0.382*(highs - lows)
    fib_618 = lows + 0.618*(highs - lows)

    stop = cur - atr*2
    t1 = cur + atr
    t2 = cur + atr*2
    rr1 = (t1-cur)/(cur-stop)
    rr2 = (t2-cur)/(cur-stop)
    risk_dollar = cur - stop
    pos_size = 10000 / risk_dollar

    print(f'=== {sym} FINAL ANALYSIS ===')
    print(f'Price: ${cur:.2f}  Prev: ${h["Close"].iloc[-2]:.2f}  Chg: {((cur-h["Close"].iloc[-2])/h["Close"].iloc[-2]*100):+.2f}%')
    sma_str = f'SMA20: ${sma20:.2f}  SMA50: ${sma50:.2f}  SMA200: ${sma200:.2f}' if not np.isnan(sma200) else f'SMA20: ${sma20:.2f}  SMA50: ${sma50:.2f}'
    print(sma_str)
    print(f'RSI(14): {rsi.iloc[-1]:.1f}  MACD Hist: {hist.iloc[-1]:.4f} (was {hist.iloc[-2]:.4f})')
    print(f'ATR(14): ${atr:.2f} ({atr/cur*100:.2f}%)')
    print(f'20d High: ${highs:.2f}  20d Low: ${lows:.2f}  vs High: {(cur/highs-1)*100:+.2f}%')
    print(f'Fib 38.2%: ${fib_382:.2f}  Fib 61.8%: ${fib_618:.2f}')
    print(f'Pivot: ${pivot:.2f}  R1: ${r1:.2f}  S1: ${s1:.2f}')
    print(f'Vol today: {vol_today:,.0f}  20d avg: {vol_avg:,.0f}  Ratio: {vol_today/vol_avg:.2f}x')
    print(f'--- TRADE LEVELS ---')
    print(f'Entry: Market at ${cur:.2f}  Stop: ${stop:.2f}  Risk: ${risk_dollar:.2f} ({risk_dollar/cur*100:.2f}%)')
    print(f'T1: ${t1:.2f}  T2: ${t2:.2f}  RR={rr1:.1f}:1 and {rr2:.1f}:1')
    print(f'Pos size (1% risk / $10k acct): {pos_size:.0f} shares')
    print()
