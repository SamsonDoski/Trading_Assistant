import os
import time
from dotenv import load_dotenv

from utils.profile_manager import load_profiles, is_stale
from utils.notifier import DiscordNotifier
from engine.scanner import StrategyScanner
from engine.allocator import PortfolioAllocator
from engine.executioner import AlpacaExecutioner
from config import TRAILING_STOP_PERCENT


def run_live_pipeline():
    """
    The True Controller: orchestrates the pipeline by passing data between
    isolated micro-modules. It decides actions; the modules do the work.
    """
    load_dotenv()
    print("⚙️ Initializing V3.1 True Controller...")

    # 1. Wire up the micro-modules
    notifier = DiscordNotifier()
    scanner = StrategyScanner()
    allocator = PortfolioAllocator()

    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    executioner = AlpacaExecutioner(api_key, secret_key, paper=True)

    # 2. Universe + tuned params come from profiles, not hardcoded lists
    profiles = load_profiles()
    if not profiles:
        notifier.send_message("⚠️ No stock profiles found. Nothing to trade.")
        return

    notifier.send_message(
        "Good Morning, Olajide. Running Trading Assistant Engine for the day..."
    )

    # Running budget for this session — sized against real buying power so we
    # never submit an order Alpaca would bounce for insufficient funds.
    budget = executioner.get_buying_power()
    bp_msg = f"💰 Buying power available: ${budget:,.2f}"
    print(bp_msg)
    notifier.send_message(bp_msg)

    # Report any positions the broker stopped out while we were asleep.
    for symbol, qty, fill_price in executioner.get_recent_stopouts(hours=24):
        so_msg = f"🛑 STOPPED OUT: {symbol} — {qty} shares @ ${float(fill_price):.2f} (trailing stop filled)"
        print(so_msg)
        notifier.send_message(so_msg)

    # 3. Orchestration loop
    for ticker, rules in profiles.items():
        try:
            if is_stale(ticker):
                msg = f"🔍 **{ticker}** | ⚠️ Stale profile. Skipping."
                print(msg)
                notifier.send_message(msg)
                continue

            short_ma = rules["best_short_window"]
            long_ma = rules["best_long_window"]
            rsi_period = rules.get("rsi_period", 14)

            # Step A: Scanner (the brain) does all the math
            signals = scanner.get_signals(ticker, short_ma, long_ma, rsi_period)
            if not signals:
                msg = f"🔍 **{ticker}** | ❌ Data fetch failed."
                print(msg)
                notifier.send_message(msg)
                continue

            latest_signal = signals["latest_signal"]
            previous_signal = signals["previous_signal"]
            price = signals["current_price"]
            rsi = signals["current_rsi"]

            # Step B: Executioner reports state (no raw SDK objects leak in here)
            holding = executioner.is_holding(ticker)

           # Step C: State machine — this is the controller's real job
            if latest_signal == 1 and previous_signal == 0 and not holding:
                qty = allocator.calculate_shares(price, budget)
                if qty > 0:
                    executioner.execute_market_buy(ticker, qty)
                    budget -= qty * price              # spend from the running budget
                    state_msg = f"🚀 BUY EXECUTED: {qty} shares @ ${price:.2f} (BP left: ${budget:,.0f})"
                else:
                    state_msg = "⏸️ BUY signal — skipped, insufficient buying power."

            elif latest_signal == 0 and holding:
                pl = executioner.get_unrealized_pl_pct(ticker)
                executioner.liquidate_position(ticker)
                state_msg = f"🛑 SELL EXECUTED (Liquidated) (P/L: {pl:+.2f}%)"

            elif latest_signal == 1 and holding:
                pl = executioner.get_unrealized_pl_pct(ticker)
                state_msg = f"⏳ Holding (P/L: {pl:+.2f}%)"

            elif latest_signal == 1 and previous_signal == 1 and not holding:
                state_msg = "⏳ Trend positive but missed RSI dip. Waiting for next RSI reset."

            else:
                state_msg = "⏳ Waiting, Trend negative or RSI is high."

            # Step D: Notifier announces the result
            log_msg = (
                f"🔍 **{ticker}** | MA: {short_ma}/{long_ma} | "
                f"Price: ${price:.2f} | RSI: {rsi:.1f} | Sig: {latest_signal} | {state_msg}"
            )
            print(log_msg)
            notifier.send_message(log_msg)

        except Exception as e:
            err = f"❌ Pipeline error on {ticker}: {e}"
            print(err)
            notifier.send_message(err)

    # 4. Protection pass — ensure every open position carries a broker-side
    #    trailing stop. Pause first so market-open fills for THIS run's buys
    #    settle and get protected now, instead of waiting until tomorrow.
    time.sleep(10)  # Pause for 10 seconds
    executioner.refresh_positions()
    executioner.refresh_open_orders()
    for ticker in executioner.held_symbols():
        if executioner.ensure_trailing_stop(ticker, TRAILING_STOP_PERCENT):
            msg = f"🛡️ **{ticker}** | Trailing stop {TRAILING_STOP_PERCENT}% attached."
            print(msg)
            notifier.send_message(msg)

    print("✅ V3.1 Pipeline Execution Complete.")


if __name__ == "__main__":
    run_live_pipeline()