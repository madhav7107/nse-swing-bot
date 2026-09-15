import requests
import config

def send_alert(message: str):
    """
    Sends notification message to Telegram channel/user if configured,
    and prints to console.
    """
    print(f"\n[ALERT] {message}")
    
    if not config.TELEGRAM_ENABLED or not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return
    
    try:
        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": config.TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Telegram notification error: {e}")

def notify_buy_signal(setup: dict, qty: int, trade_id: int):
    symbol = setup['symbol'].replace('.NS', '')
    msg = (
        f"🚀 *SWING BUY SIGNAL* [{config.TRADING_MODE} MODE]\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📌 *Stock:* `{symbol}` (NSE)\n"
        f"💰 *Entry Price:* ₹{setup['entry_price']}\n"
        f"📦 *Quantity:* {qty} shares\n"
        f"🎯 *Target Price:* ₹{setup['target_price']} (+{setup['target_pct']}%)\n"
        f"🛑 *Stop Loss:* ₹{setup['stop_loss']} (-{setup['risk_pct']}%)\n"
        f"📊 *Setup:* {setup['pattern']} (RSI: {setup['rsi']})\n"
        f"🆔 *Trade ID:* #{trade_id}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    send_alert(msg)

def notify_exit_signal(trade: dict, current_price: float, reason: str, pnl: float, pnl_pct: float):
    symbol = trade['symbol'].replace('.NS', '')
    icon = "🎯" if pnl >= 0 else "🛑"
    pnl_str = f"+₹{round(pnl, 2)} (+{round(pnl_pct, 2)}%)" if pnl >= 0 else f"-₹{round(abs(pnl), 2)} ({round(pnl_pct, 2)}%)"
    
    msg = (
        f"{icon} *SWING EXIT ALERT* [{config.TRADING_MODE} MODE]\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📌 *Stock:* `{symbol}`\n"
        f"🏷️ *Exit Reason:* {reason}\n"
        f"💵 *Exit Price:* ₹{current_price} (Entry: ₹{trade['entry_price']})\n"
        f"📊 *Result:* {pnl_str}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    send_alert(msg)

def notify_trailing_sl(trade: dict, old_sl: float, new_sl: float):
    symbol = trade['symbol'].replace('.NS', '')
    msg = (
        f"🛡️ *TRAILING STOP-LOSS UPDATED*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📌 *Stock:* `{symbol}`\n"
        f"📈 *Old SL:* ₹{old_sl} ➡️ *New SL:* ₹{new_sl}\n"
        f"🔒 *Profit Locked In!*\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    send_alert(msg)
