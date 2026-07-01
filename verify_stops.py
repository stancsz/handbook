#!/usr/bin/env python3
import yfinance as yf
import pandas as pd
import numpy as np

candidates = [
    {'ticker': 'TSLA',  'close': 420.60, 'atr14': 17.48, 'sma20': 400.59, 'sma50': 405.62, 'rsi14': 58.3, 'rsi_4h': 93.1, 'range_pos': 0.80},
    {'ticker': 'MELI',  'close': 1697.39,'atr14': 65.63, 'sma20': 1634.50,'sma50': 1688.56,'rsi14': 56.0, 'rsi_4h': 57.3, 'range_pos': 0.76},
    {'ticker': 'NET',   'close': 245.28, 'atr14': 11.96, 'sma20': 237.68, 'sma50': 223.93, 'rsi14': 55.7, 'rsi_4h': 65.1, 'range_pos': 0.51},
]

qqq = yf.Ticker('QQQ')
hq = qqq.history(period='1mo', interval='1h', auto_adjust=True)
c = hq['Close']
d = c.diff()
g = d.where(d > 0, 0).rolling(14).mean()
l = (-d.where(d < 0, 0)).rolling(14).mean()
qqq_rsi_4h = (100 - (100 / (1 + g / l))).iloc[-1]
print(f"QQQ 4H RSI: {qqq_rsi_4h:.1f}")
print()

for c in candidates:
    t = c['ticker']
    entry = c['close']
    atr = c['atr14']
    sma20 = c['sma20']
    sma50 = c['sma50']
    rsi4h = c['rsi_4h']
    
    tight_stop_1 = entry - 1.5 * atr
    tight_stop_2 = entry - 2.0 * atr
    sma_stop = sma50
    
    stop = max(tight_stop_1, sma_stop * 0.99)
    risk_pct = (entry - stop) / entry * 100
    risk_per_share = entry - stop
    
    t1 = entry + 2 * risk_per_share
    t2 = entry + 3 * risk_per_share
    
    atr_pct = atr / entry * 100
    
    print(f"{'='*60}")
    print(f"{t}: Entry=${entry:.2f} | ATR=${atr:.2f} ({atr_pct:.1f}% of price)")
    print(f"  Conservative Stop (2x ATR):  ${tight_stop_2:.2f} | Risk: {(entry-tight_stop_2)/entry*100:.1f}%")
    print(f"  Tighter Stop (1.5x ATR):     ${tight_stop_1:.2f} | Risk: {(entry-tight_stop_1)/entry*100:.1f}%")
    print(f"  SMA50 Floor:                 ${sma50:.2f}")
    print(f"  RECOMMENDED STOP:            ${stop:.2f} | Risk: {risk_pct:.1f}%")
    print(f"  T1 (2:1): ${t1:.2f} | T2 (3:1): ${t2:.2f}")
    print(f"  Max Risk/Share: ${risk_per_share:.2f}")
    warn = " OVERBOUGHT 4H" if rsi4h > 80 else ""
    print(f"  4H RSI: {rsi4h:.1f}{warn}")
