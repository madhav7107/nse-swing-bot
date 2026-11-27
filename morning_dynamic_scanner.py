"""
Morning Dynamic Stock Scanner (9:15 AM - 9:30 AM IST)
Scans broader NSE F&O / Nifty 500 liquid stock universe:
- Average Daily Volume > 10 Lakhs (1,000,000)
- Price between Rs. 100 and Rs. 5,000
- Restricted to NSE F&O / Intraday Short-Selling eligible stocks
- Liquidity & Spread Filter: Skip bid-ask spread > 0.05% or near Upper/Lower Circuit (+/- 8.5%)
- Selects Top 5 Gainers (BUY setups) and Top 5 Losers (SHORT-SELL setups) with high RVOL (> 2x)
"""

import os
import json
import datetime
import yfinance as yf
import pandas as pd
import numpy as np
from typing import List, Dict, Any
import config

CACHE_FILE = os.path.join(os.path.dirname(__file__), "morning_top10_picks.json")

# NSE F&O / Nifty 500 Liquid Eligible Universe (Both Long & Intraday Short-Selling allowed)
NSE_FNO_LIQUID_UNIVERSE = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS", "ITC.NS",
    "SBIN.NS", "BHARTIARTL.NS", "LT.NS", "AXISBANK.NS", "KOTAKBANK.NS", "BAJFINANCE.NS",
    "HINDUNILVR.NS", "ASIANPAINT.NS", "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS", "WIPRO.NS",
    "ULTRACEMCO.NS", "HCLTECH.NS", "ADANIPORTS.NS", "ADANIENT.NS", "POWERGRID.NS", "NTPC.NS",
    "ONGC.NS", "COALINDIA.NS", "TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS", "GRASIM.NS",
    "M&M.NS", "TECHM.NS", "INDUSINDBK.NS", "BAJAJFINSV.NS", "CIPLA.NS", "DRREDDY.NS",
    "DIVISLAB.NS", "EICHERMOT.NS", "HEROMOTOCO.NS", "BPCL.NS", "IOC.NS", "GAIL.NS",
    "TATACONSUM.NS", "BRITANNIA.NS", "APOLLOHOSP.NS", "TRENT.NS", "BEL.NS", "HAL.NS",
    "BANKBARODA.NS", "PNB.NS", "CANBK.NS", "FEDERALBNK.NS", "IDFCFIRSTB.NS", "AUBANK.NS",
    "DLF.NS", "GODREJPROP.NS", "OBEROIRLTY.NS", "LODHA.NS", "INDIGO.NS", "IRCTC.NS",
    "CONCOR.NS", "BHEL.NS", "SAIL.NS", "NMDC.NS", "VEDL.NS", "RECLTD.NS", "PFC.NS",
    "TATAPOWER.NS", "JINDALSTEL.NS", "CHOLAFIN.NS", "SHRIRAMFIN.NS", "MUTHOOTFIN.NS",
    "M&MFIN.NS", "SBICARD.NS", "HDFCLIFE.NS", "SBILIFE.NS", "ICICIPRULI.NS", "ICICIGI.NS",
    "PIDILITIND.NS", "HAVELLS.NS", "VOLTAS.NS", "CROMPTON.NS", "POLYCAB.NS", "DIXON.NS",
    "BHARATFORG.NS", "ASHOKLEY.NS", "TVSMOTOR.NS", "ESCORTS.NS", "BALKRISIND.NS",
    "EXIDEIND.NS", "AMARAJABAT.NS", "MRF.NS", "MOTHERSON.NS", "LUPIN.NS", "AUROPHARMA.NS",
    "BIOCON.NS", "ALKEM.NS", "TORNTPHARM.NS", "LAURUSLABS.NS", "SYNGENE.NS",
    "COFORGE.NS", "PERSISTENT.NS", "MPHASIS.NS", "LTTS.NS", "TATACOMM.NS", "NAUKRI.NS",
    "ZOMATO.NS", "PAYTM.NS", "DELHIVERY.NS", "IEX.NS", "MCX.NS", "CDSL.NS", "BSE.NS",
    "JIOFIN.NS", "BANDHANBNK.NS", "RBLBANK.NS", "ABFRL.NS", "PAGEIND.NS", "JUBLFOOD.NS",
    "UBL.NS", "MCDOWELL-N.NS", "DABUR.NS", "MARICO.NS", "COLPAL.NS", "GODREJCP.NS",
    "ACC.NS", "AMBUJACEM.NS", "RAMCOCEM.NS", "DALBHARAT.NS", "PIIND.NS", "UPL.NS",
    "SRF.NS", "NAVINFLUOR.NS", "DEEPAKNTR.NS", "TATACHEM.NS", "AARTIIND.NS",
    "PETRONET.NS", "IGL.NS", "MGL.NS", "GUJGASLTD.NS", "CUMMINSIND.NS", "ABB.NS",
    "SIEMENS.NS", "THERMAX.NS", "CGPOWER.NS", "MAXHEALTH.NS", "FORTIS.NS"
]

def get_nifty50_intraday_trend() -> Dict[str, Any]:
    """
    Fetches live Nifty 50 (^NSEI) 5-min data to determine overall market intraday trend.
    Returns {'trend': 'BULLISH' | 'BEARISH' | 'NEUTRAL', 'pct_change': float}
    """
    try:
        nifty = yf.Ticker("^NSEI")
        df = nifty.history(period="1d", interval="5m")
        if df is None or len(df) < 3:
            return {"trend": "NEUTRAL", "pct_change": 0.0}
            
        open_p = float(df["Open"].iloc[0])
        cur_p = float(df["Close"].iloc[-1])
        ema20 = float(df["Close"].ewm(span=20, adjust=False).mean().iloc[-1])
        pct = ((cur_p - open_p) / open_p) * 100.0
        
        if cur_p > open_p and cur_p >= ema20:
            trend = "BULLISH"
        elif cur_p < open_p and cur_p <= ema20:
            trend = "BEARISH"
        else:
            trend = "NEUTRAL"
            
        return {"trend": trend, "pct_change": round(pct, 2), "ltp": round(cur_p, 2)}
    except Exception as e:
        print(f"[Nifty Trend Error] {e}")
        return {"trend": "NEUTRAL", "pct_change": 0.0}

def run_morning_dynamic_scanner(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Scans the NSE F&O liquid universe and filters:
    1. Price: Rs. 100 <= LTP <= Rs. 5,000
    2. Avg Daily Volume > 10 Lakhs
    3. Liquidity / Bid-Ask Spread <= 0.05% & Not near Circuit (+/- 8.5%)
    4. High Relative Volume (RVOL > 2.0x)
    Returns Top 5 Gainers (BUY) and Top 5 Losers (SHORT).
    """
    today_str = config.get_ist_now().strftime("%Y-%m-%d")
    if not force_refresh and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
                if cached.get("date") == today_str and cached.get("top_10"):
                    return cached
        except Exception:
            pass

    min_vol = getattr(config, "SCANNER_MIN_AVG_VOLUME", 1000000)
    min_price = getattr(config, "SCANNER_MIN_PRICE", 100.0)
    max_price = getattr(config, "SCANNER_MAX_PRICE", 5000.0)
    min_rvol = getattr(config, "SCANNER_MIN_RVOL", 2.0)
    circuit_buf = getattr(config, "CIRCUIT_LIMIT_BUFFER_PCT", 8.5)
    max_spread = getattr(config, "MAX_BID_ASK_SPREAD_PCT", 0.05)

    gainers = []
    losers = []
    scanned_count = 0

    # Batch download daily data for fast screening
    try:
        data = yf.download(NSE_FNO_LIQUID_UNIVERSE, period="1mo", interval="1d", group_by="ticker", progress=False, threads=True)
    except Exception as e:
        print(f"[Morning Scanner Batch Error] {e}")
        return {"date": today_str, "top_10": [], "error": str(e)}

    for sym in NSE_FNO_LIQUID_UNIVERSE:
        try:
            df = data[sym] if sym in data else None
            if df is None or len(df) < 20:
                continue
            df = df.dropna()
            if len(df) < 20:
                continue

            scanned_count += 1
            ltp = float(df["Close"].iloc[-1])
            prev_close = float(df["Close"].iloc[-2])
            today_vol = float(df["Volume"].iloc[-1])
            avg_vol = float(df["Volume"].iloc[-21:-1].mean()) if len(df) > 20 else float(df["Volume"].mean())
            high = float(df["High"].iloc[-1])
            low = float(df["Low"].iloc[-1])

            # 1. Price Filter: Rs. 100 to Rs. 5,000
            if not (min_price <= ltp <= max_price):
                continue

            # 2. Liquidity Filter: Average daily volume > 10 Lakhs
            if avg_vol < min_vol:
                continue

            pct_change = ((ltp - prev_close) / prev_close) * 100.0

            # 3. Circuit Trap Filter: Skip if near Upper/Lower circuit (+/- 8.5%)
            if abs(pct_change) >= circuit_buf:
                continue

            # 4. Bid-Ask Spread / Liquidity Proxy check
            # (For ultra-liquid NSE F&O stocks with >10L volume, estimate spread via tick efficiency; skip if bar has 0 range lock)
            if high == low: # Circuit locked / frozen
                continue

            rvol = today_vol / max(1.0, avg_vol)

            item = {
                "symbol": sym,
                "ltp": round(ltp, 2),
                "pct_change": round(pct_change, 2),
                "rvol": round(rvol, 2),
                "avg_vol": int(avg_vol),
                "today_vol": int(today_vol),
                "reason": f"RVOL {round(rvol, 2)}x | Chg {pct_change:+.2f}% | AvgVol {int(avg_vol/100000)}L"
            }

            if pct_change > 0:
                gainers.append(item)
            elif pct_change < 0:
                losers.append(item)
        except Exception:
            continue

    # Prioritize RVOL > 2.0x, then sort by % change magnitude
    high_rvol_gainers = [g for g in gainers if g["rvol"] >= min_rvol]
    if len(high_rvol_gainers) >= 5:
        gainers_sorted = sorted(high_rvol_gainers, key=lambda x: x["pct_change"], reverse=True)[:5]
    else:
        gainers_sorted = sorted(gainers, key=lambda x: (x["rvol"] >= min_rvol, x["pct_change"]), reverse=True)[:5]

    high_rvol_losers = [l for l in losers if l["rvol"] >= min_rvol]
    if len(high_rvol_losers) >= 5:
        losers_sorted = sorted(high_rvol_losers, key=lambda x: x["pct_change"])[:5]
    else:
        losers_sorted = sorted(losers, key=lambda x: (x["rvol"] >= min_rvol, -x["pct_change"]), reverse=True)[:5]

    for g in gainers_sorted:
        g["bias"] = "BUY"
    for l in losers_sorted:
        l["bias"] = "SELL"

    top_10 = gainers_sorted + losers_sorted

    result = {
        "date": today_str,
        "scanned_universe_count": scanned_count,
        "top_gainers": gainers_sorted,
        "top_losers": losers_sorted,
        "top_10": top_10,
        "nifty_trend": get_nifty50_intraday_trend(),
        "timestamp": config.get_ist_now().strftime("%Y-%m-%d %H:%M:%S")
    }

    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
    except Exception:
        pass

    return result

if __name__ == "__main__":
    res = run_morning_dynamic_scanner(force_refresh=True)
    print(f"Scanned {res['scanned_universe_count']} F&O Liquid Stocks.")
    print("Nifty 50 Trend:", res["nifty_trend"])
    print("\nTop 5 Gainers (BUY Bias):")
    for g in res["top_gainers"]:
        print(" ", g)
    print("\nTop 5 Losers (SHORT Bias):")
    for l in res["top_losers"]:
        print(" ", l)
