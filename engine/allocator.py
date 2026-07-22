class PortfolioAllocator:
    def __init__(self, cash_reserve_pct=0.15):
        # Retaining V3.0 Legacy Logic: Flat $5,000 base allocation per asset
        self.flat_allocation_usd = 5000.00
        self.cash_reserve_pct = cash_reserve_pct

    def usable_budget(self, buying_power):
        """Deployable portion of buying power after the cash reserve.
        Sizing policy lives here, not in the controller."""
        if buying_power is None or buying_power <= 0:
            return 0.0
        return buying_power * (1.0 - self.cash_reserve_pct)

    def calculate_shares(self, current_price, buying_power=None, multiplier=1.0):
        """Whole shares to buy for one ticker: base allocation x conviction
        multiplier, capped by the remaining session budget, floored to whole
        shares. Returns 0 if even one share is unaffordable."""
        if current_price is None or current_price <= 0:
            return 0
        budget = self.flat_allocation_usd * multiplier
        if buying_power is not None:
            budget = min(budget, buying_power)
        return int(budget // current_price)

    def generate_buy_orders(self, approved_signals, current_prices):
        """
        Takes a list of tickers with a '1.0' Buy signal and calculates
        the whole-share count needed to approach the target allocation.
        """
        orders = {}
        for ticker in approved_signals:
            if ticker in current_prices and current_prices[ticker] > 0:
                orders[ticker] = self.calculate_shares(current_prices[ticker])
        return orders