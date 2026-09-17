import urllib.request
import config

def send_ntfy(title: str, message: str, priority: str = "default", tags: list = None):
    try:
        topic = getattr(config, "NTFY_TOPIC", "sr_trading_madhav")
        url = f"https://ntfy.sh/{topic}"
        headers = {"Title": title.encode("utf-8"), "Priority": priority}
        if tags:
            headers["Tags"] = ",".join(tags)
        req = urllib.request.Request(url, data=message.encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[ntfy notification error] {e}")
        return False

def notify_buy(trade: dict):
    sym = trade["symbol"].replace(".NS", "")
    title = f"🚀 SR-TRADING: BUY {sym}"
    p_name = trade.get("pattern", "Zone Bounce")
    score = trade.get("confluence_score", 75)
    entry = float(trade["entry_price"])
    sl = float(trade["stop_loss"])
    tgt = float(trade["target_price"])
    qty = trade["quantity"]
    
    sl_pct = round(((sl - entry) / entry) * 100, 2)
    tgt_pct = round(((tgt - entry) / entry) * 100, 2)
    risk = max(0.01, abs(entry - sl))
    reward = abs(tgt - entry)
    rr = round(reward / risk, 2)
    
    msg = (
        f"Stock: {sym}\n"
        f"Action: BUY (Cash CNC)\n"
        f"Qty: {qty} shares\n"
        f"Entry: Rs. {entry}\n"
        f"SL: Rs. {sl} ({sl_pct}%)\n"
        f"Target: Rs. {tgt} (+{tgt_pct}%)\n"
        f"Risk:Reward: 1:{rr}\n"
        f"Setup: {p_name} [{score}%]"
    )
    return send_ntfy(title, msg, priority="high", tags=["chart_with_upwards_trend", "rocket"])

def notify_trailing_sl(symbol: str, old_sl: float, new_sl: float, ltp: float):
    sym = symbol.replace(".NS", "")
    title = f"🛡️ SL Trailed to Cost: {sym}"
    msg = (
        f"{sym} reached 1R profit milestone!\n"
        f"Current LTP: Rs. {ltp}\n"
        f"SL moved from Rs. {old_sl} to Cost Rs. {new_sl}\n"
        f"Trade is now 100% Risk-Free!"
    )
    return send_ntfy(title, msg, priority="default", tags=["shield", "arrow_up"])

def notify_target_hit(trade: dict, ltp: float, pnl: float):
    sym = trade["symbol"].replace(".NS", "")
    pnl_round = round(pnl, 2)
    title = f"🎉 TARGET HIT: {sym} (+Rs. {pnl_round})"
    msg = (
        f"{sym} hit profit target!\n"
        f"Exit Price: Rs. {ltp}\n"
        f"Realized Profit: +Rs. {pnl_round}\n"
        f"Position closed in profit!"
    )
    return send_ntfy(title, msg, priority="urgent", tags=["tada", "moneybag"])

def notify_stop_loss_hit(trade: dict, ltp: float, pnl: float):
    sym = trade["symbol"].replace(".NS", "")
    pnl_round = round(pnl, 2)
    title = f"🛑 STOP LOSS HIT: {sym}"
    msg = (
        f"{sym} hit stop loss.\n"
        f"Exit Price: Rs. {ltp}\n"
        f"Loss: Rs. {pnl_round}\n"
        f"Position closed to protect capital."
    )
    return send_ntfy(title, msg, priority="high", tags=["warning", "octagonal_sign"])
