import os

# ==========================================
# TRADING SYSTEM CONFIGURATION
# ==========================================

# Execution Mode: "PAPER" or "ANGEL_ONE"
TRADING_MODE = os.getenv("TRADING_MODE", "PAPER")

# Portfolio & Capital Settings
INITIAL_CAPITAL = 500000.0  # ₹5,00,000 for MegaBull Paper Trading
RISK_PER_TRADE_PCT = 1.0    # Strict 1.0% max risk per trade (e.g. ₹4,500 max risk)
MAX_RISK_AMOUNT_INR = 4500.0 # Absolute risk cap: No trade can risk more than ₹4,500
MAX_CAPITAL_PER_TRADE_PCT = 20.0 # Max 20% of portfolio in a single stock (₹1,00,000 max)
MAX_OPEN_POSITIONS = 3      # Maximum 3 concurrent high-conviction positions (Focus > Dispersion)
CASH_RESERVE_MIN = 150000.0 # Keep minimum ₹1.5L to ₹2L in pure Cash Reserve at all times
INTRADAY_TRADING_ENABLED = False # Strictly disabled: Only trade high-probability institutional swings (No noisy 5-min scalps)
MAX_INTRADAY_POSITIONS = 0  # No intraday scalps
INTRADAY_SQUARE_OFF_TIME = "15:15" # Mandatory exit by 03:15 PM IST (Never carry overnight shorts)

# Zone Bounce Strategy Parameters
TREND_EMA_LONG = 200        # Macro Trend filter: Price > 200 EMA
TREND_EMA_MID = 50          # Secondary trend filter: Price > 50 EMA
PULLBACK_EMA = 20           # Dynamic support/pullback EMA zone
RSI_PERIOD = 14
RSI_OVERSOLD_ZONE = 40      # Looking for RSI turning upwards from 40-50 zone
RSI_MAX_ENTRY = 60          # Don't buy if already overbought (>60)
ZONE_LOOKBACK_BARS = 50     # Swing low lookback for horizontal support zone detection

# Risk & Reward
TARGET_RR_RATIO = 2.0       # Strict 1:2 Risk to Reward (Risk ₹3,500 to make ₹7,000)
BREAKEVEN_TRIGGER_R = 1.0   # Move SL to Cost once price reaches 1R profit
TRAILING_STOP_ENABLED = True

# Official NSE Trading Holidays (2026)
NSE_HOLIDAYS_2026 = {
    "2026-01-26": "Republic Day",
    "2026-02-17": "Mahashivratri",
    "2026-03-04": "Holi",
    "2026-03-20": "Id-Ul-Fitr (Ramzan Eid)",
    "2026-04-03": "Good Friday",
    "2026-04-14": "Dr. Ambedkar Jayanti",
    "2026-05-01": "Maharashtra Day",
    "2026-05-27": "Bakri Id",
    "2026-08-15": "Independence Day",
    "2026-09-14": "Ganesh Chaturthi",
    "2026-10-02": "Mahatma Gandhi Jayanti",
    "2026-10-20": "Dussehra",
    "2026-11-10": "Diwali Laxmi Pujan",
    "2026-11-11": "Diwali Balipratipada",
    "2026-11-24": "Guru Nanak Jayanti",
    "2026-12-25": "Christmas"
}

# Institutional Confluence Threshold (75% for strict high-probability institutional setups)
CONFLUENCE_THRESHOLD = 75

def get_ist_now():
    import datetime
    try:
        import zoneinfo
        return datetime.datetime.now(zoneinfo.ZoneInfo("Asia/Kolkata"))
    except Exception:
        import datetime
        return datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)

def get_market_status():
    now = get_ist_now()
    today_str = now.strftime("%Y-%m-%d")
    
    # 1. Weekend check
    if now.weekday() >= 5:
        return False, "CLOSED (Weekend - Saturday/Sunday)"
        
    # 2. NSE Holiday check
    if today_str in NSE_HOLIDAYS_2026:
        return False, f"CLOSED (NSE Holiday: {NSE_HOLIDAYS_2026[today_str]})"
        
    # 3. Market hours check (09:15 to 15:30 IST)
    market_start = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_end = now.replace(hour=15, minute=30, second=0, microsecond=0)
    
    if now < market_start:
        return False, "CLOSED (Pre-Market - Opens at 09:15 AM IST)"
    elif now > market_end:
        return False, "CLOSED (Market Closed at 03:30 PM IST)"
    else:
        return True, "OPEN (Trading Active: 09:15 AM - 03:30 PM IST)"

# Watchlist: 50 High-Liquidity Nifty Large/Midcap Stocks
WATCHLIST = [
    # Core Largecaps
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
    "ITC.NS", "LT.NS", "SBIN.NS", "BHARTIARTL.NS", "KOTAKBANK.NS",
    "AXISBANK.NS", "WIPRO.NS", "COALINDIA.NS", "SUNPHARMA.NS", "TITAN.NS",
    "BAJFINANCE.NS", "MARUTI.NS", "ASIANPAINT.NS", "TATASTEEL.NS", "NTPC.NS",
    "POWERGRID.NS", "M&M.NS", "HAL.NS", "BEL.NS", "VBL.NS", "TRENT.NS",
    
    # Expanded Top Nifty 50 High-Volume Stocks
    "TATAMOTORS.NS", "BAJAJ-AUTO.NS", "HINDALCO.NS", "GRASIM.NS", "SIEMENS.NS",
    "CUMMINSIND.NS", "TECHM.NS", "HCLTECH.NS", "EICHERMOT.NS", "DRREDDY.NS",
    "CIPLA.NS", "APOLLOHOSP.NS", "JSWSTEEL.NS", "HINDUNILVR.NS", "NESTLEIND.NS",
    "BRITANNIA.NS", "ADANIENT.NS", "ADANIPORTS.NS", "BPCL.NS", "ONGC.NS",
    "DIVISLAB.NS", "HEROMOTOCO.NS", "INDUSINDBK.NS", "SHREECEM.NS"
]

# Database Path
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trades.db")
BACKUP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trades_backup.json")

# ntfy.sh Mobile Push Notifications Configuration
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "sr_trading_madhav")

# MegaBull Paper Trading API Integration
MEGABULL_API_KEY = os.getenv("MEGABULL_API_KEY", "dc09ce27-75b6-4f06-b3e9-646c484ab7ee")
MEGABULL_ENABLED = os.getenv("MEGABULL_ENABLED", "True").lower() in ("true", "1", "yes")

# Angel One SmartAPI Credentials (For Live Trading after 2 months paper trading)
ANGEL_API_KEY = os.getenv("ANGEL_API_KEY", "")
ANGEL_CLIENT_CODE = os.getenv("ANGEL_CLIENT_CODE", "")
ANGEL_PASSWORD = os.getenv("ANGEL_PASSWORD", "")
ANGEL_TOTP_KEY = os.getenv("ANGEL_TOTP_KEY", "")


# Fresh clean build
