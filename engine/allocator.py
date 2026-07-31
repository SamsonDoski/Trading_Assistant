import math


class PortfolioAllocator:
    """Sizing information-expert: turns dollars + conviction into a share count.
    Knows nothing about the broker — it deals only in prices and dollars."""

    def __init__(self, cash_reserve_pct=0.15, min_fractional_notional_usd=1.00):
        self.cash_reserve_pct = cash_reserve_pct
        self.min_fractional_notional_usd = min_fractional_notional_usd
        # Legacy V3.0 flat base — only used by generate_buy_orders below.
        self.flat_allocation_usd = 5000.00

    def usable_budget(self, buying_power):
        """Deployable dollars after the standing cash reserve is held back.
        Sizing policy lives here, not in the controller."""
        if buying_power is None or buying_power <= 0:
            return 0.0
        return buying_power * (1.0 - self.cash_reserve_pct)

    def base_allocation(self, usable_budget_usd, not_held_count):
        """Equal-weight dollar slice for ONE new position: deployable capital
        split across every watchlist name not currently held. This is the
        pre-conviction size; the sentiment multiplier scales it afterward.
        No flat cap — auto-scales to any account size. Returns 0.0 when there
        is nothing to deploy or every name is already held (guards /0)."""
        if usable_budget_usd is None or usable_budget_usd <= 0:
            return 0.0
        if not_held_count is None or not_held_count <= 0:
            return 0.0
        return usable_budget_usd / not_held_count

    def position_budget(self, base_allocation_usd, remaining_budget_usd=None,
                        conviction_multiplier=1.0):
        """Dollars to commit to one buy — the sizing decision in its purest form:

            desired_position_usd    = base_allocation_usd * conviction_multiplier
            affordable_position_usd = min(desired_position_usd, remaining_budget_usd)

        The budget cap is applied AFTER the multiplier. Public because a
        fractional buy is placed as a NOTIONAL (dollar) order, so the caller
        needs the dollar figure itself rather than a share count."""
        if base_allocation_usd is None or base_allocation_usd <= 0:
            return 0.0
        affordable_position_usd = base_allocation_usd * conviction_multiplier
        if remaining_budget_usd is not None:
            affordable_position_usd = min(affordable_position_usd, remaining_budget_usd)
        return max(affordable_position_usd, 0.0)

    def calculate_shares(self, current_price, base_allocation_usd,
                         remaining_budget_usd=None, conviction_multiplier=1.0,
                         allow_fractional=False):
        """Size one buy. Returns (shares, is_fractional).

        Whole shares are preferred; if even one whole share is unaffordable and
        fractional buying is allowed (and the slice clears the dust floor), a
        sub-1 share quantity is returned instead. (0, False) means buy nothing.

        Note the fractional share count is advisory — the controller places
        fractional buys as notional dollar orders (see position_budget), which
        removes the price-drift error entirely."""
        if current_price is None or current_price <= 0:
            return 0, False
        if base_allocation_usd is None or base_allocation_usd <= 0:
            return 0, False

        affordable_position_usd = self.position_budget(
            base_allocation_usd, remaining_budget_usd, conviction_multiplier)
        if affordable_position_usd <= 0:
            return 0, False

        whole_shares = int(affordable_position_usd // current_price)
        if whole_shares >= 1:
            return whole_shares, False

        # Can't afford a whole share — consider a fractional slice. It is always
        # < 1 here by construction, so no upper bound is needed.
        if not allow_fractional:
            return 0, False
        if affordable_position_usd < self.min_fractional_notional_usd:
            return 0, False  # too small to be worth a trade
        # Floor to 4 dp so rounding never pushes the notional above what we can
        # afford (Alpaca accepts fractional quantities to this precision).
        fractional_shares = math.floor((affordable_position_usd / current_price) * 1e4) / 1e4
        if fractional_shares <= 0:
            return 0, False
        return fractional_shares, True

    def generate_buy_orders(self, approved_signals, current_prices):
        """Legacy V3.0 helper (not on the live path). Sizes each approved ticker
        at a full flat slice, no conviction scaling, no fractional fallback."""
        orders = {}
        for ticker in approved_signals:
            if ticker in current_prices and current_prices[ticker] > 0:
                shares, _ = self.calculate_shares(
                    current_prices[ticker], base_allocation_usd=self.flat_allocation_usd)
                orders[ticker] = shares
        return orders