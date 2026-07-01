import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

print(f"=== SWING SCAN {datetime.now().strftime('%Y-%m-%d %H:%M')} ===\n")

end = datetime.now()
start = end - timedelta(days=90)

# ── Key Indices ─────────────────────────────────────────────────────────────
indices = {
    'QQQ': 'Nasdaq 100 ETF',
    'SPY': 'S&P 500 ETF',
    'IWM': 'Russell 2000 ETF',
    '^VIX': 'CBOE Volatility Index',
}
print("=== INDEX SNAPSHOT ===")
for sym, name in indices.items():
    try:
        tk = yf.Ticker(sym)
        h = tk.history(start=start, end=end, interval='1d')
        if h.empty:
            print(f"  {sym} ({name}): No data")
            continue
        cur = h['Close'].iloc[-1]
        prev = h['Close'].iloc[-2] if len(h) > 1 else cur
        chg = (cur - prev) / prev * 100
        # SMAs
        sma20 = h['Close'].rolling(20).mean().iloc[-1]
        sma50 = h['Close'].rolling(50).mean().iloc[-1] if len(h) >= 50 else np.nan
        sma200 = h['Close'].rolling(200).mean().iloc[-1] if len(h) >= 200 else np.nan
        # RSI
        deltas = h['Close'].diff()
        gain = deltas.clip(lower=0).rolling(14).mean()
        loss = (-deltas.clip(upper=0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + gain/loss))
        rsi_val = rsi.iloc[-1]
        # ATR
        tr1 = h['High'] - h['Low']
        tr2 = abs(h['High'] - h['Close'].shift(1))
        tr3 = abs(h['Low'] - h['Close'].shift(1))
        atr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(14).mean().iloc[-1]

        above_sma20 = cur > sma20
        above_sma200 = not np.isnan(sma200) and cur > sma200
        regime = "BULL" if above_sma200 and above_sma20 else ("BEAR" if not above_sma200 else "TRANSITIONAL")

        print(f"  {sym} ({name})")
        print(f"    Price: ${cur:.2f}  Change: {chg:+.2f}%")
        print(f"    SMA20: ${sma20:.2f}  SMA50: ${sma50:.2f}  SMA200: ${sma200:.2f}")
        print(f"    Above SMA20: {above_sma20}  Above SMA200: {above_sma200}")
        print(f"    RSI(14): {rsi_val:.1f}  ATR(14): ${atr:.2f} ({atr/cur*100:.2f}%)")
        print(f"    Regime: {regime}")
        print()
    except Exception as e:
        print(f"  {sym}: Error - {e}\n")

# ── Top NASDAQ 100 Components ───────────────────────────────────────────────
nasdaq100_tops = [
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA',
    'AVGO', 'ORCL', 'AMD', 'ADBE', 'CRM', 'NFLX', 'COST',
    'LIN', 'CSCO', 'INTU', 'AMAT', 'TXN', 'MU'
]
print("=== NASDAQ 100 COMPONENT SCAN ===\n")

results = []
for sym in nasdaq100_tops:
    try:
        tk = yf.Ticker(sym)
        h = tk.history(start=start, end=end, interval='1d')
        if h.empty or len(h) < 30:
            continue
        cur = h['Close'].iloc[-1]
        prev = h['Close'].iloc[-2] if len(h) > 1 else cur
        chg_1d = (cur - prev) / prev * 100
        chg_5d = (cur - h['Close'].iloc[-6]) / h['Close'].iloc[-6] * 100 if len(h) > 5 else 0
        chg_20d = (cur - h['Close'].iloc[-21]) / h['Close'].iloc[-21] * 100 if len(h) > 20 else 0

        sma20 = h['Close'].rolling(20).mean().iloc[-1]
        sma50 = h['Close'].rolling(50).mean().iloc[-1] if len(h) >= 50 else np.nan
        sma200 = h['Close'].rolling(200).mean().iloc[-1] if len(h) >= 200 else np.nan

        # RSI
        deltas = h['Close'].diff()
        gain = deltas.clip(lower=0).rolling(14).mean()
        loss = (-deltas.clip(upper=0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + gain/loss))
        rsi_val = rsi.iloc[-1]

        # MACD
        ema12 = h['Close'].ewm(span=12).mean().iloc[-1]
        ema26 = h['Close'].ewm(span=26).mean().iloc[-1]
        macd_line = ema12 - ema26
        macd_signal = pd.Series(ema12 - ema26).ewm(span=9).mean().iloc[-1]
        macd_hist = macd_line - macd_signal

        # ATR
        tr1 = h['High'] - h['Low']
        tr2 = abs(h['High'] - h['Close'].shift(1))
        tr3 = abs(h['Low'] - h['Close'].shift(1))
        atr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(14).mean().iloc[-1]

        # Volume relative to 50-day avg
        vol_avg = h['Volume'].rolling(50).mean().iloc[-1]
        vol_today = h['Volume'].iloc[-1]
        vol_ratio = vol_today / vol_avg if vol_avg > 0 else 1

        above_sma20 = cur > sma20
        above_sma50 = not np.isnan(sma50) and cur > sma50
        above_sma200 = not np.isnan(sma200) and cur > sma200

        # Score: bullish if above MAs, RSI in sweet spot, MACD bullish, vol expanding
        score = 0
        if above_sma20: score += 1
        if above_sma50: score += 1
        if above_sma200: score += 1
        if 40 <= rsi_val <= 70: score += 1  # room to run
        if rsi_val < 30: score += 1  # oversold bounce potential
        if macd_hist > 0: score += 1
        if vol_ratio > 1.2: score += 1
        if chg_5d > 3: score += 1  # recent momentum

        results.append({
            'Symbol': sym,
            'Price': cur,
            'Chg_1d': chg_1d,
            'Chg_5d': chg_5d,
            'Chg_20d': chg_20d,
            'SMA20': sma20,
            'SMA50': sma50,
            'SMA200': sma200,
            'Above_SMA20': above_sma20,
            'Above_SMA50': above_sma50,
            'Above_SMA200': above_sma200,
            'RSI': rsi_val,
            'MACD_hist': macd_hist,
            'ATR': atr,
            'ATR_pct': atr/cur*100,
            'Vol_ratio': vol_ratio,
            'Score': score,
        })
    except Exception as e:
        pass

df = pd.DataFrame(results)
if not df.empty:
    df = df.sort_values('Score', ascending=False)
    print(f"{'SYM':<6} {'Price':>8} {'1d%':>6} {'5d%':>6} {'20d%':>6} {'RSI':>6} {'ATR%':>5} {'VolR':>5} {'Score':>5} {'SMA20':>8} {'SMA200':>8} {'Abv20':>5} {'Abv200':>6}")
    print("-" * 110)
    for _, row in df.iterrows():
        print(f"{row['Symbol']:<6} {row['Price']:>8.2f} {row['Chg_1d']:>6.2f} {row['Chg_5d']:>6.2f} {row['Chg_20d']:>6.2f} {row['RSI']:>6.1f} {row['ATR_pct']:>5.2f} {row['Vol_ratio']:>5.2f} {row['Score']:>5} {row['SMA20']:>8.2f} {row['SMA200']:>8.2f} {str(row['Above_SMA20']):>5} {str(row['Above_SMA200']):>6}")

    print("\n=== TOP 5 SCORE SUMMARY ===")
    for _, row in df.head(5).iterrows():
        print(f"\n  {row['Symbol']}: Score={row['Score']}/8, Price=${row['Price']:.2f}")
        print(f"    1d={row['Chg_1d']:+.2f}%, 5d={row['Chg_5d']:+.2f}%, 20d={row['Chg_20d']:+.2f}%")
        print(f"    RSI={row['RSI']:.1f}, MACD_hist={row['MACD_hist']:.3f}, ATR={row['ATR_pct']:.2f}%")
        print(f"    Above SMA20: {row['Above_SMA20']}, SMA50: {row['Above_SMA50']}, SMA200: {row['Above_SMA200']}")
        print(f"    Vol ratio: {row['Vol_ratio']:.2f}x avg")
else:
    print("  No data retrieved.")

print("\n=== DONE ===")
