import pandas as pd
import numpy as np
from typing import Optional, Dict
import config
from data_engine import check_nifty_market_health

def analyze_breakout_signal(df: pd.DataFrame, symbol: str) -> Optional[Dict]:
    """
    Institutional Momentum Breakout & Volatility Contraction Pattern (VCP) Engine:
    
    Captures stocks consolidating near multi-week highs and breaking out with
    heavy Smart Money volume expansion.
    
    1. Macro Protection: Nifty 50 Crash Shield
    2. Category 1: Base & Resistance Breakout (30 Pts)
    3. Category 2: Smart Money Institutional Volume Surge (25 Pts)
    4. Category 3: Trend & Moving Average Structure (20 Pts)
    5. Category 4: Momentum Sweet Spot & Volatility Contraction (15 Pts)
    6. Category 5: Asymmetric Risk-to-Reward Geometry (10 Pts)
    
    Strict Minimum Entry Threshold: 75 / 100 Confluence Score.
    """
    if df is None or len(df) < 60:
        return None
        
    # Pillar 0: Macro Protection
    if not check_nifty_market_health():
        return None
        
    current = df.iloc[-1]
    prev = df.iloc[-2]
    
    close = float(current["Close"])
    open_p = float(current["Open"])
    high = float(current["High"])
    low = float(current["Low"])
    volume = float(current["Volume"])
    vol_sma = float(current["Volume_SMA20"]) if not np.isnan(current["Volume_SMA20"]) else 1.0
    
    ema9 = float(current["EMA_9"]) if "EMA_9" in current else close
    ema20 = float(current["EMA_20"])
    ema21 = float(current["EMA_21"]) if "EMA_21" in current else ema20
    ema50 = float(current["EMA_50"])
    ema200 = float(current["EMA_200"])
    
    rsi = float(current["RSI"])
    atr = float(current["ATR"]) if not np.isnan(current["ATR"]) else (high - low)
    macd_hist = float(current["MACD_Hist"]) if "MACD_Hist" in current else 0.0
    prev_macd_hist = float(prev["MACD_Hist"]) if "MACD_Hist" in prev else 0.0
    supertrend_bullish = bool(current["Supertrend_Bullish"]) if "Supertrend_Bullish" in current else True
    
    # ----------------------------------------------------
    # HARD GATEKEEPER 1: Long-term Bullish Trend
    # ----------------------------------------------------
    if close < ema200:
        return None
        
    # Look back 25 bars for Consolidation Resistance Range
    lookback = df.iloc[-30:-2]
    prior_resistance = float(lookback["High"].max())
    prior_support = float(lookback["Low"].min())
    
    # HARD GATEKEEPER 2: Breakout Condition
    # Today's High must break above prior 25-day resistance, and Close must be very strong
    if high <= prior_resistance:
        return None
        
    candle_range = max(0.01, high - low)
    close_strength = (close - low) / candle_range # Where did candle close in its range?
    
    # Must close in top 35% of the day's candle (buyers in firm control)
    if close_strength < 0.65 or close < open_p:
        return None
        
    score = 0
    score_breakdown = {}
    
    # ----------------------------------------------------
    # CATEGORY 1: BASE & RESISTANCE BREAKOUT (Max 30 Pts)
    # ----------------------------------------------------
    b_score = 0
    
    # Decisive close above prior resistance
    if close > prior_resistance:
        b_score += 15
        score_breakdown["Resistance Clean Close"] = 15
    elif close >= prior_resistance * 0.998:
        b_score += 10
        score_breakdown["At Resistance Edge"] = 10
        
    # Bullish Body Dominance (>75% of candle range is body)
    body_pct = abs(close - open_p) / candle_range
    if body_pct >= 0.70 and close_strength >= 0.75:
        b_score += 10
        score_breakdown["Dominant Bullish Marubozu"] = 10
    elif body_pct >= 0.50:
        b_score += 5
        score_breakdown["Solid Bullish Body"] = 5
        
    # Volatility Contraction before breakout (Base Consolidation)
    base_range_pct = (prior_resistance - prior_support) / prior_resistance
    if base_range_pct <= 0.12:  # Tight base <= 12% width
        b_score += 5
        score_breakdown["Tight VCP Base (<=12%)"] = 5
        
    score += b_score
    
    # ----------------------------------------------------
    # CATEGORY 2: SMART MONEY VOLUME SURGE (Max 25 Pts)
    # ----------------------------------------------------
    v_score = 0
    vol_ratio = volume / vol_sma if vol_sma > 0 else 1.0
    
    if vol_ratio >= 2.5:
        v_score += 25
        score_breakdown["Institutional Volume (>2.5x SMA)"] = 25
    elif vol_ratio >= 1.8:
        v_score += 20
        score_breakdown["High Volume Expansion (>1.8x SMA)"] = 20
    elif vol_ratio >= 1.4:
        v_score += 12
        score_breakdown["Moderate Volume Surge (>1.4x SMA)"] = 12
        
    score += v_score
    
    # ----------------------------------------------------
    # CATEGORY 3: TREND & MOVING AVERAGE STRUCTURE (Max 20 Pts)
    # ----------------------------------------------------
    t_score = 0
    
    # Perfect Bullish Alignment: 20 EMA > 50 EMA > 200 EMA
    if ema20 > ema50 > ema200:
        t_score += 10
        score_breakdown["Bullish EMA Stack (20>50>200)"] = 10
    elif ema20 > ema50:
        t_score += 6
        score_breakdown["Short-term Trend Bullish (20>50)"] = 6
        
    # 9 EMA > 21 EMA Short-term Momentum
    if ema9 > ema21:
        t_score += 5
        score_breakdown["Fast Momentum (EMA 9>21)"] = 5
        
    # Supertrend Indicator
    if supertrend_bullish:
        t_score += 5
        score_breakdown["Supertrend Bullish"] = 5
        
    score += t_score
    
    # ----------------------------------------------------
    # CATEGORY 4: MOMENTUM & VCP SWEET SPOT (Max 15 Pts)
    # ----------------------------------------------------
    m_score = 0
    
    # Breakout RSI Sweet Spot (55 to 72)
    if 56.0 <= rsi <= 72.0:
        m_score += 10
        score_breakdown["RSI Breakout Sweet Spot (56-72)"] = 10
    elif 50.0 <= rsi < 56.0:
        m_score += 5
        score_breakdown["RSI Gaining Momentum (50-56)"] = 5
        
    # MACD Histogram Positive and Expanding
    if macd_hist > 0 and macd_hist > prev_macd_hist:
        m_score += 5
        score_breakdown["MACD Histogram Expanding"] = 5
    elif macd_hist > 0:
        m_score += 3
        score_breakdown["MACD Histogram Positive"] = 3
        
    score += m_score
    
    # ----------------------------------------------------
    # CATEGORY 5: RISK-TO-REWARD GEOMETRY (Max 10 Pts)
    # ----------------------------------------------------
    # Stop loss placed below breakout candle low or 20 EMA, whichever is closer
    sl_level = max(low - (0.5 * atr), ema20 * 0.995)
    
    # Safety cap: Stop loss must be between 2.0% and 5.0%
    risk_pct = (close - sl_level) / close
    if risk_pct < 0.02:
        sl_level = round(close * 0.975, 2) # minimum 2.5% risk buffer
    elif risk_pct > 0.05:
        sl_level = round(close * 0.955, 2) # maximum 4.5% risk cap
        
    risk_per_share = close - sl_level
    if risk_per_share <= 0:
        return None
        
    # Target: 1:2.5 to 1:3.0 Risk-to-Reward
    target_price = round(close + (2.5 * risk_per_share), 2)
    rr_ratio = round((target_price - close) / risk_per_share, 2)
    
    rr_score = 0
    if rr_ratio >= 2.5:
        rr_score = 10
        score_breakdown[f"Asymmetric R:R (1:{rr_ratio})"] = 10
    elif rr_ratio >= 2.0:
        rr_score = 8
        score_breakdown[f"Good R:R (1:{rr_ratio})"] = 8
        
    score += rr_score
    
    # ----------------------------------------------------
    # STRICT 75% CONFLUENCE THRESHOLD GATEKEEPER
    # ----------------------------------------------------
    threshold = getattr(config, "CONFLUENCE_THRESHOLD", 75)
    if score < threshold:
        return None
        
    return {
        "symbol": symbol,
        "entry_price": round(close, 2),
        "stop_loss": round(sl_level, 2),
        "target_price": target_price,
        "risk_reward": rr_ratio,
        "confluence_score": score,
        "strategy": "BREAKOUT",
        "pattern": "Institutional Breakout",
        "reason": f"Resistance Breakout with {round(vol_ratio, 1)}x Volume [Confluence: {score}%]",
        "score_breakdown": score_breakdown
    }
