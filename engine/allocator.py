class PortfolioAllocator:
    def __init__(self):
        # Retaining V3.0 Legacy Logic: Flat $5,000 allocation per asset
        self.flat_allocation_usd = 5000.00

    def calculate_shares(self, current_price, buying_power=None):
        """Whole shares to buy for one ticker. Targets the flat allocation, but
        never exceeds available buying power, so Alpaca can't bounce the order.
        Returns 0 if even one share is unaffordable within the budget."""
        if current_price is None or current_price <= 0:
            return 0
        budget = self.flat_allocation_usd
        if buying_power is not None:
            budget = min(budget, buying_power)   # cap the $5k target at what's actually available
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