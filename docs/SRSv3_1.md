# Software Requirements Specification (SRS) - Trading Assistant V3.1

**Project:** Autonomous Quantitative Trading Pipeline
**Branch:** OlajideCode / mainV3.1 (Optimization & Hardening)
**Primary Focus:** Architectural Modularization and Execution Reliability (AWS Migration)
**Brokerage Integration:** [Alpaca API](https://app.alpaca.markets/dashboard/overview) (Paper Trading Validation)

---

## 1. Introduction

### 1.1 Purpose
The purpose of V3.1 is to upgrade the V3.0 pipeline's infrastructure. While V3.0 successfully automated the core MA/RSI logic, it relies on a "God Object" architecture (`live_controller.py`) and experiences unpredictable execution latency via GitHub Actions runners. V3.1 strictly decouples the system into single-responsibility modules and migrates the execution environment to AWS Serverless.

### 1.2 System Scope
The V3.1 upgrade is a **pure infrastructure and structural deployment**. It focuses strictly on two major architectural shifts:
1. **System Modularization:** Decoupling logic into Allocator (Math), Executioner (API), and Handler (Scheduler) modules.
2. **Infrastructure Migration:** Moving the pipeline from GitHub Actions to AWS Lambda + EventBridge for zero-delay order routing.

*(Note: Advanced quantitative upgrades—including Dynamic Position Sizing, Synthetic Trailing Stops, and Global Macro Index Overrides—are explicitly deferred to V4.0 to ensure infrastructure stability during the AWS migration.)*

---

## 2. Architectural Modularization

To ensure maintainability and isolate failures, the monolithic `live_controller.py` is deprecated and replaced by three distinct components.

### 2.1 The Entry Point (`aws/lambda_handler.py`)
- **Responsibility:** Acts solely as the execution manager.
- **Logic:** Initializes secure AWS environment variables, queries the Allocator for share sizes, and passes those variables to the Executioner. It contains zero calculation or API routing logic itself.

### 2.2 The Math Engine (`engine/allocator.py`)
- **Responsibility:** Handles portfolio math and position sizing parameters.
- **Logic:** Takes the list of approved "Buy" signals from the strategy switchboard and applies the legacy V3.0 sizing logic (calculating the exact number of shares required to allocate a flat $5,000 cost basis per ticker). 

### 2.3 The API Interface (`engine/executioner.py`)
- **Responsibility:** Strictly handles Alpaca API communications.
- **Logic:** Accepts the payload dictionary from the Allocator and loops through it, authenticating with the broker and submitting standard Market Buy/Sell orders. 

---

## 3. Infrastructure: The AWS Serverless Migration

### 3.1 The Latency Resolution
GitHub Actions utilizes shared runners, resulting in unpredictable queue delays during high-volume market hours. V3.1 resolves this by hosting the Python environment natively on AWS Lambda.

### 3.2 Execution Protocol
- **Trigger:** AWS EventBridge replaces the `.yml` cron file, utilizing precise UTC cron syntax to execute precisely at market open and close.
- **Environment:** The Lambda function utilizes a custom `.zip` dependency layer containing `pandas` and the `alpaca-trade-api` SDK to eliminate cold-boot installation delays.

---

## 4. Algorithmic Logic (Retained from V3.0)

To ensure accurate debugging of the new AWS infrastructure, the core mathematical logic remains completely unchanged from V3.0.

### 4.1 Capital Allocation
- **Mechanism:** The system retains a flat allocation model. Every approved asset will be assigned exactly **$5,000** of buying power, regardless of historical drawdown or volatility profiles.

### 4.2 Structural Exits
- **Mechanism:** The system retains the primary Moving Average Reverse Trend logic. A position will be passively held and only liquidated when the short-term MA officially crosses below the long-term MA, generating a `0.0` signal.

---

## 5. Implementation Roadmap

1. **Phase 1 (Module Build):** Write `allocator.py` and `executioner.py` locally, porting the existing V3.0 logic into the new isolated class structures.
2. **Phase 2 (AWS Pipeline):** Wrap the pipeline in `lambda_handler.py`, compile the Python dependency layer, and deploy the architecture to AWS Lambda.
3. **Phase 3 (Live Paper Test):** Disable the GitHub Actions schedule and run the new AWS architecture on the Alpaca paper environment. The success metric is verifying that the bot executes the flat $5k allocations instantly without timeout errors.
2. **Phase 2 (AWS Pipeline):** Wrap the pipeline in `lambda_handler.py`, compile the Python dependency layer, and deploy to AWS Lambda.
3. **Phase 3 (Live Paper Test):** Disable the GitHub Actions schedule and run the new AWS architecture on the Alpaca paper environment to validate the exact-minute execution and dynamic share counts.
