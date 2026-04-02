import os
from dotenv import load_dotenv
from alpaca.data.requests import StockLatestQuoteRequest
from alpaca.data.historical import StockHistoricalDataClient

load_dotenv()
data_client = StockHistoricalDataClient(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"))

# Request latest price for Nvidia
request_params = StockLatestQuoteRequest(symbol_or_symbols="NVDA")
latest_quote = data_client.get_stock_latest_quote(request_params)

price = latest_quote["NVDA"].ask_price
print(f"📈 Current Ask Price for NVDA: ${price}")