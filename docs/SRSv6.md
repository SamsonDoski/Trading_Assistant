# Software Requirements Specification (SRS)
## Project: Trading Assistant V6.0 (Capital Concentration & Run Observability)

### 1. Objective
V6.0 adds no new decision layer. V5.0 settled **what** to trade and **when**;
V6.0 fixes **how much**, and makes the result **visible**.

The diagnosis is narrow and measured. V5.0 shipped correct signals into an
allocator that divided the session budget by every watchlist name not currently
held — 21 of 24 on a typical day — sizing each entry for a session in which the
whole list fires at once. That session does not occur: over 2024-2026 at most
**4** names signalled on the same day and the average was **1.3**. The result was
a permanently cash-heavy account holding roughly 90% idle, not because the
strategy was wrong but because the divisor was.

The per-trade edge was never the problem. Win rate measured **40-41%** across
every configuration tested, before and after this change. V6.0 deploys more of
the capital the strategy already had; it does not trade better, and the drawdown
figures in §6 are the price of that.

Four changes, two behavioral and two observational:

| | Change | Kind |
|---|---|---|
| §4.1 | `ALLOCATION_DENOMINATOR_CAP` — cap the sizing divisor at 4 | behavioral |
| §4.2 | Flat re-entry extended to every preset mode | behavioral |
| §4.3 | Run header reports equity, day move, open P/L, lifetime P&L | observational |
| §4.4 | Sentiment logs the pre-clamp score when the clamp bit | observational |

V6.0 also becomes the **production branch**, with V5.0 frozen as a pre-cap4
rollback anchor (§2).

### 2. Branch Topology & Deployment
The concentration work was merged into `mainV5.0` and deployed before it had a
branch of its own. V6.0 corrects that retroactively: the commits were preserved
onto `mainV6.0`, `mainV5.0` was reset to its pre-cap4 tip (`f7b9d30`), and the
deploy trigger moved.

| Branch | Role | Auto-deploys |
|---|---|---|
| `mainV6.0` | production — cap4, re-entry, reporting | yes, on push |
| `mainV5.0` | frozen pre-cap4 rollback anchor | no — `workflow_dispatch` only |
| `OlajideCode` | integration branch; PRs target `mainV6.0` | no |

`mainV5.0`'s own `deploy.yml` push trigger was removed as part of the freeze.
GitHub Actions evaluates a workflow from the commit being pushed, so a branch
that is both pre-cap4 *and* wired to auto-deploy would redeploy the old sizing
to live accounts on any push to it. The frozen tip therefore differs from
`f7b9d30` in `.github/workflows/deploy.yml` and in no trading code.

**`mainV6.0` must never be merged into `mainV5.0`.** V5.0's only job is to stay
pre-cap4. Rolling production back means repointing the deploy trigger (§9), not
merging branches.

Deployment is unchanged otherwise: one build pushed to three Lambda functions
(`trading-assistant-live`, `-secondary`, `-fractional`), gated on `pytest -q`.
The functions run identical code and differ only by environment variable.

| Env var | Purpose | Set on |
|---|---|---|
| `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` | per-account credentials | all three |
| `ALPACA_PAPER` | paper vs. live endpoint; defaults to paper | all three |
| `ACTIVE_MODE` | mode selector; `V4_Legacy` is the rollback anchor | all three |
| `ANTHROPIC_API_KEY` | sentiment scoring | all three |
| `DISCORD_WEBHOOK_URL` | per-account notification channel | all three |
| `TRADING_HALTED` | kill switch on new buys; defaults to false | **missing on `-fractional`** (§8.6) |
| `ACCOUNT_BASELINE_USD` | **new in V6.0** — capital funded into that account | all three |

### 3. Architecture Additions / Changes
* **Modified:** `config.py` — `ALLOCATION_DENOMINATOR_CAP` (constant, not env-driven);
  `ACCOUNT_BASELINE_USD` (env-driven, non-numeric input warns and degrades to `None`).
* **Modified:** `engine/allocator.py` — `denominator_cap` constructor argument and a
  public `funded_count()` so the caller can report the effective divisor without
  re-deriving the rule.
* **Modified:** `engine/modes.py` — `allow_multi_entry=True` for `Swing` and
  `Long_Term` (`Aggressive` and `Volatile` already had it; `V4_Legacy` stays `False`).
* **Modified:** `engine/executioner.py` — new `get_account_snapshot(baseline_usd=None)`.
  Reporting only: returns `None` on any failure rather than raising.
* **Modified:** `engine/sentiment.py` — capture the model's multiplier before the
  mode clamp is applied and report it when the two differ.
* **Modified:** `live_controller.py` — pass `denominator_cap` to the allocator;
  print the account header after the buying-power line.
* **Modified:** `.github/workflows/deploy.yml` — deploy trigger `mainV5.0` → `mainV6.0`.

No new modules. No schema change to `stock_profile.json`.

### 4. Feature Specifications

#### 4.1 Allocation Denominator Cap
```
usable_budget      = buying_power * (1 - cash_reserve_pct)
funded_count       = min(not_held_count, ALLOCATION_DENOMINATOR_CAP)
base_allocation    = usable_budget / funded_count
position_budget    = min(base_allocation * conviction_multiplier, remaining_budget)
```

**Invariant: the cap can only ever concentrate.** When fewer names are un-held
than the cap, the real count wins — `min()`, never a fixed divisor. A session
with 2 un-held names funds 2 positions, not 4.

`base_allocation_usd` is computed **once per session** (`live_controller.py:104`),
so every buy within a run receives the same slice; `remaining_budget_usd`
decrements after each fill and caps the last one. At cap 4 with the standing 15%
reserve, one slice is **21.25% of buying power**, and four fills in one session
deploy 85% of it. Across sessions the slice shrinks geometrically — buying power
falls to 78.75% after a single-name session, so consecutive single-name sessions
deploy 21.25%, 16.7%, 13.2% and so on. Cash is never fully consumed.

Set to `None` to restore the V5.0 uncapped divisor. The allocator's own default
is `None`, and the test suite covers both paths, so the rollback is a one-line
change that breaks nothing (§9).

#### 4.2 Flat Re-entry for Every Preset
A trailing stop can end a **position** without ending the **trend**. Under V5.0,
single-entry modes were then locked out for the remainder of that trend — MU sat
out a 32% run that way. V6.0 lets every preset re-enter.

Re-entry fires only when all of the following hold:

1. `settings.allow_multi_entry` is true for the resolved mode
2. the account is **flat** in that ticker
3. the strategy signal is still long (`latest_signal == 1`)
4. it is not already a fresh crossover entry
5. `rsi < settings.rsi_buy_threshold` — it has dipped
6. `rsi > previous_rsi` — the dip is **turning up**

Conditions 5 and 6 together buy the bounce, never the descent. Condition 2 is
the hard guarantee: **re-entry can never add to an open position** — no
scale-in, no pyramiding. When the gate does not fire the controller logs which
condition blocked it, so a waiting state is distinguishable from a dead one.

| Mode | `allow_multi_entry` | Re-entry RSI gate |
|---|---|---|
| V4_Legacy | false — rollback anchor | — |
| Aggressive | true (V5.0) | 55 |
| Swing | **true (new in V6.0)** | 55 |
| Long_Term | **true (new in V6.0)** | 40 |
| Volatile | true (V5.0) | 45 |

Long_Term's gate of 40 means it re-enters only on a deep dip, consistent with its
50/200 window family.

#### 4.3 Run Header: Equity and Lifetime P&L
The run header reported buying power, which says what can be **spent**, not how
the account is **doing** — with most of the book in cash the two barely move
together, so a health check could not answer the basic question.

`AlpacaExecutioner.get_account_snapshot(baseline_usd=None)` returns equity, cash,
long market value, the move since the prior close, summed open-position
unrealized P/L, and lifetime P&L. The controller prints it directly beneath the
buying-power line:

```
📊 Equity: $104,312.55 | since prior close: +$812.40 (+0.78%) | open P/L: +$2,140.11 | total on $100,000 funded: +$4,312.55 (+4.31%)
```

Three constraints govern the design:

* **Reporting only.** The method returns `None` on any failure instead of
  raising, and the controller skips the header. Unlike `refresh_positions()`,
  which raises deliberately, a broken status line must never interrupt stop
  management or exits. A test pins this.
* **No invented baseline.** Alpaca exposes current equity but keeps no record of
  deposits, so lifetime P&L is unanswerable from the API alone.
  `ACCOUNT_BASELINE_USD` supplies it per account — env-driven because the three
  accounts are funded differently. Unset or `0`, the header reports equity and
  the day's move only and says how to enable the rest. It never touches sizing.
* **`last_equity` is the prior session's close**, not the start of this run, so
  the day-change field is the move since yesterday's close in every run of the
  day. Documented in the docstring so it is not misread later.

One unreadable position is skipped rather than voiding the whole unrealized
total.

#### 4.4 Pre-clamp Sentiment Reporting
The multiplier was logged **after** the mode clamp. On a mode with a pinned band
— `Long_Term` is `conviction_min=1.0, conviction_max=1.0` — a discarded bearish
call and genuine neutrality both printed `x1.00`, so the model's actual judgment
was unrecoverable from the logs. V6.0 captures the raw score before clamping and
reports it when the two differ:

```
📰 NVDA: x1.00 (model said x0.60, clamped to the 1.00-1.00 band) veto=False — ...
```

Lines where the clamp did not bite are unchanged. This is a diagnostic only — it
does not alter sizing, and it does not fix the underlying issue that sentiment
cannot size a Long_Term position at all (§8.3).

### 5. Inherited from the V5.0 Lineage
These shipped on the `mainV5.0` branch after SRSv5 was written and are carried
into V6.0 undocumented. Recorded here so V6.0 is a complete description of
production.

* **Kill switch** — `TRADING_HALTED` freezes new buys while sells, stop
  attachment and stop-out reporting keep running. Deliberately surgical:
  disabling the EventBridge schedules would switch off the safety systems in the
  exact situation that calls for them. Closes the first half of SRSv5 §10.
* **Parallel accounts** — `ALPACA_PAPER` endpoint flag and a multi-function
  deploy; account kind surfaced in the startup log and Discord greeting.
* **Exact position sizing** — fractional buys placed as notional dollar orders,
  removing price-drift error; live quote used for whole-share sizing.
* **Fractional software trailing stop** — fractional positions cannot carry a
  broker-side GTC trailing stop, so state is tagged into `client_order_id`
  (`tstop-` / `fstop-`). A stale-stop bug was fixed by filtering recovered stops
  on entry price to 4 dp, so a stop left by an earlier position in the same
  ticker is no longer adopted by a new one.
* **Profile freshness warning** — `PROFILE_STALE_WARNING_DAYS = 2` warns before
  profiles expire, after a batch expiry once left the bot silently idle for a
  session.
* **Re-entry cooldown removed**, and news headlines HTML-unescaped before
  reaching the model or Discord.
* **All 24 profiles re-optimized** 2026-10-28 (90-day refresh).

### 6. Measured Results
**Walk-forward, parameters fitted on 2020-2023 only, traded 2024-2026** — the
primary gate for the concentration change:

| | V5.0 (uncapped) | V6.0 (cap 4 + re-entry) |
|---|---|---|
| Total return | 35% | 196% |
| Max drawdown | -15.0% | -29.9% |
| Win rate | 40-41% | 40-41% |

**Full history 2020-04 → 2026-11 (6.35 years), Auto mode at cap 4**, against an
equal-weight buy-and-hold of the same 24 names. This window overlaps the
parameter-fitting period, so treat it as descriptive, not predictive:

| | Strategy | Equal-weight buy & hold |
|---|---|---|
| Total return | 573% | 567% |
| Max drawdown | -29.0% | -36.3% |
| Losing half-years | 19% | 26% |

The return is indistinguishable from buy-and-hold; the measured contribution is
**risk reduction**, concentrated almost entirely in the one bear half-year
(-7.7% vs -29.9%).

**Rolling six-month windows:** median +10% to +20%, with roughly one half-year in
five negative. Only ~5.7 non-overlapping half-years exist in the out-of-sample
period, so these distributions rest on a small independent sample.

**Underwater test** (total account value vs. contributed capital): no breach in
the walk-forward window. One real 18-session episode 2026-04-08 → 2026-05-01
bottomed at -2.6% below contributed capital.

Full methodology, per-mode breakdowns, tax modelling and risk-ratio comparisons
live in a standalone backtest report that is **not yet committed** (§10.7).

### 7. Testing Requirements
Suite: **176 passed, 1 skipped**, offline and fully mocked. No test reaches the
network or a broker.

* `allocator`: `test_denominator_cap_concentrates_the_slice`; the uncapped path is
  asserted for both `PortfolioAllocator()` and an explicit `denominator_cap=None`,
  so the V5.0 behavior stays under test after the cap ships.
* `modes`: `test_every_preset_mode_can_re_enter_while_flat` asserts all four
  presets re-enter and that `V4_Legacy` does not;
  `test_re_entry_gate_is_per_mode` pins the four RSI thresholds.
* `live_controller` re-entry: fires only on an RSI dip that is turning up
  (`test_multi_entry_requires_rsi_turning_up`), buys the recovery
  (`test_multi_entry_buys_the_recovery`), and never adds to an open position
  (`test_multi_entry_never_adds_to_an_open_position`).
* Run header: equity and open P/L reported; total P&L reported when a baseline is
  set; the enabling hint shown when it is not; and
  `test_header_failure_does_not_stop_trading` proves a `None` snapshot leaves
  stops and exits running.
* Sentiment: `test_clamped_verdict_reports_what_the_model_actually_said` and
  `test_unclamped_verdict_logs_no_clamp_note`.
* Regression: `ACTIVE_MODE="V4_Legacy"` continues to reproduce V4.0 behavior.

The controller tests run under both `TestControllerOrchestration` and
`TestControllerModes`, so each is exercised twice.

`pytest -q` is the deploy gate — a red suite blocks the Lambda push, which is
why any rollback that changes a mode flag must change its assertion in the same
commit (§9).

### 8. Known Risks & Edge Cases
1. **Concentration cuts both ways.** Four times the per-name exposure doubled the
   walk-forward drawdown, -15.0% → -29.9%. This is the intended trade, but it is
   a trade, and the account can be expected to sit through deeper holes than V5.0
   would have produced.
2. **Long_Term now re-enters and still has no stop.**
   `trailing_stop_percent=None` is deliberate position-trading behavior, but
   combined with re-entry a name can be re-bought into a decline that never
   death-crosses. The RSI-40 gate and the turning-up requirement are the only
   mitigations.
3. **Sentiment is structurally inert on Long_Term.** Its conviction band is
   pinned at 1.0/1.0, so the multiplier cannot size the position; the veto is the
   only live channel, and the system prompt restricts vetoes to disqualifying
   events (fraud, bankruptcy risk, investigation, delisting). Ordinary bad news
   on a Long_Term name therefore has no effect on anything. §4.4 makes this
   visible in the logs; it does not resolve it.
4. **Profile expiry cliff.** All 24 profiles were optimized on the same day
   (2026-10-28) and expire together at `PROFILE_STALE_DAYS = 90`, roughly
   2027-01-26. The 2-day warning mitigates the surprise, not the batching.
5. **A wrong `ACCOUNT_BASELINE_USD` produces a confidently wrong header.** The
   figure is unverifiable from the API, so nothing can cross-check it. An account
   with $0 equity and a non-zero baseline reports a near-total loss, which is
   arithmetically correct and operationally useless.
6. **`TRADING_HALTED` is absent on `-fractional`.** The kill switch predates that
   function by a month and the variable was never copied across. Behavior is
   correct (the default is not-halted), but in an emergency that account needs the
   variable **added** rather than flipped.
7. **No re-entry cooldown.** A name that is bought, stopped out, and dips and
   recovers again can be re-entered on a subsequent run with nothing but the RSI
   gate between it and a third attempt.
8. **Small independent sample.** The out-of-sample period holds ~5.7
   non-overlapping half-years. Rolling-window statistics look more precise than
   the underlying evidence supports.

### 9. Migration & Rollback
Three rollback levels, cheapest first.

**Mode level (no redeploy).** `ACTIVE_MODE="V4_Legacy"` remains the behavioral
anchor: single entry, 15% trailing stop, legacy free-searched windows, combo hard
stop at -15%. It is a Lambda env var, so this takes effect on the next run with
no deploy. Note it does **not** undo the sizing cap, which is account-level.

**Feature level (redeploy).**
* Sizing: `ALLOCATION_DENOMINATOR_CAP = None` in `config.py` restores the V5.0
  uncapped divisor. One line, no test changes — the allocator defaults to `None`
  and both paths are already covered.
* Re-entry: `allow_multi_entry=False` for `Swing` and `Long_Term` in
  `engine/modes.py`. This **also requires editing**
  `test_every_preset_mode_can_re_enter_while_flat`, or the deploy gate fails.

`ALLOCATION_DENOMINATOR_CAP` being a constant rather than an env var is a known
asymmetry with `ACTIVE_MODE` and `TRADING_HALTED`; §10.1 addresses it.

**Branch level.** Repoint `deploy.yml` at `mainV5.0`, or run `workflow_dispatch`
from `mainV5.0`'s Actions tab, to ship the frozen pre-cap4 build. Do not merge.

Sizing changes affect **new entries only** — reverting the cap does not unwind
positions opened under it.

### 10. Deferred / Roadmap
What V6.0 is expected to take on, in rough priority order.

1. **Make `ALLOCATION_DENOMINATOR_CAP` an env var**, so the highest-impact
   capital setting can be rolled back without a redeploy, matching `ACTIVE_MODE`
   and `TRADING_HALTED`.
2. **Widen Long_Term's conviction band** so the sentiment layer can size it
   (§8.3), or state explicitly that Long_Term is a no-sentiment mode and set
   `sentiment_enabled=False` to stop spending news and LLM calls on it.
3. **Stagger profile re-optimization** so the watchlist does not expire in one
   batch (§8.4).
4. **Add `TRADING_HALTED=false` to `-fractional`** so all three accounts present
   the same controls (§8.6).
5. **Set `ACCOUNT_BASELINE_USD` accurately per account**, and keep it updated on
   every deposit or withdrawal — otherwise §4.3's total P&L drifts silently.
6. **Resolve `-secondary`**: it runs with `ALPACA_PAPER=false` against a $0
   balance. Either fund it or halt it; a live-endpoint function with no capital
   is a trap.
7. **Commit the backtest report** into `docs/` with its reproduction scripts, so
   the §6 figures are re-runnable from the repo rather than from a transient
   working directory.
8. **A re-entry cooldown**, if §8.7 proves costly in live logs.
9. **Daily-loss circuit breaker** — still outstanding from SRSv5 §10. The kill
   switch is manual; nothing automatic stops a bad day.
10. **Tax-aware reporting.** Realized short/long-term split and wash-sale
    tracking have been modelled externally (98-99% of lots are short-term, 7-day
    median hold, over half of losing trades are wash sales) but the system itself
    reports no after-tax figure.
