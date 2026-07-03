#!/usr/bin/env python3
"""
NASDAQ / SPY Swing Trade Scanner
Fetches real-time-ish data via yfinance and computes technical indicators.
"""

import sys
sys.path.insert(0, '/opt/hermes/.venv/lib/python3.13/site-packages')

import requests
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# Custom session to avoid Yahoo rate limiting
_session = requests.Session()
_session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
})

def yf_download(ticker, period='3mo', interval='1d'):
    """Wrapper that uses the custom session."""
    t = yf.Ticker(ticker, session=_session)
    return t.history(period=period, interval=interval)

# ── Config ──────────────────────────────────────────────────────────────────
SCAN_DATE = datetime.now().strftime('%Y-%m-%d %H:%M')
REGION   = "US/Eastern"

TICKERS = {
    "SPY":   "S&P 500 ETF",
    "QQQ":   "Nasdaq 100 ETF",
    # Top NASDAQ-100 components (liquid, swing-friendly)
    "AAPL":  "Apple",
    "MSFT":  "Microsoft",
    "NVDA":  "NVIDIA",
    "GOOGL": "Alphabet",
    "AMZN":  "Amazon",
    "META":  "Meta Platforms",
    "AVGO":  "Broadcom",
    "TSM":   "TSMC ADR",
    "AMD":   "AMD",
    "QCOM":  "Qualcomm",
    "PANW":  "Palo Alto Networks",
    "ORLY":  "O'Reilly Automotive",
    "AMAT":  "Applied Materials",
    "ADP":   "ADP",
    "INTU":  "Intuit",
    "HON":   "Honeywell",
    "LRCX":  "Lam Research",
    "MU":    "Micron",
    "KLAC":  "KLA Corp",
    "ADI":   "Analog Devices",
    "CRWD":  "CrowdStrike",
    "SNPS":  "Synopsys",
    "CDNS":  "Cadence Design",
}

PERIOD  = "3mo"   # 3-month daily data for swing analysis
RSI_PD  = 14
ATR_PD  = 14

# ── Helpers ──────────────────────────────────────────────────────────────────
def sma(series, n):
    return series.rolling(n).mean()

def ema(series, n):
    return series.ewm(span=n, adjust=False).mean()

def atr(high, low, close, n=14):
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low  - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def rsi(series, n=14):
    delta = series.diff()
    gain  = delta.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    rs    = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def macd_signal(series, fast=12, slow=26, sig=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd     = ema_fast - ema_slow
    signal   = macd.ewm(span=sig, adjust=False).mean()
    return macd, signal

def fetch_and_analyze(ticker, name, period=PERIOD):
    """Download data and compute swing indicators."""
    try:
        df = yf_download(ticker, period=period)
        if df.empty or len(df) < 60:
            return None
    except Exception as e:
        return None

    df = df.sort_index()

    close  = df['Close']
    high   = df['High']
    low    = df['Low']
    volume = df['Volume']

    # ── Moving Averages ────────────────────────────────────────────────────
    ma20  = sma(close, 20)
    ma50  = sma(close, 50)
    ma200 = sma(close, 200)
    ema9  = ema(close, 9)
    ema20 = ema(close, 20)

    # ── Indicators ─────────────────────────────────────────────────────────
    df['rsi']    = rsi(close, RSI_PD)
    df['atr']    = atr(high, low, close, ATR_PD)
    df['macd'], df['macd_sig'] = macd_signal(close)

    # ── Regime ─────────────────────────────────────────────────────────────
    cur  = close.iloc[-1]
    p20  = ma20.iloc[-1]
    p50  = ma50.iloc[-1]
    p200 = ma200.iloc[-1]

    above_ma20  = cur > p20
    above_ma50  = cur > p50
    above_ma200 = cur > p200 if not pd.isna(p200) else True
    ema9_above_20 = ema9.iloc[-1] > ema20.iloc[-1]

    # ── Volatility / ATR ───────────────────────────────────────────────────
    cur_atr  = df['atr'].iloc[-1]
    atr_pct  = (cur_atr / cur) * 100
    vol_ratio = volume.iloc[-1] / volume.rolling(20).mean().iloc[-1] if volume.iloc[-1] > 0 else 1.0

    # ── Recent range ───────────────────────────────────────────────────────
    ret_5d  = (close.iloc[-1] / close.iloc[-6] - 1) * 100 if len(close) > 5 else 0
    ret_20d = (close.iloc[-1] / close.iloc[-21] - 1) * 100 if len(close) > 20 else 0

    # ── Swing high / low (20d) ─────────────────────────────────────────────
    swing_high_20 = high.rolling(20).max().iloc[-1]
    swing_low_20  = low.rolling(20).min().iloc[-1]
    dist_to_high  = (swing_high_20 - cur) / cur * 100
    dist_to_low   = (cur - swing_low_20) / cur * 100

    # ── RSI state ───────────────────────────────────────────────────────────
    cur_rsi = df['rsi'].iloc[-1]
    rsi_5d_ago = df['rsi'].iloc[-6] if len(df) > 5 else 50

    # ── MACD state ─────────────────────────────────────────────────────────
    macd_cur  = df['macd'].iloc[-1]
    macd_sig  = df['macd_sig'].iloc[-1]
    macd_prev = df['macd'].iloc[-2] if len(df) > 1 else 0
    macd_cross_up = macd_cur > macd_sig and macd_prev <= macd_sig

    # ── ATR stop distances (2ATR and 3ATR) ────────────────────────────────
    stop_2atr  = cur - 2 * cur_atr
    stop_3atr  = cur - 3 * cur_atr

    # ── Higher High / Higher Low check (last 5 bars) ───────────────────────
    highs_5  = high.iloc[-5:]
    hh_check = highs_5.iloc[-1] > highs_5.iloc[:-1].max()
    lows_5   = low.iloc[-5:]
    hl_check = lows_5.iloc[-1] > lows_5.iloc[:-1].min()

    return {
        "ticker": ticker,
        "name":   name,
        "close":  cur,
        "atr":    cur_atr,
        "atr_pct": atr_pct,
        "rsi":    cur_rsi,
        "macd":   macd_cur,
        "macd_sig": macd_sig,
        "macd_cross_up": macd_cross_up,
        "ma20":   p20,
        "ma50":   p50,
        "ma200":  p200,
        "above_ma20":  above_ma20,
        "above_ma50":  above_ma50,
        "above_ma200": above_ma200,
        "ema9_above_20": ema9_above_20,
        "ret_5d":  ret_5d,
        "ret_20d": ret_20d,
        "swing_high_20": swing_high_20,
        "swing_low_20":  swing_low_20,
        "dist_to_high":  dist_to_high,
        "dist_to_low":   dist_to_low,
        "vol_ratio":     vol_ratio,
        "stop_2atr": stop_2atr,
        "stop_3atr": stop_3atr,
        "hh_check": hh_check,
        "hl_check": hl_check,
        "volume_20_avg": volume.rolling(20).mean().iloc[-1],
        "volume_today":  volume.iloc[-1],
        "close_1d_ago":  close.iloc[-2],
        "close_2d_ago":  close.iloc[-3],
        "df": df,
    }

# ── Fetch all tickers ─────────────────────────────────────────────────────────
print(f"=== NASDAQ Swing Scan | {SCAN_DATE} ===\n")

results = {}
for ticker, name in TICKERS.items():
    r = fetch_and_analyze(ticker, name)
    if r:
        results[ticker] = r
        print(f"  Fetched {ticker} — Close: ${r['close']:.2f}  "
              f"ATR: ${r['atr']:.2f} ({r['atr_pct']:.1f}%)  "
              f"RSI: {r['rsi']:.1f}  "
              f"5d ret: {r['ret_5d']:+.1f}%")
    else:
        print(f"  FAILED  {ticker}")

print(f"\nSuccessfully analyzed: {len(results)}/{len(TICKERS)} tickers\n")

# ── Market Regime ─────────────────────────────────────────────────────────────
def assess_regime(spy, qqq):
    spy_cur  = spy['close']
    qqq_cur  = qqq['close']
    spy_ma200 = spy['above_ma200']
    qqq_ma200 = qqq['above_ma200']
    spy_ma50  = spy['above_ma50']
    qqq_ma50  = qqq['above_ma50']
    spy_rsi   = spy['rsi']
    qqq_rsi   = qqq['rsi']
    spy_ret   = spy['ret_20d']
    qqq_ret   = qqq['ret_20d']

    bull_signals = sum([
        spy_ma200 and spy_ma50,
        qqq_ma200 and qqq_ma50,
        spy_rsi > 50 and qqq_rsi > 50,
        spy_ret > 0,
        qqq_ret > 0,
    ])

    if bull_signals >= 4:
        regime = "BULL"
        description = "Both SPY and QQQ above 50 & 200 SMAs, RSI > 50, positive 20d returns — structural uptrend."
    elif bull_signals <= 1:
        regime = "BEAR"
        description = "Both SPY and QQQ below key MAs, RSI < 50, negative 20d returns — structural downtrend."
    else:
        regime = "TRANSITIONAL"
        description = "Mixed signals — market in chop/ranging phase. Trend ambiguous, use range-bound strategies."

    return regime, description, {
        "SPY above 200MA": spy['above_ma200'],
        "SPY above 50MA":  spy['above_ma50'],
        "QQQ above 200MA": qqq['above_ma200'],
        "QQQ above 50MA":  qqq['above_ma50'],
        "SPY RSI(14)": round(spy_rsi, 1),
        "QQQ RSI(14)": round(qqq_rsi, 1),
        "SPY 20d return": f"{spy_ret:+.1f}%",
        "QQQ 20d return": f"{qqq_ret:+.1f}%",
        "SPY ATR%": f"{spy['atr_pct']:.1f}%",
        "QQQ ATR%": f"{qqq['atr_pct']:.1f}%",
    }

regime, regime_desc, regime_meta = assess_regime(results["SPY"], results["QQQ"])

# ── Score candidates ──────────────────────────────────────────────────────────
def score_long(r, regime):
    """Score a potential LONG setup. Higher = better."""
    score = 0
    # Trend alignment
    if r['above_ma50']: score += 2
    if r['above_ma20']:  score += 1
    if r['above_ma200']: score += 1
    if r['ema9_above_20']: score += 1
    # Momentum
    if 40 <= r['rsi'] <= 60: score += 2        # Room to run
    elif 30 <= r['rsi'] < 40: score += 3       # Oversold bounce potential
    elif r['rsi'] > 70:   score -= 2           # Overbought — risk
    if r['macd_cross_up']: score += 2
    if r['macd'] > r['macd_sig']: score += 1
    # Structure
    if r['hl_check']: score += 1
    if r['hh_check']: score += 1
    # Recent momentum
    if r['ret_5d'] > 0: score += 1
    if r['ret_5d'] < -5: score += 1  # Oversold bounce candidate
    # Volume confirmation
    if r['vol_ratio'] > 1.2: score += 1
    # Not too extended
    if r['dist_to_high'] > 5: score += 1
    # ATR reasonable (not extreme)
    if r['atr_pct'] < 4:  score += 1
    elif r['atr_pct'] > 7: score -= 1
    # Regime alignment
    if regime == "BULL":
        if r['above_ma50']: score += 2
        else:               score -= 2
    elif regime == "BEAR":
        score -= 2  # Shorts favored
    return score

def score_short(r, regime):
    """Score a potential SHORT setup. Higher = better."""
    score = 0
    if not r['above_ma50']: score += 2
    if not r['above_ma20']: score += 1
    if not r['above_ma200']: score += 1
    if not r['ema9_above_20']: score += 1
    if r['rsi'] > 70:   score += 2
    elif r['rsi'] > 60:  score += 1
    elif r['rsi'] < 40:  score -= 2
    if r['macd'] < r['macd_sig']: score += 1
    if not r['hh_check']: score += 1  # Making lower highs
    if not r['hl_check']: score += 1  # Breaking lows
    if r['ret_5d'] > 5: score += 1   # Extended
    if r['dist_to_low'] > 3: score += 1
    if r['vol_ratio'] > 1.2: score += 1
    if regime == "BEAR":
        if not r['above_ma50']: score += 2
    elif regime == "BULL":
        score -= 2
    return score

# ── Score all stocks ─────────────────────────────────────────────────────────
stock_results = {k: v for k, v in results.items()
                 if k not in ("SPY", "QQQ")}

long_scores  = {k: score_long(v, regime)  for k, v in stock_results.items()}
short_scores = {k: score_short(v, regime) for k, v in stock_results.items()}

sorted_long  = sorted(long_scores.items(),  key=lambda x: x[1], reverse=True)
sorted_short = sorted(short_scores.items(), key=lambda x: x[1], reverse=True)

print("=== LONG SCORES (top 10) ===")
for t, s in sorted_long[:10]:
    r = stock_results[t]
    print(f"  {t:6s} ({r['name']:22s}) score={s:3d}  "
          f"RSI={r['rsi']:5.1f}  "
          f"above50={r['above_ma50']}  "
          f"5d={r['ret_5d']:+6.1f}%  "
          f"volR={r['vol_ratio']:.2f}  "
          f"distHi={r['dist_to_high']:.1f}%")

print("\n=== SHORT SCORES (top 10) ===")
for t, s in sorted_short[:10]:
    r = stock_results[t]
    print(f"  {t:6s} ({r['name']:22s}) score={s:3d}  "
          f"RSI={r['rsi']:5.1f}  "
          f"above50={r['above_ma50']}  "
          f"5d={r['ret_5d']:+6.1f}%  "
          f"distLo={r['dist_to_low']:.1f}%")

# ── Top 3 Setups ─────────────────────────────────────────────────────────────
print("\n\n" + "="*70)
print("=== TOP SWING TRADE SETUPS ===")
print("="*70)

# Pick best long and best short
top_long_tickers  = [t for t, s in sorted_long  if s > 0][:3]
top_short_tickers = [t for t, s in sorted_short if s > 0][:2]

def build_setup(ticker, direction, score, r, regime):
    cur    = r['close']
    atr    = r['atr']
    atr_pct = r['atr_pct']
    rsi    = r['rsi']

    if direction == "LONG":
        entry     = cur  # market entry, or pullback entry zone
        stop_loss = round(r['stop_3atr'], 2)
        risk_pct  = (cur - stop_loss) / cur * 100

        # T1: 2:1 reward-to-risk  T2: 3:1
        t1 = round(cur + 2 * (cur - stop_loss), 2)
        t2 = round(cur + 3 * (cur - stop_loss), 2)

        # Limit entry if RSI > 65 (slight pullback preferred)
        if rsi > 65:
            entry_type = f"BUY LIMIT @ ${round(cur * 0.995, 2):.2f} (slight pullback from overbought)"
        elif rsi < 40:
            entry_type = "BUY STOP-LIMIT @ last close breakout (oversold momentum reversal)"
        else:
            entry_type = f"BUY @ market (${cur:.2f})"

        if r['macd_cross_up']:
            catalyst = "MACD bullish crossover on declining RSI pullback — momentum shift confirmation"
        elif rsi < 40:
            catalyst = "Oversold RSI + MACD bullish divergence — snap-back rally setup"
        elif r['above_ma50'] and r['hl_check']:
            catalyst = "Above 50MA with higher low formation — trend continuation"
        else:
            catalyst = f"RSI={rsi:.0f}, above MA50={r['above_ma50']}, MACD cross={r['macd_cross_up']}"

        invalidation = (f"Break below {r['swing_low_20']:.2f} (20d swing low) "
                        f"OR daily close below ${stop_loss:.2f} (3ATR stop)")

    else:  # SHORT
        entry     = cur
        stop_loss = round(cur + 2 * atr, 2)
        risk_pct  = (stop_loss - cur) / cur * 100
        t1        = round(cur - 2 * (stop_loss - cur), 2)
        t2        = round(cur - 3 * (stop_loss - cur), 2)

        if rsi > 75:
            entry_type = "SHORT SELL @ market / SELL SHORT on any push toward MA50"
        else:
            entry_type = f"SHORT @ market (${cur:.2f})"

        catalyst = (f"RSI={rsi:.0f}, below MA50={not r['above_ma50']}, "
                    f"MACDbearish={'MACD < Signal' if r['macd'] < r['macd_sig'] else 'MACD > Signal'}")

        invalidation = (f"Break above ${round(cur + 2 * atr, 2):.2f} (2ATR resistance) "
                        f"OR daily close above MA50 @ ${r['ma50']:.2f}")

    return {
        "ticker":      ticker,
        "direction":   direction,
        "score":       score,
        "name":        r['name'],
        "close":       cur,
        "entry":       entry,
        "entry_type":  entry_type,
        "stop_loss":   stop_loss,
        "risk_pct":    risk_pct,
        "t1":          t1,
        "t2":          t2,
        "rr1":         round((t1 - cur) / (cur - stop_loss) if direction == "LONG"
                              else (cur - t1) / (stop_loss - cur), 2),
        "rr2":         round((t2 - cur) / (cur - stop_loss) if direction == "LONG"
                              else (cur - t2) / (stop_loss - cur), 2),
        "rsi":         rsi,
        "atr":         atr,
        "atr_pct":     atr_pct,
        "catalyst":    catalyst,
        "invalidation": invalidation,
        "above_ma50":  r['above_ma50'],
        "above_ma200": r['above_ma200'],
        "macd_cross_up": r['macd_cross_up'],
        "ret_5d":      r['ret_5d'],
        "ret_20d":     r['ret_20d'],
        "dist_to_high": r['dist_to_high'],
        "dist_to_low":  r['dist_to_low'],
        "vol_ratio":    r['vol_ratio'],
        "hh_check":     r['hh_check'],
        "hl_check":     r['hl_check'],
        "regime":       regime,
    }

# Build top 3 (prefer longs in bull, shorts in bear)
if regime == "BULL":
    top_tickers = top_long_tickers[:3]
    preferred_dir = "LONG"
elif regime == "BEAR":
    top_tickers = top_short_tickers[:3]
    preferred_dir = "SHORT"
else:
    # In transitional, show best of both
    top_tickers = top_long_tickers[:2] + top_short_tickers[:1]
    preferred_dir = "MIXED"

setups = []
for ticker in top_tickers:
    r = stock_results[ticker]
    if ticker in top_long_tickers:
        dir_ = "LONG"
        score = long_scores[ticker]
    else:
        dir_ = "SHORT"
        score = short_scores[ticker]
    setups.append(build_setup(ticker, dir_, score, r, regime))

# Sort by score
setups.sort(key=lambda x: x['score'], reverse=True)

# ── Print Advisory ───────────────────────────────────────────────────────────
for i, s in enumerate(setups, 1):
    print(f"\n{'─'*65}")
    print(f"SETUP #{i}:  {s['ticker']} — {s['name']}")
    print(f"Direction: {s['direction']}  |  Confidence Score: {s['score']}  |  Regime: {s['regime']}")
    print(f"{'─'*65}")
    print(f"  Current Price:    ${s['close']:.2f}")
    print(f"  Entry:            {s['entry_type']}")
    print(f"  Stop Loss:        ${s['stop_loss']:.2f}  (risk: {s['risk_pct']:.1f}% / {s['atr_pct']:.1f}% ATR)")
    print(f"  T1 (2:1 R/R):     ${s['t1']:.2f}  (+{s['rr1']:.1f}x) — partial take profit here")
    print(f"  T2 (3:1 R/R):     ${s['t2']:.2f}  (+{s['rr2']:.1f}x) — close position here")
    print(f"  Invalidation:     {s['invalidation']}")
    print(f"  Catalyst:        {s['catalyst']}")
    print(f"  ─── Technical ────────────────────────────────────────────────")
    print(f"  RSI(14):         {s['rsi']:.1f}  {'(overbought — caution)' if s['rsi']>70 else '(oversold — bounce potential)' if s['rsi']<40 else '(neutral zone)'}")
    print(f"  ATR(14):         ${s['atr']:.2f}  ({s['atr_pct']:.1f}% of price)")
    print(f"  Above 50MA:      {s['above_ma50']}  |  Above 200MA: {s['above_ma200']}")
    print(f"  MACD Cross Up:   {s['macd_cross_up']}  |  Higher Low: {s['hl_check']}  |  Higher High: {s['hh_check']}")
    print(f"  5d Return:       {s['ret_5d']:+.1f}%  |  20d Return: {s['ret_20d']:+.1f}%")
    print(f"  Dist to 20d High:{s['dist_to_high']:.1f}%  |  Dist to 20d Low: {s['dist_to_low']:.1f}%")
    print(f"  Volume Ratio:    {s['vol_ratio']:.2f}x  (today vs 20d avg)")

# ── Position Sizing Advisory ─────────────────────────────────────────────────
print(f"\n\n{'='*70}")
print("POSITION SIZING & RISK MANAGEMENT")
print("="*70)
account = 100000  # placeholder $100k reference

for s in setups:
    risk_dollar  = s['risk_pct'] / 100 * account
    size_1pct    = account * 0.01 / s['risk_pct'] * 100  # shares for 1% risk
    size_2pct    = account * 0.02 / s['risk_pct'] * 100  # shares for 2% risk
    print(f"  {s['ticker']} ({s['direction']}): "
          f"Risk ${risk_dollar:.0f} @ {s['risk_pct']:.1f}% per share | "
          f"Size @ 1% risk = {size_1pct:.0f} shares | "
          f"Size @ 2% risk = {size_2pct:.0f} shares")

# ── Export results to JSON for reference ─────────────────────────────────────
import json, pathlib
out = {
    "scan_time": SCAN_DATE,
    "regime": regime,
    "regime_description": regime_desc,
    "regime_meta": regime_meta,
    "all_long_scores": {k: int(v) for k, v in sorted_long},
    "all_short_scores": {k: int(v) for k, v in sorted_short},
    "setups": setups,
}
pathlib.Path("/opt/data/handbook/swing_scan_results.json").write_text(
    json.dumps(out, indent=2, default=str))
print(f"\n[Results exported to /opt/data/handbook/swing_scan_results.json]")
