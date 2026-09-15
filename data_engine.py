import yfinance as yf
import pandas as pd
import numpy as np
from typing import Optional, Dict
import config

def get_stock_data(symbol: str, period: str = "1y", interval: str = "1d") -> Optional[pd.DataFrame]:
    """
    Fetches historical OHLCV data from Yahoo Finance for NSE stocks.
    Ensures standard formatting and handles potential network or missing data issues.
    """
    try:
        # Standardize NSE symbol format
        formatted_symbol = symbol if symbol.endswith(".NS") else f"{symbol}.NS"
        ticker = yf.Ticker(formatted_symbol)
        df = ticker.history(period=period, interval=interval)
        
        if df.empty or len(df) < 50:
            return None
        
        # Clean index and column names
        df = df.reset_index()
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
        
        df = df[["Date", "Open", "High", "Low", "Close", "Volume"]]
        df = calculate_indicators(df)
        return df
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return None

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes technical indicators required for the Zone Bounce Swing Strategy:
    - 20 EMA, 50 EMA, 200 EMA
    - 14-period RSI
    - 14-period ATR (Average True Range)
    - 20-period Volume Moving Average
    """
    # Exponential Moving Averages
    df["EMA_20"] = df["Close"].ewm(span=config.PULLBACK_EMA, adjust=False).mean()
    df["EMA_50"] = df["Close"].ewm(span=config.TREND_EMA_MID, adjust=False).mean()
    df["EMA_200"] = df["Close"].ewm(span=config.TREND_EMA_LONG, adjust=False).mean()
    
    # RSI (Relative Strength Index)
    delta = df["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=config.RSI_PERIOD).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=config.RSI_PERIOD).mean()
    rs = gain / (loss + 1e-9)
    df["RSI"] = 100 - (100 / (1 + rs))
    
    # ATR (Average True Range)
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["ATR"] = true_range.rolling(window=14).mean()
    
    # Volume average
    df["Volume_SMA20"] = df["Volume"].rolling(window=20).mean()
    
    return df

def get_latest_price(symbol: str) -> Optional[float]:
    """Fetches the latest real-time/closing price for a stock."""
    try:
        formatted_symbol = symbol if symbol.endswith(".NS") else f"{symbol}.NS"
        ticker = yf.Ticker(formatted_symbol)
        todays_data = ticker.history(period="2d", interval="1d")
        if not todays_data.empty:
            return float(todays_data["Close"].iloc[-1])
        return None
    except Exception as e:
        print(f"Error fetching latest price for {symbol}: {e}")
        return None

def find_support_zones(df: pd.DataFrame, lookback: int = 40) -> Dict[str, float]:
    """
    Identifies key support zones based on:
    1. Dynamic EMA Support: 20 EMA and 50 EMA levels
    2. Static Swing Low Support: Minimum low in recent pullbacks
    """
    recent_slice = df.tail(lookback)
    swing_low = float(recent_slice["Low"].min())
    current_ema20 = float(df["EMA_20"].iloc[-1])
    current_ema50 = float(df["EMA_50"].iloc[-1])
    current_ema200 = float(df["EMA_200"].iloc[-1])
    
    return {
        "swing_low": swing_low,
        "ema20": current_ema20,
        "ema50": current_ema50,
        "ema200": current_ema200
    }
