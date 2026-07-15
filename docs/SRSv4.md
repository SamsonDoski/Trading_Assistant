# Software Requirements Specification (SRS)
## Project: Trading Assistant V4.0 (Sentiment-Driven Dynamic Sizing)

### 1. Objective
Upgrade the `PortfolioAllocator` from a static, flat-budget model ($5,000/trade) to a dynamic, **AI-sentiment-weighted** model. When a fresh buy signal fires, the bot scores recent news for that ticker with **Claude Haiku** and scales the position size up or down by the resulting multiplier — while still strictly respecting the `buying_power` and whole-share constraints introduced in V3.1. Catastrophic news can veto a buy outright.

Claude Haiku is chosen over classical NLP (VADER/FinBERT) deliberately: lexicon models misread financial phrasing ("Apple slashes prices" reads bearish to them but is bullish for volume), and FinBERT is too large for the Lambda layer. Haiku understands financial context, is fast and cheap, and — because scoring runs only on buy candidates (0–2 tickers/run) — costs pennies per month.

### 2. Architecture Additions
Sentiment is isolated into its own single-responsibility micro-module, consistent with the V3.1 decoupled design.

* **New Module:** `engine/sentiment.py` (The Analyst) — fetches news + calls Claude Haiku, returns a structured verdict.
* **Modified Module:** `engine/allocator.py` (The Calculator) — accepts a sentiment multiplier.
* **Modified Module:** `live_controller.py` (The Orchestrator) — invokes sentiment only on fresh buys, applies veto + sizing.
* **External dependency:** Anthropic API (Claude Haiku) + Alpaca News API (both keyed by existing credentials / a new `ANTHROPIC_API_KEY`).

---

### 3. Execution Roadmap

#### Phase 1: The Sentiment Engine (`engine/sentiment.py`)
`SentimentAnalyzer.get_verdict(ticker)` returns a structured object; it must **never raise** into the trade loop.

* **Data Source:** Alpaca News API (alpaca-py `NewsClient`) — pull the top ~5–10 headlines from the past 24 hours for the ticker.
* **Scoring model:** **Claude Haiku 4.5**, model ID `claude-haiku-4-5`, via the official `anthropic` Python SDK. Use structured outputs (`client.messages.parse(...)`) so the response validates against a fixed schema:
    * `sentiment_multiplier` — float in `[0.5, 1.5]` (0.5 = bearish/cautious, 1.0 = neutral, 1.5 = bullish/aggressive).
    * `veto` — bool; `true` only for disqualifying news (fraud, bankruptcy, SEC action, major litigation, going-concern doubt).
    * `rationale` — one-line explanation (for the Discord log).
* **No-news / failure fallback:** if there are no headlines, the news API errors, or the Anthropic call fails/times out, return a **safe default** (`multiplier = 1.0`, `veto = False`) so the trade proceeds at baseline size. The sentiment layer is advisory — it must degrade gracefully, exactly like the notifier.
* **Auth:** reads `ANTHROPIC_API_KEY` from the environment (a Lambda env var; the SDK picks it up automatically).

#### Phase 2: The Dynamic Allocator (`engine/allocator.py`)
Extend `calculate_shares` to accept the multiplier (default `1.0`, preserving current behavior for any other caller).
* **The Math:** `target_budget = min(base_allocation * multiplier, buying_power)`
    * **Bullish (1.5×):** NVDA targets $7,500 instead of $5,000.
    * **Bearish (0.5×):** TSLA targets only $2,500 — reduced risk exposure.
* **Safety guards (unchanged):** cap at `buying_power`, floor to whole shares via `//`, return `0` if even one share is unaffordable.

#### Phase 3: Controller Wiring (`live_controller.py`)
Inject sentiment **only at the point of a fresh buy** — not for every `signal == 1` (that includes ~11 held positions and would waste news/LLM calls). Step order inside the buy branch (`latest == 1 and previous == 0 and not holding`):
1. Ask `sentiment.py` for the verdict.
2. If `veto` → skip the trade, log `⛔ VETO: <ticker> — <rationale>`.
3. Else `qty = allocator.calculate_shares(price, budget, multiplier)`.
4. If `qty > 0` → buy, decrement running budget, log the multiplier + rationale.
5. Else → skip (insufficient buying power).

This scoping keeps the News/Anthropic call count to the number of *actual* buy triggers per run (typically 0–2), which is what makes the cost and latency negligible.

#### Phase 4: CI/CD & Cloud Infrastructure
> ⚠️ Correction from prior draft: the GitHub Actions `deploy.yml` pipeline packages **code only** — it does **not** bundle dependencies. New libraries do not reach Lambda automatically.

* **Dependency management:** add `anthropic` to **`requirements-lambda.txt`** (the layer manifest), not just `requirements.txt`. The `anthropic` SDK is pure-Python and small (`pydantic` is already in the layer), so layer-size impact is modest.
* **Layer rebuild (manual):** rebuild the dependency layer (`pip install -r requirements-lambda.txt --target lambda_layer/python …`), upload to S3, `publish-layer-version`, and `update-function-configuration --layers <new arn>`. Only *then* does `anthropic` exist at runtime.
* **Secrets:** add `ANTHROPIC_API_KEY` as a **Lambda environment variable** (and to GitHub secrets only if CI ever needs it).
* **Timeout / cost check:** each buy-candidate adds one news fetch (~0.5s) + one Haiku call (~1–2s). At 0–2 candidates/run this is a few seconds, well under the 300s timeout. Cost per scored ticker ≈ 0.1¢ (Haiku 4.5: $1/1M input, $5/1M output; ~1K input + ~50 output tokens). Monthly cost: pennies.

---

### 4. Algorithmic Logic (Retained from V3.1)
The MA/RSI combo signal, the buying-power-aware sizing, whole-share orders, broker-side trailing stops, and stop-out detection all carry over unchanged. Sentiment modifies **only the entry size / veto** — it does not alter signals or exits.

---

### 5. Testing Requirements
Consistent with the existing 52-test offline suite and CI deploy gate, V4.0 ships with mocked tests (no live Anthropic/Alpaca calls):
* **`sentiment.py`:** mock the news client and the Anthropic client. Assert the happy path returns a valid multiplier/veto, and that **every failure mode** (no headlines, news error, Anthropic error) returns the safe default `(1.0, veto=False)`.
* **`allocator.py`:** assert `target = base × multiplier` capped by buying power (1.5→$7,500, 0.5→$2,500) and that the whole-share floor + buying-power cap still hold.
* **`live_controller.py`:** assert sentiment is invoked **only** on a fresh buy (not on holds), that `veto=True` skips the trade, and that the multiplier flows into sizing.

---

### 6. Known Risks & Edge Cases
1. **No news fallback:** smaller tickers may have zero recent headlines — `sentiment.py` must catch the empty result and return `1.0` so the trade executes at baseline size.
2. **External-API failure:** the Anthropic or News API can be down or rate-limited. Sentiment failure must **never block trading** — default to neutral and log a warning.
3. **Latency/cost creep:** scoping to fresh buys keeps this bounded. If entry frequency ever spikes, consider caching a ticker's daily verdict.
4. **Model misjudgment:** Haiku is strong on financial context but not infallible. The `[0.5, 1.5]` band caps downside/upside distortion, and `veto` is reserved for clearly disqualifying events.
5. **Concentration risk (deferred to portfolio risk layer):** sizing *up* to 1.5× with no portfolio-level cap can over-concentrate a single high-sentiment name. V4.0 does not bound this; the pending risk layer (max % per position / max concurrent positions) should.

---

### 7. Deferred
Portfolio-level risk (max positions, daily-loss circuit breaker, kill switch), walk-forward validation of MA parameters, and ATR/volatility sizing remain out of scope for V4.0. 