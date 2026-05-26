import os
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
import pandas as pd
import time

# --- CONFIG ---
PORT = int(os.environ.get("PORT", 8000))
API_KEY = os.environ.get("APCA_API_KEY_ID", "PKRXJGKGWKTGDK7EAGUOOUVSUK")
API_SECRET = os.environ.get("APCA_API_SECRET_KEY", "13W4dx3X4AJZLkLzXpc2DXtta8NFruYv4oogJFuMuY9y")

STOCKS = ['AMZN', 'META']
USE_PCT = 0.9
PROFIT_TARGET = 0.005
HARD_STOP_LOSS = 0.10
MA_FAST, MA_SLOW = 20, 52
RSI_PERIOD = 14
RSI_OVERSOLD, RSI_OVERBOUGHT = 30, 70
MACD_FAST, MACD_SLOW = 12, 26

# --- VALIDATE KEYS ---
if not API_KEY or len(API_KEY) < 10:
    print("ERROR: Missing or invalid API key. Set APCA_API_KEY_ID env var.")
    sys.exit(1)

# --- CLIENTS ---
trading_client = TradingClient(API_KEY, API_SECRET, paper=True)
data_client = StockHistoricalDataClient(API_KEY, API_SECRET)

# --- DATA + SIGNALS ---
def get_df(symbol):
    bars = data_client.get_stock_bars(
        StockBarsRequest(symbol_or_symbols=[symbol], timeframe=TimeFrame.Day, limit=100)
    ).data[symbol]
    return pd.DataFrame([{'c': bar.close} for bar in bars])

def get_sig(df):
    c = df['c']
    ma = 1 if c.rolling(MA_FAST).mean().iloc[-1] > c.rolling(MA_SLOW).mean().iloc[-1] else -1
    d = c.diff()
    gain = d.where(d > 0, 0).rolling(RSI_PERIOD).mean()
    loss = -d.where(d < 0, 0).rolling(RSI_PERIOD).mean()
    rsi = 100 - (100 / (1 + gain / loss))
    r = 1 if rsi.iloc[-1] < RSI_OVERSOLD else (-1 if rsi.iloc[-1] > RSI_OVERBOUGHT else 0)
    macd_line = c.ewm(span=MACD_FAST).mean() - c.ewm(span=MACD_SLOW).mean()
    m = 1 if macd_line.iloc[-1] > 0 else -1
    return (ma + r + m) / 3

# --- TRADING LOOP ---
def trading_loop():
    iteration = 0
    while True:
        iteration += 1
        print(f"\n--- Iteration {iteration} ---")
        for sym in STOCKS:
            try:
                df = get_df(sym)
                if len(df) < MA_SLOW:
                    print(f"  {sym}: not enough data ({len(df)} bars), skipping")
                    continue

                price = df['c'].values[-1]
                sig = get_sig(df)
                print(f"  {sym}: price=${price:.2f}, signal={sig:.2f}")

                try:
                    pos = trading_client.get_open_position(sym)
                except Exception:
                    pos = None

                if pos:
                    entry = float(pos.avg_entry_price)
                    p = (price - entry) / entry
                    print(f"  {sym}: holding {pos.qty} shares, P&L={p*100:.1f}%")
                    if p >= PROFIT_TARGET or p <= -HARD_STOP_LOSS:
                        trading_client.submit_order(MarketOrderRequest(
                            symbol=sym,
                            qty=float(pos.qty),
                            side="sell",
                            time_in_force="day"
                        ))
                        print(f"  SELL {sym}: {p*100:.1f}%")
                elif sig > 0.2:
                    account = trading_client.get_account()
                    cash = float(account.cash)
                    qty = int(cash * USE_PCT / price)
                    if qty > 0:
                        trading_client.submit_order(MarketOrderRequest(
                            symbol=sym,
                            qty=qty,
                            side="buy",
                            time_in_force="day"
                        ))
                        print(f"  BUY {sym}: {qty} shares @ ${price:.2f}")
                    else:
                        print(f"  {sym}: signal to buy but not enough cash (${cash:.2f})")
                else:
                    print(f"  {sym}: no action (signal too weak)")

            except Exception as e:
                print(f"  ERROR {sym}: {e}")

        print(f"Sleeping 30 minutes...")
        time.sleep(1800)

# --- HTTP HEALTH CHECK (keeps Render/Railway web service alive) ---
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Trading bot running!")
    def log_message(self, *args):
        pass  # suppress noisy access logs

# --- START ---
print(f"=== TRADING BOT STARTING ON PORT {PORT} ===")

# Run trading loop in background thread
t = threading.Thread(target=trading_loop, daemon=True)
t.start()

# HTTP server runs on main thread (required by Render/Railway)
HTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
