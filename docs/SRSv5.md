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

Backward compatibility is the ship-dark safety anchor, not the destination.
`ACTIVE_MODE = "Swing"` reproduces current V4.0 behavior exactly — same behavior
flags, inheriting each ticker's legacy free-optimized windows — so V5.0 deploys
with zero behavioral change and is proven regression-free before any flip.

But V4.0 is itself an incoherent hybrid: it applies ONE uniform swing-like
behavior (15% trailing stop, single entry, exit-on-reversal) to per-ticker
windows that actually span aggressive (CRWV 5/10) to long-term (QQQ 50/350)
families. So a long-trend name gets a swing stop that can shake it out of the
very trend its slow windows were chosen to ride — entry timeframe and exit
timeframe disagree.

The intended production end-state is `ACTIVE_MODE = "Auto"`, where the research
layer assigns each ticker a COHERENT mode (matching window family AND behavior),
resolving that mismatch. Migration path: ship dark on Swing (prove no
regression) -> per-mode research (Phase 4) -> flip to Auto (coherent per-ticker
modes). Swing is the checkpoint; Auto is the goal.

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


### 3. Execution Roadmap
Each phase is an independently mergeable, tested increment. Phases 1–2 are pure
additions (no behavior change). Phase 3 is the cutover. No mode other than Swing
reaches production until Phase 6.

**Phase 1 — Mode definitions (`engine/modes.py`)**
* `ModeSettings` frozen dataclass + `TRADING_MODES` (Aggressive/Swing/Long_Term/
  Volatile) + `ModeResolver`. Wired to nothing.
* Gate: `test_swing_matches_v4_behavior` passes; existing suite and live behavior unchanged.

**Phase 2 — Strategy honors mode thresholds (`strategies/ma_rsi_combo.py`)**
* Replace hardcoded `RSI < 55` with `rsi_buy_threshold`; add optional
  `sell_on_overbought` / `rsi_sell_threshold`.
* Defaults preserve current behavior (55, overbought off).
* Gate: regression test proves identical signals under Swing defaults.

**Phase 3 — Settings threaded through the pipeline (CUTOVER)**
* Controller / executioner / allocator read a resolved `ModeSettings` instead of
  importing config constants (`TRAILING_STOP_PERCENT`, `CASH_RESERVE_PCT`,
  sentiment, conviction band); honor `exit_on_trend_reversal` and
  `allow_multi_entry` (RSI-recovery trigger + cooldown). Add `config.ACTIVE_MODE`
  (Lambda env var).
* Gate: with `ACTIVE_MODE="Swing"`, every existing controller test passes
  unchanged. On green, `mainV5.0` becomes the default branch.

**Phase 4 — Per-mode research + schema (`research/run_optimizer.py`, `researcher.py`)**
* Grid search scoped to each mode's window family; `select_best_mode` ranks all
  four by risk-adjusted return.
* Extend `stock_profile.json` with `best_mode` + `best_windows[mode]` (additive,
  backward-compatible); migrate legacy flat windows into `best_windows["Swing"]`.
* Gate: research populates a coherent best mode + windows per ticker.

**Phase 5 — Auto mode**
* Resolver consumes `best_mode` / `best_windows`; retire the transitional
  legacy-window bridge in `_resolve_windows`.
* Gate: Auto resolves each ticker to its researched mode.

**Phase 6 — Validation (backtest each mode) — HARD GATE**
* Extend the backtest harness to score each mode and Auto vs buy-and-hold, with
  max-drawdown and Sharpe, including a bear sub-window.
* Gate: no mode is promoted to production until it clears this. Machinery may
  ship on Swing before Phase 6; non-Swing modes may not.

**Phase 7 — Production flip**
* Set `ACTIVE_MODE="Auto"` (or a chosen mode) via env var. Instant rollback =
  `"Swing"`.

### 4. The Mode Contract
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

### 5. Per-Mode Research (Grid Search)
The optimizer's grid search is scoped to each mode's window family, so a mode is tuned
only within its own regime:

* Aggressive:  short {5, 8, 10, 12} x long {20, 25, 30, 40}
* Swing:       short {15, 20, 25}   x long {40, 50, 60}
* Long_Term:   short {40, 50, 60}   x long {150, 200, 250}
* Volatile:    short {10, 15, 20}   x long {35, 40, 50}

`research_cycle(ticker, mode)` grid-searches that mode's space and stores the best params.
`select_best_mode(ticker)` runs all four, ranks by the chosen metric (risk-adjusted return),
and records `best_mode` + its params. `Auto` consumes that record.

### 6. Algorithmic Logic Changes
* Buy threshold is now `rsi_buy_threshold` (was hardcoded 55) — modes finally differ on entry depth.
* `exit_on_trend_reversal` gates the MA cross-down sell (true for all shipped modes; the flag
  exists so a future pure-hold mode can set it false).
* `allow_multi_entry` (Aggressive/Volatile) permits re-entry on an RSI **recovery** dip
  (RSI below threshold AND turning up), subject to `reentry_cooldown_days`. Buys the bounce,
  not the descent — never a naive "RSI below X" descent buy.
* Long_Term: exit only on 50/200 reversal, no trailing or hard stop — rides drawdowns.
* Stops consolidated: `trailing_stop_percent` is the single exit-protection; the legacy
  signal-level `stop_loss_pct` in the combo is retired.

### 7. Testing Requirements (mocked; extends the existing offline suite)
* `modes.py`: resolver returns the correct bundle per mode; `Auto` reads the stored best mode
  and falls back to Swing when absent; unknown mode defaults to Swing.
* `ma_rsi_combo`: buys at `rsi_buy_threshold` not 55; `sell_on_overbought` triggers only when enabled.
* `live_controller`: `exit_on_trend_reversal=false` suppresses the MA-cross sell; multi-entry
  fires only on RSI recovery and respects the cooldown; settings thread through to sizing/stop.
* `research`: per-mode grid search stays within its window family; `select_best_mode` records a winner.
* Regression: `ACTIVE_MODE="Swing"` reproduces V4.0 numbers on the existing controller tests.

### 8. Known Risks & Edge Cases
1. Behavior divergence: modes must stay parameter+flag bundles; deep per-mode code forks would
   erode the state machine. New behaviors must be flag-gated.
2. Schema drift: `stock_profile.json` gains fields; missing fields must fall back gracefully
   (Swing + existing windows), so old profiles keep working.
3. Unvalidated modes: each mode must be backtested before being flipped live (Phase 6 gate).
   A selectable preset is not a proven strategy.
4. Multi-entry knife-catching: mitigated by the recovery trigger + cooldown; still the highest-risk flag.
5. Long_Term with no stop: a genuine reversal that never death-crosses could ride a large drawdown.
   This is intentional (position trading), but must be a conscious user choice.

### 9. Migration & Rollback
Ships behind `ACTIVE_MODE="Swing"` (== V4.0). Rollback at any point = set `ACTIVE_MODE="Swing"`
(no redeploy if it is an env var) or revert the merge. Schema changes are additive and
backward-compatible.

### 10. Deferred
Portfolio risk layer (kill switch, daily-loss circuit breaker) remains separate and pending.
Walk-forward validation of the per-mode grids. Per-mode sentiment prompt tuning.
