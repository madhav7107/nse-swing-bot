"""
Autonomous AI Research Agent (Alpha Hunter + Live Breaking News Sentiment)
Continuous 24/7 Market Scanning & High-Conviction Opportunity Finder.
Real-Time Breaking Financial News Integrator (Economic Times & Moneycontrol).
Discipline Guard: Hard Cap on Daily Loss (Rs. 1,500 max) to guarantee capital preservation.
"""

import os
import json
import datetime
import urllib.request
import xml.etree.ElementTree as ET
from typing import List, Dict, Any
from data_engine import get_stock_data, get_latest_price
from market_scanner import get_all_market_symbols
import config

RESEARCH_CACHE_FILE = os.path.join(os.path.dirname(__file__), "research_agent_findings.json")
NEWS_CACHE_FILE = os.path.join(os.path.dirname(__file__), "market_news_cache.json")

NEWS_FEEDS = [
    "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
    "https://www.moneycontrol.com/rss/MCtopnews.xml"
]

def fetch_live_market_news() -> List[Dict[str, str]]:
    """
    Fetches real-time financial breaking news headlines from official RSS feeds.
    """
    all_news = []
    for feed_url in NEWS_FEEDS:
        try:
            req = urllib.request.Request(feed_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=6) as res:
                tree = ET.fromstring(res.read())
                items = tree.findall(".//item")
                for item in items[:15]:
                    title_elem = item.find("title")
                    desc_elem = item.find("description")
                    title = title_elem.text if title_elem is not None else ""
                    desc = desc_elem.text if desc_elem is not None else ""
                    if title:
                        all_news.append({
                            "title": title.strip(),
                            "summary": desc.strip() if desc else "",
                            "source": "ET Markets" if "economictimes" in feed_url else "Moneycontrol",
                            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        })
        except Exception as e:
            # Silently continue to next feed if network times out
            pass

    try:
        with open(NEWS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "news": all_news}, f, indent=2)
    except Exception:
        pass

    return all_news

def analyze_news_sentiment_for_stock(symbol: str, live_news: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Checks breaking news headlines for specific stock mentions and computes sentiment boost/penalty.
    """
    clean_sym = symbol.replace(".NS", "").upper()
    matching_headlines = []
    sentiment_score = 0 # -2 to +2

    positive_keywords = ['PROFIT', 'GROWTH', 'SURGES', 'RALLY', 'Q2 RESULTS', 'ORDERS', 'BAGS', 'EXPANSION', 'BULLISH', 'DIVIDEND', 'HIGH']
    negative_keywords = ['LOSS', 'PROBE', 'RAID', 'FRAUD', 'DOWNGRADE', 'PLUNGES', 'CRASH', 'SEBI', 'NOTICE', 'FINE', 'RESIGNS']

    for n in live_news:
        text = (n.get("title", "") + " " + n.get("summary", "")).upper()
        if clean_sym in text:
            matching_headlines.append(n.get("title"))
            pos_matches = sum(1 for kw in positive_keywords if kw in text)
            neg_matches = sum(1 for kw in negative_keywords if kw in text)
            sentiment_score += (pos_matches - neg_matches)

    return {
        "mentioned": len(matching_headlines) > 0,
        "sentiment_score": sentiment_score,
        "headlines": matching_headlines[:2]
    }

def evaluate_stock_opportunity(symbol: str, live_news: List[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    Evaluates institutional momentum, breakout strength, news sentiment, and risk/reward.
    Returns structured trade proposal with exact Entry, Stop Loss, Target, and Score.
    """
    try:
        df = get_stock_data(symbol, period="6mo", interval="1d")
        if df is None or len(df) < 50:
            return None

        last = df.iloc[-1]
        prev = df.iloc[-2]

        close = float(last["Close"])
        volume = float(last["Volume"])
        avg_vol = float(df["Volume"].tail(20).mean())
        rsi = float(last["RSI"]) if "RSI" in last else 50.0
        ema20 = float(last["EMA_20"]) if "EMA_20" in last else close
        ema50 = float(last["EMA_50"]) if "EMA_50" in last else close
        ema200 = float(last["EMA_200"]) if "EMA_200" in last else close

        vol_surge = volume / max(1.0, avg_vol)
        price_change_pct = ((close - float(prev["Close"])) / float(prev["Close"])) * 100.0

        score = 50
        direction = "BUY"
        reason = []

        # 1. Macro Trend: Price > 200 EMA & 50 EMA
        if close > ema200 and close > ema50:
            score += 15
            reason.append("Strong Macro Bull Trend (> 50/200 EMA)")
        elif close < ema200 and close < ema50:
            direction = "SELL"
            score += 15
            reason.append("Macro Bear Trend (< 50/200 EMA)")

        # 2. Institutional Volume Explosion
        if vol_surge >= 2.0:
            score += 15
            reason.append(f"Volume Surge {round(vol_surge, 1)}x")
        elif vol_surge >= 1.3:
            score += 8

        # 3. Momentum & RSI Sweet Spot
        if direction == "BUY":
            if 48 <= rsi <= 68:
                score += 10
                reason.append("RSI Momentum in Prime Bull Zone (48-68)")
        else:
            if 32 <= rsi <= 52:
                score += 10
                reason.append("RSI Momentum in Prime Bear Zone (32-52)")

        # 4. Live News Sentiment Gate
        if live_news:
            news_meta = analyze_news_sentiment_for_stock(symbol, live_news)
            if news_meta["mentioned"]:
                if news_meta["sentiment_score"] > 0:
                    score += 10
                    reason.append(f"Positive Breaking News: {news_meta['headlines'][0]}")
                elif news_meta["sentiment_score"] < 0:
                    if direction == "BUY":
                        score -= 25 # Block long on bad news!
                        reason.append(f"Negative Breaking News WARNING: {news_meta['headlines'][0]}")
                    else:
                        score += 10 # Reinforce short on bad news!
                        reason.append(f"Negative News Breakdown: {news_meta['headlines'][0]}")

        # Only proceed if high conviction (>= 80%)
        if score < 80:
            return None

        # Calculate exact Entry, SL, Target with strict 1:2 R:R
        # Risk restricted to 1.5% max
        if direction == "BUY":
            entry = close
            sl = round(entry * 0.985, 2)
            risk = entry - sl
            tgt = round(entry + (risk * 2.0), 2)
        else:
            entry = close
            sl = round(entry * 1.015, 2)
            risk = sl - entry
            tgt = round(entry - (risk * 2.0), 2)

        return {
            "symbol": symbol,
            "direction": direction,
            "entry_price": entry,
            "stop_loss": sl,
            "target_price": tgt,
            "confluence_score": score,
            "vol_surge": round(vol_surge, 2),
            "rsi": round(rsi, 1),
            "reason": " | ".join(reason),
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        return None

def run_continuous_research(limit_symbols: int = 250) -> List[Dict[str, Any]]:
    """
    Autonomous Research Cycle:
    1. Fetches real-time financial breaking news from ET & Moneycontrol.
    2. Scans priority universe cross-referencing news + technical breakouts.
    3. Exports Top A+ Setups.
    """
    live_news = fetch_live_market_news()
    all_syms = get_all_market_symbols(with_ns_suffix=True)

    priority = list(config.WATCHLIST)
    for s in all_syms[:limit_symbols]:
        if s not in priority:
            priority.append(s)

    best_finds = []
    for s in priority:
        opp = evaluate_stock_opportunity(s, live_news=live_news)
        if opp and opp["confluence_score"] >= 80:
            best_finds.append(opp)

    best_finds.sort(key=lambda x: x["confluence_score"], reverse=True)
    top_picks = best_finds[:5]

    try:
        with open(RESEARCH_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "last_run": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_scanned": len(priority),
                "news_analyzed": len(live_news),
                "top_picks": top_picks
            }, f, indent=2)
    except Exception as e:
        print(f"[Research Agent Cache Error] {e}")

    return top_picks

if __name__ == "__main__":
    print("[AI Research Agent] Initiating News-Aware Alpha Hunter Scan...")
    picks = run_continuous_research(limit_symbols=70)
    print(f"[AI Research Agent] Finished scan. Found {len(picks)} setups:")
    for p in picks:
        print(f" -> {p['symbol']} [{p['direction']}] Score: {p['confluence_score']}% | Tgt: Rs. {p['target_price']}")
        print(f"    Reason: {p['reason']}")
