import os
import alpaca
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
import pandas as pd
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

port = int(os.environ.get("PORT", 8050))

API_KEY = "PKRXJGKGWKTGDK7EAGUOOUVSUK"
API_SECRET = "13W4dx3X4AJZLkLzXpc2DXtta8NFruYv4oogJFuMuY9y"

STOCKS = ['AMZN', 'META']
USE_PCT = 0.9
PROFIT_TARGET = 0.005
HARD_STOP_LOSS = 0.10
MA_FAST = 20
MA_SLOW = 52
RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
MACD_FAST = 12
MACD_SLOW = 26

if API_KEY == "YOUR_KEY_HERE":
    print("EDIT YOUR KEYS!")
    exit()

trading_client = TradingClient(API_KEY, API_SECRET, paper=True)
data_client = StockHistoricalDataClient(API_KEY, API_SECRET)

def get_data(symbol):
    request = StockBarsRequest(symbol_or_symbols=[symbol], timeframe=TimeFrame.Day, limit=100)
    bars = data_client.get_stock_bars(request)
    return pd.DataFrame([{'close': bar.close} for bar in bars.data[symbol]])

def get_signal(df):
    ma_fast = df['close'].rolling(MA_FAST).mean()
    ma_slow = df['close'].rolling(MA_SLOW).mean()
    ma = 1 if ma_fast.iloc[-1] > ma_slow.iloc[-1] else -1
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(RSI_PERIOD).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(RSI_PERIOD).mean()
    rsi_val = 100 - (100 / (1 + gain / loss))
    rsi = 1 if rsi_val.iloc[-1] < RSI_OVERSOLD else (-1 if rsi_val.iloc[-1] > RSI_OVERBOUGHT else 0)
    ema_f = df['close'].ewm(span=MACD_FAST, adjust=False).mean()
    ema_s = df['close'].ewm(span=MACD_SLOW, adjust=False).mean()
    macd = 1 if (ema_f.iloc[-1] - ema_s.iloc[-1]) > 0 else -1
    return (ma + rsi + macd) / 3

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot running!")

print("="*50)
print("PAPER TRADING LIVE!")
print("="*50)

iteration = 0
while True:
    iteration += 1
    for sym in STOCKS:
        try:
            df = get_data(sym)
            if len(df) < 52:
                continue
            price = df['close'].values[-1]
            sig = get_signal(df)
            try:
                pos = trading_client.get_position(sym)
            except:
                pos = None
            if pos:
                profit = (price - float(pos.avg_entry_price)) / float(pos.avg_entry_price)
                if profit >= PROFIT_TARGET or profit <= -HARD_STOP_LOSS:
                    trading_client.submit_order(MarketOrderRequest(symbol=sym, qty=float(pos.qty), side="sell", time_in_force="gtc"))
                    print(f"SELL {sym}: {profit*100:.1f}%")
            else:
                if sig > 0.2:
                    cash = float(trading_client.get_account().cash)
                    qty = int(cash * USE_PCT / price)
                    if qty > 0:
                        trading_client.submit_order(MarketOrderRequest(symbol=sym, qty=qty, side="buy", time_in_force="gtc"))
                        print(f"BUY {sym} @ ${price:.0f}")
        except Exception as e:
            print(f"Error {sym}: {e}")
    print(f"[{iteration}] 30 min...")
    # Check every 30 min
    time.sleep(1800)

server = HTTPServer(('0.0.0.0', port), Handler)
server.serve_forever()
