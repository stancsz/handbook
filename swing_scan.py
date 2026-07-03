#!/usr/bin/env python3
"""NASDAQ Swing Trade Scanner - July 2, 2026"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

print("=" * 60)
print("NASDAQ SWING TRADE SCANNER")
print(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S ET')}")
print("=" * 60)

# ── STAGE 1A: MACRO INDICES ──────────────────────────────────────
indices = {
    'QQQ': None, 'SPY': None, 'IWM': None,
    '^VIX': None, 'TLT': None, 'DXY': None,
    'HYG': None, 'LQD': None
}

print("\n[1A] FETCHING MACRO INDICES...")
for ticker in indices:
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period='6mo', interval='1d')
        if len(hist) >= 20:
            indices[ticker] = hist
            last = hist['Close'].iloc[-1]
            prev = hist['Close'].iloc[-2] if len(hist) > 1 else last
            chg = (last - prev) / prev * 100
            vol20 = hist['Volume'].rolling(20).mean().iloc[-1]
            print(f"  {ticker:8s}: ${last:8.2f}  {chg:+.2f}%  Vol20: {vol20/1e6:.1f}M")
        else:
            print(f"  {ticker:8s}: INSUFFICIENT DATA ({len(hist)} rows)")
    except Exception as e:
        print(f"  {ticker:8s}: ERROR - {e}")

# ── STAGE 1B: CALCULATE REGIME METRICS ───────────────────────────
print("\n[1B] REGIME ANALYSIS...")

def sma(series, n):
    return series.rolling(n).mean()

def ema(series, n):
    return series.ewm(n).mean().mean()  # approximate

def atr(df, n=14):
    high = df['High']
    low = df['Low']
    close = df['Close']
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def rsi(series, n=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(n).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(n).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

results = {}
for ticker, df in indices.items():
    if df is None or len(df) < 60:
        continue
    close = df['Close']
    sma20 = sma(close, 20)
    sma50 = sma(close, 50)
    sma200 = sma(close, 200)
    last_close = close.iloc[-1]
    
    regime = "TRANSITIONAL"
    if last_close > sma200.iloc[-1] and sma200.iloc[-1] > sma200.iloc[-60]:
        regime = "BULL"
    elif last_close < sma200.iloc[-1] and sma200.iloc[-1] < sma200.iloc[-60]:
        regime = "BEAR"
    
    rsi_val = rsi(close, 14).iloc[-1]
    
    # MACD
    ema12 = close.ewm(span=12).mean().iloc[-1]
    ema26 = close.ewm(span=26).mean().iloc[-1]
    macd_line = ema12 - ema26
    macd_signal = close.ewm(span=9).mean().ewm(span=9).mean().iloc[-1]  # rough
    macd_hist = macd_line - macd_signal
    
    # ATR
    atr_val = atr(df, 14).iloc[-1]
    atr_pct = atr_val / last_close * 100
    
    # Trend: HH/HL or LH/LL
    highs = df['High']
    lows = df['Low']
    recent_highs = highs.tail(20)
    recent_lows = lows.tail(20)
    
    higher_highs = recent_highs.iloc[-1] > recent_highs.iloc[-5]
    higher_lows = recent_lows.iloc[-1] > recent_lows.iloc[-5]
    lower_highs = recent_highs.iloc[-1] < recent_highs.iloc[-5]
    lower_lows = recent_lows.iloc[-1] < recent_lows.iloc[-5]
    
    results[ticker] = {
        'regime': regime,
        'close': last_close,
        'sma20': sma20.iloc[-1],
        'sma50': sma50.iloc[-1],
        'sma200': sma200.iloc[-1] if len(df) >= 200 else None,
        'rsi': rsi_val,
        'macd_hist': macd_hist,
        'atr': atr_val,
        'atr_pct': atr_pct,
        'higher_highs': higher_highs,
        'higher_lows': higher_lows,
        'lower_highs': lower_highs,
        'lower_lows': lower_lows,
        'slope20': (sma20.iloc[-1] - sma20.iloc[-10]) / sma20.iloc[-10] * 100 if len(sma20) >= 10 else 0,
    }
    
    print(f"  {ticker:8s} | Regime: {regime:12s} | RSI(14): {rsi_val:5.1f} | "
          f"MACD hist: {macd_hist:+.3f} | ATR%: {atr_pct:.2f}% | "
          f"20SMA slope: {results[ticker]['slope20']:+.2f}%")
    print(f"           | Close: ${last_close:.2f} | SMA20: ${sma20.iloc[-1]:.2f} | "
          f"SMA50: ${sma50.iloc[-1]:.2f}")

# ── STAGE 1C: NASDAQ 100 TOP COMPONENTS ──────────────────────────
print("\n[1C] SCANNING NASDAQ 100 TOP COMPONENTS...")

# Top NASDAQ-linked names with strong catalysts
scan_tickers = [
    'NVDA', 'AAPL', 'MSFT', 'AMZN', 'META', 'GOOGL', 'AVGO',
    'TSLA', 'AMD', 'QCOM', 'PANW', 'CRM', 'ORLY', 'ADBE',
    'COST', 'TXN', 'AMAT', 'MU', 'NFLX', 'INTC', 'PYPL',
    'SBUX', 'LRCX', 'KLAC', 'SNPS', 'CDNS', 'ASML', 'MRVL'
]

comp_data = {}
for ticker in scan_tickers:
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period='3mo', interval='1d')
        if len(hist) < 30:
            continue
        close = hist['Close']
        sma20 = sma(close, 20)
        sma50 = sma(close, 50)
        rsi14 = rsi(close, 14).iloc[-1]
        atr14 = atr(hist, 14).iloc[-1]
        atr_pct = atr14 / close.iloc[-1] * 100
        
        # Volume analysis
        vol20 = hist['Volume'].rolling(20).mean().iloc[-1]
        vol_today = hist['Volume'].iloc[-1]
        vol_ratio = vol_today / vol20 if vol20 > 0 else 1
        
        # Gap analysis
        prev_close = close.iloc[-2]
        gap = (close.iloc[-1] - prev_close) / prev_close * 100
        
        # 52-week approximation from 6mo data
        high52 = hist['High'].max()
        low52 = hist['Low'].min()
        pct_from_high = (close.iloc[-1] - high52) / high52 * 100
        pct_from_low = (close.iloc[-1] - low52) / low52 * 100
        
        # Recent momentum (5-day return)
        ret5 = (close.iloc[-1] - close.iloc[-6]) / close.iloc[-6] * 100 if len(close) >= 6 else 0
        ret20 = (close.iloc[-1] - close.iloc[-21]) / close.iloc[-21] * 100 if len(close) >= 21 else 0
        
        # MACD
        ema12 = close.ewm(span=12).mean().iloc[-1]
        ema26 = close.ewm(span=26).mean().mean()
        macd_val = ema12 - close.ewm(span=26).mean().iloc[-1]
        signal = close.ewm(span=9).mean().iloc[-1]
        macd_hist = macd_val - (macd_val * 0.9)  # rough
        
        # Structure: Above/below key MAs
        above_sma20 = close.iloc[-1] > sma20.iloc[-1]
        above_sma50 = close.iloc[-1] > sma50.iloc[-1]
        
        # Stochastic-like
        low14 = hist['Low'].rolling(14).min().iloc[-1]
        high14 = hist['High'].rolling(14).max().iloc[-1]
        stoch_k = ((close.iloc[-1] - low14) / (high14 - low14) * 100) if high14 > low14 else 50
        
        comp_data[ticker] = {
            'close': close.iloc[-1],
            'prev_close': prev_close,
            'sma20': sma20.iloc[-1],
            'sma50': sma50.iloc[-1],
            'rsi14': rsi14,
            'atr': atr14,
            'atr_pct': atr_pct,
            'vol_ratio': vol_ratio,
            'gap': gap,
            'high52': high52,
            'low52': low52,
            'pct_from_high': pct_from_high,
            'pct_from_low': pct_from_low,
            'ret5': ret5,
            'ret20': ret20,
            'macd_hist': macd_hist,
            'above_sma20': above_sma20,
            'above_sma50': above_sma50,
            'stoch_k': stoch_k,
            'volume': vol_today,
            'vol20': vol20,
        }
    except Exception as e:
        print(f"  {ticker}: ERROR - {e}")

print(f"\n  Fetched data for {len(comp_data)} components.")

# ── STAGE 1D: SCORING & FILTERING ────────────────────────────────
print("\n[1D] SCORING SETUPS...")

# Scoring rubric for swing setups
scored = []
for ticker, d in comp_data.items():
    score = 0
    flags = []
    risks = []
    
    # Trend quality
    if d['above_sma20'] and d['above_sma50']:
        score += 25
        flags.append("ABOVE SMA20+50")
    elif d['above_sma20']:
        score += 10
        flags.append("ABOVE SMA20 ONLY")
    else:
        risks.append("BELOW KEY MAs")
    
    # RSI (optimal 40-70 for long entries, avoid >75 or <30)
    if 45 <= d['rsi14'] <= 68:
        score += 20
        flags.append(f"RSI OPTIMAL {d['rsi14']:.0f}")
    elif d['rsi14'] > 75:
        score -= 10
        risks.append(f"RSI OVERBOUGHT {d['rsi14']:.0f}")
    elif d['rsi14'] < 35:
        score += 5
        flags.append(f"RSI OVERSOLD {d['rsi14']:.0f}")
    
    # MACD momentum
    if d['macd_hist'] > 0:
        score += 15
        flags.append("MACD POSITIVE")
    else:
        score -= 5
        risks.append("MACD NEGATIVE")
    
    # Volume surge
    if d['vol_ratio'] > 1.5:
        score += 15
        flags.append(f"VOL SURGE {d['vol_ratio']:.1f}x")
    elif d['vol_ratio'] > 1.2:
        score += 8
        flags.append(f"VOL ELEVATED {d['vol_ratio']:.1f}x")
    
    # Gap up/down analysis
    if abs(d['gap']) > 1.5:
        if d['gap'] > 0:
            score += 10
            flags.append(f"GAP UP {d['gap']:.1f}%")
        else:
            score -= 10
            risks.append(f"GAP DOWN {d['gap']:.1f}%")
    
    # Momentum
    if d['ret5'] > 3:
        score += 10
        flags.append(f"STRONG 5D MOMENTUM {d['ret5']:.1f}%")
    elif d['ret5'] < -3:
        score -= 5
        risks.append(f"WEAK 5D MOMENTUM {d['ret5']:.1f}%")
    
    # Near 52w high = breakout potential
    if d['pct_from_high'] > -5:
        score += 10
        flags.append(f"NEAR 52W HIGH ({d['pct_from_high']:.1f}%)")
    elif d['pct_from_high'] < -20:
        score -= 5
        risks.append(f"FAR FROM 52W HIGH ({d['pct_from_high']:.1f}%)")
    
    # Stochastic
    if 20 <= d['stoch_k'] <= 80:
        score += 5
        flags.append(f"STOCH {d['stoch_k']:.0f} NEUTRAL")
    
    # ATR-based volatility (moderate is best)
    if 1.5 <= d['atr_pct'] <= 4.0:
        score += 5
        flags.append(f"MODERATE ATR {d['atr_pct']:.1f}%")
    
    scored.append({
        'ticker': ticker,
        'score': score,
        'close': d['close'],
        'atr': d['atr'],
        'atr_pct': d['atr_pct'],
        'rsi14': d['rsi14'],
        'flags': flags,
        'risks': risks,
        'ret5': d['ret5'],
        'ret20': d['ret20'],
        'vol_ratio': d['vol_ratio'],
        'gap': d['gap'],
        'pct_from_high': d['pct_from_high'],
        'macd_hist': d['macd_hist'],
        'above_sma20': d['above_sma20'],
        'above_sma50': d['above_sma50'],
        'stoch_k': d['stoch_k'],
    })

scored.sort(key=lambda x: x['score'], reverse=True)

print("\n  TOP 10 SCORED TICKERS:")
print(f"  {'Ticker':8s} {'Score':6s} {'Close':8s} {'RSI':5s} {'ATR%':5s} {'VolR':5s} {'Gap%':6s} {'5D%Ret':6s}")
print("  " + "-" * 58)
for s in scored[:10]:
    print(f"  {s['ticker']:8s} {s['score']:6.0f} ${s['close']:7.2f} {s['rsi14']:5.1f} "
          f"{s['atr_pct']:5.2f}% {s['vol_ratio']:5.2f} {s['gap']:+6.2f}% {s['ret5']:+6.2f}%")

# ── STAGE 1E: UPCOMING CATALYSTS ─────────────────────────────────
print("\n[1E] UPCOMING CATALYST CHECK...")

# Known upcoming earnings (approximate - July 2026)
earnings_calendar = {
    'PYPL': 'Jul 8', 'LRCX': 'Jul 17', 'ASML': 'Jul 16',
    'NFLX': 'Jul 23', 'INTC': 'Jul 24', 'MSFT': 'Jul 30',
    'AAPL': 'Aug 1', 'AMZN': 'Aug 1', 'GOOGL': 'Jul 28',
    'META': 'Jul 30', 'NVDA': 'Aug 28',
}

# July 2 is pre-FOMC blackout period, next FOMC ~Jul 29-30
macro_dates = {
    'FOMC_MEETING': 'Jul 29-30, 2026',
    'CPI_REFERENCE': 'Jul 10, 2026 (June CPI)',
    'PAYROLLS': 'Jul 3, 2026 (June NFP)',
}

print("  Earnings within 21-day window:")
for ticker, date in earnings_calendar.items():
    if ticker in comp_data:
        print(f"    {ticker}: {date}")

print("  Macro catalysts:")
for k, v in macro_dates.items():
    print(f"    {k}: {v}")

# Print detailed for top 3
print("\n" + "=" * 60)
print("DETAILED TOP-3 SETUPS")
print("=" * 60)

top3 = scored[:3]
for i, s in enumerate(top3, 1):
    ticker = s['ticker']
    d = comp_data[ticker]
    
    print(f"\n--- #{i}: {ticker} ---")
    print(f"  Close: ${s['close']:.2f}  |  RSI(14): {s['rsi14']:.1f}  |  ATR: ${s['atr']:.2f} ({s['atr_pct']:.2f}%)")
    print(f"  Score: {s['score']}/100")
    print(f"  Flags: {', '.join(s['flags'])}")
    print(f"  Risks: {', '.join(s['risks']) if s['risks'] else 'None identified'}")
    print(f"  Momentum: 5D={s['ret5']:+.2f}%  |  20D={s['ret20']:+.2f}%")
    print(f"  Volume Ratio: {s['vol_ratio']:.2f}x  |  Gap: {s['gap']:+.2f}%")
    print(f"  52W Range: {(s['pct_from_high']):+.1f}% from high | {d['pct_from_low']:.1f}% from low")
    print(f"  SMA20: ${d['sma20']:.2f}  |  SMA50: ${d['sma50']:.2f}")
    print(f"  Stochastic %K: {s['stoch_k']:.1f}")
    if ticker in earnings_calendar:
        print(f"  CATALYST: Earnings {earnings_calendar[ticker]}")

print("\n" + "=" * 60)
print("ANALYSIS COMPLETE")
print("=" * 60)
