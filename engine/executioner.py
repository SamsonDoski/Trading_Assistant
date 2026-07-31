from datetime import datetime, timezone, timedelta
import time
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    TrailingStopOrderRequest,
    StopOrderRequest,
    GetOrdersRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus


class AlpacaExecutioner:
    def __init__(self, api_key, secret_key, paper=True):
        self.api = TradingClient(api_key, secret_key, paper=paper)
        self._positions = {}
        self._open_order_symbols = set()
        self._fractionable_cache = {}  # cache of symbols that support fractional shares
        self.refresh_positions()
        self.refresh_open_orders()

    def refresh_positions(self, attempts=3, delay=2.0):
        """Snapshot all open positions. Retries transient failures (Alpaca times
        out fairly often), then RAISES. Deliberately does not swallow errors:
        assuming 'flat' on a failed fetch lets the bot re-buy what it already
        owns and silently skip real exits."""
        last_err = None
        for i in range(attempts):
            try:
                self._positions = {p.symbol: p for p in self.api.get_all_positions()}
                return self._positions
            except Exception as e:
                last_err = e
                print(f"⚠️ Position fetch failed (attempt {i + 1}/{attempts}): {e}")
                if i < attempts - 1:
                    time.sleep(delay)
        raise RuntimeError(f"Could not read positions after {attempts} attempts: {last_err}")

    def refresh_open_orders(self):
        """Snapshot which symbols already have an open (unfilled) order, so we
        never stack a second trailing stop on an already-protected position."""
        try:
            req = GetOrdersRequest(status=QueryOrderStatus.OPEN)
            self._open_order_symbols = {o.symbol for o in self.api.get_orders(filter=req)}
        except Exception as e:
            print(f"❌ Failed to fetch open orders: {e}")
            self._open_order_symbols = set()
        return self._open_order_symbols

    def is_holding(self, ticker):
        """True if we currently own the asset. Controller uses this, not raw objects."""
        return ticker in self._positions

    def held_symbols(self):
        """Public list of currently-held symbols (keeps _positions private)."""
        return list(self._positions.keys())

    def get_unrealized_pl_pct(self, ticker):
        """Unrealized P/L as a percent, or None if not held."""
        pos = self._positions.get(ticker)
        if pos is None:
            return None
        return float(pos.unrealized_plpc) * 100
    
    def get_buying_power(self):
        """Cash available to buy WITHOUT using margin — prevents order bounces
        and keeps the long-only bot from silently leveraging. 0.0 on failure."""
        try:
            account = self.api.get_account()
            return float(account.non_marginable_buying_power)
        except Exception as e:
            print(f"❌ Failed to fetch buying power: {e}")
            return 0.0

    def fractionable(self, ticker):
        """True if Alpaca allows fractional-share orders on this symbol. Cached
        per run. Defaults to False on lookup failure so we never fire a
        fractional order the broker would reject."""
        if ticker in self._fractionable_cache:
            return self._fractionable_cache[ticker]
        try:
            asset = self.api.get_asset(ticker)
            result = bool(getattr(asset, "fractionable", False))
        except Exception as e:
            print(f"⚠️ Could not check fractionable for {ticker}: {e}")
            result = False
        self._fractionable_cache[ticker] = result
        return result

    def position_qty(self, ticker):
        """Raw share quantity held (float; may be fractional). 0.0 if not held."""
        pos = self._positions.get(ticker)
        return float(pos.qty) if pos else 0.0

    def execute_market_buy(self, ticker, qty):
        """Submits a whole-share market buy for the qty the allocator sized."""
        if qty is None or qty <= 0:
            return
        try:
            order = MarketOrderRequest(
                symbol=ticker,
                qty=qty,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
            )
            self.api.submit_order(order_data=order)
            print(f"✅ Executed BUY for {qty} shares of {ticker}")
        except Exception as e:
            print(f"❌ Failed to execute BUY for {ticker}: {e}")


    def days_since_last_buy(self, ticker, lookback_days=90):
        """Days since the most recent FILLED buy on this symbol.
        `inf` = no buy found in the lookback (cooldown trivially satisfied).
        `None` = history unreadable — caller must treat that as NOT satisfied,
        so an unverifiable cooldown can never authorize an extra entry."""
        now = datetime.now(timezone.utc)
        try:
            req = GetOrdersRequest(
                status=QueryOrderStatus.CLOSED,
                after=now - timedelta(days=lookback_days),
                symbols=[ticker],
                limit=200,
            )
            orders = self.api.get_orders(filter=req)
        except Exception as e:
            print(f"⚠️ Could not read buy history for {ticker}: {e}")
            return None
        newest = None
        for o in orders:
            side = str(getattr(o, "side", "") or "").lower()
            status = str(getattr(o, "status", "") or "").lower()
            if "buy" in side and "filled" in status:
                ts = getattr(o, "filled_at", None) or getattr(o, "submitted_at", None)
                if ts is not None and (newest is None or ts > newest):
                    newest = ts
        if newest is None:
            return float("inf")
        return (now - newest).total_seconds() / 86400.0

    def ensure_protective_stop(self, ticker, stop_percent):
        """Attach the right kind of broker-side stop to a held position, or sell
        it if it's already past its stop. Returns a Discord-ready status line, or
        None if nothing needed doing.

        Whole-share position -> GTC trailing stop (trails natively, survives
        overnight). Fractional position -> Alpaca forbids trailing stops on
        sub-share qty and only allows DAY time-in-force, so we place a DAY stop
        at a high-water `protected_stop_price` that ratchets up run to run
        (software trailing) and re-place it each run. If price is already at or
        below that level (e.g. an overnight gap after the DAY stop expired), we
        liquidate directly as the backstop instead of submitting a stop that
        would fire on placement."""
        pos = self._positions.get(ticker)
        if pos is None:
            return None
        if stop_percent is None:
            return None   # mode runs without stops (Long_Term rides drawdowns)
        if ticker in self._open_order_symbols:
            return None  # already protected this session — don't stack

        qty = float(pos.qty)
        entry_price = float(pos.avg_entry_price)
        is_whole = qty >= 1 and qty == int(qty)
        if is_whole:
            return self._attach_trailing_stop(ticker, int(qty), entry_price, stop_percent)
        return self._attach_fractional_stop(ticker, qty, entry_price, stop_percent / 100.0)

    def _attach_trailing_stop(self, ticker, qty, entry_price, stop_percent):
        """GTC trailing stop for a whole-share position (unchanged V4.0 behavior).
        Entry price rides on the order id so a broker-side fill can report
        realized P/L later — no state store needed."""
        try:
            order = TrailingStopOrderRequest(
                symbol=ticker,
                qty=qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.GTC,
                trail_percent=stop_percent,
                client_order_id=f"tstop-{ticker}-{entry_price:.4f}-{int(time.time())}",
            )
            self.api.submit_order(order_data=order)
            self._open_order_symbols.add(ticker)
            print(f"🛡️ Trailing stop {stop_percent}% set on {ticker} ({qty} shares)")
            return f"🛡️ **{ticker}** | Trailing stop {stop_percent}% attached ({qty} shares)."
        except Exception as e:
            print(f"❌ Failed to set trailing stop for {ticker}: {e}")
            return None

    def _attach_fractional_stop(self, ticker, qty, entry_price, stop_fraction):
        """Software trailing stop for a fractional position via a re-placed DAY
        stop whose level only ever ratchets up:

            candidate_stop_price = current_price * (1 - stop_fraction)
            protected_stop_price = max(previous_protected_stop_price, candidate_stop_price)

        Both `protected_stop_price` AND the entry price are carried on the order's
        client_order_id and recovered next run (same trick the trailing stop uses),
        so no external state store is needed — the stop level drives the ratchet,
        the entry price lets a fill be reported with realized P/L. DAY stops expire
        at close, hence the re-placement each run — and hence no overnight coverage,
        which the 'already past stop' branch below backstops on the next run."""
        pos = self._positions.get(ticker)
        try:
            current_price = float(pos.current_price)
        except (TypeError, ValueError, AttributeError):
            current_price = entry_price  # field missing — fall back to entry

        seed_stop = entry_price * (1.0 - stop_fraction)
        previous_stop = self._recover_protected_stop(ticker)
        floor_stop = previous_stop if previous_stop is not None else seed_stop
        candidate_stop = current_price * (1.0 - stop_fraction)
        protected_stop_price = max(floor_stop, candidate_stop)

        # Already at/below the locked level -> the trailing stop has been hit
        # while we were away (DAY stop had expired). Sell now.
        if current_price <= protected_stop_price:
            self.liquidate_position(ticker)
            return (f"🩹 **{ticker}** | Fractional position past stop "
                    f"(${current_price:.2f} ≤ ${protected_stop_price:.2f}) — liquidated.")

        stop_price = round(protected_stop_price, 2)  # note: sub-$1 tickers lose precision here
        try:
            order = StopOrderRequest(
                symbol=ticker,
                qty=qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
                stop_price=stop_price,
                client_order_id=(f"fstop-{ticker}-{protected_stop_price:.4f}"
                                 f"-{entry_price:.4f}-{int(time.time())}"),
            )
            self.api.submit_order(order_data=order)
            self._open_order_symbols.add(ticker)
            print(f"🛡️ Fractional DAY stop @ ${stop_price} on {ticker} ({qty} shares)")
            return (f"🛡️ **{ticker}** | Fractional DAY stop @ ${stop_price:.2f} "
                    f"(software-trailing, re-set each run).")
        except Exception as e:
            # Broker rejected the fractional stop (docs are ambiguous on support)
            # — degrade to the next-run backstop rather than crash the pass.
            print(f"❌ Fractional stop rejected for {ticker}: {e} — relying on run-time check.")
            return None

    @staticmethod
    def _parse_fractional_stop_id(client_order_id):
        """(protected_stop_price, entry_price) from one of our fractional-stop ids.

        Current format: fstop-{ticker}-{stop}-{entry}-{timestamp}
        Legacy format:  fstop-{ticker}-{stop}-{timestamp}  -> entry is None.
        Returns (None, None) for anything that isn't ours or won't parse, so a
        manually placed stop is never mistaken for a bot stop."""
        parts = str(client_order_id or "").split("-")
        if len(parts) < 4 or parts[0] != "fstop":
            return None, None
        try:
            stop_level = float(parts[2])
        except ValueError:
            return None, None
        entry_price = None
        if len(parts) >= 5:
            try:
                entry_price = float(parts[3])
            except ValueError:
                entry_price = None
        return stop_level, entry_price

    def _recover_protected_stop(self, ticker):
        """Highest `protected_stop_price` previously committed for a fractional
        position, parsed from the client_order_id of past DAY stops (open or
        expired). Returns None if none found — caller then seeds from entry.
        One order-history call per fractional name; fine at current scale, could
        be batched into a single bulk fetch later if the watchlist grows."""
        try:
            req = GetOrdersRequest(status=QueryOrderStatus.ALL, symbols=[ticker], limit=50)
            orders = self.api.get_orders(filter=req)
        except Exception as e:
            print(f"⚠️ Could not recover prior stop for {ticker}: {e}")
            return None
        best = None
        prefix = f"fstop-{ticker}-"
        for o in orders:
            coid = str(getattr(o, "client_order_id", "") or "")
            if not coid.startswith(prefix):
                continue
            level, _ = self._parse_fractional_stop_id(coid)
            if level is not None and (best is None or level > best):
                best = level
        return best

    def liquidate_position(self, ticker):
        """Closes the entire position. Cancels any protective stop first so the
        shares aren't locked by an open order when we close."""
        try:
            self._cancel_open_orders_for(ticker)
            self.api.close_position(ticker)
            print(f"🛑 Executed SELL (Liquidated) {ticker}")
        except Exception as e:
            print(f"❌ Failed to liquidate {ticker}: {e}")

    def _cancel_open_orders_for(self, ticker):
        """Cancel any open orders on a symbol (e.g., its trailing stop) so the
        position can be closed cleanly."""
        try:
            req = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[ticker])
            for o in self.api.get_orders(filter=req):
                self.api.cancel_order_by_id(o.id)
            self._open_order_symbols.discard(ticker)
        except Exception as e:
            print(f"⚠️ Could not cancel open orders for {ticker}: {e}")

    def get_recent_stopouts(self, hours=24):
        """Filled protective-stop SELL orders in the last `hours`. Returns
        [(symbol, qty, fill_price, pl_pct, pl_usd)].

        Covers BOTH stop flavors, which have different broker order types:
          * whole-share  -> GTC trailing_stop, entry price on a `tstop-` id
          * fractional   -> DAY plain stop,   entry price on an `fstop-` id
        Matching fractional stops by their client_order_id rather than by order
        type keeps a manually placed stop from being reported as a bot exit.
        P/L is None for legacy ids placed before the entry price was tagged on."""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        try:
            req = GetOrdersRequest(status=QueryOrderStatus.CLOSED, after=since, limit=200)
            orders = self.api.get_orders(filter=req)
        except Exception as e:
            print(f"❌ Failed to fetch recent orders: {e}")
            return []

        stopouts = []
        for o in orders:
            order_type = str(getattr(o, "order_type", "") or "").lower()
            status = str(o.status).lower()
            if "filled" not in status:
                continue
            coid = str(getattr(o, "client_order_id", "") or "")
            is_trailing_stop = "trailing_stop" in order_type
            is_fractional_stop = coid.startswith("fstop-")
            if not (is_trailing_stop or is_fractional_stop):
                continue

            entry_price = None
            if is_fractional_stop:
                _, entry_price = self._parse_fractional_stop_id(coid)
            elif coid.startswith("tstop-"):
                try:
                    entry_price = float(coid.rsplit("-", 2)[1])
                except (IndexError, ValueError):
                    entry_price = None

            pl_pct = pl_usd = None
            if entry_price:
                try:
                    fill_price = float(o.filled_avg_price)
                    pl_pct = (fill_price - entry_price) / entry_price * 100
                    pl_usd = (fill_price - entry_price) * float(o.filled_qty)
                except (TypeError, ValueError):
                    pl_pct = pl_usd = None      # unusable fill data — report without P/L

            stopouts.append((o.symbol, o.filled_qty, o.filled_avg_price, pl_pct, pl_usd))
        return stopouts