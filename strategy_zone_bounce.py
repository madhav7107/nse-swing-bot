import pandas as pd
import numpy as np
from typing import Optional, Dict
import config

def analyze_zone_bounce_signal(df: pd.DataFrame, symbol: str) -> Optional[Dict]:
    """
    Evaluates high-probability setups combining:
    1. Price Action: Support/Demand Zone Bounce OR 2x Volume Resistance Breakout
    2. Trend Filter: 200 EMA Macro Trend + 20/50 EMA Alignment
    3. Next Resistance Target: Minimum 1:2 Risk-to-Reward ratio
    4. Smart Money Volume Confirmation
    """
    if df is None or len(df) < 60:
        return None
    
    current = df.iloc[-1]
    prev = df.iloc[-2]
    
    close = float(current["Close"])
    open_p = float(current["Open"])
    high = float(current["High"])
    low = float(current["Low"])
    volume = float(current["Volume"])
    vol_sma = float(current["Volume_SMA20"]) if not np.isnan(current["Volume_SMA20"]) else 1.0
    
    ema20 = float(current["EMA_20"])
    ema50 = float(current["EMA_50"])
    ema200 = float(current["EMA_200"])
    rsi = float(current["RSI"])
    prev_rsi = float(prev["RSI"])
    atr = float(current["ATR"]) if not np.isnan(current["ATR"]) else (high - low)
    
    # ----------------------------------------------------
    # RULE 3: Trend Filter (200 EMA & 50 EMA Alignment)
    # ----------------------------------------------------
    is_macro_uptrend = (close > ema200) and (ema50 >= ema200 * 0.98)
    if not is_macro_uptrend:
        return None
        
    # Calculate Key Swing Levels (Support & Next Resistance)
    # Look back past 40 days (excluding today and yesterday)
    lookback_slice = df.iloc[-45:-2]
    prior_support = float(lookback_slice["Low"].min())
    prior_resistance = float(lookback_slice["High"].max())
    
    # ----------------------------------------------------
    # SETUP TYPE 1: Support Zone Bounce (Price Action)
    # ----------------------------------------------------
    dist_to_ema20 = abs(low - ema20) / ema20
    dist_to_ema50 = abs(low - ema50) / ema50
    touching_ema_zone = (dist_to_ema20 <= 0.025) or (dist_to_ema50 <= 0.025) or (low <= ema20 and close >= ema20 * 0.99)
    near_support_zone = abs(low - prior_support) / prior_support <= 0.025
    in_support_zone = touching_ema_zone or near_support_zone
    
    # Price Action Candlesticks
    candle_range = high - low
    body = abs(close - open_p)
    lower_wick = min(open_p, close) - low
    is_hammer = (lower_wick >= 1.4 * body) and (close >= open_p or (close - low) > 0.6 * candle_range)
    is_green = close > open_p
    engulfing = is_green and (prev["Close"] < prev["Open"]) and (close >= prev["High"]) and (open_p <= prev["Close"])
    strong_bounce = is_green and (close > prev["High"])
    is_reversal = is_hammer or engulfing or strong_bounce
    
    rsi_bouncing = (rsi >= 38.0) and (rsi <= config.RSI_MAX_ENTRY) and (rsi >= prev_rsi)
    vol_bounce_ok = volume >= 0.75 * vol_sma
    
    is_support_bounce_setup = in_support_zone and is_reversal and rsi_bouncing and vol_bounce_ok
    
    # ----------------------------------------------------
    # SETUP TYPE 2: Resistance Breakout with High Volume (Smart Money)
    # ----------------------------------------------------
    # Breakout: Price breaks above the recent 20-day high with 1.5x - 2x volume surge
    recent_20d_high = float(df["High"].iloc[-25:-1].max())
    is_breakout = (close > recent_20d_high) and is_green and (volume >= 1.5 * vol_sma) and (rsi >= 52.0 and rsi <= 72.0)
    
    if not is_support_bounce_setup and not is_breakout:
        return None
        
    # ----------------------------------------------------
    # RULE 1 & 2: Stop Loss & Next Resistance Target (1:2+ RR)
    # ----------------------------------------------------
    if is_breakout:
        pattern_name = "Smart Money Breakout (High Volume)"
        # SL below breakout candle low
        stop_loss = round(low - (0.3 * atr), 2)
        # Target: Prior resistance + height of consolidation or minimum 1:2 RR
        risk_per_share = close - stop_loss
        target_price = round(max(close + (2.0 * risk_per_share), prior_resistance * 1.03), 2)
    else:
        pattern_name = "Bullish Hammer" if is_hammer else ("Bullish Engulfing" if engulfing else "Support Zone Bounce")
        # SL below support zone low with 0.4 ATR buffer
        zone_low = min(low, float(prev["Low"]))
        stop_loss = round(zone_low - (0.4 * atr), 2)
        risk_per_share = close - stop_loss
        
        # Target: Aim for Next Resistance or minimum 1:2 RR
        min_target = close + (config.TARGET_RR_RATIO * risk_per_share)
        target_price = round(max(min_target, prior_resistance), 2)
        
    risk_pct = (risk_per_share / close) * 100.0
    if risk_pct < 1.0 or risk_pct > 6.5:
        return None
        
    target_pct = ((target_price - close) / close) * 100.0
    rr_ratio = round((target_price - close) / risk_per_share, 2)
    
    # Enforce minimum 1:2 Risk to Reward
    if rr_ratio < 1.9:
        return None
        
    return {
        "symbol": symbol,
        "entry_price": round(close, 2),
        "stop_loss": stop_loss,
        "target_price": target_price,
        "risk_per_share": round(risk_per_share, 2),
        "risk_pct": round(risk_pct, 2),
        "target_pct": round(target_pct, 2),
        "rr_ratio": f"1:{rr_ratio}",
        "next_resistance": round(prior_resistance, 2),
        "pattern": pattern_name,
        "rsi": round(rsi, 1),
        "ema20": round(ema20, 2),
        "ema50": round(ema50, 2),
        "ema200": round(ema200, 2),
        "volume_ratio": round(volume / vol_sma, 2),
        "reason": f"{pattern_name} with 1:{rr_ratio} RR (Target @ Next Resistance Rs. {round(prior_resistance, 2)})"
    }
