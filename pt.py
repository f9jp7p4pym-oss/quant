import os
import signal
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
import alpaca
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
import pandas as pd
import time

# RENDER PORT
PORT = int(os.environ.get("PORT", 8000))

# YOUR KEYS - EDIT THESE!
API_KEY = "PKRXJGKGWKTGDK7EAGUOOUVSUK"
API_SECRET = "13W4dx3X4AJZLkLzXpc2DXtta8NFruYv4oogJFuMuY9y"

STOCKS = ['AMZN', 'META']
USE_PCT = 0.9
PROFIT_TARGET = 0.005
HARD_STOP_LOSS = 0.10
MA_FAST, MA_SLOW = 20, 52
RSI_PERIOD = 14
RSI_OVERSOLD, RSI_OVERBOUGHT = 30, 70
MACD_FAST, MACD_SLOW = 12, 26

if API_KEY == "YOUR_KEY_HERE" or len(API_KEY) < 10:
    print("EDIT YOUR KEYS FIRST!")
    sys.exit(1)

trading_client = TradingClient(API_KEY, API_SECRET, paper=True)
data_client = StockHistoricalDataClient(API_KEY, API_SECRET)

def get_df(symbol):
    return pd.DataFrame([{'c': bar.c} for bar in data_client.get_stock_bars(
        StockBarsRequest(symbol_or_symbols=[symbol], timeframe=TimeFrame.Day, limit=100)).data[symbol]])

def get_sig(df):
    c = df['c']
    ma = 1 if c.rolling(MA_FAST).mean().iloc[-1] > c.rolling(MA_SLOW).mean().iloc[-1] else -1
    d = c.diff()
    rsi = 100 - (100 / (1 + d.where(d>0,0).rolling(RSI_PERIOD).mean() / -d.where(d<0,0).rolling(RSI_PERIOD).mean()))
    r = 1 if rsi.iloc[-1] < RSI_OVERSOLD else (-1 if rsi.iloc[-1] > RSI_OVERBOUGHT else 0)
    m = 1 if (c.ewm(span=MACD_FAST).mean() - c.ewm(span=MACD_SLOW).mean()).iloc[-1] > 0 else -1
    return (ma + r + m) / 3

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Trading bot running!")

server = HTTPServer(('0.0.0.0', PORT), Handler)
print(f"=== TRADING BOT LIVE ON PORT {PORT} ===")

while True:
    iteration = 0
    for sym in STOCKS:
        try:
            df = get_df(sym)
            if len(df) < 52: continue
            price = df['c'].values[-1]
            sig = get_sig(df)
            try: pos = trading_client.get_position(sym)
            except: pos = None
            if pos:
                p = (price - float(pos.avg_entry_price)) / float(pos.avg_entry_price)
                if p >= PROFIT_TARGET or p <= -HARD_STOP_LOSS:
                    trading_client.submit_order(MarketOrderRequest(symbol=sym, qty=float(pos.qty), side="sell", time_in_force="gtc"))
                    print(f"SELL {sym}: {p*100:.1f}%")
            elif sig > 0.2:
                qty = int(float(trading_client.get_account().cash) * USE_PCT / price)
                if qty > 0:
                    trading_client.submit_order(MarketOrderRequest(symbol=sym, qty=qty, side="buy", time_in_force="gtc"))
                    print(f"BUY {sym} @ ${price:.0f}")
        except Exception as e:
            print(f"Error {sym}: {e}")
    print(f"[{iteration}] Checking in 30 min...")
    time.sleep(1800)
