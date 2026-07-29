# Software Requirements Specification (SRS)
## Project: Trading Assistant V5.0 (Configurable Trading Modes)

### 1. Objective
Introduce user-selectable **trading modes** — coherent bundles of signal parameters
and behavior flags (Aggressive, Swing, Long_Term, Volatile) — plus an **Auto** mode
in which the research layer selects the best-performing mode per ticker. One selection
reshapes the entire pipeline's decisions: entries, exits, stops, sizing, and sentiment.

This extends the existing config-driven design (the V1 `strategy_config.PROFILES` seed)
into a wired, full-behavior system, and preserves the V3.1 decoupled architecture. The
core mechanism is dependency injection: modules read a single resolved **settings object**
instead of importing hardcoded constants.

Backward compatibility is a hard requirement: `ACTIVE_MODE = "Swing"` must reproduce
current V4.0 behavior exactly, so V5.0 can ship dark and be validated before any mode flip.

### 2. Architecture Additions / Changes
* **New:** `engine/modes.py` — `TRADING_MODES` definitions + `ModeResolver` (resolves the
  active settings for a given ticker, handling the `Auto` per-ticker lookup).
* **Modified:** `config.py` — `ACTIVE_MODE` selector (a mode name or `"Auto"`).
* **Modified:** `strategies/ma_rsi_combo.py` — use `rsi_buy_threshold` (retire hardcoded 55);
  honor `sell_on_overbought` + `rsi_sell_threshold`.
* **Modified:** `live_controller.py` — thread the resolved settings; honor
  `exit_on_trend_reversal` and `allow_multi_entry`; pass stop/sizing/sentiment settings down.
* **Modified:** `engine/executioner.py` — trailing-stop width from settings, including
  `None` (no stop) for Long_Term.
* **Modified:** `engine/allocator.py` — conviction band, cash reserve, fractional flag from settings.
* **Modified:** `research/run_optimizer.py` + `research/researcher.py` — per-mode grid search
  and best-mode selection; extend `stock_profile.json` schema with per-ticker best mode + params.

### 3. The Mode Contract
Each mode is a bundle of the following fields.

**Entry:** `ma_short`, `ma_long`, `rsi_window`, `rsi_buy_threshold`,
`allow_multi_entry`, `reentry_cooldown_days`
**Exit:** `exit_on_trend_reversal`, `trailing_stop_percent` (nullable),
`sell_on_overbought`, `rsi_sell_threshold`
**Sizing/capital:** `sentiment_enabled`, `conviction_min`, `conviction_max`,
`cash_reserve_pct`, `allow_fractional`

| Field | Aggressive | Swing | Long_Term | Volatile |
|---|---|---|---|---|
| ma_short / ma_long | 10 / 30 | 20 / 50 | 50 / 200 | 15 / 40 |
| rsi_window | 10 | 14 | 14 | 14 |
| rsi_buy_threshold | 55 | 55 | 40 | 45 |
| allow_multi_entry | true | false | false | true |
| reentry_cooldown_days | 2 | 0 | 0 | 3 |
| exit_on_trend_reversal | true | true | true | true |
| trailing_stop_percent | 6 | 15 | null (none) | 18 |
| sell_on_overbought | true | false | false | false |
| rsi_sell_threshold | 80 | — | — | — |
| sentiment_enabled | true | true | false | true |
| conviction_min / max | 0.5 / 1.8 | 0.5 / 1.5 | 1.0 / 1.0 | 0.5 / 1.5 |
| cash_reserve_pct | 0.10 | 0.15 | 0.05 | 0.20 |
| allow_fractional | true | true | true | true |

**Auto** is not a fixed bundle — it is a resolution directive: for each ticker, use the
mode and optimized parameters the research layer stored as best in `stock_profile.json`.
Requires Phase 4 to have run; falls back to `Swing` for any ticker without a stored best mode.

### 4. Per-Mode Research (Grid Search)
The optimizer's grid search is scoped to each mode's window family, so a mode is tuned
only within its own regime:

* Aggressive:  short {5, 8, 10, 12} x long {20, 25, 30, 40}
* Swing:       short {15, 20, 25}   x long {40, 50, 60}
* Long_Term:   short {40, 50, 60}   x long {150, 200, 250}
* Volatile:    short {10, 15, 20}   x long {35, 40, 50}

`research_cycle(ticker, mode)` grid-searches that mode's space and stores the best params.
`select_best_mode(ticker)` runs all four, ranks by the chosen metric (risk-adjusted return),
and records `best_mode` + its params. `Auto` consumes that record.

### 5. Algorithmic Logic Changes
* Buy threshold is now `rsi_buy_threshold` (was hardcoded 55) — modes finally differ on entry depth.
* `exit_on_trend_reversal` gates the MA cross-down sell (true for all shipped modes; the flag
  exists so a future pure-hold mode can set it false).
* `allow_multi_entry` (Aggressive/Volatile) permits re-entry on an RSI **recovery** dip
  (RSI below threshold AND turning up), subject to `reentry_cooldown_days`. Buys the bounce,
  not the descent — never a naive "RSI below X" descent buy.
* Long_Term: exit only on 50/200 reversal, no trailing or hard stop — rides drawdowns.
* Stops consolidated: `trailing_stop_percent` is the single exit-protection; the legacy
  signal-level `stop_loss_pct` in the combo is retired.

### 6. Testing Requirements (mocked; extends the existing offline suite)
* `modes.py`: resolver returns the correct bundle per mode; `Auto` reads the stored best mode
  and falls back to Swing when absent; unknown mode defaults to Swing.
* `ma_rsi_combo`: buys at `rsi_buy_threshold` not 55; `sell_on_overbought` triggers only when enabled.
* `live_controller`: `exit_on_trend_reversal=false` suppresses the MA-cross sell; multi-entry
  fires only on RSI recovery and respects the cooldown; settings thread through to sizing/stop.
* `research`: per-mode grid search stays within its window family; `select_best_mode` records a winner.
* Regression: `ACTIVE_MODE="Swing"` reproduces V4.0 numbers on the existing controller tests.

### 7. Known Risks & Edge Cases
1. Behavior divergence: modes must stay parameter+flag bundles; deep per-mode code forks would
   erode the state machine. New behaviors must be flag-gated.
2. Schema drift: `stock_profile.json` gains fields; missing fields must fall back gracefully
   (Swing + existing windows), so old profiles keep working.
3. Unvalidated modes: each mode must be backtested before being flipped live (Phase 6 gate).
   A selectable preset is not a proven strategy.
4. Multi-entry knife-catching: mitigated by the recovery trigger + cooldown; still the highest-risk flag.
5. Long_Term with no stop: a genuine reversal that never death-crosses could ride a large drawdown.
   This is intentional (position trading), but must be a conscious user choice.

### 8. Migration & Rollback
Ships behind `ACTIVE_MODE="Swing"` (== V4.0). Rollback at any point = set `ACTIVE_MODE="Swing"`
(no redeploy if it is an env var) or revert the merge. Schema changes are additive and
backward-compatible.

### 9. Deferred
Portfolio risk layer (kill switch, daily-loss circuit breaker) remains separate and pending.
Walk-forward validation of the per-mode grids. Per-mode sentiment prompt tuning.
