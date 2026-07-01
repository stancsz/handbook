#!/usr/bin/env python3
"""
NASDAQ Swing Trade Scanner - Multi-dimensional analysis
Fetches real-time(ish) data via yfinance
"""
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

today = datetime.now().strftime('%Y-%m-%d')
print(f"Swing Scan Executed: {today} {datetime.now().strftime('%H:%M:%S')}")
print("="*70)

# ---- STAGE 1: CORE INDEX DATA ----
indices = ['QQQ', 'SPY', 'IWM', '^VIX', 'TLT', 'DXY', 'GLD']

print("\n[STAGE 1a] Core Index Data (3-month daily)")
print("-"*70)

idx_data = {}
for ticker in indices:
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period='3mo', interval='1d', auto_adjust=True)
        if len(hist) >= 20:
            close = hist['Close']
            high = hist['High']
            low = hist['Low']
            vol = hist['Volume']
            
            # SMAs
            sma20 = close.rolling(20).mean()
            sma50 = close.rolling(50).mean()
            sma200 = close.rolling(200).mean()
            
            # ATR
            tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
            atr14 = tr.rolling(14).mean().iloc[-1]
            
            # RSI(14)
            delta = close.diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            last_close = close.iloc[-1]
            prev_close = close.iloc[-2]
            day_chg = (last_close - prev_close) / prev_close * 100
            
            # Trend classification
            above_sma20 = last_close > sma20.iloc[-1]
            above_sma50 = last_close > sma50.iloc[-1]
            
            idx_data[ticker] = {
                'close': last_close,
                'prev_close': prev_close,
                'day_chg_pct': day_chg,
                'sma20': sma20.iloc[-1],
                'sma50': sma50.iloc[-1],
                'sma200': sma200.iloc[-1] if len(sma200.dropna()) > 0 else None,
                'atr14': atr14,
                'rsi14': rsi.iloc[-1],
                'volume': vol.iloc[-1],
                'avg_vol': vol.rolling(20).mean().iloc[-1],
                'above_sma20': above_sma20,
                'above_sma50': above_sma50,
                'hist': hist
            }
            
            regime = "BULL" if above_sma50 else "BEAR"
            print(f"  {ticker:6s}: ${last_close:>9.2f} | {day_chg:>+6.2f}% | SMA50: ${sma50.iloc[-1]:>8.2f} | "
                  f"RSI: {rsi.iloc[-1]:>5.1f} | ATR: ${atr14:>5.2f} | Regime: {regime}")
    except Exception as e:
        print(f"  {ticker}: ERROR - {e}")

# ---- BROAD MARKET REGIME ----
print("\n[STAGE 1b] Macro Regime Assessment")
print("-"*70)

qqq = idx_data.get('QQQ', {})
spy = idx_data.get('SPY', {})
iwm = idx_data.get('IWM', {})
vix = idx_data.get('^VIX', {})
dxy = idx_data.get('DXY', {})

# Market structure: Higher Highs / Higher Lows check
def get_hh_hl(hist, lookback=20):
    closes = hist['Close'].tail(lookback).reset_index(drop=True)
    if len(closes) < 10:
        return "UNKNOWN"
    recent_highs = [closes.iloc[i] for i in range(1, len(closes)-1) if closes.iloc[i] > closes.iloc[i-1] and closes.iloc[i] > closes.iloc[i+1]]
    recent_lows = [closes.iloc[i] for i in range(1, len(closes)-1) if closes.iloc[i] < closes.iloc[i-1] and closes.iloc[i] < closes.iloc[i+1]]
    if len(recent_highs) >= 2 and len(recent_lows) >= 2:
        if recent_highs[-1] > recent_highs[-2] and recent_lows[-1] > recent_lows[-2]:
            return "HH/HL (BULL)"
        elif recent_highs[-1] < recent_highs[-2] and recent_lows[-1] < recent_lows[-2]:
            return "LH/LL (BEAR)"
        else:
            return "RANGE"
    return "INSUFFICIENT_DATA"

spy_regime = get_hh_hl(spy.get('hist', pd.DataFrame()))
qqq_regime = get_hh_hl(qqq.get('hist', pd.DataFrame()))

vix_level = vix.get('close', 0)
regime_flag = "BULL" if (qqq.get('above_sma50', False) and qqq.get('close', 0) > qqq.get('sma50', 0)) else "BEAR" if (qqq.get('close', 0) < qqq.get('sma50', 0)) else "TRANSITIONAL"

print(f"  QQQ Regime: {regime_flag}")
print(f"  QQQ Structure: {qqq_regime}")
print(f"  SPY Structure: {spy_regime}")
print(f"  VIX Level: {vix_level:.2f} ({'LOW VOL (confirming BULL)' if vix_level < 18 else 'MODERATE' if vix_level < 25 else 'HIGH VOL (confirming BEAR/TURMOIL)'})")
print(f"  DXY (USD): ${dxy.get('close', 0):.2f}")

# ---- NASDAQ 100 COMPONENT SCAN ----
print("\n[STAGE 1c] NASDAQ 100 Component Scan")
print("-"*70)

# Top NASDAQ 100 components by weight / relevance for swing trading
nasdaq100_focus = [
    'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA', 'AVGO',
    'AMD', 'QCOM', 'NFLX', 'ORLY', 'INTU', 'TXN', 'AMAT', 'KLAC',
    'LRCX', 'MU', 'ADI', 'SNPS', 'CDNS', 'PANW', 'CRWD', 'FTNT',
    'HON', 'ADP', 'PYPL', 'BKNG', 'MELI', 'COST', 'MDLZ', 'KDP',
    'ABNB', 'MAR', 'REGN', 'VRTX', 'BIIB', 'MRNA', 'DXCM', 'ISRG',
    'ZS', 'DDOG', 'NET', 'SNOW', 'PLTR', 'TEAM', 'WDAY', 'OKTA'
]

# Filter to those with recent catalysts: earnings in past 30 days or upcoming
# We'll scan all for technical setups, then cross-reference

def analyze_ticker(ticker_sym):
    try:
        t = yf.Ticker(ticker_sym)
        hist = t.history(period='3mo', interval='1d', auto_adjust=True)
        if len(hist) < 60:
            return None
        
        close = hist['Close']
        high = hist['High']
        low = hist['Low']
        vol = hist['Volume']
        
        # SMAs
        sma20 = close.rolling(20).mean()
        sma50 = close.rolling(50).mean()
        sma200 = close.rolling(200).mean()
        
        # ATR
        tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
        atr14 = tr.rolling(14).mean().iloc[-1]
        
        # RSI(14)
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        # MACD (12, 26, 9)
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        macd_hist = macd - signal
        
        last_close = close.iloc[-1]
        prev_close = close.iloc[-2]
        
        # Gap analysis
        gap_pct = (last_close - close.iloc[-2]) / close.iloc[-2] * 100 if len(close) >= 2 else 0
        
        # 20-day range position
        range_20d_hi = high.rolling(20).max().iloc[-1]
        range_20d_lo = low.rolling(20).min().iloc[-1]
        range_pos = (last_close - range_20d_lo) / (range_20d_hi - range_20d_lo) if (range_20d_hi - range_20d_lo) > 0 else 0.5
        
        # Volume ratio
        vol_ratio = vol.iloc[-1] / vol.rolling(20).mean().iloc[-1]
        
        # Momentum score
        mom_score = 0
        if last_close > sma20.iloc[-1]: mom_score += 1
        if last_close > sma50.iloc[-1]: mom_score += 1
        if rsi.iloc[-1] > 50: mom_score += 1
        if rsi.iloc[-1] < 70: mom_score += 1  # not overbought bonus
        if macd_hist.iloc[-1] > 0: mom_score += 1
        if macd_hist.iloc[-1] > macd_hist.iloc[-2]: mom_score += 1  # improving
        
        return {
            'ticker': ticker_sym,
            'close': last_close,
            'day_chg_pct': (last_close - prev_close) / prev_close * 100,
            'sma20': sma20.iloc[-1],
            'sma50': sma50.iloc[-1],
            'sma200': sma200.iloc[-1] if len(sma200.dropna()) > 0 else None,
            'atr14': atr14,
            'rsi14': rsi.iloc[-1],
            'macd_hist': macd_hist.iloc[-1],
            'macd_trend': 'POS' if macd_hist.iloc[-1] > macd_hist.iloc[-2] else 'NEG',
            'volume_ratio': vol_ratio,
            'range_pos': range_pos,
            'momentum_score': mom_score,
            'above_sma20': last_close > sma20.iloc[-1],
            'above_sma50': last_close > sma50.iloc[-1],
            'above_sma200': last_close > sma200.iloc[-1] if len(sma200.dropna()) > 0 else None,
            'gap_pct': gap_pct,
            'vol': vol.iloc[-1],
            'avg_vol': vol.rolling(20).mean().iloc[-1],
        }
    except Exception as e:
        return None

# Parallel-ish scan
results = []
for sym in nasdaq100_focus:
    res = analyze_ticker(sym)
    if res:
        results.append(res)

print(f"  Scanned {len(results)} tickers successfully")

# Score and rank setups
# Score criteria: above key SMAs, improving MACD, RSI in sweet spot (40-65 for longs), volume confirmation
scored = []
for r in results:
    score = 0
    # Alignment with trend
    if r['above_sma50']: score += 3
    if r['above_sma20']: score += 2
    # RSI sweet spot (not overbought, not oversold)
    if 42 <= r['rsi14'] <= 65: score += 3
    elif r['rsi14'] < 30: score += 2  # oversold bounce candidate
    elif r['rsi14'] > 70: score += 0  # overbought, penalize
    # MACD improving
    if r['macd_hist'] > 0 and r['macd_trend'] == 'POS': score += 2
    elif r['macd_hist'] > 0: score += 1
    # Volume confirmation
    if r['volume_ratio'] > 1.3: score += 1
    # Range position (not at absolute top)
    if 0.3 <= r['range_pos'] <= 0.85: score += 2
    # Momentum score
    score += min(r['momentum_score'], 4)
    
    r['score'] = score
    scored.append(r)

scored.sort(key=lambda x: x['score'], reverse=True)

print("\n[STAGE 1d] Top Ranked Swing Candidates")
print("-"*70)
for r in scored[:15]:
    print(f"  {r['ticker']:6s} | Score: {r['score']:3.0f} | ${r['close']:>8.2f} | "
          f"RSI: {r['rsi14']:>5.1f} | MACD: {r['macd_hist']:>+8.4f} | "
          f"VolR: {r['volume_ratio']:>4.1f}x | RangePos: {r['range_pos']:>5.2f} | "
          f"SMA50: {'ABOVE' if r['above_sma50'] else 'BELOW'}")

# ---- UPCOMING EARNINGS (next 2 weeks) ----
print("\n[STAGE 1e] Upcoming Earnings / Events (next 14 days)")
print("-"*70)

# Major earnings calendar approximation (Jul 2026 - common names)
# We'll check actual earnings dates from yfinance
earnings_tickers = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD',
    'QCOM', 'INTU', 'NFLX', 'PYPL', 'SNPS', 'CDNS', 'AMAT', 'KLAC',
    'LRCX', 'MU', 'ADI', 'TXN', 'AVGO', 'ORLY', 'BKNG', 'MELI',
    'COST', 'MDLZ', 'HON', 'ADP', 'PANW', 'CRWD', 'FTNT', 'ZS',
    'DDOG', 'NET', 'SNOW', 'TEAM', 'WDAY', 'OKTA', 'ABNB', 'MAR'
]

earnings_info = {}
for sym in earnings_tickers:
    try:
        t = yf.Ticker(sym)
        cal = t.calendar
        if cal is not None and not cal.empty:
            earnings_info[sym] = cal
    except:
        pass

# Try to get from info
for sym in ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD']:
    try:
        t = yf.Ticker(sym)
        info = t.info
        next_earnings = info.get('earningsCalendar', None) or info.get('nextEarningsDate', None)
        if next_earnings:
            print(f"  {sym}: Earnings ~{next_earnings}")
    except:
        pass

# ---- SECTOR ROTATION ----
print("\n[STAGE 1f] Sector Rotation & Relative Strength")
print("-"*70)

sector_etfs = {
    'XLK': 'Technology',
    'XLF': 'Financials',
    'XLV': 'Healthcare',
    'XLY': 'Consumer Discretionary',
    'XLC': 'Communication Services',
    'XLE': 'Energy',
    'XLRE': 'Real Estate',
    'XLU': 'Utilities',
    'XLP': 'Consumer Staples',
    'XLB': 'Materials',
    'XLI': 'Industrials',
    'QQQ': 'Nasdaq-100'
}

sector_data = {}
for etf, name in sector_etfs.items():
    try:
        t = yf.Ticker(etf)
        hist = t.history(period='1mo', interval='1d', auto_adjust=True)
        if len(hist) >= 5:
            chg_1d = (hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2] * 100
            chg_5d = (hist['Close'].iloc[-1] - hist['Close'].iloc[-5]) / hist['Close'].iloc[-5] * 100 if len(hist) >= 5 else 0
            chg_1m = (hist['Close'].iloc[-1] - hist['Close'].iloc[-20]) / hist['Close'].iloc[-20] * 100 if len(hist) >= 20 else 0
            sector_data[etf] = {'name': name, 'chg_1d': chg_1d, 'chg_5d': chg_5d, 'chg_1m': chg_1m}
    except:
        pass

for etf, d in sorted(sector_data.items(), key=lambda x: x[1]['chg_1d'], reverse=True):
    print(f"  {d['name']:25s} ({etf}): 1D: {d['chg_1d']:>+6.2f}% | 5D: {d['chg_5d']:>+6.2f}% | 1M: {d['chg_1m']:>+6.2f}%")

# ---- DETAILED TOP 3 SETUPS ----
print("\n\n" + "="*70)
print("[STAGE 2] TOP 3 SWING TRADE SETUPS - DETAILED ANALYSIS")
print("="*70)

top3 = scored[:3]

for rank, candidate in enumerate(top3, 1):
    sym = candidate['ticker']
    print(f"\n{'='*70}")
    print(f"SETUP #{rank}: {sym}")
    print(f"{'='*70}")
    
    # Get more detailed data
    t = yf.Ticker(sym)
    hist_4h = t.history(period='1mo', interval='1h', auto_adjust=True)
    hist_d = t.history(period='6mo', interval='1d', auto_adjust=True)
    
    close_d = hist_d['Close']
    high_d = hist_d['High']
    low_d = hist_d['Low']
    
    # SMAs
    sma20_d = close_d.rolling(20).mean()
    sma50_d = close_d.rolling(50).mean()
    sma200_d = close_d.rolling(200).mean()
    
    # ATR
    tr = pd.concat([high_d - low_d, (high_d - close_d.shift(1)).abs(), (low_d - close_d.shift(1)).abs()], axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean().iloc[-1]
    
    # Fibonacci retracements from recent swing
    recent_swing_hi = high_d.rolling(20).max().iloc[-1]
    recent_swing_lo = low_d.rolling(20).min().iloc[-1]
    
    # Support/resistance
    r1 = high_d.rolling(20).max().iloc[-1]
    s1 = low_d.rolling(20).min().iloc[-1]
    
    # 4H analysis
    if len(hist_4h) >= 20:
        close_4h = hist_4h['Close']
        high_4h = hist_4h['High']
        low_4h = hist_4h['Low']
        sma20_4h = close_4h.rolling(20).mean()
        ema9_4h = close_4h.ewm(span=9, adjust=False).mean()
        
        # RSI 4H
        delta = close_4h.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi_4h = 100 - (100 / (1 + rs))
        
        last_close_4h = close_4h.iloc[-1]
        above_ema9_4h = last_close_4h > ema9_4h.iloc[-1]
    else:
        above_ema9_4h = None
        rsi_4h = None
        last_close_4h = close_d.iloc[-1]
    
    last_close = close_d.iloc[-1]
    prev_close = close_d.iloc[-2]
    day_vol = hist_d['Volume'].iloc[-1]
    avg_vol = hist_d['Volume'].rolling(20).mean().iloc[-1]
    
    # Info
    try:
        info = t.info
        pe = info.get('trailingPE', 'N/A')
        fwd_pe = info.get('forwardPE', 'N/A')
        mkt_cap = info.get('marketCap', 0)
        beta = info.get('beta', 'N/A')
        avg_vol_info = info.get('averageVolume', 0)
        rec = info.get('recommendationKey', 'N/A')
        target = info.get('targetMeanPrice', 0)
        target_upside = (target / last_close - 1) * 100 if target else 0
    except:
        pe = fwd_pe = beta = rec = 'N/A'
        mkt_cap = avg_vol_info = 0
        target_upside = 0
    
    print(f"  PRICE & VOLUME:")
    print(f"    Last Close:      ${last_close:.2f}")
    print(f"    Previous Close:  ${prev_close:.2f}")
    print(f"    Day Change:      {(last_close-prev_close)/prev_close*100:+.2f}%")
    print(f"    Daily Volume:    {day_vol/1e6:.1f}M (Avg20d: {avg_vol/1e6:.1f}M)")
    print(f"    Volume Ratio:    {day_vol/avg_vol:.1f}x")
    print(f"")
    print(f"  TECHNICAL LEVELS:")
    print(f"    SMA20 (Daily):   ${sma20_d.iloc[-1]:.2f}  ({'ABOVE' if last_close > sma20_d.iloc[-1] else 'BELOW'})")
    print(f"    SMA50 (Daily):   ${sma50_d.iloc[-1]:.2f}  ({'ABOVE' if last_close > sma50_d.iloc[-1] else 'BELOW'})")
    print(f"    SMA200 (Daily):  ${sma200_d.iloc[-1]:.2f}  ({'ABOVE' if last_close > sma200_d.iloc[-1] else 'BELOW' if len(sma200_d.dropna())>0 else 'N/A'})")
    print(f"    4H EMA9:         {'$' + f'{ema9_4h.iloc[-1]:.2f}' + ' (' + ('ABOVE' if above_ema9_4h else 'BELOW') + ')' if above_ema9_4h is not None else 'N/A'}")
    print(f"    Range 20d Hi:    ${r1:.2f}")
    print(f"    Range 20d Lo:    ${s1:.2f}")
    print(f"    ATR(14):         ${atr14:.2f} ({atr14/last_close*100:.1f}% of price)")
    print(f"    ATR-based Stop:  ${last_close - 1.5*atr14:.2f} to ${last_close - 2*atr14:.2f}")
    print(f"")
    print(f"  MOMENTUM:")
    print(f"    RSI(14) Daily:   {candidate['rsi14']:.1f} ({'OVERBOUGHT' if candidate['rsi14']>70 else 'OVERSOLD' if candidate['rsi14']<30 else 'NEUTRAL'})")
    print(f"    RSI(14) 4H:      {rsi_4h.iloc[-1]:.1f}" if rsi_4h is not None else "    RSI(14) 4H: N/A")
    print(f"    MACD Hist:      {candidate['macd_hist']:+.4f} ({candidate['macd_trend']})")
    print(f"    Momentum Score: {candidate['momentum_score']}/8")
    print(f"    Range Position: {candidate['range_pos']*100:.0f}% (0%=at low, 100%=at high)")
    print(f"")
    print(f"  FUNDAMENTALS:")
    print(f"    Market Cap:     ${mkt_cap/1e12:.2f}T" if mkt_cap > 1e12 else f"    Market Cap:     ${mkt_cap/1e9:.1f}B")
    print(f"    P/E (Trailing): {pe:.2f}" if isinstance(pe, float) else f"    P/E (Trailing): {pe}")
    print(f"    P/E (Forward):  {fwd_pe:.2f}" if isinstance(fwd_pe, float) else f"    P/E (Forward):  {fwd_pe}")
    print(f"    Beta:           {beta:.2f}" if isinstance(beta, float) else f"    Beta:           {beta}")
    print(f"    Analyst Rec:    {rec}")
    print(f"    Target Upside:  {target_upside:+.1f}%")
    print(f"")
    
    # Risk/Reward calculation
    entry = last_close
    # Conservative stop: below SMA50 or 2x ATR
    stop = min(s1, entry - 2 * atr14)
    risk_pct = (entry - stop) / entry * 100
    
    # T1: 2:1 reward, T2: 3:1 reward
    t1_price = entry + 2 * (entry - stop)
    t2_price = entry + 3 * (entry - stop)
    
    rr1 = (t1_price - entry) / (entry - stop)
    rr2 = (t2_price - entry) / (entry - stop)
    
    print(f"  RISK/REWARD PARAMETERS:")
    print(f"    Entry:           ${entry:.2f}")
    print(f"    Stop Loss:       ${stop:.2f} (Risk: {risk_pct:.1f}%)")
    print(f"    T1 (2:1 R/R):    ${t1_price:.2f} (R/R: {rr1:.1f}:1)")
    print(f"    T2 (3:1 R/R):    ${t2_price:.2f} (R/R: {rr2:.1f}:1)")
    print(f"    Max Risk/Share:  ${entry - stop:.2f}")

# ---- COGNITIVE CRITIQUE ----
print("\n\n" + "="*70)
print("[STAGE 3] COGNITIVE CRITIQUE & REGIME ALIGNMENT")
print("="*70)

print("\n[BULL CASE]")
for r in top3:
    print(f"  {r['ticker']}: {r['above_sma50']}, RSI={r['rsi14']:.0f}, MACD+{'POS' if r['macd_hist']>0 else 'NEG'}, Score={r['score']:.0f}")

print("\n[BEAR CASE / INVALIDATION TRIGGERS]")
print("  - Broad market fails to hold current support levels → all longs invalid")
print("  - VIX spikes above 25 → risk-off triggers cascade selling")
print("  - Any of the top3 breaks below SMA50 on daily close → immediate exit")
print("  - RSI divergence on daily vs 4H → early profit-taking warranted")
print("  - Gap-fill of today's/instrument's recent gap → stop triggered")

print("\n[LIQUIDITY CHECK]")
for r in top3:
    vol_ratio = r['volume_ratio']
    print(f"  {r['ticker']}: Vol={r['vol']/1e6:.1f}M, AvgVol={r['avg_vol']/1e6:.1f}M, Ratio={vol_ratio:.1f}x → "
          f"{'GOOD' if vol_ratio >= 0.7 else 'THIN - WIDE SPREAD RISK'}")

print("\n\n" + "="*70)
print("[STAGE 4] FINAL TACTICAL ADVISORY")
print("="*70)

# Print summary table
print("\n{:<8} {:>10} {:>8} {:>8} {:>8} {:>8} {:>8}".format(
    "TICKER", "CLOSE", "ENTRY", "STOP", "T1", "T2", "R/R T1"))
print("-" * 65)

for r in top3:
    entry = r['close']
    atr = r['atr14']
    stop = min(r.get('sma50', r['close'] - 2*atr), entry - 2*atr)
    t1 = entry + 2*(entry - stop)
    t2 = entry + 3*(entry - stop)
    rr = (t1 - entry) / (entry - stop)
    print("{:<8} {:>10.2f} {:>8.2f} {:>8.2f} {:>8.2f} {:>8.2f} {:>7.1f}:1".format(
        r['ticker'], entry, entry, stop, t1, t2, rr))

print("\n" + "="*70)
print("POSITION SIZING: Risk 1-2% of capital per trade | Max 3 concurrent positions")
print("HOLDING WINDOW:  2-21 days | Exit on T1 hit OR invalidation, whichever first")
print("="*70)
