from datetime import datetime, timezone, timedelta
import time
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    TrailingStopOrderRequest,
    GetOrdersRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus


class AlpacaExecutioner:
    def __init__(self, api_key, secret_key, paper=True):
        self.api = TradingClient(api_key, secret_key, paper=paper)
        self._positions = {}
        self._open_order_symbols = set()
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

    def ensure_trailing_stop(self, ticker, trail_percent):
        """Attach a broker-side trailing stop to a held position that lacks one.
        The trail distance also serves as the hard stop at entry (trail% below
        the fill). Returns True only if a new stop was actually submitted."""
        pos = self._positions.get(ticker)
        if pos is None:
            return False
        if ticker in self._open_order_symbols:
            return False  # already protected — don't stack orders
        qty = int(float(pos.qty))  # advanced orders require whole shares
        if qty <= 0:
            return False
        entry = float(pos.avg_entry_price)
        try:
            order = TrailingStopOrderRequest(
                symbol=ticker,
                qty=qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.GTC,
                trail_percent=trail_percent,
                # Entry price rides on the order id so a broker-side fill can
                # report realized P/L later — no state store needed.
                client_order_id=f"tstop-{ticker}-{entry:.4f}-{int(time.time())}",
            )
            self.api.submit_order(order_data=order)
            self._open_order_symbols.add(ticker)
            print(f"🛡️ Trailing stop {trail_percent}% set on {ticker} ({qty} shares)")
            return True
        except Exception as e:
            print(f"❌ Failed to set trailing stop for {ticker}: {e}")
            return False

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
        """Filled trailing-stop SELL orders in the last `hours`. Returns
        [(symbol, qty, fill_price, pl_pct, pl_usd)] — P/L fields are None for
        stops placed before we started tagging orders with the entry price."""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        try:
            req = GetOrdersRequest(status=QueryOrderStatus.CLOSED, after=since, limit=200)
            orders = self.api.get_orders(filter=req)
        except Exception as e:
            print(f"❌ Failed to fetch recent orders: {e}")
            return []
        stopouts = []
        for o in orders:
            otype = str(getattr(o, "order_type", "") or "").lower()
            status = str(o.status).lower()
            if "trailing_stop" in otype and "filled" in status:
                pl_pct = pl_usd = None
                coid = str(getattr(o, "client_order_id", "") or "")
                if coid.startswith("tstop-"):
                    try:
                        entry = float(coid.rsplit("-", 2)[1])
                        fill = float(o.filled_avg_price)
                        pl_pct = (fill - entry) / entry * 100
                        pl_usd = (fill - entry) * float(o.filled_qty)
                    except (IndexError, ValueError):
                        pass  # unexpected id format — report without P/L
                stopouts.append((o.symbol, o.filled_qty, o.filled_avg_price, pl_pct, pl_usd))
        return stopouts