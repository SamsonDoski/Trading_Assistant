from datetime import datetime, timedelta
from utils.alpaca_data import fetch_data
from strategies.ma_rsi_combo import apply_combo_strategy


class StrategyScanner:
    """Signal math for one ticker. Takes a resolved ModeSettings so every
    strategy parameter is mode-driven — the scanner holds no policy of its own."""

    def get_signals(self, ticker, settings):
        # Calendar buffer: enough history to warm up the long MA.
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now()
                      - timedelta(days=(settings.ma_long * 2) + 365)).strftime("%Y-%m-%d")

        df = fetch_data(ticker, start_date, end_date)
        if df.empty:
            return None

        df_signal = apply_combo_strategy(
            df,
            short_window=settings.ma_short,
            long_window=settings.ma_long,
            rsi_window=settings.rsi_window,
            rsi_buy_threshold=settings.rsi_buy_threshold,
            sell_on_overbought=settings.sell_on_overbought,
            rsi_sell_threshold=settings.rsi_sell_threshold,
            stop_loss_pct=settings.signal_stop_loss_pct,
        )

        # -2 is the last COMPLETED bar; -3 is the one before it.
        return {
            "latest_signal": df_signal.iloc[-2]["Signal"],
            "previous_signal": df_signal.iloc[-3]["Signal"],
            "current_price": df_signal.iloc[-2]["Close"],
            "current_rsi": df_signal.iloc[-2]["RSI"],
            # previous_rsi lets multi-entry modes require RSI TURNING UP (buy the
            # bounce, not the descent).
            "previous_rsi": df_signal.iloc[-3]["RSI"],
        }