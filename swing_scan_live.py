import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json

print(f"SWING SCAN — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}\n")

end = datetime.now()
start = end - timedelta(days=90)

def get_data(sym):
    tk = yf.Ticker(sym)
    df = tk.history(start=start, end=end, interval='1d')
    return df

def compute_rsi(series, n=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(n).mean()
    loss = (-delta.clip(upper=0)).rolling(n).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def compute_atr(df, n=14):
    tr = pd.concat([
        df['High'] - df['Low'],
        (df['High'] - df['Close'].shift()).abs(),
        (df['Low'] - df['Close'].shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(n).mean().iloc[-1]

def compute_macd(series, f=12, s=26, sig=9):
    ema_f = series.ewm(span=f, adjust=False).mean()
    ema_s = series.ewm(span=s, adjust=False).mean()
    macd = ema_f - ema_s
    signal = macd.ewm(span=sig, adjust=False).mean()
    return macd.iloc[-1], signal.iloc[-1]

def score_stock(cur, sma20, sma50, rsi, macd_val, vol, avg_vol, chg5d):
    score = 0
    if cur > sma50: score += 3
    if cur > sma20: score += 1
    if 42 <= rsi <= 58: score += 3
    elif rsi > 72 or rsi < 32: score += 1
    else: score += 2
    if macd_val > 0: score += 3
    elif macd_val > -1: score += 1
    if vol > avg_vol * 1.2: score += 2
    elif vol > avg_vol * 0.8: score += 1
    if chg5d > 0: score += 2
    if rsi < 68: score += 1
    return score

# ── Core Index Data ─────────────────────────────────────────────
indices = {'QQQ': 'Nasdaq 100 ETF', 'SPY': 'S&P 500 ETF', 'IWM': 'Russell 2000 ETF', '^VIX': 'CBOE VIX', 'TLT': '20+ Yr Treasury ETF'}

print("=== INDEX SNAPSHOT ===")
index_data = {}
for sym, name in indices.items():
    df = get_data(sym)
    if df.empty:
        print(f"  {sym}: NO DATA"); continue
    cur = df['Close'].iloc[-1]
    prev = df['Close'].iloc[-2] if len(df) > 1 else cur
    chg = (cur - prev) / prev * 100
    sma20 = df['Close'].rolling(20).mean().iloc[-1]
    sma50 = df['Close'].rolling(50).mean().iloc[-1]
    rsi = compute_rsi(df['Close'], 14).iloc[-1]
    atr = compute_atr(df, 14)
    regime = "BULL" if cur > sma50 else "BEAR"
    # Market structure
    highs = df['High'].iloc[-20:]
    lows = df['Low'].iloc[-20:]
    hh = highs.nlargest(5).iloc[-1]
    ll = lows.nsmallest(5).iloc[-1]
    structure = "LH/LL (BEAR)" if highs.iloc[-1] < highs.iloc[-5] else "HH/HL (BULL)"
    index_data[sym] = {'close': cur, 'chg': chg, 'sma20': sma20, 'sma50': sma50,
                       'rsi': rsi, 'atr': atr, 'regime': regime, 'structure': structure,
                       'vol': df['Volume'].iloc[-1], 'avg_vol': df['Volume'].rolling(20).mean().iloc[-1]}
    print(f"  {sym:6s}: ${cur:8.2f} | {chg:+.2f}% | SMA50 ${sma50:8.2f} | RSI {rsi:5.1f} | ATR ${atr:.2f} | {regime} | {structure}")

# ── NASDAQ 100 Component Scan ───────────────────────────────────
candidates = [
    'AAPL','MSFT','NVDA','AMZN','GOOGL','META','TSLA','AVGO','ORCL',
    'AMD','ADBE','CRM','NFLX','COST','LIN','CSCO','INTU','AMAT','TXN','MU',
    'PYPL','QCOM','AMAT','KLAC','LRCX','SNPS','CDNS','MRVL','PANW','CRWD',
    'NOW','TEAM','DDOG','NET','SNOW','ZS','HUBS','MELI','BKNG','ORLY',
    'ADP','HON','MDLZ','KDP','FAST','CTAS','EA','NXPI','INTC','GILD',
    'VRTX','REGN','BIIB','IDXX','DXCM','ISRG','GEHC','ABB','CPRT','PAYX',
]

print(f"\n=== NASDAQ 100 COMPONENT SCAN ({len(candidates)} tickers) ===")
results = []
for sym in candidates:
    try:
        df = get_data(sym)
        if df.empty or len(df) < 30: continue
        cur = df['Close'].iloc[-1]
        prev = df['Close'].iloc[-2] if len(df) > 1 else cur
        chg1d = (cur - prev) / prev * 100
        chg5d = (cur - df['Close'].iloc[-6]) / df['Close'].iloc[-6] * 100 if len(df) > 5 else 0
        chg20d = (cur - df['Close'].iloc[-21]) / df['Close'].iloc[-21] * 100 if len(df) > 20 else 0
        sma20 = df['Close'].rolling(20).mean().iloc[-1]
        sma50 = df['Close'].rolling(50).mean().iloc[-1]
        sma200 = df['Close'].rolling(200).mean().iloc[-1] if len(df) >= 200 else np.nan
        vol = df['Volume'].iloc[-1]
        avg_vol = df['Volume'].rolling(20).mean().iloc[-1]
        vol_ratio = vol / avg_vol if avg_vol > 0 else 1
        rsi = compute_rsi(df['Close'], 14).iloc[-1]
        macd_val, signal = compute_macd(df['Close'])
        atr = compute_atr(df, 14)
        low20 = df['Low'].rolling(20).min().iloc[-1]
        high20 = df['High'].rolling(20).max().iloc[-1]
        range_pos = (cur - low20) / (high20 - low20) if high20 > low20 else 0.5
        score = score_stock(cur, sma20, sma50, rsi, macd_val, vol, avg_vol, chg5d)
        results.append({
            'sym': sym, 'close': cur, 'chg1d': chg1d, 'chg5d': chg5d, 'chg20d': chg20d,
            'sma20': sma20, 'sma50': sma50, 'sma200': sma200,
            'rsi': rsi, 'macd': macd_val, 'atr': atr, 'vol_ratio': vol_ratio,
            'range_pos': range_pos, 'score': score, 'vol': vol, 'avg_vol': avg_vol,
            'low20': low20, 'high20': high20, 'signal': signal
        })
    except Exception as e:
        print(f"  {sym}: ERROR {e}")

results_df = pd.DataFrame(results)
results_df = results_df.sort_values('score', ascending=False)

print(f"\n{'SYM':6s} {'SCORE':5s} {'PRICE':8s} {'1D%':6s} {'5D%':6s} {'20D%':6s} {'RSI':5s} {'MACD':8s} {'VolR':5s} {'RP':5s} {'SMA50':8s}")
for _, row in results_df.head(20).iterrows():
    above = "ABOVE" if row['close'] > row['sma50'] else "BELOW"
    print(f"{row['sym']:6s} {row['score']:5.0f} ${row['close']:7.2f} {row['chg1d']:+5.2f}% {row['chg5d']:+5.2f}% {row['chg20d']:+5.2f}% {row['rsi']:5.1f} {row['macd']:+8.4f} {row['vol_ratio']:5.1f}x {row['range_pos']:5.2f} {above}")

# ── Top 3 Detailed Breakdowns ───────────────────────────────────
print("\n" + "="*70)
print("TOP 3 SWING TRADE SETUPS — DETAILED ANALYSIS")
print("="*70)

sector_map = {
    'AAPL': 'Technology', 'MSFT': 'Technology', 'NVDA': 'Semiconductors', 'GOOGL': 'Technology',
    'META': 'Technology', 'AMZN': 'Consumer Disc.', 'TSLA': 'Auto/Tech', 'ADBE': 'Technology',
    'CRM': 'Technology', 'NFLX': 'Communication', 'ORCL': 'Technology', 'AMD': 'Semiconductors',
    'AVGO': 'Semiconductors', 'QCOM': 'Semiconductors', 'AMAT': 'Semiconductors',
    'KLAC': 'Semiconductors', 'LRCX': 'Semiconductors', 'SNPS': 'Technology',
    'CDNS': 'Technology', 'INTC': 'Semiconductors', 'MU': 'Semiconductors',
    'TXN': 'Semiconductors', 'MRVL': 'Semiconductors', 'PANW': 'Cybersecurity',
    'CRWD': 'Cybersecurity', 'NOW': 'Technology', 'TEAM': 'Technology', 'DDOG': 'Technology',
    'NET': 'Technology', 'SNOW': 'Technology', 'ZS': 'Cybersecurity', 'HUBS': 'Technology',
    'MELI': 'FinTech', 'BKNG': 'Consumer Disc.', 'ORLY': 'Consumer Disc.',
    'ADP': 'IT Services', 'HON': 'Industrials', 'MDLZ': 'Staples', 'KDP': 'Staples',
    'FAST': 'Industrials', 'CTAS': 'Industrials', 'EA': 'Gaming', 'NXPI': 'Semiconductors',
    'PYPL': 'FinTech', 'CSCO': 'Comm Equipment', 'INTU': 'Technology', 'LIN': 'Industrials',
    'COST': 'Consumer Staples', 'VRTX': 'Biotech', 'REGN': 'Biotech', 'DXCM': 'Biotech',
    'ISRG': 'Medical Tech', 'GEHC': 'Medical Tech', 'CPRT': 'Industrials', 'PAYX': 'IT Services',
}

for rank, (_, row) in enumerate(results_df.head(3).iterrows(), 1):
    sym = row['sym']
    entry = row['close']
    atr = row['atr']
    sl_stop = entry - (atr * 2)
    sl_break_pct = (atr * 2) / entry * 100
    t1 = entry + (atr * 2) * 2
    t2 = entry + (atr * 2) * 3
    t1_pct = (t1 - entry) / entry * 100
    t2_pct = (t2 - entry) / entry * 100
    risk_per_share = entry - sl_stop
    rr1 = (t1 - entry) / risk_per_share
    rr2 = (t2 - entry) / risk_per_share
    sector = sector_map.get(sym, 'Other')
    
    print(f"\n{'='*70}")
    print(f"SETUP #{rank}: {sym} [{sector}]")
    print(f"{'='*70}")
    print(f"  PRICE & MOMENTUM:")
    print(f"    Current:      ${entry:.2f}")
    print(f"    1-Day Chg:    {row['chg1d']:+.2f}%")
    print(f"    5-Day Chg:    {row['chg5d']:+.2f}%")
    print(f"    20-Day Chg:   {row['chg20d']:+.2f}%")
    print(f"    RSI(14):      {row['rsi']:.1f} {'(NEUTRAL)' if 42 <= row['rsi'] <= 58 else '(BULLISH)' if row['rsi'] < 60 else '(OVERBOUGHT)'}")
    print(f"    MACD:         {row['macd']:+.4f} (Signal: {row['signal']:+.4f}) — {'POSITIVE' if row['macd'] > row['signal'] else 'NEGATIVE'}")
    print(f"  TECHNICAL LEVELS:")
    print(f"    SMA20:        ${row['sma20']:.2f} | {'ABOVE' if entry > row['sma20'] else 'BELOW'}")
    print(f"    SMA50:        ${row['sma50']:.2f} | {'ABOVE' if entry > row['sma50'] else 'BELOW'}")
    print(f"    SMA200:       ${row['sma200']:.2f}" if not np.isnan(row['sma200']) else f"    SMA200:       N/A")
    print(f"    20d Range:    ${row['low20']:.2f} — ${row['high20']:.2f}")
    print(f"    Range Pos:   {row['range_pos']:.2f} {'(MID-RANGE)' if 0.3 <= row['range_pos'] <= 0.7 else '(NEAR TOP)' if row['range_pos'] > 0.7 else '(NEAR BOTTOM)'}")
    print(f"  VOLUME:")
    print(f"    Today:        {row['vol']/1e6:.1f}M | Avg20d: {row['avg_vol']/1e6:.1f}M | Ratio: {row['vol_ratio']:.1f}x")
    print(f"  RISK PARAMETERS:")
    print(f"    ATR(14):      ${atr:.2f} ({atr/entry*100:.1f}% of price)")
    print(f"    Stop Loss:   ${sl_stop:.2f} ({sl_break_pct:.1f}% below entry)")
    print(f"    Risk/Share:  ${risk_per_share:.2f}")
    print(f"    T1 (2:1):     ${t1:.2f} ({t1_pct:+.1f}%) — R/R: {rr1:.1f}:1")
    print(f"    T2 (3:1):     ${t2:.2f} ({t2_pct:+.1f}%) — R/R: {rr2:.1f}:1")
    print(f"  INVALUATION TRIGGERS:")
    print(f"    1. Close below ${row['low20']:.2f} (20d low)")
    print(f"    2. QQQ breaks below SMA50")
    print(f"    3. Macro regime shifts to BEAR")

# ── Sector Rotation Summary ─────────────────────────────────────
print(f"\n{'='*70}")
print("SECTOR ROTATION — TOP 10 SETUPS")
print("="*70)
sector_counts = {}
for _, row in results_df.head(10).iterrows():
    sec = sector_map.get(row['sym'], 'Other')
    sector_counts[sec] = sector_counts.get(sec, 0) + 1
for sec, cnt in sorted(sector_counts.items(), key=lambda x: -x[1]):
    bar = "█" * cnt
    print(f"  {sec:20s}: {bar} ({cnt})")

# ── VIX & Macro Context ─────────────────────────────────────────
print(f"\n{'='*70}")
print("MACRO CONTEXT")
print("="*70)
if '^VIX' in index_data:
    vix = index_data['^VIX']
    print(f"  VIX: ${vix['close']:.2f} ({vix['chg']:+.2f}%) — {'LOW VOL = BULL CONFIRMATION' if vix['close'] < 20 else 'ELEVATED VOL = CAUTION'}")
if 'QQQ' in index_data:
    qqq = index_data['QQQ']
    print(f"  QQQ: ${qqq['close']:.2f} ({qqq['chg']:+.2f}%) — Regime: {qqq['regime']}")
    print(f"  QQQ Structure: {qqq['structure']}")
if 'IWM' in index_data:
    iwm = index_data['IWM']
    print(f"  IWM: ${iwm['close']:.2f} ({iwm['chg']:+.2f}%) — {'SMALL CAP CONFIRMING BULL' if iwm['chg'] > 0 else 'SMALL CAP LAGGING'}")

# Save market data
output = {}
for sym in ['QQQ', 'SPY', 'IWM', '^VIX']:
    if sym in index_data:
        output[sym] = {k: float(v) if isinstance(v, (np.floating, float)) else v 
                      for k, v in index_data[sym].items()}
        output[sym]['atr'] = float(output[sym]['atr'])
        output[sym]['vol'] = int(output[sym]['vol'])
        output[sym]['avg_vol'] = int(output[sym]['avg_vol'])

with open('/opt/data/handbook/market_data_live.json', 'w') as f:
    json.dump(output, f, indent=2)

results_df.to_csv('/opt/data/handbook/scan_results_live.csv', index=False)
print("\n[Data saved to market_data_live.json and scan_results_live.csv]")
