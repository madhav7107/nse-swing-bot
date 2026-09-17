import uvicorn
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, Response
import config
from trade_logger import (
    init_db, get_account_balance, get_open_trades, get_closed_trades,
    get_performance_stats, update_account_balance, get_connection
)
from data_engine import get_latest_price, get_stock_data
from strategy_zone_bounce import analyze_zone_bounce_signal
from strategy_breakout import analyze_breakout_signal
from paper_broker import execute_paper_buy, monitor_and_manage_positions

import threading
import time
import datetime
import subprocess
import os

app = FastAPI(title="SR-TRADING Dashboard")

init_db()

AUTO_PILOT_ACTIVE = True
LAST_AUTO_SCAN = "Not Scanned Yet"
ACTIVITY_LOGS = [
    f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Bot initialized in PAPER TRADING mode.",
    f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Monitoring 50 High Liquidity NSE Watchlist stocks."
]
RADAR_DATA = []
INDEX_CACHE = {}

def add_log(msg: str):
    global ACTIVITY_LOGS
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    formatted = f"[{timestamp}] {msg}"
    ACTIVITY_LOGS.insert(0, formatted)
    if len(ACTIVITY_LOGS) > 100:
        ACTIVITY_LOGS.pop()

def get_live_indices():
    now = datetime.datetime.now()
    if "data" in INDEX_CACHE and (now - INDEX_CACHE["time"]).total_seconds() < 8:
        return INDEX_CACHE["data"]
    
    tickers = {"NIFTY 50": "^NSEI", "SENSEX": "^BSESN"}
    try:
        import yfinance as yf
        result = []
        for name, sym in tickers.items():
            try:
                t = yf.Ticker(sym)
                cur = round(float(t.fast_info['lastPrice']), 2)
                prev = round(float(t.fast_info['previousClose']), 2)
                chg = round(cur - prev, 2)
                pct = round((chg / prev) * 100, 2)
                result.append({
                    "name": name,
                    "ltp": cur,
                    "change": chg,
                    "change_pct": pct,
                    "is_up": chg >= 0
                })
            except Exception:
                pass
        if result:
            INDEX_CACHE["data"] = result
            INDEX_CACHE["time"] = now
        return INDEX_CACHE.get("data", [])
    except Exception as e:
        print(f"[Indices Fetch Error] {e}")
        return INDEX_CACHE.get("data", [])

SCAN_LOCK = threading.Lock()

def perform_full_scan():
    global LAST_AUTO_SCAN, RADAR_DATA
    if not SCAN_LOCK.acquire(blocking=False):
        print("[AutoTrader] Scan already in progress, skipping concurrent run.")
        return {"signals_found": 0, "executed_symbols": []}
    try:
        add_log(f"Starting automated market analysis across all {len(config.WATCHLIST)} watchlist stocks...")
        
        # 1. First monitor active positions
        monitor_and_manage_positions()
        
        signals = []
        executed = []
        radar_list = []
        
        for symbol in config.WATCHLIST:
            df = get_stock_data(symbol, period="1y", interval="1d")
            if df is None:
                radar_list.append({
                    "symbol": symbol.replace(".NS", ""),
                    "ltp": 0.0,
                    "rsi": 0.0,
                    "trend": "DATA_ERROR",
                    "status": "No Market Data",
                    "color": "slate"
                })
                continue
                
            last = df.iloc[-1]
            close = round(float(last["Close"]), 2)
            rsi = round(float(last["RSI"]), 1)
            ema20 = round(float(last["EMA_20"]), 2)
            ema50 = round(float(last["EMA_50"]), 2)
            ema200 = round(float(last["EMA_200"]), 2)
            
            ema9 = round(float(last["EMA_9"]), 2) if "EMA_9" in last else close
            ema21 = round(float(last["EMA_21"]), 2) if "EMA_21" in last else ema20
            macd = round(float(last["MACD"]), 2) if "MACD" in last else 0.0
            macd_signal = round(float(last["MACD_Signal"]), 2) if "MACD_Signal" in last else 0.0
            supertrend_bullish = bool(last["Supertrend_Bullish"]) if "Supertrend_Bullish" in last else True
            
            setup = analyze_zone_bounce_signal(df, symbol)
            if not setup:
                setup = analyze_breakout_signal(df, symbol)
            
            is_uptrend = close > ema200
            near_zone = (abs(close - ema20) / ema20 <= 0.025) or (abs(close - ema50) / ema50 <= 0.025)
            
            if setup:
                signals.append(setup)
                success = execute_paper_buy(setup)
                pattern_title = setup.get("pattern", "Institutional Setup")
                status_text = f"{pattern_title.upper()} ({setup['confluence_score']}%)"
                color = "emerald"
                if success:
                    executed.append(symbol)
                    add_log(f"🚀 BUY ORDER: {symbol.replace('.NS','')} [{pattern_title} - {setup['confluence_score']}%] at Rs. {setup['entry_price']} | SL: Rs. {setup['stop_loss']} | Tgt: Rs. {setup['target_price']}")
            elif is_uptrend and near_zone:
                status_text = "Demand Zone (Watching Reversal)"
                color = "amber"
                add_log(f"👀 {symbol.replace('.NS','')}: In Demand Zone (LTP: Rs. {close}, RSI: {rsi}).")
            elif is_uptrend and (ema9 > ema21) and supertrend_bullish:
                status_text = "Strong Uptrend (9/21 EMA + Supertrend)"
                color = "blue"
            elif is_uptrend:
                status_text = "Uptrend (Pullback Phase)"
                color = "blue"
            else:
                status_text = "Below 200 EMA (Avoid)"
                color = "slate"
                
            radar_list.append({
                "symbol": symbol.replace(".NS", ""),
                "ltp": close,
                "score": setup['confluence_score'] if setup else (60 if (is_uptrend and near_zone) else (50 if is_uptrend else 20)),
                "ema9": ema9,
                "ema21": ema21,
                "ema20": ema20,
                "ema50": ema50,
                "ema200": ema200,
                "rsi": rsi,
                "ema_cross": "BULLISH" if ema9 > ema21 else "BEARISH",
                "macd_bullish": macd > macd_signal,
                "supertrend": "BULLISH" if supertrend_bullish else "BEARISH",
                "trend": "UPTREND" if is_uptrend else "DOWNTREND",
                "status": status_text,
                "color": color
            })
            
        RADAR_DATA = radar_list
        LAST_AUTO_SCAN = config.get_ist_now().strftime("%Y-%m-%d %H:%M:%S IST")
        add_log(f"Scan complete: Scanned {len(config.WATCHLIST)} stocks. Found {len(signals)} setups. Executed {len(executed)} orders.")
        return {
            "status": "success",
            "scanned_count": len(config.WATCHLIST),
            "signals_found": len(signals),
            "executed_symbols": executed
        }
    finally:
        SCAN_LOCK.release()

def auto_trader_daemon():
    print("[AutoTrader] Background 100% Hands-Free Auto-Trading Loop Active.")
    time.sleep(2)
    try:
        perform_full_scan()
    except Exception as e:
        print(f"[AutoTrader Startup Scan Error] {e}")

    last_scan_minute = -1
    while True:
        try:
            now = config.get_ist_now()
            is_open, status_reason = config.get_market_status()
            if AUTO_PILOT_ACTIVE and is_open:
                monitor_and_manage_positions()
                if now.minute % 15 == 0 and now.minute != last_scan_minute:
                    last_scan_minute = now.minute
                    perform_full_scan()
            elif not is_open and now.minute == 0 and now.minute != last_scan_minute:
                last_scan_minute = now.minute
                add_log(f"Market Status: {status_reason}")
        except Exception as e:
            print(f"[AutoTrader Exception] {e}")
            
        time.sleep(60)

threading.Thread(target=auto_trader_daemon, daemon=True).start()

@app.get("/api/stats")
def api_stats():
    stats = get_performance_stats()
    open_trades = get_open_trades()
    
    unrealized_pnl = 0.0
    for t in open_trades:
        ltp = get_latest_price(t["symbol"]) or float(t["entry_price"])
        unrealized_pnl += (ltp - float(t["entry_price"])) * int(t["quantity"])
        
    is_open, status_reason = config.get_market_status()
    stats["market_is_open"] = is_open
    stats["market_status_text"] = status_reason
    stats["unrealized_pnl"] = round(unrealized_pnl, 2)
    stats["net_equity"] = round(stats["cash_balance"] + stats["invested_capital"] + unrealized_pnl, 2)
    stats["mode"] = config.TRADING_MODE
    stats["last_scan"] = LAST_AUTO_SCAN
    stats["auto_pilot"] = AUTO_PILOT_ACTIVE
    return stats

@app.get("/api/indices")
def api_indices():
    return get_live_indices()

@app.get("/api/positions")
def api_positions():
    trades = get_open_trades()
    enriched = []
    for t in trades:
        t_dict = dict(t)
        ltp = get_latest_price(t["symbol"]) or float(t["entry_price"])
        entry = float(t["entry_price"])
        qty = int(t["quantity"])
        pnl = (ltp - entry) * qty
        pnl_pct = ((ltp - entry) / entry) * 100.0
        
        t_dict["ltp"] = round(ltp, 2)
        t_dict["pnl"] = round(pnl, 2)
        t_dict["pnl_pct"] = round(pnl_pct, 2)
        enriched.append(t_dict)
    return enriched

@app.get("/api/history")
def api_history():
    return get_closed_trades(limit=100)

@app.get("/api/radar")
def api_radar():
    return {
        "last_scan": LAST_AUTO_SCAN,
        "stocks": RADAR_DATA
    }

@app.get("/api/logs")
def api_logs():
    return ACTIVITY_LOGS[:50]

@app.get("/api/megabull")
def api_megabull():
    if not getattr(config, "MEGABULL_ENABLED", False):
        return {"enabled": False}
    try:
        from megabull_broker import get_account_profile, get_holdings
        prof = get_account_profile()
        holdings = get_holdings()
        return {
            "enabled": True,
            "connected": bool(prof),
            "user": f"{prof.get('firstName', '')} {prof.get('lastName', '')}".strip(),
            "virtual_balance": prof.get("virtualMoneyLeft", 500000),
            "tier": prof.get("premiumType", "PRO"),
            "holdings_count": len(holdings)
        }
    except Exception as e:
        return {"enabled": True, "connected": False, "error": str(e)}

@app.get("/api/test_ntfy_send")
def api_test_ntfy_send():
    from ntfy_notifier import send_ntfy
    import traceback
    try:
        ok = send_ntfy("🔔 TEST FROM RENDER CLOUD", "Madhav bhai, aa message Render Cloud parthi live aavyo che!", priority="high")
        add_log(f"Render test ntfy result: {ok}")
        return {"success": ok, "topic": getattr(config, "NTFY_TOPIC", None)}
    except Exception as e:
        err = traceback.format_exc()
        add_log(f"Render test ntfy error: {e}")
        return {"success": False, "error": str(e), "trace": err}

@app.post("/api/scan")
def api_scan():
    return perform_full_scan()

@app.post("/api/reset")
def api_reset():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM trades")
    cursor.execute("DELETE FROM equity_history")
    cursor.execute("UPDATE account SET balance = ?, initial_capital = ? WHERE id = 1", 
                   (config.INITIAL_CAPITAL, config.INITIAL_CAPITAL))
    conn.commit()
    conn.close()
    add_log("Paper Trading Account reset back to Rs. 100,000.")
    return {"status": "success", "message": "Paper portfolio successfully reset to Rs. 100,000"}

@app.get("/api/export_trades")
def api_export_trades():
    import csv
    import io
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trades ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Trade ID", "Symbol", "Direction", "Entry Date", "Entry Price",
        "Quantity", "Stop Loss", "Target Price", "Status", "Exit Date",
        "Exit Price", "P&L", "P&L %", "Exit Reason", "Notes"
    ])
    for r in rows:
        writer.writerow([
            r["id"], r["symbol"], r["direction"], r["entry_date"], r["entry_price"],
            r["quantity"], r["stop_loss"], r["target_price"], r["status"],
            r["exit_date"] or "", r["exit_price"] or "", r["pnl"] or "",
            r["pnl_pct"] or "", r["exit_reason"] or "", r["notes"] or ""
        ])
    
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sr_trading_journal.csv"}
    )

@app.get("/", response_class=HTMLResponse)
def index():
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SR-TRADING | Madhav Kotecha</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');
            body { font-family: 'Plus Jakarta Sans', sans-serif; }
            .font-mono { font-family: 'JetBrains Mono', monospace; }
        </style>
    </head>
    <body class="bg-slate-950 text-slate-100 min-h-screen">
        
        <!-- Top Clean Navbar -->
        <header class="border-b border-slate-800 bg-slate-900/95 backdrop-blur sticky top-0 z-50 py-3">
            <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 min-h-[64px] flex flex-wrap items-center justify-between gap-3">
                
                <!-- Left Brand -->
                <div class="flex items-center space-x-3.5">
                    <div class="h-11 w-11 rounded-xl bg-gradient-to-tr from-emerald-500 to-teal-400 flex items-center justify-center text-slate-950 font-black shadow-lg shadow-emerald-500/20 text-xl flex-shrink-0">
                        <i class="fa-solid fa-chart-line"></i>
                    </div>
                    <div>
                        <div class="flex items-center gap-2">
                            <h1 class="text-xl font-extrabold tracking-wider text-white">SR-TRADING</h1>
                            <span class="text-xs bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 px-2.5 py-0.5 rounded-full font-semibold">Madhav Kotecha</span>
                        </div>
                        <p class="text-xs text-slate-400 flex items-center gap-2 mt-0.5">
                            <span class="flex items-center gap-1.5">
                                <span class="inline-block h-2 w-2 rounded-full bg-emerald-400 animate-pulse"></span>
                                <span>Auto-Pilot: <strong class="text-emerald-400 font-semibold">ACTIVE</strong></span>
                            </span>
                            <span class="text-slate-600">•</span>
                            <span class="flex items-center gap-1.5">
                                <span class="inline-block h-2 w-2 rounded-full bg-blue-400 animate-pulse"></span>
                                <span>MegaBull: <strong class="text-blue-400 font-semibold">PRO SYNCED</strong></span>
                            </span>
                        </p>
                    </div>
                </div>

                <!-- Center Real-time Indices & Live Floating P&L -->
                <div class="flex items-center space-x-4 text-xs font-mono bg-slate-950/80 border border-slate-800 px-4 py-2 rounded-xl shadow-inner">
                    <div class="flex items-center gap-2">
                        <span class="text-slate-400 font-bold">NIFTY:</span>
                        <span class="text-white font-bold" id="niftyLtp">--</span>
                        <span class="text-emerald-400 text-[11px]" id="niftyChg">Loading...</span>
                    </div>
                    <div class="h-3.5 w-px bg-slate-800"></div>
                    <div class="flex items-center gap-2">
                        <span class="text-slate-400 font-bold">SENSEX:</span>
                        <span class="text-white font-bold" id="sensexLtp">--</span>
                        <span class="text-emerald-400 text-[11px]" id="sensexChg">Loading...</span>
                    </div>
                    <div class="h-3.5 w-px bg-slate-800"></div>
                    <div class="flex items-center gap-1.5">
                        <span class="text-slate-400 font-bold">LIVE P&L:</span>
                        <span id="topLivePnl" class="font-bold text-xs px-2.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">₹0.00</span>
                    </div>
                </div>

                <!-- Right Controls -->
                <div class="flex items-center space-x-3">
                    <div class="hidden sm:flex bg-slate-800/80 border border-slate-700 text-slate-300 text-xs px-3 py-2 rounded-lg items-center gap-2 font-mono">
                        <i class="fa-solid fa-clock text-slate-400"></i>
                        <span>Scan: <strong id="topLastScan" class="text-white">-</strong></span>
                    </div>
                    <button onclick="triggerScan()" id="scanBtn" class="bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold px-4 py-2 rounded-lg transition-all shadow-md shadow-emerald-600/30 flex items-center gap-2">
                        <i class="fa-solid fa-bolt"></i>
                        <span>Scan Watchlist Now</span>
                    </button>
                    <button onclick="resetAccount()" class="bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold px-3 py-2 rounded-lg border border-slate-700 transition-all">
                        <i class="fa-solid fa-rotate-left mr-1"></i> Reset
                    </button>
                </div>
            </div>
        </header>

        <!-- Main Content -->
        <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
            
            <!-- Quick Stats Cards (5 Cards) -->
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
                <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-sm">
                    <div class="flex items-center justify-between text-xs text-slate-400 font-medium">
                        <span>Total Equity</span>
                        <i class="fa-solid fa-wallet text-emerald-400"></i>
                    </div>
                    <div class="mt-2 text-2xl font-bold tracking-tight text-white" id="statEquity">₹1,00,000</div>
                    <div class="mt-1 text-xs text-slate-400">Initial: ₹1,00,000</div>
                </div>

                <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-sm">
                    <div class="flex items-center justify-between text-xs text-slate-400 font-medium">
                        <span>Free Cash</span>
                        <i class="fa-solid fa-money-bill-wave text-blue-400"></i>
                    </div>
                    <div class="mt-2 text-2xl font-bold tracking-tight text-white" id="statCash">₹1,00,000</div>
                    <div class="mt-1 text-xs text-slate-400">Ready for next trade</div>
                </div>

                <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-sm">
                    <div class="flex items-center justify-between text-xs text-slate-400 font-medium">
                        <span>Invested Capital</span>
                        <i class="fa-solid fa-layer-group text-purple-400"></i>
                    </div>
                    <div class="mt-2 text-2xl font-bold tracking-tight text-white" id="statInvested">₹0.00</div>
                    <div class="mt-1 text-xs text-slate-400" id="statPositionsCount">0 Open Trades</div>
                </div>

                <!-- Live Open P&L Card -->
                <div class="bg-slate-900 border border-emerald-500/30 rounded-2xl p-4 shadow-sm relative overflow-hidden bg-gradient-to-br from-slate-900 to-emerald-950/20">
                    <div class="flex items-center justify-between text-xs text-slate-300 font-medium">
                        <span class="flex items-center gap-1.5 font-semibold text-emerald-400">
                            <span class="h-2 w-2 rounded-full bg-emerald-400 animate-pulse"></span>
                            <span>LIVE OPEN P&L</span>
                        </span>
                        <i class="fa-solid fa-chart-line text-emerald-400"></i>
                    </div>
                    <div class="mt-2 text-2xl font-bold tracking-tight text-emerald-400" id="statLivePnl">+₹0.00</div>
                    <div class="mt-1 text-xs text-slate-400" id="statLivePnlPct">+0.00% Floating Return</div>
                </div>

                <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-sm">
                    <div class="flex items-center justify-between text-xs text-slate-400 font-medium">
                        <span>Realized P&L</span>
                        <i class="fa-solid fa-sack-dollar text-amber-400"></i>
                    </div>
                    <div class="mt-2 text-2xl font-bold tracking-tight" id="statRealized">₹0.00</div>
                    <div class="mt-1 text-xs text-slate-400" id="statAvgPct">0.0% Avg Return</div>
                </div>
            </div>

            <!-- Active Positions Section (Moved right under Stats Cards) -->
            <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-sm">
                <div class="flex items-center justify-between mb-4">
                    <div class="flex items-center gap-2">
                        <i class="fa-solid fa-clock-rotate-left text-emerald-400 text-base"></i>
                        <h2 class="text-sm font-bold text-white uppercase tracking-wider">Active Swing Positions (Auto-Managed)</h2>
                    </div>
                    <span class="text-xs bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 px-2.5 py-0.5 rounded-full font-bold" id="positionsBadge">0 Active</span>
                </div>

                <div class="overflow-x-auto">
                    <table class="w-full text-left text-xs text-slate-300">
                        <thead class="text-slate-400 uppercase bg-slate-950/60 border-b border-slate-800">
                            <tr>
                                <th class="py-3 px-4">Stock</th>
                                <th class="py-3 px-4">Entry Date</th>
                                <th class="py-3 px-4">Buy Price</th>
                                <th class="py-3 px-4">Qty</th>
                                <th class="py-3 px-4">LTP (Live)</th>
                                <th class="py-3 px-4">Stop Loss</th>
                                <th class="py-3 px-4">Target (1:2)</th>
                                <th class="py-3 px-4">Live Unrealized P&L</th>
                            </tr>
                        </thead>
                        <tbody id="positionsTableBody" class="divide-y divide-slate-800/60 font-mono">
                            <tr>
                                <td colspan="8" class="text-center py-6 text-slate-500">No active swing trades right now. The bot will automatically buy when a setup occurs!</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Watchlist Radar: Live Stock Analysis Status -->
            <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-sm">
                <div class="flex items-center justify-between mb-4">
                    <div class="flex items-center gap-2">
                        <i class="fa-solid fa-satellite-dish text-teal-400"></i>
                        <div>
                            <h2 class="text-sm font-bold text-white uppercase tracking-wider">Live Watchlist Radar (50 Stocks Analyzed)</h2>
                            <p class="text-[11px] text-slate-400">Shows exactly what the bot sees for each stock (Trend, RSI, Demand Zones)</p>
                        </div>
                    </div>
                    <span class="text-xs bg-slate-800 text-slate-300 px-2 py-1 rounded-lg border border-slate-700" id="radarCount">50 Stocks</span>
                </div>

                <div class="overflow-x-auto max-h-80 overflow-y-auto">
                    <table class="w-full text-left text-xs text-slate-300">
                        <thead class="text-slate-400 uppercase bg-slate-950/60 border-b border-slate-800 sticky top-0">
                            <tr>
                                <th class="py-3 px-4">Stock</th>
                                <th class="py-3 px-4">LTP</th>
                                <th class="py-3 px-4">9/21 Cross</th>
                                <th class="py-3 px-4">200 EMA</th>
                                <th class="py-3 px-4">RSI 14</th>
                                <th class="py-3 px-4">Supertrend</th>
                                <th class="py-3 px-4">MACD</th>
                                <th class="py-3 px-4">AI Confluence & Setup</th>
                            </tr>
                        </thead>
                        <tbody id="radarTableBody" class="divide-y divide-slate-800/60">
                            <tr>
                                <td colspan="8" class="text-center py-6 text-slate-500">Loading Watchlist Radar data...</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Trade History Section -->
            <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-sm">
                <div class="flex items-center justify-between mb-4">
                    <div class="flex items-center gap-2">
                        <i class="fa-solid fa-book-bookmark text-blue-400"></i>
                        <h2 class="text-sm font-bold text-white uppercase tracking-wider">Completed Trades Journal</h2>
                    </div>
                    <div class="flex items-center gap-3">
                        <a href="/api/export_trades" download="sr_trading_journal.csv" class="bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs px-3 py-1.5 rounded-lg border border-slate-700 transition flex items-center gap-1.5 shadow-sm">
                            <i class="fa-solid fa-file-arrow-down text-emerald-400"></i>
                            <span>Export CSV</span>
                        </a>
                        <span class="text-xs text-slate-400" id="historyBadge">0 Completed</span>
                    </div>
                </div>

                <div class="overflow-x-auto">
                    <table class="w-full text-left text-xs text-slate-300">
                        <thead class="text-slate-400 uppercase bg-slate-950/60 border-b border-slate-800">
                            <tr>
                                <th class="py-3 px-4">Stock</th>
                                <th class="py-3 px-4">Entry Date</th>
                                <th class="py-3 px-4">Buy Price</th>
                                <th class="py-3 px-4">Exit Date</th>
                                <th class="py-3 px-4">Exit Price</th>
                                <th class="py-3 px-4">Exit Reason</th>
                                <th class="py-3 px-4">Realized P&L</th>
                            </tr>
                        </thead>
                        <tbody id="historyTableBody" class="divide-y divide-slate-800/60">
                            <tr>
                                <td colspan="7" class="text-center py-6 text-slate-500">No completed trades yet. Paper trades will appear here after hitting target or stop-loss.</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            <!-- Bot Live Activity Feed (Console) at bottom -->
            <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-sm">
                <div class="flex items-center justify-between mb-3">
                    <div class="flex items-center gap-2">
                        <i class="fa-solid fa-terminal text-emerald-400"></i>
                        <h2 class="text-sm font-bold text-white uppercase tracking-wider">Bot Live Activity Feed</h2>
                    </div>
                    <span class="text-[11px] bg-slate-800 border border-slate-700 text-slate-300 px-2 py-0.5 rounded">Realtime Logs</span>
                </div>
                <div id="logsConsole" class="bg-slate-950 border border-slate-800 rounded-xl p-3 h-32 overflow-y-auto font-mono text-xs text-slate-300 space-y-1">
                    <div class="text-slate-500">Waiting for bot logs...</div>
                </div>
            </div>

        </main>

        <script>
            async function loadIndices() {
                try {
                    const res = await fetch('/api/indices');
                    const indices = await res.json();
                    indices.forEach(idx => {
                        const isUp = idx.change >= 0;
                        const sign = isUp ? '+' : '';
                        const arrow = isUp ? '▲' : '▼';
                        const colorClass = isUp ? 'text-emerald-400' : 'text-rose-400';
                        
                        if (idx.name === 'NIFTY 50' || idx.name === 'NIFTY') {
                            const ltpEl = document.getElementById('niftyLtp');
                            const chgEl = document.getElementById('niftyChg');
                            if (ltpEl) ltpEl.innerText = idx.ltp.toLocaleString('en-IN');
                            if (chgEl) {
                                chgEl.className = `${colorClass} text-[11px] font-semibold`;
                                chgEl.innerText = `${sign}${idx.change} (${sign}${idx.change_pct}%) ${arrow}`;
                            }
                        } else if (idx.name === 'SENSEX') {
                            const ltpEl = document.getElementById('sensexLtp');
                            const chgEl = document.getElementById('sensexChg');
                            if (ltpEl) ltpEl.innerText = idx.ltp.toLocaleString('en-IN');
                            if (chgEl) {
                                chgEl.className = `${colorClass} text-[11px] font-semibold`;
                                chgEl.innerText = `${sign}${idx.change} (${sign}${idx.change_pct}%) ${arrow}`;
                            }
                        }
                    });
                } catch(e) {
                    console.error("Indices error:", e);
                }
            }

            async function loadDashboard() {
                try {
                    // 1. Stats
                    const statsRes = await fetch('/api/stats');
                    const stats = await statsRes.json();
                    
                    document.getElementById('statEquity').innerText = '₹' + stats.net_equity.toLocaleString('en-IN');
                    document.getElementById('statCash').innerText = '₹' + stats.cash_balance.toLocaleString('en-IN');
                    document.getElementById('statInvested').innerText = '₹' + stats.invested_capital.toLocaleString('en-IN');
                    document.getElementById('topLastScan').innerText = stats.last_scan.substring(11, 19) || 'Just now';
                    
                    // Live Open P&L
                    const livePnl = stats.unrealized_pnl || 0;
                    const liveColor = livePnl >= 0 ? 'text-emerald-400' : 'text-rose-400';
                    const liveSign = livePnl >= 0 ? '+' : '';
                    const liveBadgeClass = livePnl >= 0 ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' : 'bg-rose-500/10 text-rose-400 border-rose-500/30';

                    const statLiveEl = document.getElementById('statLivePnl');
                    if (statLiveEl) {
                        statLiveEl.className = 'mt-2 text-2xl font-bold tracking-tight ' + liveColor;
                        statLiveEl.innerText = liveSign + '₹' + livePnl.toLocaleString('en-IN');
                    }
                    const statLivePctEl = document.getElementById('statLivePnlPct');
                    if (statLivePctEl) {
                        const inv = stats.invested_capital > 0 ? ((livePnl / stats.invested_capital) * 100).toFixed(2) : '0.00';
                        statLivePctEl.innerText = liveSign + inv + '% Floating Return';
                    }
                    
                    const topPnl = document.getElementById('topLivePnl');
                    if (topPnl) {
                        topPnl.className = 'font-bold text-xs px-2 py-0.5 rounded border ' + liveBadgeClass;
                        topPnl.innerText = liveSign + '₹' + livePnl.toLocaleString('en-IN');
                    }

                    // Realized P&L
                    const pnlColor = stats.total_realized_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400';
                    const pnlSign = stats.total_realized_pnl >= 0 ? '+' : '';
                    document.getElementById('statRealized').className = 'mt-2 text-2xl font-bold tracking-tight ' + pnlColor;
                    document.getElementById('statRealized').innerText = pnlSign + '₹' + stats.total_realized_pnl.toLocaleString('en-IN');
                    document.getElementById('statAvgPct').innerText = pnlSign + stats.avg_pnl_pct + '% Avg Trade';
                    
                    // 2. Positions
                    const posRes = await fetch('/api/positions');
                    const positions = await posRes.json();
                    document.getElementById('positionsBadge').innerText = `${positions.length} Active`;
                    document.getElementById('statPositionsCount').innerText = `${positions.length} Open Positions`;
                    
                    const pTable = document.getElementById('positionsTableBody');
                    if (positions.length === 0) {
                        pTable.innerHTML = '<tr><td colspan="8" class="text-center py-6 text-slate-500 font-sans">No active swing trades right now. The bot will automatically buy when a setup occurs!</td></tr>';
                    } else {
                        pTable.innerHTML = positions.map(p => {
                            const curLtp = p.ltp || p.entry_price;
                            const curPnl = ((curLtp - p.entry_price) * p.quantity).toFixed(2);
                            const curPnlPct = (((curLtp - p.entry_price) / p.entry_price) * 100).toFixed(2);
                            const pnlClass = curPnl >= 0 ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold';
                            const pnlPlus = curPnl >= 0 ? '+' : '';
                            return `
                                <tr class="hover:bg-slate-800/40 transition">
                                    <td class="py-3 px-4 font-bold text-white flex items-center gap-2 font-sans">
                                        <span class="h-2 w-2 rounded-full bg-emerald-400 animate-pulse"></span>
                                        ${p.symbol.replace('.NS', '')}
                                    </td>
                                    <td class="py-3 px-4 text-slate-400 font-sans">${p.entry_date.substring(0, 10)}</td>
                                    <td class="py-3 px-4">₹${p.entry_price}</td>
                                    <td class="py-3 px-4">${p.quantity}</td>
                                    <td class="py-3 px-4 font-semibold text-white">₹${curLtp}</td>
                                    <td class="py-3 px-4 text-rose-400">₹${p.stop_loss}</td>
                                    <td class="py-3 px-4 text-emerald-400">₹${p.target_price}</td>
                                    <td class="py-3 px-4 ${pnlClass}">${pnlPlus}₹${curPnl} (${pnlPlus}${curPnlPct}%)</td>
                                </tr>
                            `;
                        }).join('');
                    }

                    // 3. Radar Data
                    const radarRes = await fetch('/api/radar');
                    const radar = await radarRes.json();
                    const rTable = document.getElementById('radarTableBody');
                    if (radar.stocks && radar.stocks.length > 0) {
                        rTable.innerHTML = radar.stocks.map(s => {
                            let badgeClass = "bg-slate-800 border-slate-700 text-slate-400";
                            if (s.color === "emerald") badgeClass = "bg-emerald-500/10 border-emerald-500/30 text-emerald-400 font-semibold";
                            else if (s.color === "amber") badgeClass = "bg-amber-500/10 border-amber-500/30 text-amber-400 font-semibold";
                            else if (s.color === "blue") badgeClass = "bg-blue-500/10 border-blue-500/30 text-blue-400";

                            const emaCrossClass = s.ema_cross === "BULLISH" ? "text-emerald-400 font-bold" : "text-slate-500";
                            const stClass = s.supertrend === "BULLISH" ? "text-emerald-400 font-bold" : "text-rose-400";
                            const macdClass = s.macd_bullish ? "text-emerald-400 font-bold" : "text-slate-500";
                            const rsiClass = (s.rsi >= 50 && s.rsi <= 65) ? "text-emerald-400 font-bold" : ((s.rsi >= 40 && s.rsi < 50) ? "text-amber-400" : "text-slate-300");

                            return `
                                <tr class="hover:bg-slate-800/40 transition">
                                    <td class="py-3 px-4 font-bold text-white font-sans">${s.symbol}</td>
                                    <td class="py-3 px-4 font-semibold text-white font-mono">₹${s.ltp}</td>
                                    <td class="py-3 px-4 ${emaCrossClass}">${s.ema_cross || '-'}</td>
                                    <td class="py-3 px-4 text-slate-400 font-mono">₹${s.ema200 || '-'}</td>
                                    <td class="py-3 px-4 ${rsiClass} font-mono">${s.rsi || '-'}</td>
                                    <td class="py-3 px-4 ${stClass}">${s.supertrend || '-'}</td>
                                    <td class="py-3 px-4 ${macdClass}">${s.macd_bullish ? 'BULLISH' : 'NEUTRAL'}</td>
                                    <td class="py-3 px-4 font-sans">
                                        <span class="px-2.5 py-1 rounded-md text-[11px] border ${badgeClass}">
                                            ${s.status}
                                        </span>
                                    </td>
                                </tr>
                            `;
                        }).join('');
                    }

                    // 4. Live Logs
                    const logsRes = await fetch('/api/logs');
                    const logs = await logsRes.json();
                    const logBox = document.getElementById('logsConsole');
                    if (logs && logs.length > 0) {
                        logBox.innerHTML = logs.map(l => {
                            let color = "text-slate-300";
                            if (l.includes("BUY ORDER")) color = "text-emerald-400 font-bold";
                            else if (l.includes("Demand Zone")) color = "text-amber-300";
                            else if (l.includes("complete")) color = "text-blue-300";
                            return `<div class="${color}">${l}</div>`;
                        }).join('');
                    }

                    // 5. History
                    const histRes = await fetch('/api/history');
                    const history = await histRes.json();
                    document.getElementById('historyBadge').innerText = `${history.length} Completed`;
                    const hTable = document.getElementById('historyTableBody');
                    if (history.length === 0) {
                        hTable.innerHTML = '<tr><td colspan="7" class="text-center py-6 text-slate-500 font-sans">No completed trades yet. Paper trades will appear here after hitting target or stop-loss.</td></tr>';
                    } else {
                        hTable.innerHTML = history.map(h => {
                            const pnlClass = h.pnl >= 0 ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold';
                            const pnlPlus = h.pnl >= 0 ? '+' : '';
                            return `
                                <tr class="hover:bg-slate-800/40 transition">
                                    <td class="py-3 px-4 font-bold text-white font-sans">${h.symbol.replace('.NS', '')}</td>
                                    <td class="py-3 px-4 text-slate-400 font-sans">${h.entry_date.substring(0, 10)}</td>
                                    <td class="py-3 px-4 font-mono">₹${h.entry_price}</td>
                                    <td class="py-3 px-4 text-slate-400 font-sans">${(h.exit_date || '').substring(0, 10)}</td>
                                    <td class="py-3 px-4 font-semibold text-white font-mono">₹${h.exit_price || '-'}</td>
                                    <td class="py-3 px-4 font-sans">
                                        <span class="px-2 py-0.5 rounded text-[11px] bg-slate-800 border border-slate-700 text-slate-300">
                                            ${h.exit_reason || h.status}
                                        </span>
                                    </td>
                                    <td class="py-3 px-4 ${pnlClass} font-mono">${pnlPlus}₹${h.pnl} (${pnlPlus}${h.pnl_pct}%)</td>
                                </tr>
                            `;
                        }).join('');
                    }

                } catch (e) {
                    console.error("Dashboard refresh error:", e);
                }
            }

            async function triggerScan() {
                const btn = document.getElementById('scanBtn');
                btn.disabled = true;
                btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> <span>Scanning NSE...</span>';
                try {
                    const res = await fetch('/api/scan', { method: 'POST' });
                    const data = await res.json();
                    alert(`Scan Complete! Found ${data.signals_found} Zone Bounce setups. Executed ${data.executed_symbols.length} paper orders.`);
                    loadDashboard();
                } catch (e) {
                    alert('Error running scan: ' + e);
                } finally {
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fa-solid fa-bolt"></i> <span>Scan Watchlist Now</span>';
                }
            }

            async function resetAccount() {
                if (confirm("Are you sure you want to reset your Paper Trading account balance to ₹1,00,000?")) {
                    await fetch('/api/reset', { method: 'POST' });
                    loadDashboard();
                }
            }

            window.onload = () => {
                loadIndices();
                loadDashboard();
                setInterval(loadIndices, 4000);   // Refresh NIFTY & SENSEX every 4 seconds
                setInterval(loadDashboard, 3000); // Refresh Positions & Live P&L every 3 seconds
            };
        </script>
    </body>
    </html>
    """
    return html

def run_server(port: int = None):
    if port is None:
        port = int(os.environ.get("PORT", 8000))
    print(f"\n==================================================")
    print(f"  Starting NSE Swing Bot Web Dashboard")
    print(f"  Port: {port}")
    print(f"==================================================\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

if __name__ == "__main__":
    run_server()
