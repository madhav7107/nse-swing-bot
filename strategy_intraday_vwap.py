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
    High-Probability Intraday Entry (Strict VWAP + Trend Filter):
    Only triggers a BUY order when:
    1. 5-minute candle closes above both VWAP and 20 EMA (close > VWAP and close > EMA_20).
    2. RSI (14-period) is between 55.0 and 68.0.
    3. Volume is strictly higher than 20-period average volume (volume > Vol_SMA20).
    4. Immediate 0.75% Stop-Loss and 1.50% Target (Exact 1:2 Risk to Reward).
    """
    if df_intraday is None or len(df_intraday) < 20:
        return None
        
    df = df_intraday.copy()
    df["VWAP"] = compute_vwap(df)
    df["EMA_20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["Vol_SMA20"] = df["Volume"].rolling(window=20, min_periods=5).mean()
    
    # 14-period RSI
    delta = df["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14, min_periods=5).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14, min_periods=5).mean()
    rs = gain / (loss + 1e-9)
    df["RSI"] = 100 - (100 / (1 + rs))
    
    current = df.iloc[-1]
    close = float(current["Close"])
    volume = float(current["Volume"])
    vol_sma = float(current["Vol_SMA20"]) if not np.isnan(current["Vol_SMA20"]) and current["Vol_SMA20"] > 0 else 1.0
    vwap = float(current["VWAP"])
    ema20 = float(current["EMA_20"])
    rsi = float(current["RSI"]) if not np.isnan(current["RSI"]) else 50.0

    # ----------------------------------------------------
    # STRICT HIGH-PROBABILITY ENTRY GATES (Rules 3 & 4)
    # ----------------------------------------------------
    # Gate 1: 5-min candle closes above both VWAP and 20 EMA
    is_above_vwap_and_ema20 = (close > vwap) and (close > ema20)
    if not is_above_vwap_and_ema20:
        return None

    # Gate 2: RSI is strictly between 55 and 68
    is_rsi_in_sweet_spot = (55.0 <= rsi <= 68.0)
    if not is_rsi_in_sweet_spot:
        return None

    # Gate 3: Volume is higher than 20-period average volume
    is_volume_confirmed = (volume > vol_sma)
    if not is_volume_confirmed:
        return None

    # Gate 4: Immediate 0.75% Stop-Loss and 1.50% Target (1:2 R:R)
    sl_pct = getattr(config, "INTRADAY_SL_PCT", 0.75) / 100.0
    tgt_pct = getattr(config, "INTRADAY_TARGET_PCT", 1.50) / 100.0
    
    stop_loss = round(close * (1.0 - sl_pct), 2)
    target_price = round(close * (1.0 + tgt_pct), 2)
    risk_per_share = round(close - stop_loss, 2)
    reward_per_share = round(target_price - close, 2)
    
    if risk_per_share <= 0:
        return None

    score = 88 # High-probability confluence score
    score_breakdown = {
        "VWAP_EMA20_Cross": "PASS (Above VWAP & 20 EMA)",
        "RSI_Momentum": f"PASS (RSI: {round(rsi, 1)} in 55-68 range)",
        "Volume_Surge": f"PASS (Vol: {int(volume):,} > Avg: {int(vol_sma):,})",
        "Risk_Reward": f"1:2.0 (SL: -0.75%, Tgt: +1.50%)"
    }

    return {
        "symbol": symbol,
        "direction": "BUY",
        "entry_price": round(close, 2),
        "stop_loss": stop_loss,
        "target_price": target_price,
        "risk_per_share": risk_per_share,
        "risk_pct": 0.75,
        "target_pct": 1.50,
        "rr_ratio": "1:2.0",
        "pattern": "High-Probability VWAP+20EMA Trend BUY",
        "trade_type": "INTRADAY",
        "confluence_score": score,
        "score_breakdown": score_breakdown,
        "vwap": round(vwap, 2),
        "ema20": round(ema20, 2),
        "rsi": round(rsi, 1),
        "volume": int(volume),
        "vol_sma20": int(vol_sma)
    }
