# Software Requirements Specification (SRS) - Trading Assistant V3.1

**Project:** Autonomous Quantitative Trading Pipeline
**Branch:** OlajideCode / mainV3.1 (Optimization & Hardening)
**Primary Focus:** Architectural Modularization, Execution Reliability, and Dynamic Sizing
**Brokerage Integration:** Alpaca API (Transitioning to Live Readiness)

---

## 1. Introduction

### 1.1 Purpose
The purpose of V3.1 is to upgrade the V3.0 pipeline from a functional prototype to an institutional-grade trading system. While V3.0 successfully automated the MA/RSI logic, it suffered from a "God Object" architecture (`live_controller.py`) and relied on delayed GitHub Actions runners. V3.1 strictly decouples the system into single-responsibility modules, migrates the execution to AWS Serverless, and introduces quantitative position sizing.

### 1.2 System Scope
The V3.1 upgrade focuses strictly on three major architectural shifts:
1. **System Modularization:** Decoupling logic into Allocator (Math), Executioner (API), and Handler (Scheduler) modules.
2. **Infrastructure Migration:** Moving from GitHub Actions to AWS Lambda + EventBridge for zero-delay order routing.
3. **Dynamic Position Sizing:** Replacing static allocations with a quantitative composite score model.

*(Note: Advanced asymmetric exit logic and synthetic trailing stops are explicitly deferred to future builds.)*

---

## 2. Architectural Modularization

To ensure maintainability and isolate failures, the monolithic `live_controller.py` is deprecated and replaced by three distinct components.

### 2.1 The Entry Point (`aws/lambda_handler.py`)
- **Responsibility:** Acts solely as the execution manager.
- **Logic:** It initializes the secure environment variables, queries the Allocator for share sizes, and passes those sizes to the Executioner. It contains zero calculation or API routing logic itself.

### 2.2 The Math Engine (`engine/allocator.py`)
- **Responsibility:** Handles all portfolio math and dynamic position sizing.
- **Logic:** Takes the total Alpaca account equity and the list of approved "Buy" signals. It applies the ETF override weights (50%) and dynamically slices the remaining equity based on the MA/Drawdown composite scores, returning a clean dictionary of `{ticker: exact_share_count}`.

### 2.3 The API Interface (`engine/executioner.py`)
- **Responsibility:** Strictly handles Alpaca API communications and order formatting.
- **Logic:** Accepts the dictionary from the Allocator and loops through it, submitting orders to the broker. 

---

## 3. Infrastructure: The AWS Serverless Migration

### 3.1 The Latency Resolution
GitHub Actions utilizes shared runners, resulting in unpredictable queue delays. V3.1 solves this by hosting the `lambda_handler.py` on AWS Lambda.

### 3.2 Execution Protocol
- **Trigger:** AWS EventBridge replaces the GitHub Actions cron file, utilizing precise UTC cron syntax to execute precisely at market open and close.
- **Environment:** The Lambda function utilizes a custom `.zip` dependency layer containing `pandas` and the `alpaca-trade-api` SDK to run the Python environment natively without cold-boot delays.

---

## 4. Algorithmic Optimization: Dynamic Sizing

### 4.1 The Composite Risk Score
The `allocator.py` engine dynamically distributes capital using a hybrid model:
- **Formula:** `(Short MA / Long MA) * (1 / Abs(Max DD))`
- **Result:** Volatile assets are automatically starved of capital, while balanced "Sweet Spot" profiles receive heavy allocations.

### 4.2 Structural Exits (Retained from V3.0)
- **Mechanism:** The system will continue to rely strictly on the primary MA Reverse Trend logic for exits (e.g., selling only when the short MA crosses below the long MA).

---

## 5. Implementation Roadmap

1. **Phase 1 (Module Build):** Write `allocator.py` and `executioner.py` locally, ensuring all math and API logic is fully decoupled from the core controller.
2. **Phase 2 (AWS Pipeline):** Wrap the pipeline in `lambda_handler.py`, compile the Python dependency layer, and deploy to AWS Lambda.
3. **Phase 3 (Live Paper Test):** Disable the GitHub Actions schedule and run the new AWS architecture on the Alpaca paper environment to validate the exact-minute execution and dynamic share counts.