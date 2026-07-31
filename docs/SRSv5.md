# Software Requirements Specification (SRS)
## Project: Trading Assistant V5.0 (Configurable Trading Modes)

### 1. Objective
Introduce user-selectable **trading modes** — coherent bundles of signal parameters
and behavior flags (V4_Legacy, Aggressive, Swing, Long_Term, Volatile) — plus an **Auto** mode
in which the research layer selects the best-performing mode per ticker. One selection
reshapes the entire pipeline's decisions: entries, exits, stops, sizing, and sentiment.

This extends the existing config-driven design (the V1 `strategy_config.PROFILES` seed)
into a wired, full-behavior system, and preserves the V3.1 decoupled architecture. The
core mechanism is dependency injection: modules read a single resolved **settings object**
instead of importing hardcoded constants.

Backward compatibility is the ship-dark safety anchor, not the destination.
`ACTIVE_MODE = "V4_Legacy"` reproduces current V4.0 behavior exactly — same
behavior flags, inheriting each ticker's legacy free-optimized windows — so V5.0
deploys with zero behavioral change and is proven regression-free before any flip.

**V4_Legacy is not a preset.** V4.0 free-searched windows per ticker over
{5..50} x {10..400}, a space no mode grid can reproduce, so V4_Legacy is DEFINED
as "whatever that legacy search chose": its MA windows and RSI period come from
the flat profile fields (`best_short_window` / `best_long_window` / `rsi_period`),
and it is deliberately excluded from `MODE_GRIDS` so per-mode research can never
write `best_windows["V4_Legacy"]` and shadow them. `Swing` is a genuine
swing-trading preset with its own researched grid, and is therefore NOT V4.0.

V4.0 is itself an incoherent hybrid: it applies ONE uniform swing-like
behavior (15% trailing stop, single entry, exit-on-reversal) to per-ticker
windows that actually span aggressive (CRWV 5/10) to long-term (QQQ 50/350)
families. So a long-trend name gets a swing stop that can shake it out of the
very trend its slow windows were chosen to ride — entry timeframe and exit
timeframe disagree.

The intended production end-state is `ACTIVE_MODE = "Auto"`, where the research
layer assigns each ticker a COHERENT mode (matching window family AND behavior),
resolving that mismatch. Migration path: ship dark on V4_Legacy (prove no
regression) -> per-mode research (Phase 4) -> flip to Auto (coherent per-ticker
modes). V4_Legacy is the checkpoint; Auto is the goal.

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
additions (no behavior change). Phase 3 is the cutover. No mode other than
V4_Legacy reaches production until Phase 6.

**Phase 1 — Mode definitions (`engine/modes.py`)**
* `ModeSettings` frozen dataclass + `TRADING_MODES` (V4_Legacy/Aggressive/Swing/
  Long_Term/Volatile) + `ModeResolver`. Wired to nothing.
* Gate: `test_v4_legacy_matches_v4_behavior` passes; existing suite and live
  behavior unchanged.

**Phase 2 — Strategy honors mode thresholds (`strategies/ma_rsi_combo.py`)**
* Replace hardcoded `RSI < 55` with `rsi_buy_threshold`; add optional
  `sell_on_overbought` / `rsi_sell_threshold`.
* Defaults preserve current behavior (55, overbought off).
* Gate: regression test proves identical signals under V4_Legacy defaults.

**Phase 3 — Settings threaded through the pipeline (CUTOVER)**
* Controller / executioner / allocator read a resolved `ModeSettings` instead of
  importing config constants (`TRAILING_STOP_PERCENT`, `CASH_RESERVE_PCT`,
  sentiment, conviction band); honor `exit_on_trend_reversal` and
  `allow_multi_entry` (RSI-recovery trigger + cooldown). Add `config.ACTIVE_MODE`
  (Lambda env var).
* Gate: with `ACTIVE_MODE="V4_Legacy"`, every existing controller test passes
  unchanged. On green, `mainV5.0` becomes the default branch.

**Phase 4 — Per-mode research + schema (`research/run_optimizer.py`, `researcher.py`)**
* Grid search scoped to each mode's window family (V4_Legacy excluded — it is not
  researched per-mode); `select_best_mode` ranks the four presets by risk-adjusted
  score over the standard optimization window.
* Extend `stock_profile.json` with `best_mode` + `best_windows[mode]` +
  `mode_scores` (additive, backward-compatible). The legacy flat window fields are
  left in place permanently — they are V4_Legacy's source of truth.
* Gate: research populates a best mode + windows per ticker.

**Phase 5 — Auto mode**
* Resolver consumes `best_mode` / `best_windows`. (The legacy-window bridge is
  NOT retired — it permanently defines V4_Legacy.)
* Gate: Auto resolves each ticker to its researched mode.

**Phase 6 — Validation — HARD GATE**
* Standalone comparison script (no live module changes): score **V4_Legacy**,
  **Auto**, and **buy-and-hold** over the same window and watchlist, reporting
  total return and max drawdown per config plus a per-ticker breakdown.
* Gate: no mode is promoted to production until it clears this. Machinery may
  ship on V4_Legacy before Phase 6; non-V4_Legacy modes may not.

**Phase 7 — Production flip**
* Set `ACTIVE_MODE="Auto"` (or a chosen mode) via env var. Instant rollback =
  `"V4_Legacy"`.

### 4. The Mode Contract
Each mode is a bundle of the following fields.

**Entry:** `ma_short`, `ma_long`, `rsi_window`, `rsi_buy_threshold`,
`allow_multi_entry`, `reentry_cooldown_days`
**Exit:** `exit_on_trend_reversal`, `trailing_stop_percent` (nullable),
`sell_on_overbought`, `rsi_sell_threshold`
**Sizing/capital:** `sentiment_enabled`, `conviction_min`, `conviction_max`,
`cash_reserve_pct`, `allow_fractional`

A sixth field, `signal_stop_loss_pct`, controls the combo's signal-level hard stop;
it is `None` for every preset (stops consolidated onto the broker trailing stop) and
`-0.15` for V4_Legacy only, where it preserves exact V4.0 behavior.

| Field | V4_Legacy | Aggressive | Swing | Long_Term | Volatile |
|---|---|---|---|---|---|
| ma_short / ma_long | from profile* | 10 / 30 | 20 / 50 | 50 / 200 | 15 / 40 |
| rsi_window | from profile* | 10 | 14 | 14 | 14 |
| rsi_buy_threshold | 55 | 55 | 55 | 40 | 45 |
| allow_multi_entry | false | true | false | false | true |
| reentry_cooldown_days | 0 | 2 | 0 | 0 | 3 |
| exit_on_trend_reversal | true | true | true | true | true |
| trailing_stop_percent | 15 | 6 | 15 | null (none) | 18 |
| sell_on_overbought | false | true | false | false | false |
| rsi_sell_threshold | 70 | 80 | — | — | — |
| signal_stop_loss_pct | -0.15 | null | null | null | null |
| sentiment_enabled | true | true | true | false | true |
| conviction_min / max | 0.5 / 1.5 | 0.5 / 1.8 | 0.5 / 1.5 | 1.0 / 1.0 | 0.5 / 1.5 |
| cash_reserve_pct | 0.15 | 0.10 | 0.15 | 0.05 | 0.20 |
| allow_fractional | true | true | true | true | true |

\* V4_Legacy reads `best_short_window` / `best_long_window` / `rsi_period` from the
ticker's flat profile fields; the values in its bundle are unused placeholders.

**Auto** is not a fixed bundle — it is a resolution directive: for each ticker, use the
mode and optimized parameters the research layer stored as best in `stock_profile.json`.
Requires Phase 4 to have run; falls back to `V4_Legacy` for any ticker without a stored
best mode.

**Account-level settings.** `cash_reserve_pct` cannot be per-ticker — one session budget
cannot honor 24 different reserves — so `ModeResolver.portfolio_settings()` resolves it
once per run from the active mode, and `Auto` uses V4_Legacy's account policy.

### 5. Per-Mode Research (Grid Search)
The optimizer's grid search is scoped to each mode's window family, so a mode is tuned
only within its own regime:

* Aggressive:  short {5, 8, 10, 12} x long {20, 25, 30, 40}
* Swing:       short {15, 20, 25}   x long {40, 50, 60}
* Long_Term:   short {40, 50, 60}   x long {150, 200, 250}
* Volatile:    short {10, 15, 20}   x long {35, 40, 50}

V4_Legacy has no grid: it is excluded from `MODE_GRIDS` by design, so nothing ever
writes `best_windows["V4_Legacy"]` to shadow its flat profile fields.

`optimize_for_mode(ticker, mode)` grid-searches that mode's space over the standard
optimization window. `select_best_mode(ticker)` runs all four presets on the SAME
window, ranks by risk-adjusted score (return / |max drawdown|), and records
`best_mode`, `best_windows[mode]`, and `mode_scores`. `Auto` consumes that record.

### 6. Algorithmic Logic Changes
* Buy threshold is now `rsi_buy_threshold` (was hardcoded 55) — modes finally differ on entry depth.
* `exit_on_trend_reversal` gates the MA cross-down sell (true for all shipped modes; the flag
  exists so a future pure-hold mode can set it false).
* `allow_multi_entry` (Aggressive/Volatile) permits re-entry on an RSI **recovery** dip
  (RSI below threshold AND turning up), subject to `reentry_cooldown_days`. Buys the bounce,
  not the descent — never a naive "RSI below X" descent buy.
* Long_Term: exit only on 50/200 reversal, no trailing or hard stop — rides drawdowns.
* Stops consolidated: for every preset `trailing_stop_percent` is the single
  exit-protection and `signal_stop_loss_pct` is `None`. V4_Legacy alone keeps the
  legacy `-0.15` combo stop, because dropping it would change V4.0 behavior.

### 7. Testing Requirements (mocked; extends the existing offline suite)
* `modes.py`: resolver returns the correct bundle per mode; `Auto` reads the stored best mode
  and falls back to V4_Legacy when absent; unknown mode defaults to V4_Legacy; V4_Legacy
  inherits the flat profile windows while presets ignore them; V4_Legacy stays out of
  `MODE_GRIDS`.
* `ma_rsi_combo`: buys at `rsi_buy_threshold` not 55; `sell_on_overbought` triggers only when enabled.
* `live_controller`: `exit_on_trend_reversal=false` suppresses the MA-cross sell; multi-entry
  fires only on RSI recovery and respects the cooldown; settings thread through to sizing/stop.
* `research`: per-mode grid search stays within its window family; `select_best_mode` records a winner.
* Regression: `ACTIVE_MODE="V4_Legacy"` reproduces V4.0 numbers on the existing controller tests.

### 8. Known Risks & Edge Cases
1. Behavior divergence: modes must stay parameter+flag bundles; deep per-mode code forks would
   erode the state machine. New behaviors must be flag-gated.
2. Schema drift: `stock_profile.json` gains fields; missing fields must fall back gracefully
   (V4_Legacy + existing flat windows), so old profiles keep working.
3. Unvalidated modes: each mode must be backtested before being flipped live (Phase 6 gate).
   A selectable preset is not a proven strategy.
4. Multi-entry knife-catching: mitigated by the recovery trigger + cooldown; still the highest-risk flag.
5. Long_Term with no stop: a genuine reversal that never death-crosses could ride a large drawdown.
   This is intentional (position trading), but must be a conscious user choice.

### 9. Migration & Rollback
Ships behind `ACTIVE_MODE="V4_Legacy"` (== V4.0), which is also the code default. Rollback
at any point = set `ACTIVE_MODE="V4_Legacy"` (no redeploy, it is a Lambda env var) or revert
the merge. Schema changes are additive and backward-compatible: the flat window fields are
never removed, so V4_Legacy always resolves even on a pre-V5 profile.

### 10. Deferred
Portfolio risk layer (kill switch, daily-loss circuit breaker) remains separate and pending.
Walk-forward validation of the per-mode grids. Per-mode sentiment prompt tuning.
