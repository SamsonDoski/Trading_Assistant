# Trading_Assistant
This trading assistant tests and compares moving average crossover strategies across multiple tickers, ranking them by risk‑adjusted performance. It identifies the best MA pair for each stock, simulates weighted portfolios, and guides capital allocation—helping traders build profitable, resilient systems ready for real‑world deployment. 

---

# **Risk‑Adjusted Multi‑Ticker MA Strategy Engine**  

A modular, Python‑based backtesting and portfolio simulation framework for **moving average crossover strategies**.  
It evaluates both **fast‑reacting MA pairs** (e.g., 7/30) and **slow trend filters** (e.g., 50/200) to determine **per‑ticker strategy fit**, ranks them by **risk‑adjusted performance**, and simulates weighted portfolios for **survivability and scalability**.

---

## 🚀 **Features**
- **Custom MA Pair Testing** — Compare short‑term vs long‑term crossovers per ticker  
- **Risk Metrics** — Total Return, Max Drawdown, Win Rate, Risk‑Adjusted Score (Return ÷ |Max DD|)  
- **Ticker Personality Mapping** — Match strategy style to each stock’s behavior  
- **Portfolio Simulation** — Combine weighted equity curves, measure diversification and combined drawdown  
- **Forward‑Test Ready** — Modular design for integration with live data feeds and automation

---

## 📂 **Repository Structure**

```
src/
  backtest_engine.py       # Core MA crossover backtest logic, trade simulation, P/L tracking
  strategy_config.py       # Stores MA parameters, risk settings, ticker-strategy mapping
  portfolio_simulator.py   # Combines per-ticker equity curves into weighted portfolio results
  risk_metrics.py          # Functions for drawdown, Sharpe ratio, risk-adjusted scoring
  data_loader.py           # Fetches, validates, and caches historical OHLCV data

notebooks/
  strategy_comparison.ipynb # Exploratory analysis, visualizations, parameter testing

data/
  historical_prices/        # CSVs of raw or cleaned price data per ticker

results/
  equity_curves/            # PNG/CSV equity curves per strategy/ticker
  summary_tables/           # CSV/Markdown backtest summaries
  portfolio_simulation.csv  # Combined portfolio equity curve and stats

README.md                   # Project overview, usage instructions
requirements.txt            # Python dependencies
.gitignore                  # Files/folders excluded from version control
```

---

## 📊 **Example Workflow**
1. Define MA pairs and tickers in `strategy_config.py`  
2. Run `backtest_engine.py` to generate per‑ticker results  
3. Use `risk_metrics.py` to calculate risk‑adjusted scores  
4. Feed results into `portfolio_simulator.py` for combined performance  
5. Review outputs in `/results` and visualize in `/notebooks`

---

## 🧭 **Vision**
This engine is built for traders who want **clarity, survivability, and adaptability** — turning raw backtest data into a **deployable, risk‑aware trading plan**.

---

