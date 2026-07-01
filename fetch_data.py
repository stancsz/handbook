import yfinance as yf
import json

tickers = ['QQQ', 'SPY', 'NVDA', 'AMD', 'MSFT', 'AAPL', 'GOOGL', 'AMZN', 'META']

data = {}
for t in tickers:
    try:
        tk = yf.Ticker(t)
        hist = tk.history(period='5d', interval='1d')
        if not hist.empty:
            info = tk.info
            last = hist.iloc[-1]
            prev = hist.iloc[-2] if len(hist) > 1 else last
            data[t] = {
                'close': round(float(last['Close']), 2),
                'prev_close': round(float(prev['Close']), 2),
                'pct_change': round(((float(last['Close']) - float(prev['Close'])) / float(prev['Close'])) * 100, 2),
                'volume': int(last['Volume']),
                '52w_high': info.get('fiftyTwoWeekHigh', None),
                '52w_low': info.get('fiftyTwoWeekLow', None),
                'pe_ratio': info.get('trailingPE', None),
                'beta': info.get('beta', None),
            }
    except Exception as e:
        data[t] = {'error': str(e)}

with open('/opt/data/handbook/market_data.json', 'w') as f:
    json.dump(data, f, indent=2)
print("Done")
