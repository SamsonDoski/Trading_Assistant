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


# ================================================================ NEW: allocator
class TestAllocator:
    def test_calculate_shares(self):
        from engine.allocator import PortfolioAllocator
        a = PortfolioAllocator()
        assert a.calculate_shares(200.0) == 25
        # no cap -> full $5k
        assert a.calculate_shares(200.0, buying_power=3000) == 15  # capped to $3k
        assert a.calculate_shares(200.0, buying_power=100) == 0    # can't afford one share
        assert a.calculate_shares(200.0, buying_power=0) == 0
        assert a.calculate_shares(0) == 0.0
        assert a.calculate_shares(None) == 0.0

    def test_legacy_generate_buy_orders(self):
        from engine.allocator import PortfolioAllocator
        orders = PortfolioAllocator().generate_buy_orders(
            ["AAPL", "MSFT"], {"AAPL": 100.0, "MSFT": 0})
        assert orders["AAPL"] == 50.0 and "MSFT" not in orders


# ================================================================ NEW: scanner
class TestScanner:
    def test_get_signals_contract(self, monkeypatch):
        import engine.scanner as sm
        t = np.arange(400)
        fake = make_price_df(100 + 0.5 * t + 8 * np.sin(t / 10.0))
        monkeypatch.setattr(sm, "fetch_data", lambda *a, **k: fake.copy())
        d = sm.StrategyScanner().get_signals("AAPL", 5, 20, 14)
        assert set(d) == {"latest_signal", "previous_signal",
                          "current_price", "current_rsi"}
        assert d["latest_signal"] in (0, 1)
        assert 0 <= d["current_rsi"] <= 100

    def test_get_signals_empty_returns_none(self, monkeypatch):
        import engine.scanner as sm
        monkeypatch.setattr(sm, "fetch_data", lambda *a, **k: pd.DataFrame())
        assert sm.StrategyScanner().get_signals("X", 5, 20, 14) is None


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
    def _client_cls(positions, open_order_symbols=(), buying_power="100000", closed_stopouts=()):
        class FakePos:
            def __init__(self, sym, plpc, qty):
                self.symbol, self.unrealized_plpc, self.qty = sym, plpc, qty
                self.avg_entry_price = "100.0"
        class FakeOrder:
            def __init__(self, sym, oid):
                self.symbol, self.id = sym, oid
        class FakeClosed:
            def __init__(self, sym, qty, price, coid=""):
                self.symbol, self.filled_qty, self.filled_avg_price = sym, qty, price
                self.order_type, self.status = "trailing_stop", "filled"
                self.client_order_id = coid
        class FakeAccount:
            def __init__(self): self.non_marginable_buying_power = buying_power
        class FakeClient:
            def __init__(self, *a, **k):
                self.submitted, self.closed, self.canceled = [], [], []
                self._pos = [FakePos(s, plpc, qty) for s, (plpc, qty) in positions.items()]
                self._orders = [FakeOrder(s, f"oid-{s}") for s in open_order_symbols]
                self._closed = [FakeClosed(*c) for c in closed_stopouts]
            def get_all_positions(self): return self._pos
            def get_account(self): return FakeAccount()
            def get_orders(self, filter=None):
                if "closed" in str(getattr(filter, "status", "")).lower():
                    return list(self._closed)
                syms = getattr(filter, "symbols", None)
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

    def test_held_symbols(self, monkeypatch):
        import engine.executioner as em
        monkeypatch.setattr(em, "TradingClient",
                            self._client_cls({"AAPL": ("0.05", "10"), "MU": ("0.1", "3")}))
        ex = em.AlpacaExecutioner("k", "s", paper=True)
        assert set(ex.held_symbols()) == {"AAPL", "MU"}

    def test_trailing_stop_attached_when_unprotected(self, monkeypatch):
        import engine.executioner as em
        monkeypatch.setattr(em, "TradingClient", self._client_cls({"AAPL": ("0.05", "10")}))
        ex = em.AlpacaExecutioner("k", "s", paper=True)
        assert ex.ensure_trailing_stop("AAPL", 8.0) is True
        assert len(ex.api.submitted) == 1            # a trailing stop was placed
        assert "AAPL" in ex._open_order_symbols       # cached so we don't stack
        assert ex.ensure_trailing_stop("AAPL", 8.0) is False   # now a no-op
        assert len(ex.api.submitted) == 1

    def test_trailing_stop_skipped_when_already_protected(self, monkeypatch):
        import engine.executioner as em
        monkeypatch.setattr(em, "TradingClient",
                            self._client_cls({"AAPL": ("0.05", "10")}, open_order_symbols=["AAPL"]))
        ex = em.AlpacaExecutioner("k", "s", paper=True)
        assert ex.ensure_trailing_stop("AAPL", 8.0) is False
        assert ex.api.submitted == []                 # nothing placed

    def test_trailing_stop_skipped_when_not_held(self, monkeypatch):
        import engine.executioner as em
        monkeypatch.setattr(em, "TradingClient", self._client_cls({"AAPL": ("0.05", "10")}))
        ex = em.AlpacaExecutioner("k", "s", paper=True)
        assert ex.ensure_trailing_stop("MSFT", 8.0) is False

    def test_liquidate_cancels_open_orders_first(self, monkeypatch):
        import engine.executioner as em
        monkeypatch.setattr(em, "TradingClient",
                            self._client_cls({"AAPL": ("0.05", "10")}, open_order_symbols=["AAPL"]))
        ex = em.AlpacaExecutioner("k", "s", paper=True)
        ex.liquidate_position("AAPL")
        assert ex.api.canceled == ["oid-AAPL"]        # cancelled the protective stop...
        assert ex.api.closed == ["AAPL"]              # ...then closed the position

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
        assert pl_pct == pytest.approx(2.0)      # 900 -> 918 = +2%
        assert pl_usd == pytest.approx(144.0)    # 18 * 8 shares

    def test_position_fetch_failure_raises(self, monkeypatch):
        import engine.executioner as em
        class BoomClient:
            def __init__(self, *a, **k): pass
            def get_all_positions(self): raise RuntimeError("request timed out")
        monkeypatch.setattr(em, "TradingClient", BoomClient)
        monkeypatch.setattr(em.time, "sleep", lambda *a, **k: None)   # no real waiting
        with pytest.raises(Exception):
            em.AlpacaExecutioner("k", "s", paper=True)   # __init__ calls refresh_positions


# ================================================================ NEW: run_live_pipeline() state machine (all modules faked)
class TestControllerOrchestration:
    def _wire(self, monkeypatch, signals, held, buying_power=1_000_000.0):
        import live_controller as lc
        class FakeScanner:
            def get_signals(self, *a, **k): return signals
        class FakeAllocator:
            def calculate_shares(self, price, buying_power=None):
                if buying_power is not None and buying_power < price:
                    return 0
                return 42
        class FakeNotifier:
            def __init__(self): self.msgs = []
            def send_message(self, m): self.msgs.append(m)
        class FakeExec:
            def __init__(self, *a, **k):
                self.buys, self.sells, self.stops = [], [], []
            def is_holding(self, t): return held
            def get_unrealized_pl_pct(self, t): return 3.0
            def get_buying_power(self): return buying_power
            def execute_market_buy(self, t, q): self.buys.append((t, q))
            def liquidate_position(self, t): self.sells.append(t)
            def refresh_positions(self): pass
            def refresh_open_orders(self): pass
            def held_symbols(self): return ["AAPL"] if held else []
            def get_recent_stopouts(self, hours=24): return []
            def ensure_trailing_stop(self, t, pct):
                self.stops.append((t, pct)); return True
        holder = {}
        monkeypatch.setattr(lc, "load_profiles", lambda: {
            "AAPL": {"best_short_window": 5, "best_long_window": 20, "rsi_period": 14}})
        monkeypatch.setattr(lc, "is_stale", lambda t: False)
        monkeypatch.setattr(lc, "StrategyScanner", FakeScanner)
        monkeypatch.setattr(lc, "PortfolioAllocator", FakeAllocator)
        monkeypatch.setattr(lc, "DiscordNotifier", FakeNotifier)
        monkeypatch.setattr(lc.time, "sleep", lambda *a, **k: None)
        def make_exec(*a, **k):
            holder["exec"] = FakeExec(); return holder["exec"]
        monkeypatch.setattr(lc, "AlpacaExecutioner", make_exec)
        return lc, holder

    def test_buy_on_fresh_crossover(self, monkeypatch):
        lc, h = self._wire(monkeypatch, {"latest_signal": 1, "previous_signal": 0,
            "current_price": 200.0, "current_rsi": 40.0}, held=False)
        lc.run_live_pipeline()
        assert h["exec"].buys == [("AAPL", 42)] and h["exec"].sells == []

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
        assert h["exec"].stops == [("AAPL", lc.TRAILING_STOP_PERCENT)]


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
              "utils.notifier"):
        importlib.import_module(m)


# ================================================================ documented exclusions
@pytest.mark.skip(reason="Manual live-account scripts: they touch Alpaca at import "
                         "(v3_first_order.py even places an order). Not unit-testable "
                         "without real credentials.")
def test_live_scripts_excluded():
    pass