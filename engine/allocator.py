class PortfolioAllocator:
    def __init__(self):
        # Retaining V3.0 Legacy Logic: Flat $5,000 allocation per asset
        self.flat_allocation_usd = 5000.00

    def calculate_shares(self, current_price):
        """Fractional shares needed to hit the flat allocation for one ticker."""
        if current_price is None or current_price <= 0:
            return 0.0
        return round(self.flat_allocation_usd / current_price, 9)

    def generate_buy_orders(self, approved_signals, current_prices):
        """
        Takes a list of tickers with a '1.0' Buy signal and calculates
        the exact fractional share count needed to hit the target allocation.
        """
        orders = {}
        for ticker in approved_signals:
            if ticker in current_prices and current_prices[ticker] > 0:
                orders[ticker] = self.calculate_shares(current_prices[ticker])
        return orders