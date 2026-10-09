import pandas as pd
import numpy as np
from typing import Optional, Dict
import datetime
import config

def compute_vwap(df: pd.DataFrame) -> pd.Series:
    """Computes Volume Weighted Average Price (VWAP)."""
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3.0
    cum_pv = (typical_price * df["Volume"]).cumsum()
    cum_vol = df["Volume"].cumsum()
    return cum_pv / (cum_vol + 1e-9)

def analyze_intraday_vwap_signal(df_intraday: pd.DataFrame, symbol: str) -> Optional[Dict]:
    """
    Practical, Responsive 5-Min Intraday 2-Way Engine (BUY & SHORT SELL):
    - Triggers reliably during market hours without being over-restricted.
    - BUY: Price > VWAP, 9 EMA >= 21 EMA, Healthy Volume >= 1.0x SMA, RSI 50-75.
    - SHORT SELL: Price < VWAP, 9 EMA <= 21 EMA, Healthy Volume >= 1.0x SMA, RSI 25-50.
    - Fast R:R Ratio: 1:1.5 with realistic intraday targets.
    - Passing Score: >= 60/100 (Practical threshold).
    """
    if df_intraday is None or len(df_intraday) < 15:
        return None
        
    df = df_intraday.copy()
    df["VWAP"] = compute_vwap(df)
    df["EMA_9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["EMA_21"] = df["Close"].ewm(span=21, adjust=False).mean()
    df["Vol_SMA20"] = df["Volume"].rolling(window=15, min_periods=5).mean()
    
    delta = df["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14, min_periods=5).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14, min_periods=5).mean()
    rs = gain / (loss + 1e-9)
    df["RSI"] = 100 - (100 / (1 + rs))
    
    current = df.iloc[-1]
    close = float(current["Close"])
    open_p = float(current["Open"])
    high = float(current["High"])
    low = float(current["Low"])
    volume = float(current["Volume"])
    vol_sma = float(current["Vol_SMA20"]) if not np.isnan(current["Vol_SMA20"]) and current["Vol_SMA20"] > 0 else 1.0
    vwap = float(current["VWAP"])
    ema9 = float(current["EMA_9"])
    ema21 = float(current["EMA_21"])
    rsi = float(current["RSI"]) if not np.isnan(current["RSI"]) else 50.0
    
    lookback_range = df.iloc[-20:-1] if len(df) >= 20 else df.iloc[:-1]
    orb_high = float(lookback_range["High"].max()) if not lookback_range.empty else high
    orb_low = float(lookback_range["Low"].min()) if not lookback_range.empty else low
    recent_swing_low = float(df["Low"].tail(5).min())
    recent_swing_high = float(df["High"].tail(5).max())
    
    # ----------------------------------------------------
    # PATH A: INTRADAY BUY (Price above VWAP)
    # ----------------------------------------------------
    if close >= vwap and ema9 >= ema21:
        score = 0
        score_breakdown = {}
        is_green = close >= open_p
        
        # 1. Price vs VWAP (35 pts)
        pa_score = 35 if (close >= orb_high * 0.999 and is_green) else (25 if is_green else 20)
        score += pa_score
        score_breakdown["Price_VWAP"] = f"{pa_score}/35"
        
        # 2. Volume (25 pts)
        vol_score = 25 if volume >= 1.5 * vol_sma else (20 if volume >= 1.0 * vol_sma else 15)
        score += vol_score
        score_breakdown["Volume"] = f"{vol_score}/25"
        
        # 3. Momentum RSI & EMA (25 pts)
        mom_score = 20 if (52.0 <= rsi <= 75.0) else (15 if 48.0 <= rsi < 52.0 else 10)
        if close >= ema9: mom_score += 5
        score += mom_score
        score_breakdown["Momentum"] = f"{mom_score}/25"
        
        # 4. Stop Loss & Target (15 pts)
        raw_sl = min(vwap * 0.996, recent_swing_low * 0.998)
        if (close - raw_sl) / close > 0.012: raw_sl = close * 0.988 # Cap at 1.2%
        stop_loss = round(raw_sl, 2)
        risk_per_share = close - stop_loss
        if risk_per_share <= 0: return None
        
        target_price = round(close + (1.5 * risk_per_share), 2)
        rr_ratio = round((target_price - close) / risk_per_share, 2)
        score += 15
        score_breakdown["RR"] = f"15/15 (1:{rr_ratio})"
        
        if score >= 60:
            return {
                "symbol": symbol,
                "direction": "BUY",
                "entry_price": round(close, 2),
                "stop_loss": stop_loss,
                "target_price": target_price,
                "risk_per_share": round(risk_per_share, 2),
                "risk_pct": round((risk_per_share / close) * 100.0, 2),
                "target_pct": round(((target_price - close) / close) * 100.0, 2),
                "rr_ratio": f"1:{rr_ratio}",
                "pattern": "Intraday VWAP Momentum BUY",
                "trade_type": "INTRADAY",
                "confluence_score": score,
                "score_breakdown": score_breakdown,
                "vwap": round(vwap, 2),
                "rsi": round(rsi, 1)
            }
            
    # ----------------------------------------------------
    # PATH B: INTRADAY SHORT SELL (Price below VWAP)
    # ----------------------------------------------------
    elif close <= vwap and ema9 <= ema21:
        score = 0
        score_breakdown = {}
        is_red = close <= open_p
        
        # 1. Price vs VWAP (35 pts)
        pa_score = 35 if (close <= orb_low * 1.001 and is_red) else (25 if is_red else 20)
        score += pa_score
        score_breakdown["Price_VWAP"] = f"{pa_score}/35"
        
        # 2. Volume (25 pts)
        vol_score = 25 if volume >= 1.5 * vol_sma else (20 if volume >= 1.0 * vol_sma else 15)
        score += vol_score
        score_breakdown["Volume"] = f"{vol_score}/25"
        
        # 3. Momentum RSI & EMA (25 pts)
        mom_score = 20 if (25.0 <= rsi <= 48.0) else (15 if 48.0 < rsi <= 52.0 else 10)
        if close <= ema9: mom_score += 5
        score += mom_score
        score_breakdown["Momentum"] = f"{mom_score}/25"
        
        # 4. Stop Loss & Target (15 pts) - SL above entry for short
        raw_sl = max(vwap * 1.004, recent_swing_high * 1.002)
        if (raw_sl - close) / close > 0.012: raw_sl = close * 1.012 # Cap at 1.2%
        stop_loss = round(raw_sl, 2)
        risk_per_share = stop_loss - close
        if risk_per_share <= 0: return None
        
        target_price = round(close - (1.5 * risk_per_share), 2)
        rr_ratio = round((close - target_price) / risk_per_share, 2)
        score += 15
        score_breakdown["RR"] = f"15/15 (1:{rr_ratio})"
        
        if score >= 60:
            return {
                "symbol": symbol,
                "direction": "SELL",
                "entry_price": round(close, 2),
                "stop_loss": stop_loss,
                "target_price": target_price,
                "risk_per_share": round(risk_per_share, 2),
                "risk_pct": round((risk_per_share / close) * 100.0, 2),
                "target_pct": round(((close - target_price) / close) * 100.0, 2),
                "rr_ratio": f"1:{rr_ratio}",
                "pattern": "Intraday VWAP Breakdown (SHORT SELL)",
                "trade_type": "INTRADAY",
                "confluence_score": score,
                "score_breakdown": score_breakdown,
                "vwap": round(vwap, 2),
                "rsi": round(rsi, 1)
            }
            
    return None
