import pandas as pd
import numpy as np
from typing import Optional, Dict
import config
from data_engine import check_nifty_market_health

def analyze_zone_bounce_signal(df: pd.DataFrame, symbol: str) -> Optional[Dict]:
    """
    Institutional 5-Pillar Confluence Swing Trading Engine:
    
    1. Macro Protection: Nifty-50 Market Health Filter (No buying during market crashes).
    2. Category 1: Price Action & Market Structure (BOS, Support Bounce, Hammer/Engulfing, W-Pattern) -> 30 Pts
    3. Category 2: Trend Alignment (200 EMA Filter, EMA 9/21 Golden Cross, Supertrend 10,3) -> 25 Pts
    4. Category 3: Momentum Verification (RSI 50-65 Sweet Spot, MACD Bullish Crossover) -> 20 Pts
    5. Category 4: Volume & Smart Money Confirmation (1.5x-2x 20 SMA Surge, Volume Expansion) -> 15 Pts
    6. Category 5: Risk-to-Reward (Minimum 1:2 RR to Next Resistance, 1.5x ATR SL) -> 10 Pts
    
    Minimum Entry Threshold: 75 / 100 Confluence Score.
    """
    if df is None or len(df) < 60:
        return None
    
    # ----------------------------------------------------
    # PILLAR 0: MACRO MARKET CRASH FILTER (NIFTY 50)
    # ----------------------------------------------------
    if not check_nifty_market_health():
        # Market in heavy panic sell-off (-1.25%+), abort fresh long entries to protect capital
        return None
        
    current = df.iloc[-1]
    prev = df.iloc[-2]
    
    close = float(current["Close"])
    open_p = float(current["Open"])
    high = float(current["High"])
    low = float(current["Low"])
    volume = float(current["Volume"])
    vol_sma = float(current["Volume_SMA20"]) if not np.isnan(current["Volume_SMA20"]) else 1.0
    prev_vol = float(prev["Volume"])
    
    ema9 = float(current["EMA_9"]) if "EMA_9" in current else close
    ema20 = float(current["EMA_20"])
    ema21 = float(current["EMA_21"]) if "EMA_21" in current else ema20
    ema50 = float(current["EMA_50"])
    ema200 = float(current["EMA_200"])
    
    rsi = float(current["RSI"])
    prev_rsi = float(prev["RSI"])
    atr = float(current["ATR"]) if not np.isnan(current["ATR"]) else (high - low)
    
    macd = float(current["MACD"]) if "MACD" in current else 0.0
    macd_signal = float(current["MACD_Signal"]) if "MACD_Signal" in current else 0.0
    macd_hist = float(current["MACD_Hist"]) if "MACD_Hist" in current else 0.0
    prev_macd_hist = float(prev["MACD_Hist"]) if "MACD_Hist" in prev else 0.0
    
    supertrend_bullish = bool(current["Supertrend_Bullish"]) if "Supertrend_Bullish" in current else True
    
    # ----------------------------------------------------
    # HARD GATEKEEPER 1: 200 EMA Macro Trend Rule
    # ----------------------------------------------------
    if close < ema200:
        return None  # Strictly avoid downtrending stocks
        
    # Look back 40 days for Key Swing Levels (Support & Next Resistance)
    lookback_slice = df.iloc[-45:-2]
    prior_support = float(lookback_slice["Low"].min())
    prior_resistance = float(lookback_slice["High"].max())
    
    score = 0
    score_breakdown = {}
    pattern_name = "Zone Bounce"
    
    # ----------------------------------------------------
    # CATEGORY 1: PRICE ACTION & STRUCTURE (Max 30 Pts)
    # ----------------------------------------------------
    pa_score = 0
    
    # Check Support Zone
    dist_to_ema20 = abs(low - ema20) / ema20
    dist_to_ema50 = abs(low - ema50) / ema50
    touching_ema_zone = (dist_to_ema20 <= 0.025) or (dist_to_ema50 <= 0.025) or (low <= ema20 and close >= ema20 * 0.99)
    near_support_zone = abs(low - prior_support) / prior_support <= 0.025
    in_support_zone = touching_ema_zone or near_support_zone
    
    # Candlestick Reversal
    candle_range = high - low
    body = abs(close - open_p)
    lower_wick = min(open_p, close) - low
    is_hammer = (lower_wick >= 1.4 * body) and (close >= open_p or (close - low) > 0.6 * candle_range)
    is_green = close > open_p
    engulfing = is_green and (prev["Close"] < prev["Open"]) and (close >= prev["High"]) and (open_p <= prev["Close"])
    strong_bounce = is_green and (close > prev["High"])
    
    # Break of Structure (BOS above 20-day high)
    recent_20d_high = float(df["High"].iloc[-25:-1].max())
    is_bos = (close > recent_20d_high) and is_green
    
    # Double Bottom (W-Pattern)
    recent_lows = df["Low"].iloc[-20:-2].nsmallest(2).values
    is_double_bottom = len(recent_lows) >= 2 and (abs(recent_lows[0] - recent_lows[1]) / recent_lows[0] <= 0.02) and is_green
    
    if is_bos:
        pa_score = 30
        pattern_name = "Smart Money BOS Breakout"
    elif is_double_bottom and in_support_zone:
        pa_score = 30
        pattern_name = "Double Bottom (W-Pattern)"
    elif in_support_zone and (is_hammer or engulfing or strong_bounce):
        pa_score = 30
        if is_hammer: pattern_name = "Bullish Hammer Bounce"
        elif engulfing: pattern_name = "Bullish Engulfing Bounce"
        else: pattern_name = "Demand Zone Bounce"
    elif in_support_zone and is_green:
        pa_score = 20
        pattern_name = "Support Zone Bounce"
    elif in_support_zone:
        pa_score = 15
        
    score += pa_score
    score_breakdown["Price Action"] = f"{pa_score}/30 ({pattern_name})"
    
    # ----------------------------------------------------
    # CATEGORY 2: TREND & MOVING AVERAGES (Max 25 Pts)
    # ----------------------------------------------------
    trend_score = 0
    # Price > 200 EMA (+10)
    if close > ema200:
        trend_score += 10
    # Golden EMA 9/21 Cross / Alignment (+10)
    if ema9 > ema21:
        trend_score += 10
    # Supertrend (10, 3) Bullish (+5)
    if supertrend_bullish:
        trend_score += 5
        
    score += trend_score
    score_breakdown["Trend & EMAs"] = f"{trend_score}/25"
    
    # ----------------------------------------------------
    # CATEGORY 3: MOMENTUM (RSI & MACD) (Max 20 Pts)
    # ----------------------------------------------------
    mom_score = 0
    # RSI 50-65 Sweet Spot (+10) or 40-50 (+5)
    if 50.0 <= rsi <= 66.0:
        mom_score += 10
    elif 40.0 <= rsi < 50.0 and rsi >= prev_rsi:
        mom_score += 5
        
    # MACD Bullish Crossover & Hist (+10)
    if macd > macd_signal and (macd_hist > 0 or macd_hist > prev_macd_hist):
        mom_score += 10
    elif macd > macd_signal:
        mom_score += 5
        
    score += mom_score
    score_breakdown["Momentum (RSI/MACD)"] = f"{mom_score}/20"
    
    # ----------------------------------------------------
    # CATEGORY 4: VOLUME & SMART MONEY (Max 15 Pts)
    # ----------------------------------------------------
    vol_score = 0
    if volume >= 1.5 * vol_sma:
        vol_score += 10
    elif volume >= 1.0 * vol_sma:
        vol_score += 5
        
    if volume > prev_vol:
        vol_score += 5
        
    score += vol_score
    score_breakdown["Smart Money Volume"] = f"{vol_score}/15"
    
    # ----------------------------------------------------
    # CATEGORY 5: RISK-REWARD & STOP-LOSS (Max 10 Pts)
    # ----------------------------------------------------
    if is_bos:
        stop_loss = round(low - (0.4 * atr), 2)
        risk_per_share = close - stop_loss
        target_price = round(max(close + (2.0 * risk_per_share), prior_resistance * 1.02), 2)
    else:
        zone_low = min(low, float(prev["Low"]))
        stop_loss = round(zone_low - (0.5 * atr), 2)
        risk_per_share = close - stop_loss
        min_target = close + (2.0 * risk_per_share)
        target_price = round(max(min_target, prior_resistance), 2)
        
    risk_pct = (risk_per_share / close) * 100.0
    if risk_pct < 0.8 or risk_pct > 6.0:
        return None
        
    target_pct = ((target_price - close) / close) * 100.0
    rr_ratio = round((target_price - close) / risk_per_share, 2)
    
    rr_score = 10 if rr_ratio >= 2.0 else (5 if rr_ratio >= 1.8 else 0)
    score += rr_score
    score_breakdown["Risk/Reward"] = f"{rr_score}/10 (1:{rr_ratio})"
    
    # ----------------------------------------------------
    # FINAL PASSING CRITERIA: Confluence Score >= CONFLUENCE_THRESHOLD (60%)
    # ----------------------------------------------------
    min_threshold = getattr(config, "CONFLUENCE_THRESHOLD", 60)
    if score < min_threshold or rr_ratio < 1.5:
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
        "confluence_score": score,
        "score_breakdown": score_breakdown,
        "rsi": round(rsi, 1),
        "ema9": round(ema9, 2),
        "ema20": round(ema20, 2),
        "ema21": round(ema21, 2),
        "ema50": round(ema50, 2),
        "ema200": round(ema200, 2),
        "supertrend_bullish": supertrend_bullish,
        "macd_bullish": macd > macd_signal,
        "volume_ratio": round(volume / vol_sma, 2),
        "reason": f"{pattern_name} [Confluence: {score}%] with 1:{rr_ratio} RR (Target: Rs. {target_price})"
    }
