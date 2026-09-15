import yfinance as yf
import pandas as pd
import numpy as np
from typing import Optional, Dict
import datetime
import config

NIFTY_HEALTH_CACHE = {}

def get_stock_data(symbol: str, period: str = "1y", interval: str = "1d") -> Optional[pd.DataFrame]:
    """
    Fetches historical OHLCV data from Yahoo Finance for NSE stocks.
    Ensures standard formatting and handles potential network or missing data issues.
    """
    try:
        formatted_symbol = symbol if symbol.endswith(".NS") else f"{symbol}.NS"
        ticker = yf.Ticker(formatted_symbol)
        df = ticker.history(period=period, interval=interval)
        
        if df.empty or len(df) < 50:
            return None
        
        df = df.reset_index()
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
        
        df = df[["Date", "Open", "High", "Low", "Close", "Volume"]]
        df = calculate_indicators(df)
        return df
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return None

def compute_supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    """Computes Supertrend (10, 3) indicator."""
    hl2 = (df["High"] + df["Low"]) / 2.0
    upperband = hl2 + (multiplier * df["ATR"])
    lowerband = hl2 - (multiplier * df["ATR"])
    
    supertrend = [True] * len(df)
    st_val = [0.0] * len(df)
    
    for i in range(period, len(df)):
        curr_close = float(df["Close"].iloc[i])
        prev_st_val = st_val[i-1]
        prev_supertrend = supertrend[i-1]
        
        if upperband.iloc[i] < upperband.iloc[i-1] or df["Close"].iloc[i-1] > upperband.iloc[i-1]:
            curr_upper = upperband.iloc[i]
        else:
            curr_upper = upperband.iloc[i-1]
            
        if lowerband.iloc[i] > lowerband.iloc[i-1] or df["Close"].iloc[i-1] < lowerband.iloc[i-1]:
            curr_lower = lowerband.iloc[i]
        else:
            curr_lower = lowerband.iloc[i-1]
            
        if prev_supertrend:
            if curr_close < curr_lower:
                supertrend[i] = False
                st_val[i] = curr_upper
            else:
                supertrend[i] = True
                st_val[i] = curr_lower
        else:
            if curr_close > curr_upper:
                supertrend[i] = True
                st_val[i] = curr_lower
            else:
                supertrend[i] = False
                st_val[i] = curr_upper
                
    df["Supertrend_Bullish"] = supertrend
    df["Supertrend_Val"] = st_val
    return df

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes institutional indicators:
    - 9, 20, 21, 50, 200 EMA
    - 14-period RSI
    - 14-period ATR
    - MACD (12, 26, 9) and MACD Histogram
    - Supertrend (10, 3)
    - 20-period Volume Moving Average
    """
    # Moving Averages
    df["EMA_9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["EMA_20"] = df["Close"].ewm(span=config.PULLBACK_EMA, adjust=False).mean()
    df["EMA_21"] = df["Close"].ewm(span=21, adjust=False).mean()
    df["EMA_50"] = df["Close"].ewm(span=config.TREND_EMA_MID, adjust=False).mean()
    df["EMA_200"] = df["Close"].ewm(span=config.TREND_EMA_LONG, adjust=False).mean()
    
    # RSI (14)
    delta = df["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=config.RSI_PERIOD).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=config.RSI_PERIOD).mean()
    rs = gain / (loss + 1e-9)
    df["RSI"] = 100 - (100 / (1 + rs))
    
    # ATR (14)
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["ATR"] = true_range.rolling(window=14).mean()
    
    # Volume average
    df["Volume_SMA20"] = df["Volume"].rolling(window=20).mean()
    
    # MACD (12, 26, 9)
    ema_12 = df["Close"].ewm(span=12, adjust=False).mean()
    ema_26 = df["Close"].ewm(span=26, adjust=False).mean()
    df["MACD"] = ema_12 - ema_26
    df["MACD_Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["MACD_Hist"] = df["MACD"] - df["MACD_Signal"]
    
    # Supertrend (10, 3)
    df = compute_supertrend(df, period=10, multiplier=3.0)
    
    return df

def check_nifty_market_health() -> bool:
    """
    Evaluates Nifty-50 Macro Health.
    Halts new buying if Nifty-50 is down > 1.25% today to protect capital from market crashes.
    """
    now = datetime.datetime.now()
    if "is_healthy" in NIFTY_HEALTH_CACHE and (now - NIFTY_HEALTH_CACHE["time"]).total_seconds() < 120:
        return NIFTY_HEALTH_CACHE["is_healthy"]
        
    try:
        nifty = yf.Ticker("^NSEI")
        hist = nifty.history(period="5d", interval="1d")
        if len(hist) >= 2:
            cur = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2])
            pct_change = ((cur - prev) / prev) * 100.0
            is_healthy = pct_change > -1.25
            NIFTY_HEALTH_CACHE["is_healthy"] = is_healthy
            NIFTY_HEALTH_CACHE["time"] = now
            return is_healthy
        return True
    except Exception as e:
        print(f"[Nifty Health Warning] {e}")
        return True

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
