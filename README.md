# 📈 Quantitative Trading Assistant & Backtest Engine

A modular, Python‑based quantitative backtesting and portfolio simulation framework. This engine tests algorithmic trading strategies (Moving Average Crossovers, RSI Momentum, and a Custom Combo Strategy), ranks them by risk‑adjusted performance, and simulates capital allocation across multi-asset portfolios.

## 🚀 Core Engine Features

* **Strategy Switchboard:** Hot-swap between `MA`, `RSI`, or the proprietary `Combo` strategy (which combines macro-trend filtering with momentum dip-buying).
* **Grid Search Optimizer:** An automated parameter-sweeping tool that tests dozens of indicator combinations to mathematically prove the highest-yielding, risk-adjusted parameters for any specific stock.
* **Multi-Ticker Portfolio Simulation:** Allocates capital across multiple assets, tracking global portfolio equity and drawdowns while employing a "Let Winners Run" philosophy (zero daily rebalancing drag).
* **Advanced Visualizer:** A dynamic 3-pane charting system built with Matplotlib that overlays precise algorithmic Buy/Sell markers on price action, plots RSI indicators, and graphs the exact Mark-to-Market Equity curve.
* **Vectorized Risk Management:** Employs pandas vectorization to calculate dynamic Stop-Losses and prevent portfolio wipeouts during market crashes.

---

## 🏆 Performance Showcase: The Power of Optimization

Using the built-in `optimizer.py`, we ran a 9-year historical sweep (2017-2026) on **$NVDA** to find the absolute perfect Moving Average pairing for the Combo Strategy. 

By upgrading from the standard Wall Street 50/200 Moving Average to the mathematically optimized **50/100 Moving Average**, the engine doubled its profitability:

* **Total Return:** +4,539.21%
* **Net Profit:** $4,539,206.93 *(on a $100k initial allocation)*
* **Max Drawdown:** -43.41%
* **Win Rate:** 36.00%

*Insight: The optimizer proved that for momentum stocks, traditional 200-day trend filters are too slow, causing the bot to miss the first massive leg of tech rallies.*

---

## 💻 How to Use the Engine

### 1. The Strategy Optimizer
Run a mathematical grid search to find the perfect MA pairs for a specific stock:
```
python run_optimizer.py --ticker nvda --start 2017-01-01 --end 2026-03-28
```

2. The Multi-Ticker Portfolio Simulator
Simulate a combined portfolio over years of historical data:

```
python run_portfolio.py --tickers pltr nvda msft --start 2023-01-01 --end 2026-03-28 --equity 10000.00 --profile Long_Term --strategy Combo
```

3. The Visualizer
Run a single stock backtest to generate the 3-pane visual audit chart:

```
python main.py --ticker aapl --start 2020-01-01 --end 2024-01-01 --strategy Combo
```

📂 Repository Structure

```
trading_assistant/
│
├── engine/
│   ├── backtest.py          # Core trade execution and P/L accounting
│   └── portfolio.py         # Multi-asset allocation and global equity tracking
│
├── strategies/
│   ├── moving_average.py    # Standard MA crossover logic
│   ├── rsi.py               # Deep oversold/overbought momentum logic
│   └── ma_rsi_combo.py      # The primary hybrid trend/momentum algorithm
│
├── utils/
│   ├── data_loader.py       # API fetching, caching, and data sanitization
│   └── visualize1.py        # 3-pane Matplotlib algorithmic charting
│
├── run_portfolio.py         # Entry point for portfolio simulations
├── run_optimizer.py         # Entry point for parameter grid search
├── main.py                  # Entry point for single-stock visual testing
└── strategy_config.py       # Global parameter settings and profiles
```


