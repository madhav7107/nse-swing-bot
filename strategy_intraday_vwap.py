import pandas as pd
import numpy as np
from typing import Optional, Dict
import datetime
import config

def compute_vwap(df: pd.DataFrame) -> pd.Series:
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3.0
    cum_pv = (typical_price * df["Volume"]).cumsum()
    cum_vol = df["Volume"].cumsum()
    return cum_pv / (cum_vol + 1e-9)

def analyze_intraday_vwap_signal(df_intraday: pd.DataFrame, symbol: str) -> Optional[Dict]:
    if df_intraday is None or len(df_intraday) < 25:
        return None
        
    df = df_intraday.copy()
    df["VWAP"] = compute_vwap(df)
    df["EMA_9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["EMA_21"] = df["Close"].ewm(span=21, adjust=False).mean()
    df["Vol_SMA20"] = df["Volume"].rolling(window=20).mean()
    
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
    
    lookback_range = df.iloc[-25:-1]
    orb_high = float(lookback_range["High"].max())
    orb_low = float(lookback_range["Low"].min())
    recent_swing_low = float(lookback_range["Low"].tail(5).min())
    recent_swing_high = float(lookback_range["High"].tail(5).max())
    
    # ----------------------------------------------------
    # PATH A: INTRADAY LONG / BUY (Market Up / Price > VWAP)
    # ----------------------------------------------------
    if close > vwap and ema9 > ema21:
        score = 0
        score_breakdown = {}
        is_green = close > open_p
        above_orb = close >= orb_high * 0.998
        
        pa_score = 30 if (above_orb and is_green) else (20 if is_green else 10)
        score += pa_score
        score_breakdown["VWAP_ORB"] = f"{pa_score}/30"
        
        vol_score = 25 if volume >= 2.0 * vol_sma else (20 if volume >= 1.5 * vol_sma else (10 if volume >= vol_sma else 0))
        score += vol_score
        score_breakdown["Volume"] = f"{vol_score}/25"
        
        mom_score = 15 if (55.0 <= rsi <= 72.0) else (10 if (50.0 <= rsi < 55.0) else 5)
        if close > ema9: mom_score += 10
        score += mom_score
        score_breakdown["Momentum"] = f"{mom_score}/25"
        
        raw_sl = min(vwap * 0.996, recent_swing_low * 0.998)
        if (close - raw_sl) / close > 0.012: raw_sl = close * 0.988
        stop_loss = round(raw_sl, 2)
        risk_per_share = close - stop_loss
        if risk_per_share <= 0: return None
        target_price = round(close + (1.8 * risk_per_share), 2)
        rr_ratio = round((target_price - close) / risk_per_share, 2)
        
        rr_score = 20 if rr_ratio >= 1.8 else (15 if rr_ratio >= 1.5 else 0)
        score += rr_score
        score_breakdown["RR"] = f"{rr_score}/20"
        
        if score >= 75 and rr_ratio >= 1.5:
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
                "pattern": "Intraday VWAP Bullish Breakout",
                "trade_type": "INTRADAY",
                "confluence_score": score,
                "score_breakdown": score_breakdown,
                "vwap": round(vwap, 2),
                "rsi": round(rsi, 1)
            }
            
    # ----------------------------------------------------
    # PATH B: INTRADAY SHORT SELL (Market Down / Price < VWAP)
    # ----------------------------------------------------
    elif close < vwap and ema9 < ema21:
        score = 0
        score_breakdown = {}
        is_red = close < open_p
        below_orb = close <= orb_low * 1.002
        
        pa_score = 30 if (below_orb and is_red) else (20 if is_red else 10)
        score += pa_score
        score_breakdown["VWAP_ORB"] = f"{pa_score}/30"
        
        vol_score = 25 if volume >= 2.0 * vol_sma else (20 if volume >= 1.5 * vol_sma else (10 if volume >= vol_sma else 0))
        score += vol_score
        score_breakdown["Volume"] = f"{vol_score}/25"
        
        mom_score = 15 if (28.0 <= rsi <= 45.0) else (10 if (45.0 < rsi <= 50.0) else 5)
        if close < ema9: mom_score += 10
        score += mom_score
        score_breakdown["Momentum"] = f"{mom_score}/25"
        
        raw_sl = max(vwap * 1.004, recent_swing_high * 1.002)
        if (raw_sl - close) / close > 0.012: raw_sl = close * 1.012
        stop_loss = round(raw_sl, 2)
        risk_per_share = stop_loss - close
        if risk_per_share <= 0: return None
        target_price = round(close - (1.8 * risk_per_share), 2)
        rr_ratio = round((close - target_price) / risk_per_share, 2)
        
        rr_score = 20 if rr_ratio >= 1.8 else (15 if rr_ratio >= 1.5 else 0)
        score += rr_score
        score_breakdown["RR"] = f"{rr_score}/20"
        
        if score >= 75 and rr_ratio >= 1.5:
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
