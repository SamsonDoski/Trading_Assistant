# Software Requirements Specification (SRS)
## Project: Trading Assistant V4.0 (Sentiment-Driven Dynamic Sizing)

### 1. Objective
Upgrade the `PortfolioAllocator` from a static, flat-budget sizing model (e.g., $5,000 per trade) to a dynamic, sentiment-weighted model. Position sizes will scale up or down based on real-time news sentiment scores, while still strictly respecting the `buying_power` constraints introduced in V3.1.

### 2. Architecture Additions
To maintain high cohesion and low coupling, sentiment analysis will be isolated into its own micro-module.

* **New Module:** `engine/sentiment.py` (The Ear)
* **Modified Module:** `engine/allocator.py` (The Calculator)
* **Modified Module:** `live_controller.py` (The Orchestrator)

---

### 3. Execution Roadmap

#### Phase 1: The Sentiment Engine (`engine/sentiment.py`)
Build a dedicated module to fetch and score recent news headlines for a specific ticker.
* **Data Source:** Utilize the Alpaca News API (already accessible via your existing Alpaca credentials) to pull the top 5-10 headlines from the past 24 hours.
* **NLP Scoring:** Implement a lightweight sentiment analyzer (e.g., `nltk.sentiment.vader`) to avoid bloating the AWS Lambda deployment package. 
* **Output:** The module will return a normalized `sentiment_multiplier` ranging from `0.5` (Highly Bearish/Cautious) to `1.5` (Highly Bullish/Aggressive). Neutral news defaults to `1.0`.

#### Phase 2: The Dynamic Allocator (`engine/allocator.py`)
Refactor the allocator to ingest the `sentiment_multiplier`.
* **The Math:** `target_budget = base_allocation * sentiment_multiplier`
* **Example A (Bullish):** NVDA has a 1.5x sentiment score. The allocator targets $7,500 instead of $5,000.
* **Example B (Bearish):** TSLA has a 0.5x sentiment score (e.g., bad earnings call). The allocator targets only $2,500, reducing risk exposure.
* **Safety Guard:** The final output must still be capped by `buying_power` and converted to whole shares via floor division `//`.

#### Phase 3: Controller Wiring (`live_controller.py`)
Inject the new micro-module into the True Controller's state machine.
* **Step Order:**
    1. Check if profile is stale.
    2. Ask `scanner.py` for the technical signal (1 or 0).
    3. *NEW:* If the signal is 1 (Buy), ask `sentiment.py` for the multiplier.
    4. Pass the multiplier and `buying_power` to `allocator.py` for the final share count.
    5. Execute the trade.

#### Phase 4: CI/CD & Cloud Infrastructure
* **Dependency Management:** Add the chosen NLP library (e.g., `nltk` or `textblob`) to `requirements.txt`.
* **Lambda Layer Rebuild:** Because we are adding new libraries, the GitHub Actions `.github/workflows/deploy.yml` pipeline will automatically package these into the deployment zip. 
* **Timeout Check:** Monitor the AWS execution time. Fetching news and running NLP processing will add milliseconds to each ticker's loop. Ensure it stays safely under the 3-minute limit.

---

### 4. Known Risks & Edge Cases
1.  **News API Throttling:** Alpaca's News API has rate limits. We may need to cache requests or add a slight `time.sleep()` if pulling data for 30+ tickers.
2.  **Sarcasm & False Positives:** Lightweight NLP models struggle with financial jargon (e.g., "Apple slashes iPhone prices" might read as negative sentiment to a bot, but bullish for sales volume). 
3.  **No News Fallback:** If a smaller ticker has no news in the last 24 hours, the `sentiment.py` module must safely catch the empty array and return a default `1.0` multiplier so the trade still executes at baseline size.