class PortfolioAllocator:
    def __init__(self):
        # Retaining V3.0 Legacy Logic: Flat $5,000 allocation per asset
        self.flat_allocation_usd = 5000.00 

    def generate_buy_orders(self, approved_signals, current_prices):
        """
        Takes a list of tickers with a '1.0' Buy signal and calculates 
        the exact fractional share count needed to hit the target allocation.
        """
        orders = {}
        
        for ticker in approved_signals:
            if ticker in current_prices and current_prices[ticker] > 0:
                # Calculate fractional shares for Alpaca
                raw_shares = self.flat_allocation_usd / current_prices[ticker]
                # Rounding to 9 decimal places as per standard Alpaca fractional limits
                orders[ticker] = round(raw_shares, 9) 
                
        return orders