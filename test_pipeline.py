"""
Full offline test suite for the Trading Assistant.

Every external dependency (yfinance, Alpaca, Discord, matplotlib display) is
monkeypatched, so this is safe for CI with no secrets and no network.

Project imports are done INSIDE each test so a single broken module cannot
abort collection of the whole suite.
"""
import os
os.environ.setdefault("MPLBACKEND", "Agg")   # headless matplotlib for CI

import types
import importlib
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest



#-------------------------------------------------------NEW: Lambda Handler Tests ------------------------------------------------
class TestLambdaHandler:
    def test_returns_200_and_delegates(self, monkeypatch):
        import importlib
        mod = importlib.import_module("aws.lambda_handler")
        called = {"n": 0}
        monkeypatch.setattr(mod, "run_live_pipeline",
                            lambda: called.__setitem__("n", called["n"] + 1))
        resp = mod.lambda_handler({}, None)
        assert resp["statusCode"] == 200
        assert called["n"] == 1

    def test_returns_500_on_failure(self, monkeypatch):
        import importlib
        mod = importlib.import_module("aws.lambda_handler")
        def boom(): raise RuntimeError("kaboom")
        monkeypatch.setattr(mod, "run_live_pipeline", boom)
        resp = mod.lambda_handler({}, None)
        assert resp["statusCode"] == 500

# ---------------------------------------------------------------- helpers
def make_price_df(prices):
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="D")
    return pd.DataFrame({"Close": np.asarray(prices, dtype=float)}, index=idx)


def make_bt_df(prices, signals):
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="D")
    return pd.DataFrame({"Close": np.asarray(prices, dtype=float),
                         "Signal": signals}, index=idx)


# ================================================================ OLD: strategies
class TestLegacyStrategies:
    def test_moving_average_contract(self):
        from strategies.moving_average import apply_moving_average_strategy
        out = apply_moving_average_strategy(make_price_df(np.linspace(100, 300, 300)),
                                            short_window=5, long_window=20)
        for col in ("MA_short", "MA_long", "Signal"):
            assert col in out.columns
        assert "Entry_Price" not in out.columns and "Trade_Return" not in out.columns
        assert set(out["Signal"].unique()).issubset({0, 1})   # never shorts
        assert out["Signal"].iloc[-1] == 1                     # uptrend -> long

    def test_ma_stop_loss_forces_exit(self):
        from strategies.moving_average import apply_moving_average_strategy
        prices = list(np.linspace(100, 200, 80)) + list(np.linspace(200, 100, 20))
        out = apply_moving_average_strategy(make_price_df(prices),
                                            short_window=5, long_window=20,
                                            stop_loss_pct=-0.15)
        assert (out["Signal"] == 1).any()       # entered
        assert out["Signal"].iloc[-1] == 0      # exited after crash

    def test_rsi_bounds_and_binary(self):
        from strategies.rsi import apply_rsi_strategy
        out = apply_rsi_strategy(make_price_df(np.linspace(100, 300, 300)), rsi_window=14)
        assert out["RSI"].dropna().between(0, 100).all()
        assert set(out["Signal"].unique()).issubset({0, 1})

    def test_rsi_div_by_zero_clamps_to_100(self):
        from strategies.rsi import apply_rsi_strategy
        out = apply_rsi_strategy(make_price_df(np.arange(1, 60)), rsi_window=14)
        rsi = out["RSI"].dropna()
        assert (rsi == 100).any()
        assert np.isfinite(rsi).all()

    def test_combo_buys_dips_in_uptrend(self):
        from strategies.ma_rsi_combo import apply_combo_strategy
        # Gentle drift (0.1) with a large oscillation (amp 20) so RSI actually
        # swings below 55 on each pullback -- that's when the combo buys the dip.
        t = np.arange(500)
        out = apply_combo_strategy(make_price_df(100 + 0.1 * t + 20 * np.sin(t / 8.0)),
                                   short_window=5, long_window=20, rsi_window=14)
        for col in ("MA_short", "MA_long", "RSI", "Signal"):
            assert col in out.columns
        assert set(out["Signal"].unique()).issubset({0, 1})
        assert (out["Signal"] == 1).any()      # it bought at least one dip
        assert (out["Signal"] == 0).any()      # ...and was in cash at least once


# ================================================================ OLD: BacktestEngine
class TestBacktestEngine:
    def test_flat_when_never_invested(self):
        from research.backtest import BacktestEngine
        out = BacktestEngine(initial_equity=1000).run(make_bt_df([100, 110, 120, 130],
                                                                  [0, 0, 0, 0]))
        assert out["Equity"].iloc[-1] == 1000

    def test_equity_grows_when_long_in_uptrend(self):
        from research.backtest import BacktestEngine
        out = BacktestEngine(initial_equity=1000).run(
            make_bt_df([100, 110, 121, 133.1], [1, 1, 1, 1]))
        assert out["Equity"].iloc[-1] > 1000

    def test_max_drawdown_non_positive(self):
        from research.backtest import BacktestEngine
        eng = BacktestEngine(initial_equity=1000)
        out = eng.run(make_bt_df([100, 90, 80, 70], [1, 1, 1, 1]))
        assert eng._max_drawdown(out["Equity"]) <= 0

    def test_summary_keys_and_string_types(self):
        from research.backtest import BacktestEngine
        eng = BacktestEngine(initial_equity=1000)
        out = eng.run(make_bt_df([100, 110, 105, 120, 115], [0, 1, 1, 0, 1]))
        s = eng.summary(out)
        for k in ("Total Return", "Net Profit", "Final Balance",
                  "Max Drawdown", "Win Rate"):
            assert k in s and isinstance(s[k], str)


# ================================================================ OLD: config modules
class TestStrategyConfig:
    def test_known_profiles_complete(self):
        from strategy_config import get_profile, PROFILES
        keys = ("short_window", "long_window", "stop_loss_pct",
                "rsi_window", "overbought", "oversold")
        for name in ("Aggressive", "Swing", "Long_Term", "Volatile"):
            p = get_profile(name)
            assert p is PROFILES[name]
            assert all(k in p for k in keys)
            assert p["short_window"] < p["long_window"]
            assert p["stop_loss_pct"] < 0

    def test_unknown_defaults_to_swing(self):
        from strategy_config import get_profile, PROFILES
        assert get_profile("does-not-exist") is PROFILES["Swing"]


class TestConfig:
    def test_constants(self):
        import config
        assert isinstance(config.DEFAULT_TICKER, str)
        assert config.INITIAL_EQUITY > 0
        assert config.SHORT_MA < config.LONG_MA
        assert config.RESULTS_DIR

    def test_alpaca_paper_defaults_true_and_needs_explicit_optout(self, monkeypatch):
        # Going live must require an explicit "false" — never a missing/garbled var.
        import importlib
        import config as cfg
        for value, expected in (("false", False), ("FALSE", False), ("0", False),
                                ("no", False), ("true", True), ("", True),
                                ("anything-else", True)):
            monkeypatch.setenv("ALPACA_PAPER", value)
            assert importlib.reload(cfg).ALPACA_PAPER is expected, value
        monkeypatch.delenv("ALPACA_PAPER", raising=False)
        assert importlib.reload(cfg).ALPACA_PAPER is True      # unset -> paper


# ================================================================ NEW: allocator (V4.1 equal-weight + fractional)
class TestAllocator:
    def test_usable_budget_holds_back_reserve(self):
        from engine.allocator import PortfolioAllocator
        a = PortfolioAllocator(cash_reserve_pct=0.15)
        assert a.usable_budget(100_000) == pytest.approx(85_000)
        assert a.usable_budget(0) == 0.0
        assert a.usable_budget(None) == 0.0

    def test_base_allocation_is_equal_weight_with_no_flat_cap(self):
        from engine.allocator import PortfolioAllocator
        a = PortfolioAllocator()
        # $85k deployable split across 20 not-held names -> $4,250 each
        assert a.base_allocation(85_000, 20) == pytest.approx(4_250)
        # NO $5k cap: a $1M-ish account gets a proportionally big slice
        assert a.base_allocation(850_000, 20) == pytest.approx(42_500)
        # guards: nothing to deploy / everything already held
        assert a.base_allocation(85_000, 0) == 0.0
        assert a.base_allocation(0, 20) == 0.0
        assert a.base_allocation(None, 20) == 0.0

    def test_calculate_shares_whole(self):
        from engine.allocator import PortfolioAllocator
        a = PortfolioAllocator()
        assert a.calculate_shares(200.0, base_allocation_usd=5000) == (25, False)
        assert a.calculate_shares(0, base_allocation_usd=5000) == (0, False)
        assert a.calculate_shares(None, base_allocation_usd=5000) == (0, False)
        assert a.calculate_shares(200.0, base_allocation_usd=0) == (0, False)

    def test_multiplier_applied_before_budget_cap(self):
        from engine.allocator import PortfolioAllocator
        a = PortfolioAllocator()
        # $5000 x1.5 = $7500 / $200 -> 37
        assert a.calculate_shares(200.0, base_allocation_usd=5000,
                                  conviction_multiplier=1.5) == (37, False)
        # $5000 x0.5 = $2500 / $200 -> 12
        assert a.calculate_shares(200.0, base_allocation_usd=5000,
                                  conviction_multiplier=0.5) == (12, False)
        # cap is applied AFTER the multiplier: $3000 remaining wins over $7500
        assert a.calculate_shares(200.0, base_allocation_usd=5000,
                                  remaining_budget_usd=3000,
                                  conviction_multiplier=1.5) == (15, False)

    def test_no_flat_cap_on_large_account(self):
        from engine.allocator import PortfolioAllocator
        a = PortfolioAllocator()
        # $50k slice, no cap -> 250 shares at $200
        assert a.calculate_shares(200.0, base_allocation_usd=50_000) == (250, False)

    def test_fractional_fallback_when_whole_unaffordable(self):
        from engine.allocator import PortfolioAllocator
        a = PortfolioAllocator(min_fractional_notional_usd=1.00)
        shares, is_frac = a.calculate_shares(200.0, base_allocation_usd=14.0,
                                             allow_fractional=True)
        assert is_frac is True
        assert shares == pytest.approx(0.07)      # 14/200, always < 1 by construction
        assert 0 < shares < 1

    def test_fractional_disabled_returns_zero(self):
        from engine.allocator import PortfolioAllocator
        a = PortfolioAllocator()
        # default allow_fractional=False -> skip rather than buy a fraction
        assert a.calculate_shares(200.0, base_allocation_usd=14.0) == (0, False)

    def test_fractional_dust_floor(self):
        from engine.allocator import PortfolioAllocator
        a = PortfolioAllocator(min_fractional_notional_usd=5.00)
        # $2 slice is below the $5 dust floor -> nothing
        assert a.calculate_shares(200.0, base_allocation_usd=2.0,
                                  allow_fractional=True) == (0, False)
        # $6 slice clears it -> fractional
        shares, is_frac = a.calculate_shares(200.0, base_allocation_usd=6.0,
                                             allow_fractional=True)
        assert is_frac is True and shares == pytest.approx(0.03)

    def test_position_budget_applies_multiplier_then_cap(self):
        from engine.allocator import PortfolioAllocator
        a = PortfolioAllocator()
        assert a.position_budget(5000, conviction_multiplier=1.5) == pytest.approx(7500)
        # cap applied AFTER the multiplier
        assert a.position_budget(5000, 3000, 1.5) == pytest.approx(3000)
        assert a.position_budget(0) == 0.0
        assert a.position_budget(None) == 0.0
        assert a.position_budget(5000, 0, 1.5) == 0.0

    def test_legacy_generate_buy_orders(self):
        from engine.allocator import PortfolioAllocator
        orders = PortfolioAllocator().generate_buy_orders(
            ["AAPL", "MSFT"], {"AAPL": 100.0, "MSFT": 0})
        assert orders["AAPL"] == 50 and "MSFT" not in orders

# ================================================================ NEW: scanner
class TestScanner:
    @staticmethod
    def _settings(**over):
        from engine.modes import TRADING_MODES
        from dataclasses import replace
        return replace(TRADING_MODES["V4_Legacy"], ma_short=5, ma_long=20,
                       rsi_window=14, **over)

    def test_get_signals_contract(self, monkeypatch):
        import engine.scanner as sm
        t = np.arange(400)
        fake = make_price_df(100 + 0.5 * t + 8 * np.sin(t / 10.0))
        monkeypatch.setattr(sm, "fetch_data", lambda *a, **k: fake.copy())
        d = sm.StrategyScanner().get_signals("AAPL", self._settings())
        assert set(d) == {"latest_signal", "previous_signal", "current_price",
                          "current_rsi", "previous_rsi"}
        assert d["latest_signal"] in (0, 1)
        assert 0 <= d["current_rsi"] <= 100

    def test_get_signals_empty_returns_none(self, monkeypatch):
        import engine.scanner as sm
        monkeypatch.setattr(sm, "fetch_data", lambda *a, **k: pd.DataFrame())
        assert sm.StrategyScanner().get_signals("X", self._settings()) is None

    def test_mode_threshold_reaches_the_strategy(self, monkeypatch):
        # A deep buy threshold must produce no more long bars than a loose one.
        import engine.scanner as sm
        t = np.arange(400)
        fake = make_price_df(100 + 0.2 * t + 20 * np.sin(t / 8.0))
        seen = {}
        real = sm.apply_combo_strategy
        def spy(df, **kw):
            seen.update(kw)
            return real(df, **kw)
        monkeypatch.setattr(sm, "fetch_data", lambda *a, **k: fake.copy())
        monkeypatch.setattr(sm, "apply_combo_strategy", spy)
        sm.StrategyScanner().get_signals("X", self._settings(rsi_buy_threshold=35))
        assert seen["rsi_buy_threshold"] == 35
        assert seen["stop_loss_pct"] == -0.15        # V4_Legacy keeps the V4.0 signal stop
        


# ================================================================ NEW: notifier
class TestNotifier:
    def test_no_webhook_is_graceful(self, monkeypatch, capsys):
        monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
        from utils.notifier import DiscordNotifier
        DiscordNotifier().send_message("hello")           # must not raise
        assert "not found" in capsys.readouterr().out.lower()

    def test_posts_when_webhook_set(self, monkeypatch):
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.com/hook")
        import utils.notifier as nm
        seen = {}
        class FakeResp:
            status_code = 200
            def raise_for_status(self): pass
        def fake_post(url, json=None, **k):
            seen["url"], seen["json"] = url, json
            return FakeResp()
        monkeypatch.setattr(nm, "requests", types.SimpleNamespace(post=fake_post))
        nm.DiscordNotifier().send_message("ping")
        assert seen["url"] == "https://example.com/hook"
        assert "ping" in seen["json"]["content"]


# ================================================================ NEW: AlpacaExecutioner (TradingClient mocked, no SDK calls out)
class TestExecutioner:
    @staticmethod
    def _client_cls(positions, open_order_symbols=(), buying_power="100000",
                    closed_stopouts=(), all_orders=(), fractionable=True,
                    asset_raises=False, current_prices=None):
        current_prices = current_prices or {}
        class FakePos:
            def __init__(self, sym, plpc, qty, current_price):
                self.symbol, self.unrealized_plpc, self.qty = sym, plpc, qty
                self.avg_entry_price = "100.0"
                self.current_price = current_price
        class FakeOrder:
            def __init__(self, sym, oid):
                self.symbol, self.id = sym, oid
        class FakeAll:                       # order-history rows w/ client_order_id
            def __init__(self, sym, coid):
                self.symbol, self.client_order_id = sym, coid
        class FakeClosed:
            def __init__(self, sym, qty, price, coid="", order_type="trailing_stop"):
                self.symbol, self.filled_qty, self.filled_avg_price = sym, qty, price
                self.order_type, self.status = order_type, "filled"
                self.client_order_id = coid
        class FakeAccount:
            def __init__(self): self.non_marginable_buying_power = buying_power
        class FakeClient:
            def __init__(self, *a, **k):
                self.submitted, self.closed, self.canceled = [], [], []
                self._pos = [FakePos(s, plpc, qty, current_prices.get(s, "100.0"))
                             for s, (plpc, qty) in positions.items()]
                self._orders = [FakeOrder(s, f"oid-{s}") for s in open_order_symbols]
                self._all_orders = [FakeAll(s, c) for s, c in all_orders]
                self._closed = [FakeClosed(*c) for c in closed_stopouts]
            def get_all_positions(self): return self._pos
            def get_account(self): return FakeAccount()
            def get_asset(self, symbol):
                if asset_raises:
                    raise RuntimeError("asset lookup failed")
                return types.SimpleNamespace(fractionable=fractionable)
            def get_orders(self, filter=None):
                status = str(getattr(filter, "status", "")).lower()
                syms = getattr(filter, "symbols", None)
                if "closed" in status:
                    return list(self._closed)
                if "all" in status:
                    out = list(self._all_orders)
                    return [o for o in out if o.symbol in syms] if syms else out
                if syms:
                    return [o for o in self._orders if o.symbol in syms]
                return list(self._orders)
            def submit_order(self, order_data=None): self.submitted.append(order_data)
            def close_position(self, symbol): self.closed.append(symbol)
            def cancel_order_by_id(self, order_id): self.canceled.append(order_id)
        return FakeClient

    def test_get_buying_power(self, monkeypatch):
        import engine.executioner as em
        monkeypatch.setattr(em, "TradingClient",
                            self._client_cls({}, buying_power="12345.67"))
        ex = em.AlpacaExecutioner("k", "s", paper=True)
        assert ex.get_buying_power() == pytest.approx(12345.67)

    def test_state_and_orders(self, monkeypatch):
        import engine.executioner as em
        monkeypatch.setattr(em, "TradingClient", self._client_cls({"AAPL": ("0.05", "10")}))
        ex = em.AlpacaExecutioner("k", "s", paper=True)
        assert ex.is_holding("AAPL") is True
        assert ex.is_holding("MSFT") is False
        assert ex.get_unrealized_pl_pct("AAPL") == pytest.approx(5.0)
        assert ex.get_unrealized_pl_pct("MSFT") is None
        ex.execute_market_buy("MSFT", 10)
        assert len(ex.api.submitted) == 1
        ex.execute_market_buy("MSFT", 0)          # no-op
        assert len(ex.api.submitted) == 1
        ex.liquidate_position("AAPL")
        assert ex.api.closed == ["AAPL"]

    def test_execute_market_buy_accepts_fractional(self, monkeypatch):
        import engine.executioner as em
        monkeypatch.setattr(em, "TradingClient", self._client_cls({}))
        ex = em.AlpacaExecutioner("k", "s", paper=True)
        ex.execute_market_buy("MSFT", 0.5)
        assert len(ex.api.submitted) == 1
        assert float(ex.api.submitted[0].qty) == pytest.approx(0.5)

    def test_execute_market_buy_notional(self, monkeypatch):
        import engine.executioner as em
        monkeypatch.setattr(em, "TradingClient", self._client_cls({}))
        ex = em.AlpacaExecutioner("k", "s", paper=True)
        ex.execute_market_buy("MSFT", notional=18.8649)
        [order] = ex.api.submitted
        assert float(order.notional) == pytest.approx(18.86)   # rounded to cents
        assert getattr(order, "qty", None) is None             # never both

    def test_execute_market_buy_rejects_ambiguous_sizing(self, monkeypatch):
        import engine.executioner as em
        monkeypatch.setattr(em, "TradingClient", self._client_cls({}))
        ex = em.AlpacaExecutioner("k", "s", paper=True)
        ex.execute_market_buy("MSFT")                       # neither
        ex.execute_market_buy("MSFT", qty=1, notional=100)  # both
        ex.execute_market_buy("MSFT", notional=0)           # non-positive
        assert ex.api.submitted == []

    def test_held_symbols(self, monkeypatch):
        import engine.executioner as em
        monkeypatch.setattr(em, "TradingClient",
                            self._client_cls({"AAPL": ("0.05", "10"), "MU": ("0.1", "3")}))
        ex = em.AlpacaExecutioner("k", "s", paper=True)
        assert set(ex.held_symbols()) == {"AAPL", "MU"}

    def test_fractionable_and_position_qty(self, monkeypatch):
        import engine.executioner as em
        monkeypatch.setattr(em, "TradingClient",
                            self._client_cls({"AAPL": ("0.02", "0.5")}, fractionable=True))
        ex = em.AlpacaExecutioner("k", "s", paper=True)
        assert ex.fractionable("AAPL") is True
        assert ex.position_qty("AAPL") == pytest.approx(0.5)
        assert ex.position_qty("MSFT") == 0.0

    def test_fractionable_false_on_lookup_failure(self, monkeypatch):
        import engine.executioner as em
        monkeypatch.setattr(em, "TradingClient", self._client_cls({}, asset_raises=True))
        ex = em.AlpacaExecutioner("k", "s", paper=True)
        assert ex.fractionable("AAPL") is False

    # ---- whole-share position -> GTC trailing stop (unchanged behavior) ----
    def test_whole_position_gets_trailing_stop(self, monkeypatch):
        import engine.executioner as em
        monkeypatch.setattr(em, "TradingClient", self._client_cls({"AAPL": ("0.05", "10")}))
        ex = em.AlpacaExecutioner("k", "s", paper=True)
        msg = ex.ensure_protective_stop("AAPL", 8.0)
        assert msg is not None and "Trailing" in msg
        assert len(ex.api.submitted) == 1
        assert "AAPL" in ex._open_order_symbols
        assert ex.ensure_protective_stop("AAPL", 8.0) is None   # no stacking
        assert len(ex.api.submitted) == 1

    def test_stop_skipped_when_already_protected(self, monkeypatch):
        import engine.executioner as em
        monkeypatch.setattr(em, "TradingClient",
                            self._client_cls({"AAPL": ("0.05", "10")}, open_order_symbols=["AAPL"]))
        ex = em.AlpacaExecutioner("k", "s", paper=True)
        assert ex.ensure_protective_stop("AAPL", 8.0) is None
        assert ex.api.submitted == []

    def test_stop_skipped_when_not_held(self, monkeypatch):
        import engine.executioner as em
        monkeypatch.setattr(em, "TradingClient", self._client_cls({"AAPL": ("0.05", "10")}))
        ex = em.AlpacaExecutioner("k", "s", paper=True)
        assert ex.ensure_protective_stop("MSFT", 8.0) is None

    # ---- fractional position -> DAY stop that ratchets up, with backstop ----
    def test_fractional_position_gets_day_stop(self, monkeypatch):
        import engine.executioner as em
        from alpaca.trading.enums import TimeInForce
        monkeypatch.setattr(em, "TradingClient",
                            self._client_cls({"AAPL": ("0.02", "0.5")},
                                             current_prices={"AAPL": "100.0"}))
        ex = em.AlpacaExecutioner("k", "s", paper=True)
        msg = ex.ensure_protective_stop("AAPL", 15.0)
        assert msg is not None and "Fractional" in msg
        assert len(ex.api.submitted) == 1
        order = ex.api.submitted[0]
        assert type(order).__name__ == "StopOrderRequest"
        assert order.time_in_force == TimeInForce.DAY
        assert float(order.stop_price) == pytest.approx(85.0)   # entry 100 * (1-0.15)

    def test_fractional_stop_ratchets_up_from_prior(self, monkeypatch):
        import engine.executioner as em
        monkeypatch.setattr(em, "TradingClient",
                            self._client_cls({"AAPL": ("0.02", "0.5")},
                                             current_prices={"AAPL": "100.0"},
                                             all_orders=[("AAPL", "fstop-AAPL-90.0000-1700000000")]))
        ex = em.AlpacaExecutioner("k", "s", paper=True)
        ex.ensure_protective_stop("AAPL", 15.0)
        # prior protected 90 beats candidate (100*0.85=85) -> level holds at 90, never steps down
        assert float(ex.api.submitted[0].stop_price) == pytest.approx(90.0)

    def test_fractional_stop_backstop_liquidates_when_breached(self, monkeypatch):
        import engine.executioner as em
        monkeypatch.setattr(em, "TradingClient",
                            self._client_cls({"AAPL": ("-0.10", "0.5")},
                                             current_prices={"AAPL": "88.0"},
                                             all_orders=[("AAPL", "fstop-AAPL-90.0000-1700000000")]))
        ex = em.AlpacaExecutioner("k", "s", paper=True)
        msg = ex.ensure_protective_stop("AAPL", 15.0)
        # current 88 <= protected 90 -> sell now, place no new stop
        assert ex.api.closed == ["AAPL"]
        assert ex.api.submitted == []
        assert "liquidated" in msg.lower()

    def test_liquidate_cancels_open_orders_first(self, monkeypatch):
        import engine.executioner as em
        monkeypatch.setattr(em, "TradingClient",
                            self._client_cls({"AAPL": ("0.05", "10")}, open_order_symbols=["AAPL"]))
        ex = em.AlpacaExecutioner("k", "s", paper=True)
        ex.liquidate_position("AAPL")
        assert ex.api.canceled == ["oid-AAPL"]
        assert ex.api.closed == ["AAPL"]

    def test_get_recent_stopouts_without_tag_has_no_pl(self, monkeypatch):
        import engine.executioner as em
        monkeypatch.setattr(em, "TradingClient",
                            self._client_cls({}, closed_stopouts=[("MU", "8", "985.20")]))
        ex = em.AlpacaExecutioner("k", "s", paper=True)
        assert ex.get_recent_stopouts(hours=24) == [("MU", "8", "985.20", None, None)]

    def test_get_recent_stopouts_computes_realized_pl(self, monkeypatch):
        import engine.executioner as em
        monkeypatch.setattr(em, "TradingClient", self._client_cls(
            {}, closed_stopouts=[("MU", "8", "918.00", "tstop-MU-900.0000-1700000000")]))
        ex = em.AlpacaExecutioner("k", "s", paper=True)
        [(sym, qty, price, pl_pct, pl_usd)] = ex.get_recent_stopouts(hours=24)
        assert pl_pct == pytest.approx(2.0)
        assert pl_usd == pytest.approx(144.0)

    # ---- fractional stop-outs are plain `stop` orders, not trailing_stop ----
    def test_fractional_stopout_is_reported_with_pl(self, monkeypatch):
        import engine.executioner as em
        # fstop-{ticker}-{stop}-{entry}-{ts}: bought at 28.39, stopped out at 26.69.
        monkeypatch.setattr(em, "TradingClient", self._client_cls(
            {}, closed_stopouts=[("SMCI", "0.9536", "26.69",
                                  "fstop-SMCI-26.6900-28.3900-1700000000", "stop")]))
        ex = em.AlpacaExecutioner("k", "s", paper=True)
        [(sym, qty, price, pl_pct, pl_usd)] = ex.get_recent_stopouts(hours=24)
        assert sym == "SMCI"
        assert pl_pct == pytest.approx(-5.988, abs=0.01)      # 28.39 -> 26.69
        assert pl_usd == pytest.approx(-1.621, abs=0.01)      # x 0.9536 shares

    def test_legacy_fractional_stopout_reported_without_pl(self, monkeypatch):
        import engine.executioner as em
        # Legacy 4-part id carries the stop level but no entry price.
        monkeypatch.setattr(em, "TradingClient", self._client_cls(
            {}, closed_stopouts=[("SMCI", "0.5", "26.69",
                                  "fstop-SMCI-26.6900-1700000000", "stop")]))
        ex = em.AlpacaExecutioner("k", "s", paper=True)
        [(sym, qty, price, pl_pct, pl_usd)] = ex.get_recent_stopouts(hours=24)
        assert sym == "SMCI" and pl_pct is None and pl_usd is None

    def test_foreign_stop_order_is_not_reported(self, monkeypatch):
        import engine.executioner as em
        # A stop the bot didn't place (no fstop- id) must not be claimed as ours.
        monkeypatch.setattr(em, "TradingClient", self._client_cls(
            {}, closed_stopouts=[("SMCI", "1", "26.69", "manual-order-123", "stop")]))
        ex = em.AlpacaExecutioner("k", "s", paper=True)
        assert ex.get_recent_stopouts(hours=24) == []

    def test_fractional_stop_id_carries_stop_and_entry(self, monkeypatch):
        import engine.executioner as em
        monkeypatch.setattr(em, "TradingClient",
                            self._client_cls({"AAPL": ("0.02", "0.5")},
                                             current_prices={"AAPL": "100.0"}))
        ex = em.AlpacaExecutioner("k", "s", paper=True)
        ex.ensure_protective_stop("AAPL", 15.0)
        coid = ex.api.submitted[0].client_order_id
        stop_level, entry_price = ex._parse_fractional_stop_id(coid)
        assert stop_level == pytest.approx(85.0)     # entry 100 * (1 - 0.15)
        assert entry_price == pytest.approx(100.0)   # avg_entry_price, for later P/L

    def test_ratchet_still_reads_legacy_ids(self, monkeypatch):
        import engine.executioner as em
        # A 4-part id from before entry-price tagging must still floor the ratchet.
        monkeypatch.setattr(em, "TradingClient",
                            self._client_cls({"AAPL": ("0.02", "0.5")},
                                             current_prices={"AAPL": "100.0"},
                                             all_orders=[("AAPL", "fstop-AAPL-90.0000-1700000000")]))
        ex = em.AlpacaExecutioner("k", "s", paper=True)
        ex.ensure_protective_stop("AAPL", 15.0)
        assert float(ex.api.submitted[0].stop_price) == pytest.approx(90.0)

    def test_position_fetch_failure_raises(self, monkeypatch):
        import engine.executioner as em
        class BoomClient:
            def __init__(self, *a, **k): pass
            def get_all_positions(self): raise RuntimeError("request timed out")
        monkeypatch.setattr(em, "TradingClient", BoomClient)
        monkeypatch.setattr(em.time, "sleep", lambda *a, **k: None)
        with pytest.raises(Exception):
            em.AlpacaExecutioner("k", "s", paper=True)

    def test_no_stop_when_trail_is_none(self, monkeypatch):
        import engine.executioner as em
        monkeypatch.setattr(em, "TradingClient", self._client_cls({"AAPL": ("0.05", "10")}))
        ex = em.AlpacaExecutioner("k", "s", paper=True)
        assert ex.ensure_protective_stop("AAPL", None) is None
        assert ex.api.submitted == []            # mode runs stopless


# ================================================================ NEW: run_live_pipeline() state machine (all modules faked)
class TestControllerOrchestration:
    def _wire(self, monkeypatch, signals, held, buying_power=1_000_000.0,
              sentiment_report=None, sentiment_mode="shadow", mode="V4_Legacy",
              live_price=None):
        import live_controller as lc
        class FakeScanner:
            def get_signals(self, *a, **k):
                if signals is not None:
                    signals.setdefault("previous_rsi", signals.get("current_rsi"))
                return signals
        class FakeAllocator:
            cash_reserve_pct = 0.15
            def __init__(self, *a, **k): pass
            def usable_budget(self, bp): return bp
            def base_allocation(self, usable_budget_usd, not_held_count):
                return usable_budget_usd / max(1, not_held_count)
            def position_budget(self, base_allocation_usd, remaining_budget_usd=None,
                                conviction_multiplier=1.0):
                budget = base_allocation_usd * conviction_multiplier
                if remaining_budget_usd is not None:
                    budget = min(budget, remaining_budget_usd)
                return max(budget, 0.0)
            def calculate_shares(self, current_price, base_allocation_usd,
                                 remaining_budget_usd=None, conviction_multiplier=1.0,
                                 allow_fractional=False):
                if remaining_budget_usd is not None and remaining_budget_usd < current_price:
                    return 0, False
                return int(42 * conviction_multiplier), False

        from engine.sentiment import SentimentReport
        class FakeSentiment:
            def get_verdict(self, t, conviction_min=0.5, conviction_max=1.5):
                report = sentiment_report or SentimentReport(
                    sentiment_multiplier=1.0, veto=False, rationale="neutral", headlines=[])
                # Mirror the real analyzer: the mode's band clamps the multiplier.
                clamped = max(conviction_min,
                              min(conviction_max, report.sentiment_multiplier))
                return report.model_copy(update={"sentiment_multiplier": clamped})
        monkeypatch.setattr(lc, "SentimentAnalyzer", FakeSentiment)
        monkeypatch.setattr(lc, "SENTIMENT_MODE", sentiment_mode)

        class FakeNotifier:
            def __init__(self):
                self.msgs = []
                holder["notifier"] = self      # so tests can assert on the log text
            def send_message(self, m): self.msgs.append(m)
        class FakeExec:
            def __init__(self, *a, **k):
                self.buys, self.sells, self.stops = [], [], []
                self.notional_buys = []
            def is_holding(self, t): return held
            def get_unrealized_pl_pct(self, t): return 3.0
            def get_buying_power(self): return buying_power
            def fractionable(self, t): return True
            def execute_market_buy(self, t, qty=None, notional=None):
                if notional is not None:
                    self.notional_buys.append((t, notional))
                else:
                    self.buys.append((t, qty))
            def liquidate_position(self, t): self.sells.append(t)
            def refresh_positions(self): pass
            def refresh_open_orders(self): pass
            def held_symbols(self): return ["AAPL"] if held else []
            def get_recent_stopouts(self, hours=24): return []
            def ensure_protective_stop(self, t, pct):
                self.stops.append((t, pct)); return f"stop attached {t}"
        holder = {}
        monkeypatch.setattr(lc, "load_profiles", lambda: {
            "AAPL": {"best_short_window": 5, "best_long_window": 20, "rsi_period": 14}})
        monkeypatch.setattr(lc, "is_stale", lambda t: False)
        monkeypatch.setattr(lc, "StrategyScanner", FakeScanner)
        monkeypatch.setattr(lc, "PortfolioAllocator", FakeAllocator)
        monkeypatch.setattr(lc, "DiscordNotifier", FakeNotifier)
        monkeypatch.setattr(lc.time, "sleep", lambda *a, **k: None)
        monkeypatch.setattr(lc, "ACTIVE_MODE", mode)
        # None => quote unavailable, controller falls back to the daily-bar price.
        monkeypatch.setattr(lc, "fetch_latest_price", lambda t: live_price)
        def make_exec(*a, **k):
            holder["exec"] = FakeExec()
            holder["exec_kwargs"] = k          # so tests can assert the paper flag
            return holder["exec"]
        monkeypatch.setattr(lc, "AlpacaExecutioner", make_exec)
        return lc, holder

    def test_buy_on_fresh_crossover(self, monkeypatch):
        lc, h = self._wire(monkeypatch, {"latest_signal": 1, "previous_signal": 0,
            "current_price": 200.0, "current_rsi": 40.0}, held=False)
        lc.run_live_pipeline()
        assert h["exec"].buys == [("AAPL", 42)] and h["exec"].sells == []

    def test_sizing_uses_the_live_quote_not_the_daily_bar(self, monkeypatch):
        # Daily bar says $200, market says $250. Sizing must use $250.
        lc, h = self._wire(monkeypatch, {"latest_signal": 1, "previous_signal": 0,
            "current_price": 200.0, "current_rsi": 40.0}, held=False, live_price=250.0)
        lc.run_live_pipeline()
        [(ticker, qty)] = h["exec"].buys
        assert ticker == "AAPL"
        # FakeAllocator returns int(42 * multiplier) regardless, so assert the
        # price the controller reported — that is what it sized and logged on.
        assert "250.00" in " ".join(h["notifier"].msgs)

    def test_sizing_falls_back_when_quote_unavailable(self, monkeypatch):
        # A failed quote must never block a trade — degrade to the bar price.
        lc, h = self._wire(monkeypatch, {"latest_signal": 1, "previous_signal": 0,
            "current_price": 200.0, "current_rsi": 40.0}, held=False, live_price=None)
        lc.run_live_pipeline()
        assert h["exec"].buys == [("AAPL", 42)]
        assert "200.00" in " ".join(h["notifier"].msgs)

    def test_fractional_buy_is_placed_as_a_dollar_order(self, monkeypatch):
        # Fractional slices go out as notional so the spend is exact regardless
        # of how the price moved since the last bar.
        lc, h = self._wire(monkeypatch, {"latest_signal": 1, "previous_signal": 0,
            "current_price": 200.0, "current_rsi": 40.0}, held=False)
        class FractionalAllocator(lc.PortfolioAllocator):
            def calculate_shares(self, *a, **k): return 0.05, True
            def position_budget(self, base, remaining=None, mult=1.0): return 18.86
        monkeypatch.setattr(lc, "PortfolioAllocator", FractionalAllocator)
        lc.run_live_pipeline()
        assert h["exec"].buys == []                                # no share-qty order
        assert h["exec"].notional_buys == [("AAPL", 18.86)]        # exact dollars

    def test_alpaca_paper_flag_reaches_the_executioner(self, monkeypatch):
        signals = {"latest_signal": 1, "previous_signal": 1,
                   "current_price": 200.0, "current_rsi": 50.0}
        lc, h = self._wire(monkeypatch, signals, held=True)
        monkeypatch.setattr(lc, "ALPACA_PAPER", False)
        lc.run_live_pipeline()
        assert h["exec_kwargs"]["paper"] is False      # live endpoint requested

        lc, h = self._wire(monkeypatch, signals, held=True)
        monkeypatch.setattr(lc, "ALPACA_PAPER", True)
        lc.run_live_pipeline()
        assert h["exec_kwargs"]["paper"] is True

    def test_sell_when_trend_dies(self, monkeypatch):
        lc, h = self._wire(monkeypatch, {"latest_signal": 0, "previous_signal": 1,
            "current_price": 180.0, "current_rsi": 60.0}, held=True)
        lc.run_live_pipeline()
        assert h["exec"].sells == ["AAPL"] and h["exec"].buys == []

    def test_no_double_buy(self, monkeypatch):
        lc, h = self._wire(monkeypatch, {"latest_signal": 1, "previous_signal": 0,
            "current_price": 200.0, "current_rsi": 40.0}, held=True)
        lc.run_live_pipeline()
        assert h["exec"].buys == []

    def test_chasing_guard_no_buy(self, monkeypatch):
        lc, h = self._wire(monkeypatch, {"latest_signal": 1, "previous_signal": 1,
            "current_price": 200.0, "current_rsi": 70.0}, held=False)
        lc.run_live_pipeline()
        assert h["exec"].buys == []

    def test_protection_pass_attaches_trailing_stop(self, monkeypatch):
        lc, h = self._wire(monkeypatch, {"latest_signal": 1, "previous_signal": 1,
            "current_price": 200.0, "current_rsi": 50.0}, held=True)
        lc.run_live_pipeline()
        assert h["exec"].stops == [("AAPL", 15.0)]   # Swing mode's trailing stop


    def test_buy_skipped_when_insufficient_buying_power(self, monkeypatch):
        lc, h = self._wire(monkeypatch, {"latest_signal": 1, "previous_signal": 0,
            "current_price": 200.0, "current_rsi": 40.0}, held=False, buying_power=50.0)
        lc.run_live_pipeline()
        assert h["exec"].buys == []


    def test_aborts_when_positions_unreadable(self, monkeypatch):
        lc, h = self._wire(monkeypatch, {"latest_signal": 1, "previous_signal": 0,
            "current_price": 200.0, "current_rsi": 40.0}, held=False)
        def boom(*a, **k): raise RuntimeError("request timed out")
        monkeypatch.setattr(lc, "AlpacaExecutioner", boom)
        lc.run_live_pipeline()          # must not raise
        assert "exec" not in h          # never constructed → no trades attempted


    def test_shadow_mode_sizes_at_baseline_despite_bullish_verdict(self, monkeypatch):
        from engine.sentiment import SentimentReport
        bullish = SentimentReport(sentiment_multiplier=1.5, veto=False,
                                  rationale="great news", headlines=["Beat"])
        lc, h = self._wire(monkeypatch, {"latest_signal": 1, "previous_signal": 0,
            "current_price": 200.0, "current_rsi": 40.0}, held=False,
            sentiment_report=bullish, sentiment_mode="shadow")
        lc.run_live_pipeline()
        assert h["exec"].buys == [("AAPL", 42)]

    def test_live_mode_applies_multiplier(self, monkeypatch):
        from engine.sentiment import SentimentReport
        bullish = SentimentReport(sentiment_multiplier=1.5, veto=False,
                                  rationale="great news", headlines=["Beat"])
        lc, h = self._wire(monkeypatch, {"latest_signal": 1, "previous_signal": 0,
            "current_price": 200.0, "current_rsi": 40.0}, held=False,
            sentiment_report=bullish, sentiment_mode="live")
        lc.run_live_pipeline()
        assert h["exec"].buys == [("AAPL", 63)]

    def test_live_mode_veto_skips_buy(self, monkeypatch):
        from engine.sentiment import SentimentReport
        toxic = SentimentReport(sentiment_multiplier=0.5, veto=True,
                                rationale="fraud probe", headlines=["DOJ probes"])
        lc, h = self._wire(monkeypatch, {"latest_signal": 1, "previous_signal": 0,
            "current_price": 200.0, "current_rsi": 40.0}, held=False,
            sentiment_report=toxic, sentiment_mode="live")
        lc.run_live_pipeline()
        assert h["exec"].buys == []

    def test_shadow_mode_veto_still_buys(self, monkeypatch):
        from engine.sentiment import SentimentReport
        toxic = SentimentReport(sentiment_multiplier=0.5, veto=True,
                                rationale="fraud probe", headlines=["DOJ probes"])
        lc, h = self._wire(monkeypatch, {"latest_signal": 1, "previous_signal": 0,
            "current_price": 200.0, "current_rsi": 40.0}, held=False,
            sentiment_report=toxic, sentiment_mode="shadow")
        lc.run_live_pipeline()
        assert h["exec"].buys == [("AAPL", 42)]

# ================================================================ NEW: profile_manager
class TestProfileManager:
    def test_load_missing_returns_empty(self, monkeypatch, tmp_path):
        import utils.profile_manager as pm
        monkeypatch.setattr(pm, "PROFILE_FILE", str(tmp_path / "none.json"))
        assert pm.load_profiles() == {}

    def test_save_load_roundtrip(self, monkeypatch, tmp_path):
        import utils.profile_manager as pm
        monkeypatch.setattr(pm, "PROFILE_FILE", str(tmp_path / "p.json"))
        data = {"AAPL": {"last_optimized": "2026-01-01",
                         "best_short_window": 5, "best_long_window": 20}}
        pm.save_profiles(data)
        assert pm.load_profiles() == data

    def test_is_stale_logic(self, monkeypatch, tmp_path):
        import utils.profile_manager as pm
        monkeypatch.setattr(pm, "PROFILE_FILE", str(tmp_path / "p.json"))
        fresh = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        old = (datetime.now() - timedelta(days=200)).strftime("%Y-%m-%d")
        pm.save_profiles({"FRESH": {"last_optimized": fresh},
                          "OLD": {"last_optimized": old}})
        assert pm.is_stale("FRESH") is False
        assert pm.is_stale("OLD") is True
        assert pm.is_stale("UNKNOWN") is True


# ================================================================ OLD: data_loader
class TestDataLoader:
    def test_downloads_when_cache_missing(self, monkeypatch, tmp_path):
        import utils.data_loader as dl
        monkeypatch.setattr(dl, "DATA_DIR", str(tmp_path))
        idx = pd.date_range("2020-01-01", periods=100, freq="D")
        fake = pd.DataFrame({"Close": np.arange(100.0)}, index=idx)
        fake.index.name = "Date"
        monkeypatch.setattr(dl.yf, "download", lambda *a, **k: fake.copy())
        out = dl.fetch_data("TEST", start="2020-01-01", end="2020-04-01")
        assert not out.empty and "Close" in out.columns

    def test_empty_on_download_failure(self, monkeypatch, tmp_path):
        import utils.data_loader as dl
        monkeypatch.setattr(dl, "DATA_DIR", str(tmp_path))
        def boom(*a, **k): raise RuntimeError("network down")
        monkeypatch.setattr(dl.yf, "download", boom)
        assert dl.fetch_data("NOPE", start="2020-01-01", end="2020-04-01").empty


# ================================================================ NEW: Alpaca data source (StockHistoricalDataClient mocked)
class TestAlpacaData:
    @staticmethod
    def _fake_client(df, raise_exc=None):
        class FakeBars:
            def __init__(self, d): self.df = d
        class FakeClient:
            def __init__(self): self.requests = []
            def get_stock_bars(self, request):
                self.requests.append(request)
                if raise_exc:
                    raise raise_exc
                return FakeBars(df)
        return FakeClient()

    @staticmethod
    def _alpaca_df(ticker, n=50):
        """Mimics alpaca-py's bars.df: MultiIndex (symbol, timestamp[UTC]) with
        lowercase OHLCV columns."""
        idx = pd.MultiIndex.from_product(
            [[ticker], pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")],
            names=["symbol", "timestamp"],
        )
        return pd.DataFrame({
            "open": np.linspace(100, 150, n),
            "high": np.linspace(101, 151, n),
            "low": np.linspace(99, 149, n),
            "close": np.linspace(100, 150, n),
            "volume": np.arange(n, dtype=float),
        }, index=idx)

    def test_returns_normalized_frame(self, monkeypatch):
        import utils.alpaca_data as ad
        monkeypatch.setattr(ad, "_get_client",
                            lambda: self._fake_client(self._alpaca_df("AAPL", 50)))
        out = ad.fetch_data("AAPL", start="2024-01-01", end="2024-03-01")
        assert not out.empty
        assert "Close" in out.columns          # lowercase 'close' -> 'Close'
        assert len(out) == 50
        assert out.index.name == "Date"
        assert isinstance(out.index, pd.DatetimeIndex)
        assert out.index.tz is None             # tz stripped to match yfinance

    def test_empty_response_returns_empty(self, monkeypatch):
        import utils.alpaca_data as ad
        monkeypatch.setattr(ad, "_get_client", lambda: self._fake_client(pd.DataFrame()))
        assert ad.fetch_data("AAPL", "2024-01-01", "2024-02-01").empty

    def test_api_error_returns_empty(self, monkeypatch):
        import utils.alpaca_data as ad
        monkeypatch.setattr(ad, "_get_client",
                            lambda: self._fake_client(None, raise_exc=RuntimeError("api down")))
        assert ad.fetch_data("AAPL", "2024-01-01", "2024-02-01").empty

    def test_output_feeds_combo_strategy(self, monkeypatch):
        # Proves the Alpaca frame is a true drop-in: it flows through the exact
        # strategy the live scanner runs, producing Signal/RSI columns.
        import utils.alpaca_data as ad
        from strategies.ma_rsi_combo import apply_combo_strategy
        monkeypatch.setattr(ad, "_get_client",
                            lambda: self._fake_client(self._alpaca_df("AAPL", 300)))
        out = ad.fetch_data("AAPL")
        result = apply_combo_strategy(out, short_window=5, long_window=20, rsi_window=14)
        assert "Signal" in result.columns and "RSI" in result.columns
        assert set(result["Signal"].dropna().unique()).issubset({0, 1})


# ================================================================ OLD: researcher
class TestResearcher:
    def test_update_profile_writes_combo(self, monkeypatch):
        import research.researcher as rsr
        saved = {}
        monkeypatch.setattr(rsr, "load_profiles", lambda: {})
        monkeypatch.setattr(rsr, "save_profiles", lambda d: saved.update(d))
        rsr.update_profile("AAPL", 5, 20)
        assert saved["AAPL"]["best_short_window"] == 5
        assert saved["AAPL"]["best_long_window"] == 20
        assert saved["AAPL"]["strategy"] == "Combo"

    def test_cycle_optimizes_stale(self, monkeypatch):
        import research.researcher as rsr
        got = []
        monkeypatch.setattr(rsr, "is_stale", lambda t: True)
        monkeypatch.setattr(rsr, "run_optimization", lambda *a, **k: (10, 40))
        monkeypatch.setattr(rsr, "update_profile",
                            lambda t, s, l: got.append((t, s, l)))
        rsr.run_research_cycle(["AAPL", "MSFT"])
        assert got == [("AAPL", 10, 40), ("MSFT", 10, 40)]

    def test_cycle_skips_fresh(self, monkeypatch):
        import research.researcher as rsr
        def fail(*a, **k): raise AssertionError("optimizer must not run on fresh")
        monkeypatch.setattr(rsr, "is_stale", lambda t: False)
        monkeypatch.setattr(rsr, "run_optimization", fail)
        rsr.run_research_cycle(["AAPL"])


# ================================================================ OLD: run_optimizer
class TestRunOptimizer:
    def test_returns_none_on_empty(self, monkeypatch):
        import research.run_optimizer as opt
        monkeypatch.setattr(opt, "fetch_data", lambda *a, **k: pd.DataFrame())
        assert opt.run_optimization("X", "2022-01-01", "2023-01-01") == (None, None)

    def test_returns_int_params(self, monkeypatch):
        import research.run_optimizer as opt
        idx = pd.date_range("2019-01-01", "2023-01-01", freq="D")
        t = np.arange(len(idx))
        df = pd.DataFrame({"Close": 100 + 0.05 * t + 10 * np.sin(t / 15.0)}, index=idx)
        monkeypatch.setattr(opt, "fetch_data", lambda *a, **k: df.copy())
        bs, bl = opt.run_optimization("X", "2021-01-01", "2022-12-31", strategy="Combo")
        assert isinstance(bs, int) and isinstance(bl, int) and bs < bl


# ================================================================ OLD: portfolio
class TestPortfolioSimulator:
    def test_run_and_summary(self, monkeypatch):
        import research.portfolio as pf
        idx = pd.date_range("2021-01-01", periods=400, freq="D")
        def fake_fetch(ticker, start, end, *a, **k):
            t = np.arange(400)
            return pd.DataFrame({"Close": 100 + 0.2 * t + 5 * np.sin(t / 12.0)}, index=idx)
        monkeypatch.setattr(pf, "fetch_data", fake_fetch)
        sim = pf.PortfolioSimulator(["AAPL", "MSFT"], "2021-01-01", "2022-01-01",
                                    initial_equity=100000.0, strategy="Combo")
        dfp = sim.run_simulation()
        assert "Portfolio_Equity" in dfp.columns
        s = sim.portfolio_summary(dfp)
        for k in ("Total Portfolio Return", "Final Portfolio Balance",
                  "Top Performing Stock"):
            assert k in s


# ================================================================ OLD: visualize1
class TestVisualize:
    def test_dashboard_builds_without_show(self, monkeypatch):
        import matplotlib.pyplot as plt
        import utils.visualize1 as viz
        from strategies.ma_rsi_combo import apply_combo_strategy
        monkeypatch.setattr(plt, "show", lambda *a, **k: None)
        t = np.arange(120)
        df = apply_combo_strategy(make_price_df(100 + 0.5 * t + 8 * np.sin(t / 10.0)),
                                  short_window=5, long_window=20, rsi_window=14)
        viz.plot_combo_signals(df, "TEST")     # must not raise
        plt.close("all")


# ================================================================ import smoke
def test_entrypoint_modules_import():
    for m in ("main", "run_portfolio", "research.portfolio", "research.run_optimizer",
              "research.researcher", "research.backtest", "utils.visualize1",
              "utils.data_loader", "utils.profile_manager", "strategy_config",
              "config", "engine.scanner", "engine.allocator", "engine.executioner",
              "engine.modes", "utils.notifier"):
        importlib.import_module(m)





# ================================================================ NEW: SentimentAnalyzer (news + Claude Haiku mocked)
class TestSentiment:
    @staticmethod
    def _analyzer(headlines=None, verdict=None, llm_raises=False, news_raises=False):
        from engine.sentiment import SentimentAnalyzer
        a = SentimentAnalyzer()

        class FakeNewsItem:
            def __init__(self, h): self.headline = h
        class FakeNewsSet:
            def __init__(self, items): self.data = {"news": items}
        class FakeNewsClient:
            def get_news(self, req):
                if news_raises:
                    raise RuntimeError("news api down")
                return FakeNewsSet([FakeNewsItem(h) for h in (headlines or [])])

        class FakeParsed:
            def __init__(self, v): self.parsed_output = v
        class FakeMessages:
            def parse(self, **kwargs):
                if llm_raises:
                    raise RuntimeError("anthropic down")
                return FakeParsed(verdict)
        class FakeLLM:
            messages = FakeMessages()

        a._news_client = FakeNewsClient()
        a._llm = FakeLLM()
        return a

    def test_no_news_returns_neutral(self):
        v = self._analyzer(headlines=[]).get_verdict("AAPL")
        assert v.sentiment_multiplier == 1.0 and v.veto is False and v.headlines == []

    def test_news_api_failure_returns_neutral(self):
        v = self._analyzer(news_raises=True).get_verdict("AAPL")
        assert v.sentiment_multiplier == 1.0 and v.veto is False

    def test_llm_failure_returns_neutral_but_keeps_headlines(self):
        v = self._analyzer(headlines=["Big news"], llm_raises=True).get_verdict("AAPL")
        assert v.sentiment_multiplier == 1.0 and v.veto is False
        assert v.headlines == ["Big news"]          # evidence survives the failure

    def test_happy_path_carries_verdict_and_evidence(self):
        from engine.sentiment import SentimentVerdict
        good = SentimentVerdict(sentiment_multiplier=1.4, veto=False, rationale="strong earnings")
        v = self._analyzer(headlines=["Beats earnings"], verdict=good).get_verdict("NVDA")
        assert v.sentiment_multiplier == pytest.approx(1.4)
        assert v.headlines == ["Beats earnings"]

    def test_multiplier_is_clamped(self):
        from engine.sentiment import SentimentVerdict
        wild = SentimentVerdict(sentiment_multiplier=3.0, veto=False, rationale="moon")
        assert self._analyzer(headlines=["H"], verdict=wild).get_verdict("N").sentiment_multiplier == 1.5
        low = SentimentVerdict(sentiment_multiplier=0.1, veto=False, rationale="doom")
        assert self._analyzer(headlines=["H"], verdict=low).get_verdict("N").sentiment_multiplier == 0.5

    def test_veto_passes_through(self):
        from engine.sentiment import SentimentVerdict
        bad = SentimentVerdict(sentiment_multiplier=0.5, veto=True, rationale="SEC investigation")
        assert self._analyzer(headlines=["SEC probe"], verdict=bad).get_verdict("XYZ").veto is True

    def test_headlines_are_age_annotated(self):
        from engine.sentiment import SentimentAnalyzer
        from datetime import datetime, timedelta, timezone
        a = SentimentAnalyzer()
        class Item:
            headline = "Fresh story"
            created_at = datetime.now(timezone.utc) - timedelta(hours=3)
        class NewsSet:
            data = {"news": [Item()]}
        class Client:
            def get_news(self, req): return NewsSet()
        a._news_client = Client()
        [h] = a.fetch_headlines("NVDA")
        assert h.startswith("[3h ago]") and "Fresh story" in h


    def test_stale_headlines_are_dropped(self):
        from engine.sentiment import SentimentAnalyzer
        from datetime import datetime, timedelta, timezone
        a = SentimentAnalyzer()
        now = datetime.now(timezone.utc)
        class Item:
            def __init__(self, h, age_h):
                self.headline = h
                self.created_at = now - timedelta(hours=age_h)
        class NewsSet:
            data = {"news": [Item("Fresh", 2), Item("Ancient", 772)]}
        class Client:
            def get_news(self, req): return NewsSet()
        a._news_client = Client()
        headlines = a.fetch_headlines("MU", hours=24)
        assert any("Fresh" in h for h in headlines)
        assert not any("Ancient" in h for h in headlines)


    def test_summary_is_appended_to_headline(self):
        from engine.sentiment import SentimentAnalyzer
        from datetime import datetime, timezone
        a = SentimentAnalyzer()
        class Item:
            headline = "Meta beats on earnings"
            summary = "Meta reported Q3 revenue above estimates, driven by ad growth."
            created_at = datetime.now(timezone.utc)
        class NewsSet:
            data = {"news": [Item()]}
        class Client:
            def get_news(self, req): return NewsSet()
        a._news_client = Client()
        [h] = a.fetch_headlines("META")
        assert "Meta beats on earnings" in h
        assert "ad growth" in h          # the summary reached the prompt string

    def test_long_summary_is_truncated(self):
        from engine.sentiment import SentimentAnalyzer
        from datetime import datetime, timezone
        a = SentimentAnalyzer()
        class Item:
            headline = "Big news"
            summary = "x" * 1000
            created_at = datetime.now(timezone.utc)
        class NewsSet:
            data = {"news": [Item()]}
        class Client:
            def get_news(self, req): return NewsSet()
        a._news_client = Client()
        [h] = a.fetch_headlines("NVDA", summary_chars=50)
        assert h.endswith("…")
        assert len(h) < 200              # bounded, not the full 1000 chars




        # ================================================================ NEW: V5.0 trading modes
class TestTradingModes:
    def test_all_modes_well_formed(self):
        from engine.modes import TRADING_MODES
        for name in ("V4_Legacy", "Aggressive", "Swing", "Long_Term", "Volatile"):
            m = TRADING_MODES[name]
            assert m.name == name
            assert m.ma_short < m.ma_long
            assert 0 < m.rsi_buy_threshold <= 100
            assert m.conviction_min <= m.conviction_max
            assert 0 <= m.cash_reserve_pct < 1

    def test_v4_legacy_matches_v4_behavior(self):
        # Backward-compat guard: V4_Legacy must equal the deployed V4.0 constants.
        from engine.modes import TRADING_MODES, DEFAULT_MODE
        import config
        assert DEFAULT_MODE == "V4_Legacy"        # the rollback anchor
        s = TRADING_MODES["V4_Legacy"]
        assert s.trailing_stop_percent == config.TRAILING_STOP_PERCENT
        assert s.cash_reserve_pct == config.CASH_RESERVE_PCT
        assert s.sentiment_enabled is True        # SENTIMENT_MODE == "live"
        assert s.rsi_buy_threshold == 55          # current hardcoded combo threshold
        assert s.allow_multi_entry is False       # current single-entry
        assert s.signal_stop_loss_pct == -0.15    # V4.0 kept the combo hard stop

    def test_v4_legacy_is_not_researched_per_mode(self):
        # V4_Legacy must stay OUT of the grids, or the research cycle would write
        # best_windows['V4_Legacy'] and shadow the legacy flat windows.
        from engine.modes import MODE_GRIDS
        assert "V4_Legacy" not in MODE_GRIDS

    def test_long_term_holds_with_no_stop(self):
        from engine.modes import TRADING_MODES
        lt = TRADING_MODES["Long_Term"]
        assert lt.trailing_stop_percent is None
        assert lt.exit_on_trend_reversal is True
        assert lt.sentiment_enabled is True
        assert lt.conviction_min == 1.0 and lt.conviction_max == 1.0

    def test_settings_are_immutable(self):
        import dataclasses
        from engine.modes import TRADING_MODES
        with pytest.raises(dataclasses.FrozenInstanceError):
            TRADING_MODES["Swing"].ma_short = 999


class TestModeResolver:
    def test_named_mode_resolves(self):
        from engine.modes import ModeResolver
        assert ModeResolver("Aggressive").settings_for().name == "Aggressive"

    def test_unknown_mode_defaults_to_v4_legacy(self):
        from engine.modes import ModeResolver
        assert ModeResolver("does-not-exist").settings_for().name == "V4_Legacy"

    def test_auto_uses_profile_best_mode(self):
        from engine.modes import ModeResolver
        s = ModeResolver("Auto").settings_for(profile={"best_mode": "Volatile"})
        assert s.name == "Volatile"

    def test_auto_falls_back_to_v4_legacy(self):
        from engine.modes import ModeResolver
        assert ModeResolver("Auto").settings_for(profile={}).name == "V4_Legacy"
        assert ModeResolver("Auto").settings_for(profile=None).name == "V4_Legacy"

    def test_v4_legacy_inherits_legacy_per_ticker_windows(self):
        # Backward compat: V4_Legacy (default) uses the ticker's V4.0-optimized windows.
        from engine.modes import ModeResolver
        s = ModeResolver("V4_Legacy").settings_for(
            profile={"best_short_window": 7, "best_long_window": 33})
        assert s.ma_short == 7 and s.ma_long == 33

    def test_swing_ignores_legacy_flat_windows(self):
        # Swing is a preset now, NOT the V4 anchor — it must not inherit the flat
        # free-searched windows.
        from engine.modes import ModeResolver, TRADING_MODES
        s = ModeResolver("Swing").settings_for(
            profile={"best_short_window": 7, "best_long_window": 33})
        assert s.ma_short == TRADING_MODES["Swing"].ma_short       # 20, not 7
        assert s.ma_long == TRADING_MODES["Swing"].ma_long         # 50, not 33

    def test_non_default_mode_ignores_legacy_flat_windows(self):
        from engine.modes import ModeResolver, TRADING_MODES
        s = ModeResolver("Long_Term").settings_for(
            profile={"best_short_window": 7, "best_long_window": 33})
        assert s.ma_short == TRADING_MODES["Long_Term"].ma_short   # 50, not 7
        assert s.ma_long == TRADING_MODES["Long_Term"].ma_long     # 200, not 33

    def test_per_mode_researched_windows_win(self):
        from engine.modes import ModeResolver
        s = ModeResolver("Long_Term").settings_for(
            profile={"best_windows": {"Long_Term": {"short": 60, "long": 250}}})
        assert s.ma_short == 60 and s.ma_long == 250

    def test_auto_combines_best_mode_and_its_windows(self):
        from engine.modes import ModeResolver
        s = ModeResolver("Auto").settings_for(profile={
            "best_mode": "Aggressive",
            "best_windows": {"Aggressive": {"short": 8, "long": 24}},
        })
        assert s.name == "Aggressive" and s.ma_short == 8 and s.ma_long == 24


# ================================================================ NEW: V5.0 combo mode thresholds
class TestComboModeThresholds:
    def _oscillating_uptrend(self, n=400, amp=20.0):
        # Rising trend (MA_short > MA_long) with a big oscillation so RSI both
        # dips below the buy line and runs above the overbought line.
        t = np.arange(n)
        return make_price_df(100 + 0.2 * t + amp * np.sin(t / 8.0))

    def test_default_params_reproduce_v4_signals(self):
        # Backward-compat guard: new defaults == the old hardcoded behavior.
        from strategies.ma_rsi_combo import apply_combo_strategy
        df = self._oscillating_uptrend()
        a = apply_combo_strategy(df.copy(), short_window=5, long_window=20, rsi_window=14)
        b = apply_combo_strategy(df.copy(), short_window=5, long_window=20, rsi_window=14,
                                 rsi_buy_threshold=55, sell_on_overbought=False,
                                 stop_loss_pct=-0.15)
        assert (a["Signal"].values == b["Signal"].values).all()

    def test_lower_buy_threshold_never_buys_more(self):
        from strategies.ma_rsi_combo import apply_combo_strategy
        df = self._oscillating_uptrend()
        loose = apply_combo_strategy(df.copy(), 5, 20, 14, rsi_buy_threshold=55)
        strict = apply_combo_strategy(df.copy(), 5, 20, 14, rsi_buy_threshold=35)
        # A deeper (lower) entry threshold requires deeper dips -> at most as many buy bars.
        assert (strict["Signal"] == 1).sum() <= (loose["Signal"] == 1).sum()

    def test_sell_on_overbought_forces_exit(self):
        from strategies.ma_rsi_combo import apply_combo_strategy
        df = self._oscillating_uptrend()
        held = apply_combo_strategy(df.copy(), 5, 20, 14, sell_on_overbought=False)
        assert held["RSI"].max() >= 70                      # precondition: series reaches overbought
        scalped = apply_combo_strategy(df.copy(), 5, 20, 14,
                                       sell_on_overbought=True, rsi_sell_threshold=70)
        assert (scalped["Signal"] == 1).sum() <= (held["Signal"] == 1).sum()   # never holds more
        assert (scalped["Signal"].values != held["Signal"].values).any()        # and it changed something

    def test_none_stop_disables_signal_stop(self):
        from strategies.ma_rsi_combo import apply_combo_strategy
        # Long sustained rise (MA_long ends far BELOW price, so a pullback cannot
        # trigger the MA cross-down exit), then a sharp ~17% decline. RSI falls
        # under 55 a few bars into the decline -> entry; price then keeps falling,
        # so the -5% signal stop is the ONLY exit that can fire. With stop=None
        # the position is held through the whole decline.
        prices = list(np.linspace(100, 400, 300)) + list(np.linspace(400, 330, 25))
        df = make_price_df(prices)
        tight = apply_combo_strategy(df.copy(), 5, 200, 14, stop_loss_pct=-0.05)
        nostop = apply_combo_strategy(df.copy(), 5, 200, 14, stop_loss_pct=None)

        held_nostop = (nostop["Signal"] == 1).sum()
        held_tight = (tight["Signal"] == 1).sum()
        assert held_nostop > 0                  # precondition: an entry actually happened
        assert held_nostop > held_tight         # the -5% stop cut the position short
        assert (nostop["Signal"].values != tight["Signal"].values).any()
        for out in (tight, nostop):
            assert "Entry_Price" not in out.columns and "Trade_Return" not in out.columns



# ================================================================ NEW: V5.0 mode-driven controller behavior
class TestControllerModes(TestControllerOrchestration):
    def test_v4_legacy_is_the_baseline(self, monkeypatch):
        lc, h = self._wire(monkeypatch, {"latest_signal": 1, "previous_signal": 0,
            "current_price": 200.0, "current_rsi": 40.0}, held=False, mode="V4_Legacy")
        lc.run_live_pipeline()
        assert h["exec"].buys == [("AAPL", 42)]     # fresh-crossover buy, baseline size
        # (stop attachment is covered by test_protection_pass_attaches_trailing_stop)

    def test_long_term_attaches_no_stop(self, monkeypatch):
        lc, h = self._wire(monkeypatch, {"latest_signal": 1, "previous_signal": 1,
            "current_price": 200.0, "current_rsi": 50.0}, held=True, mode="Long_Term")
        lc.run_live_pipeline()
        assert h["exec"].stops == [("AAPL", None)]           # executioner skips on None

    def test_long_term_uses_veto_only_sentiment(self, monkeypatch):
        from engine.sentiment import SentimentReport
        bullish = SentimentReport(sentiment_multiplier=1.5, veto=False,
                                  rationale="great", headlines=[])
        lc, h = self._wire(monkeypatch, {"latest_signal": 1, "previous_signal": 0,
            "current_price": 200.0, "current_rsi": 30.0}, held=False,
            sentiment_report=bullish, sentiment_mode="live", mode="Long_Term")
        lc.run_live_pipeline()
        # 1.0x, not 63 — Long_Term's 1.0/1.0 band pins the multiplier.
        assert h["exec"].buys == [("AAPL", 42)]

    def test_long_term_still_honors_veto(self, monkeypatch):
        from engine.sentiment import SentimentReport
        toxic = SentimentReport(sentiment_multiplier=0.5, veto=True,
                                rationale="fraud probe", headlines=[])
        lc, h = self._wire(monkeypatch, {"latest_signal": 1, "previous_signal": 0,
            "current_price": 200.0, "current_rsi": 30.0}, held=False,
            sentiment_report=toxic, sentiment_mode="live", mode="Long_Term")
        lc.run_live_pipeline()
        # The veto is the ONLY entry protection a stopless Long_Term buy has.
        assert h["exec"].buys == []

    def test_hold_through_when_exit_flag_off(self, monkeypatch):
        lc, h = self._wire(monkeypatch, {"latest_signal": 0, "previous_signal": 1,
            "current_price": 180.0, "current_rsi": 60.0}, held=True, mode="V4_Legacy")
        import engine.modes as mm
        from dataclasses import replace
        holder = replace(mm.TRADING_MODES["V4_Legacy"], exit_on_trend_reversal=False)
        monkeypatch.setitem(mm.TRADING_MODES, "V4_Legacy", holder)
        lc.run_live_pipeline()
        assert h["exec"].sells == []                         # reversal ignored

    def test_waiting_message_names_the_real_blocker(self, monkeypatch):
        # Multi-entry modes must NOT claim they need a trend reset — they can
        # re-arm on an RSI recovery. Here RSI dipped but is still falling.
        lc, h = self._wire(monkeypatch, {"latest_signal": 1, "previous_signal": 1,
            "current_price": 200.0, "current_rsi": 40.0, "previous_rsi": 45.0},
            held=False, mode="Aggressive")
        lc.run_live_pipeline()
        sent = " ".join(h["notifier"].msgs).lower()
        assert "trend reset" not in sent
        assert "still falling" in sent

    def test_single_entry_message_still_says_trend_reset(self, monkeypatch):
        lc, h = self._wire(monkeypatch, {"latest_signal": 1, "previous_signal": 1,
            "current_price": 200.0, "current_rsi": 40.0, "previous_rsi": 45.0},
            held=False, mode="V4_Legacy")
        lc.run_live_pipeline()
        assert "trend reset" in " ".join(h["notifier"].msgs).lower()

    def test_multi_entry_requires_rsi_turning_up(self, monkeypatch):
        # Aggressive allows re-entry, but RSI still FALLING must not buy.
        lc, h = self._wire(monkeypatch, {"latest_signal": 1, "previous_signal": 1,
            "current_price": 200.0, "current_rsi": 40.0, "previous_rsi": 45.0},
            held=False, mode="Aggressive")
        lc.run_live_pipeline()
        assert h["exec"].buys == []

    def test_multi_entry_buys_the_recovery(self, monkeypatch):
        lc, h = self._wire(monkeypatch, {"latest_signal": 1, "previous_signal": 1,
            "current_price": 200.0, "current_rsi": 45.0, "previous_rsi": 40.0},
            held=False, mode="Aggressive")
        lc.run_live_pipeline()
        assert len(h["exec"].buys) == 1                      # RSI dipped and turned up

    def test_multi_entry_never_adds_to_an_open_position(self, monkeypatch):
        # Re-entry is FLAT-only: holding the name must never trigger a second buy
        # (that would be scale-in/pyramiding, which this system does not do).
        lc, h = self._wire(monkeypatch, {"latest_signal": 1, "previous_signal": 1,
            "current_price": 200.0, "current_rsi": 45.0, "previous_rsi": 40.0},
            held=True, mode="Aggressive")
        lc.run_live_pipeline()
        assert h["exec"].buys == []

    def test_v4_legacy_single_entry_unchanged(self, monkeypatch):
        # Same setup as the recovery test, but V4_Legacy must NOT re-enter.
        lc, h = self._wire(monkeypatch, {"latest_signal": 1, "previous_signal": 1,
            "current_price": 200.0, "current_rsi": 45.0, "previous_rsi": 40.0},
            held=False, mode="V4_Legacy")
        lc.run_live_pipeline()
        assert h["exec"].buys == []

# ================================================================ NEW: V5.0 per-mode research
class TestPerModeOptimizer:
    @staticmethod
    def _fake_df(n=900):
        idx = pd.date_range("2021-01-01", periods=n, freq="D")
        t = np.arange(n)
        return pd.DataFrame({"Close": 100 + 0.15 * t + 12 * np.sin(t / 20.0)}, index=idx)

    def test_mode_grids_cover_researched_modes(self):
        # Every mode EXCEPT V4_Legacy is researched per-mode; V4_Legacy's windows
        # come from the legacy flat profile fields instead.
        from engine.modes import TRADING_MODES, MODE_GRIDS
        assert set(MODE_GRIDS) == set(TRADING_MODES) - {"V4_Legacy"}
        for shorts, longs in MODE_GRIDS.values():
            assert min(shorts) < max(longs)

    def test_optimize_for_mode_stays_in_its_window_family(self, monkeypatch):
        import research.run_optimizer as opt
        from engine.modes import MODE_GRIDS
        monkeypatch.setattr(opt, "fetch_data", lambda *a, **k: self._fake_df())
        rec = opt.optimize_for_mode("X", "Long_Term", "2022-01-01", "2023-06-01",
                                    verbose=False)
        shorts, longs = MODE_GRIDS["Long_Term"]
        assert rec["short"] in shorts and rec["long"] in longs

    def test_unknown_mode_returns_none(self, monkeypatch):
        import research.run_optimizer as opt
        monkeypatch.setattr(opt, "fetch_data", lambda *a, **k: self._fake_df())
        assert opt.optimize_for_mode("X", "NotAMode", "2022-01-01", "2023-01-01") is None

    def test_select_best_mode_picks_top_score(self, monkeypatch):
        import research.run_optimizer as opt
        from engine.modes import MODE_GRIDS
        monkeypatch.setattr(opt, "fetch_data", lambda *a, **k: self._fake_df())
        best, records = opt.select_best_mode("X", "2022-01-01", "2023-06-01",
                                             verbose=False)
        assert best in MODE_GRIDS
        assert records[best]["score"] == max(r["score"] for r in records.values())


class TestProfileSchemaV5:
    def test_update_profile_preserves_v5_fields(self, monkeypatch, tmp_path):
        import utils.profile_manager as pm
        import research.researcher as rsr
        monkeypatch.setattr(pm, "PROFILE_FILE", str(tmp_path / "p.json"))
        pm.save_profiles({"AAPL": {"best_mode": "Volatile",
                                   "best_windows": {"Volatile": {"short": 15, "long": 40}}}})
        rsr.update_profile("AAPL", 20, 50)
        saved = pm.load_profiles()["AAPL"]
        assert saved["best_short_window"] == 20        # legacy fields updated
        assert saved["best_mode"] == "Volatile"        # V5 fields survived the merge
        assert saved["best_windows"]["Volatile"]["short"] == 15

    def test_update_mode_research_writes_schema(self, monkeypatch, tmp_path):
        import utils.profile_manager as pm
        import research.researcher as rsr
        monkeypatch.setattr(pm, "PROFILE_FILE", str(tmp_path / "p.json"))
        records = {
            "Swing": {"short": 20, "long": 50, "score": 1.0,
                      "return_pct": 10.0, "max_dd_pct": -10.0},
            "Volatile": {"short": 15, "long": 40, "score": 2.5,
                         "return_pct": 25.0, "max_dd_pct": -10.0},
        }
        rsr.update_mode_research("NVDA", "Volatile", records)
        saved = pm.load_profiles()["NVDA"]
        assert saved["best_mode"] == "Volatile"
        assert saved["best_windows"]["Volatile"] == {"short": 15, "long": 40}
        assert saved["best_windows"]["Swing"] == {"short": 20, "long": 50}
        assert saved["mode_scores"]["Volatile"]["score"] == 2.5

    def test_resolver_reads_migrated_schema(self, monkeypatch, tmp_path):
        # End-to-end: research output feeds the Phase-1 resolver.
        from engine.modes import ModeResolver
        profile = {"best_mode": "Volatile",
                   "best_windows": {"Volatile": {"short": 15, "long": 40}}}
        s = ModeResolver("Auto").settings_for(profile)
        assert s.name == "Volatile" and s.ma_short == 15 and s.ma_long == 40


class TestResearchCycleModes:
    def test_per_mode_cycle_records_winner(self, monkeypatch):
        import research.researcher as rsr
        got = {}
        monkeypatch.setattr(rsr, "is_stale", lambda t: True)
        monkeypatch.setattr(rsr, "select_best_mode",
                            lambda t, s, e: ("Volatile", {"Volatile": {
                                "short": 15, "long": 40, "score": 2.0,
                                "return_pct": 20.0, "max_dd_pct": -10.0}}))
        monkeypatch.setattr(rsr, "update_mode_research",
                            lambda t, m, r: got.__setitem__(t, m))
        rsr.run_research_cycle(["NVDA"], per_mode=True)
        assert got == {"NVDA": "Volatile"}

    def test_legacy_cycle_still_default(self, monkeypatch):
        import research.researcher as rsr
        got = []
        monkeypatch.setattr(rsr, "is_stale", lambda t: True)
        monkeypatch.setattr(rsr, "run_optimization", lambda *a, **k: (10, 40))
        monkeypatch.setattr(rsr, "update_profile", lambda t, s, l: got.append((t, s, l)))
        rsr.run_research_cycle(["AAPL"])            # per_mode defaults False
        assert got == [("AAPL", 10, 40)]



# ================================================================ documented exclusions
@pytest.mark.skip(reason="Manual live-account scripts: they touch Alpaca at import "
                         "(v3_first_order.py even places an order). Not unit-testable "
                         "without real credentials.")
def test_live_scripts_excluded():
    pass