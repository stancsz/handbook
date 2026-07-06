#!/usr/bin/env python3
"""Deep analysis for top 3 swing setups"""
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

def atr(df, n=14):
    high, low, close = df['High'], df['Low'], df['Close']
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def rsi(series, n=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(n).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(n).mean()
    return 100 - (100 / (1 + gain/loss))

tickers = ['PYPL', 'AAPL', 'ORLY', 'QQQ', 'SPY']

for ticker in tickers:
    print(f"\n{'='*55}")
    print(f"DEEP DIVE: {ticker}")
    print(f"{'='*55}")
    try:
        t = yf.Ticker(ticker)
        # 6mo daily for regime
        hist = t.history(period='6mo', interval='1d')
        # 20d hourly for intraday structure
        hist_h = t.history(period='20d', interval='60m')
        
        close = hist['Close']
        high = hist['High']
        low = hist['Low']
        
        sma20 = close.rolling(20).mean()
        sma50 = close.rolling(50).mean()
        sma200 = close.rolling(200).mean()
        
        rsi14 = rsi(close, 14)
        atr14 = atr(hist, 14)
        
        last = close.iloc[-1]
        last_date = hist.index[-1]
        
        # Daily performance series
        ret_1d = (close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100 if len(close) > 1 else 0
        ret_5d = (close.iloc[-1] - close.iloc[-6]) / close.iloc[-6] * 100 if len(close) > 5 else 0
        ret_10d = (close.iloc[-1] - close.iloc[-11]) / close.iloc[-11] * 100 if len(close) > 10 else 0
        ret_20d = (close.iloc[-1] - close.iloc[-21]) / close.iloc[-21] * 100 if len(close) > 20 else 0
        
        # Key levels
        swing_high_60 = high.tail(60).max()
        swing_low_60 = low.tail(60).min()
        swing_high_20 = high.tail(20).max()
        swing_low_20 = low.tail(20).min()
        
        # Support/resistance zones
        recent_highs = high.tail(20).sort_values(ascending=False).head(5)
        recent_lows = low.tail(20).sort_values(ascending=True).head(5)
        
        # ATR-based position sizing reference
        atr_val = atr14.iloc[-1]
        atr_pct = atr_val / last * 100
        
        # Max drawdown in period
        peak = close.expanding().max()
        drawdown = (close - peak) / peak * 100
        max_dd = drawdown.min()
        
        # Beta to QQQ (approx)
        qqq = yf.Ticker('QQQ')
        qqq_hist = qqq.history(period='6mo', interval='1d')
        if len(qqq_hist) >= len(hist):
            merged = hist.join(qqq_hist['Close'], lsuffix='_t', rsuffix='_q')
            if len(merged) > 20:
                ret_t = merged['Close_t'].pct_change().dropna()
                ret_q = merged['Close_q'].pct_change().dropna()
                common_len = min(len(ret_t), len(ret_q))
                if common_len > 20:
                    beta = np.corrcoef(ret_t.tail(common_len), ret_q.tail(common_len))[0,1]
                else:
                    beta = 1.0
            else:
                beta = 1.0
        else:
            beta = 1.0
        
        print(f"  Last Close:  ${last:.2f}  ({last_date.strftime('%Y-%m-%d')})")
        print(f"  Daily Chg:   {ret_1d:+.2f}%")
        print(f"  5D Return:   {ret_5d:+.2f}%")
        print(f"  10D Return:  {ret_10d:+.2f}%")
        print(f"  20D Return:  {ret_20d:+.2f}%")
        print(f"  RSI(14):     {rsi14.iloc[-1]:.1f}  [today]")
        print(f"  RSI(14) 5d ago: {rsi14.iloc[-6]:.1f}" if len(rsi14) > 5 else "")
        print(f"  ATR(14):     ${atr_val:.2f}  ({atr_pct:.2f}% of price)")
        print(f"  Max Drawdown: {max_dd:.2f}%")
        print(f"  Beta to QQQ:  {beta:.2f}")
        print(f"  --- KEY LEVELS ---")
        print(f"  SMA20:       ${sma20.iloc[-1]:.2f}")
        print(f"  SMA50:       ${sma50.iloc[-1]:.2f}" if len(close) >= 50 else "  SMA50: N/A (insufficient data)")
        print(f"  20d Swing High: ${swing_high_20:.2f}")
        print(f"  20d Swing Low:  ${swing_low_20:.2f}")
        print(f"  60d Swing High: ${swing_high_60:.2f}")
        print(f"  60d Swing Low:  ${swing_low_60:.2f}")
        print(f"  Gap from 20d high: {(last - swing_high_20) / swing_high_20 * 100:+.1f}%")
        print(f"  Gap from 60d high: {(last - swing_high_60) / swing_high_60 * 100:+.1f}%")
        print(f"  Distance to 20d low: {(last - swing_low_20) / swing_low_20 * 100:+.1f}%")
        
        # Vol profile from hourly
        if len(hist_h) > 0:
            h_close = hist_h['Close']
            h_high = hist_h['High']
            h_low = hist_h['Low']
            h_sma20 = h_close.rolling(20).mean()
            print(f"  --- INTRADAY STRUCTURE ---")
            print(f"  60m SMA20:   ${h_sma20.iloc[-1]:.2f}")
            print(f"  60m Range:   High ${h_high.max():.2f} | Low ${h_low.min():.2f}")
            print(f"  60m Last:    ${h_close.iloc[-1]:.2f}")
            today_h = hist_h[hist_h.index.date == last_date.date()]
            if len(today_h) > 0:
                print(f"  Today Range: High ${today_h['High'].max():.2f} | Low ${today_h['Low'].min():.2f}")
            
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()

print(f"\n{'='*55}")
print("MACRO REGIME DEEP DIVE")
print(f"{'='*55}")

for ticker in ['QQQ', 'SPY', 'VIX', 'HYG']:
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period='3mo', interval='1d')
        close = hist['Close']
        sma20 = close.rolling(20).mean()
        sma50 = close.rolling(50).mean()
        rsi14 = rsi(close, 14)
        atr14 = atr(hist, 14)
        last = close.iloc[-1]
        vol20 = hist['Volume'].rolling(20).mean().iloc[-1]
        vol_today = hist['Volume'].iloc[-1]
        
        # Bollinger position
        bb_mid = sma20.iloc[-1]
        bb_std = close.rolling(20).std().iloc[-1]
        bb_upper = bb_mid + 2*bb_std
        bb_lower = bb_mid - 2*bb_std
        bb_pos = (last - bb_lower) / (bb_upper - bb_lower) * 100 if bb_upper > bb_lower else 50
        
        print(f"\n  {ticker}: ${last:.2f}")
        print(f"    RSI: {rsi14.iloc[-1]:.1f} | ATR%: {atr14.iloc[-1]/last*100:.2f}% | BB Pos: {bb_pos:.0f}%")
        print(f"    Vol: {vol_today/1e6:.1f}M (20d avg: {vol20/1e6:.1f}M, ratio: {vol_today/vol20:.2f}x)")
        print(f"    SMA20: ${sma20.iloc[-1]:.2f} | SMA50: ${sma50.iloc[-1]:.2f}" if len(close) >= 50 else "")
        
        # Market breadth proxy
        if ticker == 'SPY':
            # VIX regime
            vix = yf.Ticker('^VIX').history(period='3mo', interval='1d')
            vix_last = vix['Close'].iloc[-1]
            vix_rsi = rsi14.iloc[-1] if ticker == '^VIX' else 0
            regime = "BULL" if last > sma20.iloc[-1] and rsi14.iloc[-1] > 50 else "BEAR" if last < sma20.iloc[-1] and rsi14.iloc[-1] < 50 else "TRANSITIONAL"
            print(f"    Regime: {regime} | VIX: {vix_last:.2f}")
    except Exception as e:
        print(f"  {ticker}: ERROR - {e}")
