import os
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

from utils.profile_manager import load_profiles, is_stale
from utils.notifier import DiscordNotifier
from utils.alpaca_data import fetch_latest_price
from engine.scanner import StrategyScanner
from engine.allocator import PortfolioAllocator
from engine.executioner import AlpacaExecutioner
from engine.modes import ModeResolver
from config import (SENTIMENT_MODE, MIN_FRACTIONAL_NOTIONAL_USD, ACTIVE_MODE,
                    ALPACA_PAPER, TRADING_HALTED)
from engine.sentiment import SentimentAnalyzer


def run_live_pipeline():
    """
    The True Controller: orchestrates the pipeline by passing data between
    isolated micro-modules. It decides actions; the modules do the work.

    V5.0: every strategy/risk parameter arrives as a resolved ModeSettings from
    the ModeResolver, per ticker. ACTIVE_MODE="V4_Legacy" reproduces V4.0 exactly.

    The brokerage account is chosen entirely by environment: ALPACA_API_KEY /
    ALPACA_SECRET_KEY pick the account, ALPACA_PAPER picks the endpoint. Running a
    second account in parallel therefore needs no code — just another deployment
    with a different environment.
    """
    load_dotenv()
    account_kind = "PAPER" if ALPACA_PAPER else "LIVE"
    print(f"⚙️ Initializing V5.0 Controller | mode: {ACTIVE_MODE} | "
          f"account: {account_kind} | halted: {TRADING_HALTED}")

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
        executioner = AlpacaExecutioner(api_key, secret_key, paper=ALPACA_PAPER)
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
        f"{greeting}, Olajide. Running Trading Assistant Engine | "
        f"mode: **{ACTIVE_MODE}** | account: **{account_kind}**"
    )

    # Announce the kill switch on EVERY run it is on. A silent freeze looks
    # identical to a quiet market, and that is how a halt gets left on for weeks.
    if TRADING_HALTED:
        halt_msg = ("🛑 **KILL SWITCH ON** — no new positions will be opened this run. "
                    "Sells, stop attachment and stop-out reporting still run normally. "
                    "Set TRADING_HALTED=false to resume buying.")
        print(halt_msg)
        notifier.send_message(halt_msg)

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
            so_msg += " (stop filled)"      # covers both trailing and fractional DAY stops
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
            # — buy the bounce, never the descent. Re-entry only ever happens while
            # FLAT; this never adds to an open position.
            recovery_entry = False
            recovery_note = ""      # why re-entry did NOT fire, for the log
            if (settings.allow_multi_entry and not holding
                    and latest_signal == 1 and not fresh_entry):
                dipped = rsi < settings.rsi_buy_threshold
                turning_up = previous_rsi is not None and rsi > previous_rsi
                if not dipped:
                    recovery_note = (f"waiting for RSI to dip below "
                                     f"{settings.rsi_buy_threshold:.0f} to re-enter")
                elif not turning_up:
                    recovery_note = (f"RSI is below {settings.rsi_buy_threshold:.0f} "
                                     f"but still falling; waiting for it to turn up")
                else:
                    recovery_entry = True

            if (fresh_entry or recovery_entry) and TRADING_HALTED:
                # Checked BEFORE sentiment so a halted run spends no news/LLM
                # calls on entries that cannot happen.
                state_msg = ("🛑 BUY SUPPRESSED — kill switch is on "
                             "(sells and stops still active).")

            elif fresh_entry or recovery_entry:
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
                    # Size against a LIVE quote, not the last completed daily bar.
                    # The signal is deliberately a closed-bar decision, but the
                    # money is spent at today's price — using the stale close made
                    # every buy off by whatever the price had moved since.
                    sizing_price = fetch_latest_price(ticker) or price
                    position_budget_usd = allocator.position_budget(
                        base_allocation_usd, remaining_budget_usd, conviction_multiplier)
                    shares, is_fractional = allocator.calculate_shares(
                        current_price=sizing_price,
                        base_allocation_usd=base_allocation_usd,
                        remaining_budget_usd=remaining_budget_usd,
                        conviction_multiplier=conviction_multiplier,
                        allow_fractional=settings.allow_fractional,
                    )
                    if is_fractional and not executioner.fractionable(ticker):
                        state_msg = (f"⏸️ BUY signal — one whole share (${sizing_price:.2f}) exceeds "
                                     f"this position's ${position_budget_usd:,.2f} budget and "
                                     f"{ticker} isn't fractionable. Skipped.")
                    elif shares > 0:
                        if is_fractional:
                            # Dollar order: the broker derives the quantity at the
                            # real fill price, so the spend is exact.
                            executioner.execute_market_buy(ticker, notional=position_budget_usd)
                            remaining_budget_usd -= position_budget_usd
                            fill_desc = f"${position_budget_usd:,.2f} (fractional)"
                            stop_desc = "software-trailing DAY stop"
                        else:
                            executioner.execute_market_buy(ticker, qty=shares)
                            remaining_budget_usd -= shares * sizing_price
                            fill_desc = f"{int(shares)} shares"
                            stop_desc = ("trailing stop" if settings.trailing_stop_percent
                                         else "no stop (mode)")
                        state_msg = (f"🚀 BUY EXECUTED ({entry_kind}): {fill_desc} @ ~${sizing_price:.2f} "
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
                # The signal is continuously 1 — armed on an earlier dip and
                # ffilled until the trend reverses.
                if settings.allow_multi_entry:
                    # This mode CAN re-enter without a trend reset; say what it's
                    # actually waiting on rather than the single-entry boilerplate.
                    state_msg = f"⏳ Trend positive — {recovery_note}."
                else:
                    # An RSI reset alone can NOT re-arm a single-entry mode; only
                    # a trend reversal followed by a fresh crossover will.
                    state_msg = ("⏳ Trend positive, entry dip already passed. "
                                 "Single-entry mode — waiting for a trend reset to re-arm.")

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