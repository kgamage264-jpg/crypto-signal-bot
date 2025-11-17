import os
import ccxt
import pandas as pd
import pandas_ta as ta
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- CONFIGURATION ---
# IMPORTANT: Replace these with your NEW, SECRET keys.
# It's best practice to use environment variables instead of hardcoding them.
TELEGRAM_BOT_TOKEN = "YOUR_NEW_TELEGRAM_BOT_TOKEN"
# You don't need the OpenAI key for this technical analysis version, which is safer.

# The Telegram Chat ID you want the bot to send messages to.
# You can get this by talking to your bot and checking the console output when you run it.
TARGET_CHAT_ID = None 

# --- TRADING STRATEGY CONFIGURATION ---
# List of cryptocurrencies and timeframes to scan
# Format: [SYMBOL, TIMEFRAME]
# Timeframes: '1m', '5m', '15m', '30m', '1h', '4h', '1d'
PAIRS_TO_SCAN = [
    ["BTC/USDT", "15m"],
    ["ETH/USDT", "15m"],
    ["BTC/USDT", "1h"],
    ["SOL/USDT", "1h"],
]

# --- SETUP LOGGING ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- TECHNICAL ANALYSIS AND SIGNAL GENERATION ---

def get_crypto_data(symbol, timeframe):
    """Fetches historical price data from Binance."""
    try:
        exchange = ccxt.binance()
        bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=100)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        logger.error(f"Error fetching data for {symbol}: {e}")
        return None

def generate_signal(df, symbol, timeframe):
    """
    Analyzes the data and generates a trading signal based on a simple strategy.
    Strategy: Buy if RSI is below 30 (oversold) and the price is above the 50-period EMA.
    """
    if df is None or len(df) < 50:
        return None

    # Calculate indicators
    df.ta.rsi(length=14, append=True)
    df.ta.ema(length=50, append=True) # Slow EMA
    
    # Get the last (most recent) row of data
    last_candle = df.iloc[-1]
    
    # --- STRATEGY LOGIC ---
    # You can create very complex strategies here. This is a simple example.
    is_oversold = last_candle['RSI_14'] < 35
    is_uptrend = last_candle['close'] > last_candle['EMA_50']

    if is_oversold and is_uptrend:
        entry_price = last_candle['close']
        # Set a 3% Take Profit and a 1.5% Stop Loss
        tp = entry_price * 1.03
        sl = entry_price * 0.985
        
        signal_message = (
            f"🚨 **New AI Signal** 🚨\n\n"
            f"**Pair:** {symbol}\n"
            f"**Timeframe:** {timeframe}\n"
            f"**Signal:** LONG (BUY)\n"
            f"**Reason:** RSI Oversold in Uptrend\n\n"
            f"**Entry:** `{entry_price:.4f}`\n"
            f"**Take Profit (TP):** `{tp:.4f}`\n"
            f"**Stop Loss (SL):** `{sl:.4f}`"
        )
        return signal_message
        
    # You can add a SHORT/SELL signal here as well
    # e.g., if RSI > 70 and close < EMA_50

    return None

async def check_for_signals(context: ContextTypes.DEFAULT_TYPE):
    """The main job that runs on a schedule to check for new signals."""
    global TARGET_CHAT_ID
    if not TARGET_CHAT_ID:
        logger.warning("TARGET_CHAT_ID is not set. Cannot send signals.")
        return
        
    logger.info("Scheduler running: Checking for new signals...")
    for symbol, timeframe in PAIRS_TO_SCAN:
        df = get_crypto_data(symbol, timeframe)
        if df is not None:
            signal = generate_signal(df, symbol, timeframe)
            if signal:
                logger.info(f"Signal found for {symbol} on {timeframe}. Sending to Telegram.")
                await context.bot.send_message(
                    chat_id=TARGET_CHAT_ID, 
                    text=signal,
                    parse_mode='MarkdownV2'
                )

# --- TELEGRAM BOT COMMANDS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command. Saves the user's chat ID."""
    global TARGET_CHAT_ID
    user_chat_id = update.effective_chat.id
    
    # We only want to send signals to one specific user (you).
    if TARGET_CHAT_ID is None:
        TARGET_CHAT_ID = user_chat_id
        logger.info(f"Target chat ID has been set to: {TARGET_CHAT_ID}")
        await update.message.reply_text(
            f"Hello! I will now send trading signals to this chat.\n"
            f"Your Chat ID is: `{user_chat_id}`. I have saved it."
        )
    elif TARGET_CHAT_ID == user_chat_id:
        await update.message.reply_text("I'm already configured to send signals here.")
    else:
        await update.message.reply_text("I'm already configured to send signals to another user.")


# --- MAIN APPLICATION ---

def main() -> None:
    """Start the bot and the scheduler."""
    # Create the Telegram Bot Application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))

    # Create and start the scheduler
    scheduler = AsyncIOScheduler()
    # Schedule the check_for_signals job to run every 15 minutes
    scheduler.add_job(check_for_signals, 'interval', minutes=15, args=[application])
    scheduler.start()
    logger.info("Signal checking scheduler has started. Will run every 15 minutes.")
    
    # Run the bot until the user presses Ctrl-C
    logger.info("Telegram bot is polling for commands...")
    application.run_polling()


if __name__ == '__main__':
    main()
