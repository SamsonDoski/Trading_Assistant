import os
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

from utils.profile_manager import load_profiles, is_stale
from utils.notifier import DiscordNotifier
from engine.scanner import StrategyScanner
from engine.allocator import PortfolioAllocator
from engine.executioner import AlpacaExecutioner
from engine.modes import ModeResolver
from config import (SENTIMENT_MODE, MIN_FRACTIONAL_NOTIONAL_USD, ACTIVE_MODE)
from engine.sentiment import SentimentAnalyzer


def run_live_pipeline():
    """
    The True Controller: orchestrates the pipeline by passing data between
    isolated micro-modules. It decides actions; the modules do the work.

    V5.0: every strategy/risk parameter arrives as a resolved ModeSettings from
    the ModeResolver, per ticker. ACTIVE_MODE="Swing" reproduces V4.0 exactly.
    """
    load_dotenv()
    print(f"⚙️ Initializing V5.0 Controller | mode: {ACTIVE_MODE}")

    # 1. Wire up the micro-modules
    notifier = DiscordNotifier()
    scanner = StrategyScanner()
    sentiment = SentimentAnalyzer()

    resolver = ModeResolver(ACTIVE_MODE)
    portfolio = resolver.portfolio_settings()      # account-level policy (cash reserve)
    allocator = PortfolioAllocator(
        cash_reserve_pct=portfolio.cash_reserve_pct,
        min_fractional_notional_usd=MIN_FRACTIONAL_NOTIONAL_USD,
    )

    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    try:
        executioner = AlpacaExecutioner(api_key, secret_key, paper=True)
    except Exception as e:
        msg = f"🚨 ABORT: cannot read positions from Alpaca ({e}). No trades this run."
        print(msg)
        notifier.send_message(msg)
        return

    # 2. Universe + tuned params come from profiles, not hardcoded lists
    profiles = load_profiles()
    if not profiles:
        notifier.send_message("⚠️ No stock profiles found. Nothing to trade.")
        return

    greeting = "Good Morning" if datetime.now(timezone.utc).hour < 16 else "Good Evening"
    notifier.send_message(
        f"{greeting}, Olajide. Running Trading Assistant Engine | mode: **{ACTIVE_MODE}**"
    )

    # Session budget: deployable buying power after the cash reserve, split
    # equally across watchlist names we don't already hold.
    buying_power = executioner.get_buying_power()
    usable_budget_usd = allocator.usable_budget(buying_power)
    remaining_budget_usd = usable_budget_usd
    not_held_count = sum(1 for t in profiles if not executioner.is_holding(t))
    base_allocation_usd = allocator.base_allocation(usable_budget_usd, not_held_count)
    bp_msg = (f"💰 Buying power: ${buying_power:,.2f} | "
              f"deployable after {allocator.cash_reserve_pct:.0%} reserve: ${usable_budget_usd:,.2f} | "
              f"{not_held_count} names open → base ${base_allocation_usd:,.2f}/position")
    print(bp_msg)
    notifier.send_message(bp_msg)

    # Report any positions the broker stopped out while we were asleep.
    for symbol, qty, fill_price, pl_pct, pl_usd in executioner.get_recent_stopouts(hours=24):
        so_msg = f"🛑 STOPPED OUT: {symbol} — {qty} shares @ ${float(fill_price):.2f}"
        if pl_pct is not None:
            so_msg += f" (P/L: {pl_pct:+.2f}% / ${pl_usd:+,.2f})"
        else:
            so_msg += " (trailing stop filled)"
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

            # Resolve this ticker's mode settings (Auto -> its researched mode).
            settings = resolver.settings_for(rules)

            # Step A: Scanner (the brain) does all the math, mode-parameterized
            signals = scanner.get_signals(ticker, settings)
            if not signals:
                msg = f"🔍 **{ticker}** | ❌ Data fetch failed."
                print(msg)
                notifier.send_message(msg)
                continue

            latest_signal = signals["latest_signal"]
            previous_signal = signals["previous_signal"]
            price = signals["current_price"]
            rsi = signals["current_rsi"]
            previous_rsi = signals.get("previous_rsi")

            # Step B: Executioner reports state (no raw SDK objects leak in here)
            holding = executioner.is_holding(ticker)

            # Step C: State machine — this is the controller's real job
            fresh_entry = (latest_signal == 1 and previous_signal == 0 and not holding)

            # Multi-entry re-entry (Aggressive/Volatile): the trend never broke but
            # we're flat (e.g. stopped out). Require an RSI dip that is TURNING UP
            # — buy the bounce, never the descent — plus a cooldown.
            recovery_entry = False
            if (settings.allow_multi_entry and not holding
                    and latest_signal == 1 and not fresh_entry):
                dipped = rsi < settings.rsi_buy_threshold
                turning_up = previous_rsi is not None and rsi > previous_rsi
                if dipped and turning_up:
                    days = executioner.days_since_last_buy(ticker)
                    # None = history unreadable -> refuse the extra entry.
                    recovery_entry = (days is not None
                                      and days >= settings.reentry_cooldown_days)

            if fresh_entry or recovery_entry:
                entry_kind = "fresh crossover" if fresh_entry else "RSI-recovery re-entry"

                report = None
                if settings.sentiment_enabled:
                    report = sentiment.get_verdict(
                        ticker,
                        conviction_min=settings.conviction_min,
                        conviction_max=settings.conviction_max,
                    )
                    mode_tag = "LIVE" if SENTIMENT_MODE == "live" else "SHADOW"
                    notifier.send_message(
                        f"📰 **{ticker}** | sentiment x{report.sentiment_multiplier:.2f}"
                        f"{' + VETO' if report.veto else ''} [{mode_tag}] — {report.rationale}"
                    )
                    if report.headlines:
                        digest = "\n".join(f"• {h[:120]}" for h in report.headlines[:5])
                        notifier.send_message(f"🗞️ **{ticker}** headlines considered:\n{digest}")
                    vetoed = (SENTIMENT_MODE == "live" and report.veto)
                    conviction_multiplier = (report.sentiment_multiplier
                                             if SENTIMENT_MODE == "live" else 1.0)
                else:
                    vetoed, conviction_multiplier = False, 1.0

                if vetoed:
                    state_msg = f"⛔ BUY VETOED by sentiment — {report.rationale}"
                else:
                    shares, is_fractional = allocator.calculate_shares(
                        current_price=price,
                        base_allocation_usd=base_allocation_usd,
                        remaining_budget_usd=remaining_budget_usd,
                        conviction_multiplier=conviction_multiplier,
                        allow_fractional=settings.allow_fractional,
                    )
                    if is_fractional and not executioner.fractionable(ticker):
                        state_msg = (f"⏸️ BUY signal — one whole share (${price:.2f}) exceeds this "
                                     f"position's ${base_allocation_usd * conviction_multiplier:,.2f} "
                                     f"budget and {ticker} isn't fractionable. Skipped.")
                    elif shares > 0:
                        executioner.execute_market_buy(ticker, shares)
                        remaining_budget_usd -= shares * price
                        if is_fractional:
                            fill_desc = f"{shares:.4f} fractional shares"
                            stop_desc = "software-trailing DAY stop"
                        else:
                            fill_desc = f"{int(shares)} shares"
                            stop_desc = ("trailing stop" if settings.trailing_stop_percent
                                         else "no stop (mode)")
                        state_msg = (f"🚀 BUY EXECUTED ({entry_kind}): {fill_desc} @ ${price:.2f} "
                                     f"[{stop_desc}] (deployable left: ${remaining_budget_usd:,.0f})")
                    else:
                        state_msg = "⏸️ BUY signal — skipped, insufficient deployable budget."

            elif latest_signal == 0 and holding:
                if settings.exit_on_trend_reversal:
                    pl = executioner.get_unrealized_pl_pct(ticker)
                    executioner.liquidate_position(ticker)
                    state_msg = f"🛑 SELL EXECUTED (trend reversal) (P/L: {pl:+.2f}%)"
                else:
                    pl = executioner.get_unrealized_pl_pct(ticker)
                    state_msg = (f"⏳ Trend reversed but this mode holds through "
                                 f"(P/L: {pl:+.2f}%)")

            elif latest_signal == 1 and holding:
                pl = executioner.get_unrealized_pl_pct(ticker)
                state_msg = f"⏳ Holding (P/L: {pl:+.2f}%)"

            elif latest_signal == 1 and previous_signal == 1 and not holding:
                # The signal is continuously 1 — it was armed on an earlier dip and
                # ffills until the trend reverses, so an RSI reset alone can NOT
                # re-arm it. Only a trend reset (or a multi-entry mode) re-enters.
                state_msg = ("⏳ Trend positive, entry dip already passed. "
                             "Waiting for a trend reset to re-arm.")

            else:
                state_msg = "⏳ Waiting, Trend negative or RSI is high."

            # Step D: Notifier announces the result
            log_msg = (
                f"🔍 **{ticker}** [{settings.name}] | MA: {settings.ma_short}/{settings.ma_long} | "
                f"Price: ${price:.2f} | RSI: {rsi:.1f} | Sig: {latest_signal} | {state_msg}"
            )
            print(log_msg)
            notifier.send_message(log_msg)

        except Exception as e:
            err = f"❌ Pipeline error on {ticker}: {e}"
            print(err)
            notifier.send_message(err)

    # 4. Protection pass — ensure every open position carries the stop its mode
    #    prescribes. Pause first so market-open fills for THIS run's buys settle
    #    and get protected now, instead of waiting until tomorrow.
    time.sleep(10)
    executioner.refresh_positions()
    executioner.refresh_open_orders()
    for ticker in executioner.held_symbols():
        held_settings = resolver.settings_for(profiles.get(ticker))
        status_msg = executioner.ensure_protective_stop(
            ticker, held_settings.trailing_stop_percent)
        if status_msg:
            print(status_msg)
            notifier.send_message(status_msg)

    print("✅ V5.0 Pipeline Execution Complete.")


if __name__ == "__main__":
    run_live_pipeline()