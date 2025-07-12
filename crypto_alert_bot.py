import warnings
warnings.filterwarnings("ignore", category=UserWarning)

import os
import ccxt
import pandas as pd
import pandas_ta as ta
import asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv
from telegram import Bot

# Load environment variables
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_IDS = [572038606, -4971731996]  # Personal and Group Chat IDs

# Initialize bot and exchange
bot = Bot(token=TELEGRAM_TOKEN)
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})

# Parameters
TOP_N = 200  # Number of coins to monitor
MIN_VOLUME_USDT = 10_000_000  # Minimum 24h volume to filter coins
TIMEFRAME = "1h"
LIMIT = 100

def fetch_top_symbols_by_volume(limit=TOP_N, min_volume_usdt=MIN_VOLUME_USDT):
    markets = exchange.fetch_tickers()
    futures_symbols = []

    for symbol, data in markets.items():
        if "/USDT" in symbol and data.get("quoteVolume") and data.get("last"):
            volume = data["quoteVolume"] * data["last"]
            if volume >= min_volume_usdt:
                futures_symbols.append((symbol, volume))

    sorted_symbols = sorted(futures_symbols, key=lambda x: x[1], reverse=True)
    return [symbol for symbol, _ in sorted_symbols[:limit]]

def fetch_ohlcv(symbol):
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=LIMIT)
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df

def analyze(df):
    df["ema20"] = ta.ema(df["close"], length=20)
    df["ema50"] = ta.ema(df["close"], length=50)
    df["rsi"] = ta.rsi(df["close"], length=14)
    stoch = ta.stoch(df["high"], df["low"], df["close"])
    df["stoch_k"] = stoch["STOCHk_14_3_3"]
    df["stoch_d"] = stoch["STOCHd_14_3_3"]
    return df

def detect_signals(df):
    signals = []
    if len(df) < 2:
        return signals

    latest = df.iloc[-1]
    previous = df.iloc[-2]

    if (
        previous["ema20"] < previous["ema50"] and
        latest["ema20"] > latest["ema50"] and
        latest["rsi"] > previous["rsi"] and
        latest["stoch_k"] > latest["stoch_d"]
    ):
        signals.append("LONG")

    if (
        previous["ema20"] > previous["ema50"] and
        latest["ema20"] < latest["ema50"] and
        latest["rsi"] < previous["rsi"] and
        latest["stoch_k"] < latest["stoch_d"]
    ):
        signals.append("SHORT")

    return signals

async def send_alert(symbol, signal, price):
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M GMT')

    msg = f"""
🚨 *{signal} Signal Detected*

🔹 Symbol: {symbol.replace("/", "")}
💰 Current Price: ${price:.4f}
📊 Exchange: Binance Futures
🕓 Time: {now}
📈 Signal Type: MA Crossover + RSI + Stochastic
"""

    bot_instance = Bot(token=TELEGRAM_TOKEN)
    for chat_id in CHAT_IDS:
        await bot_instance.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')

async def run():
    symbols = fetch_top_symbols_by_volume()
    for symbol in symbols:
        try:
            df = fetch_ohlcv(symbol)
            df = analyze(df)
            signals = detect_signals(df)
            last_price = df["close"].iloc[-1]
            for signal in signals:
                await send_alert(symbol, signal, last_price)
        except Exception as e:
            print(f"[ERROR] {symbol}: {e}")

if __name__ == "__main__":
    asyncio.run(run())
