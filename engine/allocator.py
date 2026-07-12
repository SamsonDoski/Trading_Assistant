class PortfolioAllocator:
    def __init__(self):
        # Retaining V3.0 Legacy Logic: Flat $5,000 allocation per asset
        self.flat_allocation_usd = 5000.00

    def calculate_shares(self, current_price):
        """Whole shares that fit within the flat allocation. Broker-native stop
        orders cannot attach to fractional qty, so we floor to an integer."""
        if current_price is None or current_price <= 0:
            return 0
        return int(self.flat_allocation_usd // current_price)

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