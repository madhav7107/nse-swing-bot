"""
Bi-Directional (Long & Short) Intraday Strategy with ADX (14) Sideways Filter
- Bullish Setup (BUY): 5-min Close > VWAP & 20 EMA, RSI (55-68), Volume > 20 SMA, ADX >= 22, Nifty 50 Trend == BULLISH
- Bearish Setup (SHORT): 5-min Close < VWAP & 20 EMA, RSI (32-45), Volume > 20 SMA, ADX >= 22, Nifty 50 Trend == BEARISH
- Risk/Reward: 0.75% Stop-Loss & 1.50% Target (1:2 R:R)
"""

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

def compute_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Computes 14-period Average Directional Index (ADX) to detect choppy/sideways markets."""
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0
    plus_dm[(plus_dm < minus_dm)] = 0
    minus_dm[(minus_dm < plus_dm)] = 0

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.rolling(window=period, min_periods=1).mean()
    plus_di = 100 * (plus_dm.rolling(window=period, min_periods=1).mean() / (atr + 1e-9))
    minus_di = 100 * (minus_dm.rolling(window=period, min_periods=1).mean() / (atr + 1e-9))
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9))
    adx = dx.rolling(window=period, min_periods=1).mean()
    return adx

def analyze_intraday_vwap_signal(
    df_intraday: pd.DataFrame,
    symbol: str,
    nifty_trend: str = None,
    scanner_meta: Dict = None
) -> Optional[Dict]:
    """
    Bi-Directional Intraday Entry Engine (Long & Short-Sell):
    1. Sideways / Choppy Market Filter: ADX(14) must be >= 22.0.
    2. Bullish (BUY): Close > VWAP & 20 EMA, RSI 55-68, Vol > 20 SMA, Nifty Trend == BULLISH.
    3. Bearish (SELL/SHORT): Close < VWAP & 20 EMA, RSI 32-45, Vol > 20 SMA, Nifty Trend == BEARISH.
    """
    if df_intraday is None or len(df_intraday) < 20:
        return None
        
    df = df_intraday.copy()
    df["VWAP"] = compute_vwap(df)
    df["EMA_20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["Vol_SMA20"] = df["Volume"].rolling(window=20, min_periods=5).mean()
    df["ADX"] = compute_adx(df, period=14)
    
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
    adx = float(current["ADX"]) if not np.isnan(current["ADX"]) else 0.0

    # 1. Sideways / Choppy Market Filter (No-Trade Zone)
    min_adx = getattr(config, "ADX_MIN_THRESHOLD", 22.0)
    if adx < min_adx:
        return None # Market is flat/choppy; stay out!

    # 2. Volume confirmation
    if volume <= vol_sma:
        return None

    # Fetch Nifty 50 trend if not passed
    if nifty_trend is None:
        try:
            from morning_dynamic_scanner import get_nifty50_intraday_trend
            nifty_trend = get_nifty50_intraday_trend().get("trend", "NEUTRAL")
        except Exception:
            nifty_trend = "NEUTRAL"

    sl_pct = getattr(config, "INTRADAY_SL_PCT", 0.75) / 100.0
    tgt_pct = getattr(config, "INTRADAY_TARGET_PCT", 1.50) / 100.0
    scan_reason = scanner_meta.get("reason", "Nifty Liquid Stock") if scanner_meta else "Liquid Stock"

    # ----------------------------------------------------
    # BULLISH SETUP (BUY / LONG)
    # ----------------------------------------------------
    if (close > vwap) and (close > ema20) and (55.0 <= rsi <= 68.0) and (nifty_trend == "BULLISH"):
        stop_loss = round(close * (1.0 - sl_pct), 2)
        target_price = round(close * (1.0 + tgt_pct), 2)
        risk_per_share = round(close - stop_loss, 2)
        if risk_per_share <= 0:
            return None

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
            "pattern": "Bi-Directional VWAP+20EMA+ADX BUY",
            "trade_type": "INTRADAY",
            "confluence_score": 90,
            "vwap": round(vwap, 2),
            "ema20": round(ema20, 2),
            "rsi": round(rsi, 1),
            "adx": round(adx, 1),
            "nifty_trend": nifty_trend,
            "notes": f"BUY | ADX: {round(adx, 1)} | Nifty: {nifty_trend} | Scanner: {scan_reason}"
        }

    # ----------------------------------------------------
    # BEARISH SETUP (SHORT-SELL)
    # ----------------------------------------------------
    if (close < vwap) and (close < ema20) and (32.0 <= rsi <= 45.0) and (nifty_trend == "BEARISH"):
        stop_loss = round(close * (1.0 + sl_pct), 2)
        target_price = round(close * (1.0 - tgt_pct), 2)
        risk_per_share = round(stop_loss - close, 2)
        if risk_per_share <= 0:
            return None

        return {
            "symbol": symbol,
            "direction": "SELL",
            "entry_price": round(close, 2),
            "stop_loss": stop_loss,
            "target_price": target_price,
            "risk_per_share": risk_per_share,
            "risk_pct": 0.75,
            "target_pct": 1.50,
            "rr_ratio": "1:2.0",
            "pattern": "Bi-Directional VWAP+20EMA+ADX SHORT",
            "trade_type": "INTRADAY",
            "confluence_score": 90,
            "vwap": round(vwap, 2),
            "ema20": round(ema20, 2),
            "rsi": round(rsi, 1),
            "adx": round(adx, 1),
            "nifty_trend": nifty_trend,
            "notes": f"SHORT | ADX: {round(adx, 1)} | Nifty: {nifty_trend} | Scanner: {scan_reason}"
        }

    return None
