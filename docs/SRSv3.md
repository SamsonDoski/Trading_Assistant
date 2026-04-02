# Software Requirements Specification (SRS) - Trading Assistant V3.0

**Project:** Autonomous Quantitative Trading Pipeline  
**Branch:** mainV3.0  
**Primary Strategy Focus:** MA/RSI Combo Strategy  
**Brokerage Integration:** Alpaca API (Paper/Live)  

---

## 1. Introduction

### 1.1 Purpose
The purpose of V3.0 is to transition the Trading Assistant from a passive historical backtesting engine (V2.0) into a fully autonomous live-execution pipeline. V3.0 will automatically research stale strategies, optimize parameters, maintain a live brokerage watchlist, and execute precision trades based on dynamic risk sizing.

### 1.2 System Scope
The system will operate in four distinct lifecycle phases:
1. **State Management:** Tracking the "freshness" of quantitative parameters.
2. **Research & Optimization:** Re-calculating moving average combos for stale assets.
3. **Watchlist Syncing:** Pushing approved assets to the Alpaca brokerage.
4. **Live Execution:** Calculating exact share quantities and submitting market orders based on synchronized daily data.

---

## 2. System Architecture & Components

### 2.1 The Memory Bank (State Tracker)
* **Component:** `config/memory.json`
* **Responsibility:** Acts as the persistent brain of the bot, remembering when a stock was last optimized and what its unique best-performing parameters are.
* **Expiration Rule:** Any stock whose `last_optimized` date is older than 90 days (3 months) is flagged as "Stale."
* **Schema Example:**

```json
{
    "NVDA": {
        "last_optimized": "2026-04-02",
        "strategy": "Combo",
        "best_short_window": 50,
        "best_long_window": 100,
        "rsi_period": 14
    }
}
```

### 2.2 The Researcher (Optimization Automation)
* **Component:** `engine/researcher.py`
* **Responsibility:** Scans a master list of desired tickers against the Memory Bank.
* **Action:** If a ticker is unlisted or flagged as "Stale," the Researcher invokes the V2.0 Grid Search Optimizer.
* **Constraint:** The optimizer will specifically target the Combo Strategy to find the highest risk-adjusted MA pair over the past historical window.
* **Output:** Overwrites the entry in `config/memory.json` with the new optimal parameters and today's date.

### 2.3 The Watchlist Manager
* **Component:** `utils/alpaca_watchlist.py`
* **Responsibility:** Bridges the local pipeline with the Alpaca API environment.
* **Action:** Once a stock is successfully optimized and logged in the Memory Bank, it is pushed via API to an Alpaca Watchlist (e.g., `Combo_Optimized_V3`).
* **Benefit:** Keeps the brokerage environment perfectly synced with the local bot's approved trading universe.

### 2.4 The Executioner (Live Trader)
* **Component:** `live_controller.py`
* **Responsibility:** The core loop that triggers daily trading activity based on the custom parameters.
* **Data Fetching:** Pulls daily bars via Alpaca API (replacing `yfinance`).
* **Signal Generation:** Feeds the daily data and the custom `memory.json` parameters into the `ComboStrategy` class.
* **Position Checking:** Queries the Alpaca API to see if the bot already holds an active position in the stock.
* **Risk & Sizing Logic (Whole Shares):**
  * Determines the allocated risk capital (e.g., 5% of total account equity).
  * Calculates exact whole shares using floor division to prevent over-leveraging: `qty = math.floor(allocated_cash / current_price)`.
* **Order Execution:** Submits exact whole-share `MarketOrderRequest` payloads (Buy/Sell) to Alpaca.

---

## 3. Functional Requirements

### 3.1 Parameter Expiration & Refresh
| Req ID | Description |
| :--- | :--- |
| **REQ-3.1.1** | The system must read a JSON file to check the `last_optimized` date of a target ticker. |
| **REQ-3.1.2** | If the date delta is > 90 days, the system must trigger `run_optimizer.py` logic. |
| **REQ-3.1.3** | The system must update the JSON file with the new optimal values upon successful completion. |

### 3.2 Alpaca Watchlist Integration
| Req ID | Description |
| :--- | :--- |
| **REQ-3.2.1** | The system must create or append to an Alpaca Watchlist named `Combo_Optimized`. |
| **REQ-3.2.2** | The system must only trade stocks present in this specific Watchlist. |

### 3.3 Live Order Execution
| Req ID | Description |
| :--- | :--- |
| **REQ-3.3.1** | The system must calculate order size based on total account equity, not a fixed dollar amount. |
| **REQ-3.3.2** | The system must only purchase whole shares (no fractional orders). |
| **REQ-3.3.3** | The system must liquidate a position entirely if the Combo Strategy returns a 0 (Sell) signal and the asset is currently in the Alpaca portfolio. |

---

## 4. Non-Functional Requirements
* **Security:** API keys must never be hardcoded and must be loaded via a `.env` file using the `python-dotenv` library.
* **Environment Safety:** All trading must default to `paper=True` in the Alpaca `TradingClient` initialization until explicit manual override.
* **Data Integrity:** The live controller must use Alpaca's Market Data API for daily bars to avoid latency and multi-index issues previously encountered with Yahoo Finance.
* **Modularity:** The V3.0 pipeline must strictly adhere to the Information Expert and High Cohesion principles. Optimization logic must not bleed into Execution logic.

---

## 5. Implementation Roadmap
1. **Phase 1:** Build `config/memory.json` and the JSON read/write helper functions.
2. **Phase 2:** Write `researcher.py` to bridge the JSON state with your existing `optimizer.py`.
3. **Phase 3:** Write the Alpaca Watchlist syncing script.
4. **Phase 4:** Build the final `live_controller.py` that loops the watchlist, pulls custom parameters, calculates whole shares, and executes.
```
