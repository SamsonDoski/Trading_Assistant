import alpaca_trade_api as tradeapi

class AlpacaExecutioner:
    def __init__(self, api_key, secret_key, base_url):
        self.api = tradeapi.REST(api_key, secret_key, base_url, api_version='v2')

    def execute_market_buy(self, ticker, qty):
        """Submits a standard Market Buy order for the calculated fractional shares."""
        if qty <= 0:
            return
            
        try:
            self.api.submit_order(
                symbol=ticker,
                qty=qty,
                side='buy',
                type='market',
                time_in_force='day'
            )
            print(f"✅ Executed BUY for {qty} shares of {ticker}")
        except Exception as e:
            print(f"❌ Failed to execute BUY for {ticker}: {e}")
            
    def execute_market_sell(self, ticker, qty):
        """Liquidates a position entirely when the MA Reverse Trend is triggered."""
        if qty <= 0:
            return
            
        try:
            self.api.submit_order(
                symbol=ticker,
                qty=qty,
                side='sell',
                type='market',
                time_in_force='day'
            )
            print(f"🛑 Executed SELL (Liquidated) {ticker}")
        except Exception as e:
            print(f"❌ Failed to execute SELL for {ticker}: {e}")