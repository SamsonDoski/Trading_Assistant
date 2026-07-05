from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce


class AlpacaExecutioner:
    def __init__(self, api_key, secret_key, paper=True):
        self.api = TradingClient(api_key, secret_key, paper=paper)
        self._positions = {}
        self.refresh_positions()

    def refresh_positions(self):
        """Snapshot all open positions once, so we don't hit the API per ticker."""
        try:
            self._positions = {p.symbol: p for p in self.api.get_all_positions()}
        except Exception as e:
            print(f"❌ Failed to fetch positions: {e}")
            self._positions = {}
        return self._positions

    def is_holding(self, ticker):
        """True if we currently own the asset. Controller uses this, not raw objects."""
        return ticker in self._positions

    def get_unrealized_pl_pct(self, ticker):
        """Unrealized P/L as a percent, or None if not held."""
        pos = self._positions.get(ticker)
        if pos is None:
            return None
        return float(pos.unrealized_plpc) * 100

    def execute_market_buy(self, ticker, qty):
        """Submits a fractional-share market buy for the qty the allocator sized."""
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

    def liquidate_position(self, ticker):
        """Closes the entire position — avoids the string-qty pitfall of the old SDK."""
        try:
            self.api.close_position(ticker)
            print(f"🛑 Executed SELL (Liquidated) {ticker}")
        except Exception as e:
            print(f"❌ Failed to liquidate {ticker}: {e}")