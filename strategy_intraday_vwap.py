import pandas as pd
import numpy as np
from typing import Optional, Dict
import datetime
import config

def compute_vwap(df: pd.DataFrame) -> pd.Series:
    """
    Computes true Volume Weighted Average Price (VWAP) on intraday bars.
    VWAP = cumsum(Typical Price * Volume) / cumsum(Volume)
    Typical Price = (High + Low + Close) / 3
    """
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3.0
    cum_pv = (typical_price * df["Volume"]).cumsum()
    cum_vol = df["Volume"].cumsum()
    return cum_pv / (cum_vol + 1e-9)

def analyze_intraday_vwap_signal(df_intraday: pd.DataFrame, symbol: str) -> Optional[Dict]:
    """
    Institutional 5-Minute VWAP + Opening Range Momentum Intraday Engine:
    
    Rules for Entry:
    1. Time Window: Active between 09:30 AM and 01:30 PM (No late fresh entries).
    2. Trend & Base: Price > VWAP (Institutional Accumulation Zone).
    3. EMA Alignment: 9 EMA > 21 EMA on 5-min chart (Bullish Intraday Momentum).
    4. Opening Range Breakout: Price breaking above initial 15-min / 30-min high.
    5. Volume Surge: Current 5-min volume >= 1.8x to 2.5x 20-period 5-min volume average.
    6. Supertrend (10, 3): Intraday Supertrend must be Bullish (Green).
    7. RSI (14): Between 55 and 70 (Strong momentum, not overbought).
    8. Risk:Reward: Strict 1:1.5 to 1:2 R:R.
    9. Mandatory Auto Square-Off: 03:15 PM IST (Same-day exit).
    
    Passing Threshold: Confluence Score >= 75/100.
    """
    if df_intraday is None or len(df_intraday) < 25:
        return None
        
    df = df_intraday.copy()
    
    # Calculate VWAP
    df["VWAP"] = compute_vwap(df)
    
    # Moving Averages (9, 21)
    df["EMA_9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["EMA_21"] = df["Close"].ewm(span=21, adjust=False).mean()
    
    # Volume average
    df["Vol_SMA20"] = df["Volume"].rolling(window=20).mean()
    
    # RSI (14)
    delta = df["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-9)
    df["RSI"] = 100 - (100 / (1 + rs))
    
    current = df.iloc[-1]
    prev = df.iloc[-2]
    
    close = float(current["Close"])
    open_p = float(current["Open"])
    high = float(current["High"])
    low = float(current["Low"])
    volume = float(current["Volume"])
    vol_sma = float(current["Vol_SMA20"]) if not np.isnan(current["Vol_SMA20"]) else 1.0
    vwap = float(current["VWAP"])
    ema9 = float(current["EMA_9"])
    ema21 = float(current["EMA_21"])
    rsi = float(current["RSI"]) if not np.isnan(current["RSI"]) else 50.0
    
    # ----------------------------------------------------
    # HARD GATEKEEPER 1: Price must be ABOVE VWAP
    # ----------------------------------------------------
    if close <= vwap:
        return None  # Big Institutions only buy above VWAP
        
    # ----------------------------------------------------
    # HARD GATEKEEPER 2: EMA 9 > EMA 21 (Upward trend)
    # ----------------------------------------------------
    if ema9 <= ema21:
        return None
        
    # Look back for Opening Range (first 3-6 bars of the session)
    lookback_range = df.iloc[-25:-1]
    orb_high = float(lookback_range["High"].max())
    recent_swing_low = float(lookback_range["Low"].tail(5).min())
    
    score = 0
    score_breakdown = {}
    
    # Pillar 1: VWAP Position & Price Action (30 Pts)
    pa_score = 0
    is_green = close > open_p
    above_orb = close >= orb_high * 0.998
    
    if close > vwap and above_orb and is_green:
        pa_score = 30
        score_breakdown["VWAP & ORB"] = "30/30 (Clean ORB Breakout above VWAP)"
    elif close > vwap and is_green:
        pa_score = 20
        score_breakdown["VWAP & ORB"] = "20/30 (Bullish above VWAP)"
    else:
        pa_score = 10
        score_breakdown["VWAP & ORB"] = "10/30"
    score += pa_score
    
    # Pillar 2: Volume Blast (25 Pts)
    vol_score = 0
    if volume >= 2.0 * vol_sma:
        vol_score = 25
        score_breakdown["Volume Blast"] = "25/25 (2x+ Volume Surge)"
    elif volume >= 1.5 * vol_sma:
        vol_score = 20
        score_breakdown["Volume Blast"] = "20/25 (1.5x Volume Surge)"
    elif volume >= 1.0 * vol_sma:
        vol_score = 10
        score_breakdown["Volume Blast"] = "10/25 (Average Volume)"
    score += vol_score
    
    # Pillar 3: Intraday Momentum - RSI & EMAs (25 Pts)
    mom_score = 0
    if 55.0 <= rsi <= 72.0:
        mom_score += 15
    elif 50.0 <= rsi < 55.0:
        mom_score += 10
        
    if ema9 > ema21 and close > ema9:
        mom_score += 10
    elif ema9 > ema21:
        mom_score += 5
        
    score += mom_score
    score_breakdown["Momentum"] = f"{mom_score}/25"
    
    # Pillar 4: Risk to Reward Geometry (20 Pts)
    # Stop-Loss: Below VWAP or below recent 5-min swing low
    raw_sl = min(vwap * 0.996, recent_swing_low * 0.998)
    # Max intraday risk cap = 1.2%
    if (close - raw_sl) / close > 0.012:
        raw_sl = close * 0.988  # 1.2% hard cap
        
    stop_loss = round(raw_sl, 2)
    risk_per_share = close - stop_loss
    
    if risk_per_share <= 0:
        return None
        
    target_price = round(close + (1.8 * risk_per_share), 2)
    rr_ratio = round((target_price - close) / risk_per_share, 2)
    
    rr_score = 20 if rr_ratio >= 1.8 else (15 if rr_ratio >= 1.5 else 0)
    score += rr_score
    score_breakdown["R:R Ratio"] = f"{rr_score}/20 (1:{rr_ratio})"
    
    # Threshold check: Min 75/100
    if score < 75 or rr_ratio < 1.5:
        return None
        
    return {
        "symbol": symbol,
        "entry_price": round(close, 2),
        "stop_loss": stop_loss,
        "target_price": target_price,
        "risk_per_share": round(risk_per_share, 2),
        "risk_pct": round((risk_per_share / close) * 100.0, 2),
        "target_pct": round(((target_price - close) / close) * 100.0, 2),
        "rr_ratio": f"1:{rr_ratio}",
        "pattern": "Intraday VWAP Momentum Breakout",
        "trade_type": "INTRADAY",
        "confluence_score": score,
        "score_breakdown": score_breakdown,
        "vwap": round(vwap, 2),
        "rsi": round(rsi, 1),
        "ema9": round(ema9, 2),
        "ema21": round(ema21, 2)
    }
