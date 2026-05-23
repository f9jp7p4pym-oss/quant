import alpaca
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
import pandas as pd
import time
import logging

logging.basicConfig(level=logging.ERROR)

API_KEY = "YOUR_API_KEY"
API_SECRET = "YOUR_API_SECRET"

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

if API_KEY == "YOUR_API_KEY":
    print("EDIT YOUR ALPACA KEYS FIRST!")
    exit()

trading_client = TradingClient(API_KEY, API_SECRET, paper=True)
data_client = StockHistoricalDataClient(API_KEY, API_SECRET)

def get_data(symbol):
    request = StockBarsRequest(symbol_or_symbols=[symbol], timeframe=TimeFrame.Day, limit=100)
    bars = data_client.get_stock_bars(request)
    df = pd.DataFrame([{'close': bar.close} for bar in bars.data[symbol]])
    return df

def get_signal(df):
    ma_fast = df['close'].rolling(MA_FAST).mean()
    ma_slow = df['close'].rolling(MA_SLOW).mean()
    ma_sig = 1 if ma_fast.iloc[-1] > ma_slow.iloc[-1] else -1
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(RSI_PERIOD).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(RSI_PERIOD).mean()
    rsi = 100 - (100 / (1 + gain / loss))
    rsi_sig = 1 if rsi.iloc[-1] < RSI_OVERSOLD else (-1 if rsi.iloc[-1] > RSI_OVERBOUGHT else 0)
    ema_fast = df['close'].ewm(span=MACD_FAST, adjust=False).mean()
    ema_slow = df['close'].ewm(span=MACD_SLOW, adjust=False).mean()
    macd_sig = 1 if (ema_fast.iloc[-1] - ema_slow.iloc[-1]) > 0 else -1
    return (ma_sig + rsi_sig + macd_sig) / 3

print("="*60)
print("PAPER TRADING - AMZN & META")
print("="*60)
account = trading_client.get_account()
print(f"Cash: ${float(account.cash):.2f}")
print(f"Stocks: {STOCKS}")

iteration = 0
while True:
    iteration += 1
    for symbol in STOCKS:
        try:
            df = get_data(symbol)
            if len(df) < 52:
                continue
            price = df['close'].values[-1]
            signal = get_signal(df)
            try:
                position = trading_client.get_position(symbol)
            except:
                position = None
            if position:
                qty = float(position.qty)
                avg_price = float(position.avg_entry_price)
                profit = (price - avg_price) / avg_price
                if profit >= PROFIT_TARGET or profit <= -HARD_STOP_LOSS:
                    order = MarketOrderRequest(symbol=symbol, qty=qty, side="sell", time_in_force="gtc")
                    trading_client.submit_order(order)
                    print(f"SELL {symbol}: {profit*100:.2f}%")
            else:
                if signal > 0.2:
                    cash = float(trading_client.get_account().cash)
                    qty = int(cash * USE_PCT / price)
                    if qty > 0:
                        order = MarketOrderRequest(symbol=symbol, qty=qty, side="buy", time_in_force="gtc")
                        trading_client.submit_order(order)
                        print(f"BUY {symbol} @ ${price:.2f}")
        except Exception as e:
            print(f"Error {symbol}: {e}")
    print(f"[{iteration}] Waiting 30 min...")
    time.sleep(1800)