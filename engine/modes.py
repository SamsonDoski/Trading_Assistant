"""
V5.0 trading modes: named bundles of signal parameters + behavior flags, plus a
resolver that picks the active bundle per ticker.

Backward-compat: "V4_Legacy" == deployed V4.0 and is the SHIP-DARK safety anchor
and rollback value. It is NOT a preset: its windows come from the legacy flat
per-ticker fields (best_short_window/best_long_window), which V4.0 free-searched
over {5..50}x{10..400} — a space no mode grid can reproduce. "Swing" is a real
swing-trading preset with its own researched grid, and therefore is NOT V4.0.

The intended production end-state is "Auto" (each ticker's researched best mode),
which fixes V4.0's incoherence of applying one uniform swing-like behavior to
windows that actually span aggressive -> long-term families.
"""
from dataclasses import dataclass, replace

DEFAULT_MODE = "V4_Legacy"



@dataclass(frozen=True)
class ModeSettings:
    """Immutable settings bundle for one trading mode. Read via dot-access and
    threaded through the pipeline; frozen so no module can mutate shared state."""
    name: str
    # --- entry ---
    ma_short: int
    ma_long: int
    rsi_window: int
    rsi_buy_threshold: float          # buy when RSI dips below this (replaces the old hardcoded 55)
    allow_multi_entry: bool           # re-enter on later RSI-recovery dips in an uptrend
    reentry_cooldown_days: int        # min days between entries in one name (guards multi-entry)
    # --- exit ---
    exit_on_trend_reversal: bool      # sell when MA_short crosses below MA_long
    trailing_stop_percent: float | None   # broker trailing-stop width; None = no stop
    sell_on_overbought: bool          # optional take-profit at rsi_sell_threshold
    rsi_sell_threshold: float
    # --- sizing / capital ---
    sentiment_enabled: bool           # apply the Haiku multiplier + veto on entries
    conviction_min: float             # sentiment multiplier clamp band
    conviction_max: float
    cash_reserve_pct: float
    allow_fractional: bool
    signal_stop_loss_pct: float | None    # combo signal-level hard stop; None = rely on the broker stop



# Grid-search space per mode: (short_windows, long_windows). Each mode is tuned
# ONLY within its own window family, so a "Long_Term" search can never return
# aggressive windows. Consumed by research/run_optimizer.optimize_for_mode.
# V4_Legacy is deliberately ABSENT: it is not researched per-mode — its windows
# come from the legacy flat profile fields. Including it here would make the
# research cycle write best_windows['V4_Legacy'], which would then shadow those
# flat fields and break the V4.0 anchor.
MODE_GRIDS = {
    "Aggressive": ([5, 8, 10, 12], [20, 25, 30, 40]),
    "Swing":      ([15, 20, 25],   [40, 50, 60]),
    "Long_Term":  ([40, 50, 60],   [150, 200, 250]),
    "Volatile":   ([10, 15, 20],   [35, 40, 50]),
}


TRADING_MODES = {
    # Exact deployed V4.0 behavior; the rollback anchor. Its ma_short/ma_long here
    # are placeholders — the resolver overrides them with each ticker's legacy flat
    # windows (this is the DEFAULT mode, so the flat-field bridge applies).
    "V4_Legacy": ModeSettings(
        name="V4_Legacy",
        ma_short=20, ma_long=50, rsi_window=14, rsi_buy_threshold=55,
        allow_multi_entry=False, reentry_cooldown_days=0,
        exit_on_trend_reversal=True, trailing_stop_percent=15.0,
        sell_on_overbought=False, rsi_sell_threshold=70,
        sentiment_enabled=True, conviction_min=0.5, conviction_max=1.5,
        cash_reserve_pct=0.15, allow_fractional=True,
        signal_stop_loss_pct=-0.15,
    ),
    "Aggressive": ModeSettings(
        name="Aggressive",
        ma_short=10, ma_long=30, rsi_window=10, rsi_buy_threshold=55,
        allow_multi_entry=True, reentry_cooldown_days=2,
        exit_on_trend_reversal=True, trailing_stop_percent=6.0,
        sell_on_overbought=True, rsi_sell_threshold=80,
        sentiment_enabled=True, conviction_min=0.5, conviction_max=1.8,
        cash_reserve_pct=0.10, allow_fractional=True,
        # Aggressive:  after rsi_sell_threshold=80,
        signal_stop_loss_pct=None,
    ),
    "Swing": ModeSettings(          # a real swing preset with its own grid — NOT V4.0
        name="Swing",
        ma_short=20, ma_long=50, rsi_window=14, rsi_buy_threshold=55,
        allow_multi_entry=False, reentry_cooldown_days=0,
        exit_on_trend_reversal=True, trailing_stop_percent=15.0,
        sell_on_overbought=False, rsi_sell_threshold=70,
        sentiment_enabled=True, conviction_min=0.5, conviction_max=1.5,
        cash_reserve_pct=0.15, allow_fractional=True,
        signal_stop_loss_pct=None,      # consolidated: the trailing stop is the only protection
    ),
    "Long_Term": ModeSettings(      # hold until the 50/200 trend reverses; no stops
        name="Long_Term",
        ma_short=50, ma_long=200, rsi_window=14, rsi_buy_threshold=40,
        allow_multi_entry=False, reentry_cooldown_days=0,
        exit_on_trend_reversal=True, trailing_stop_percent=None,
        sell_on_overbought=False, rsi_sell_threshold=70,
        sentiment_enabled=True, conviction_min=1.0, conviction_max=1.0,
        cash_reserve_pct=0.05, allow_fractional=True,
        # Long_Term:   after rsi_sell_threshold=70,
        signal_stop_loss_pct=None,
    ),
    "Volatile": ModeSettings(       # high-vol names (TSLA/NVDA): wide stop, room to breathe
        name="Volatile",
        ma_short=15, ma_long=40, rsi_window=14, rsi_buy_threshold=45,
        allow_multi_entry=True, reentry_cooldown_days=3,
        exit_on_trend_reversal=True, trailing_stop_percent=18.0,
        sell_on_overbought=False, rsi_sell_threshold=70,
        sentiment_enabled=True, conviction_min=0.5, conviction_max=1.5,
        cash_reserve_pct=0.20, allow_fractional=True,
        # Volatile:    after rsi_sell_threshold=70,
        signal_stop_loss_pct=None,
    ),
}


class ModeResolver:
    """Resolves the active ModeSettings for a ticker.

    active_mode is a mode name ("V4_Legacy"/"Aggressive"/"Swing"/"Long_Term"/
    "Volatile") or "Auto" (use each ticker's researched best_mode). Unknown names
    fall back to the default (V4_Legacy), so an unrecognized setting degrades to
    exact deployed V4.0 behavior rather than to an unvalidated preset.
    """

    def __init__(self, active_mode, modes=None, default=DEFAULT_MODE):
        self.active_mode = active_mode
        self.modes = modes or TRADING_MODES
        self.default = default

    def mode_name_for(self, profile=None):
        if self.active_mode == "Auto":
            name = (profile or {}).get("best_mode", self.default)
        else:
            name = self.active_mode
        return name if name in self.modes else self.default

    def settings_for(self, profile=None):
        """Ready-to-use ModeSettings for one ticker, with MA windows and RSI period
        resolved by the precedence rules below."""
        name = self.mode_name_for(profile)
        settings = self.modes[name]
        short, long = self._resolve_windows(settings, name, profile)
        rsi_window = self._resolve_rsi_window(settings, name, profile)
        if (short, long, rsi_window) != (settings.ma_short, settings.ma_long, settings.rsi_window):
            settings = replace(settings, ma_short=short, ma_long=long, rsi_window=rsi_window)
        return settings

    def _resolve_rsi_window(self, settings, name, profile):
        """Same rule as the window bridge: V4.0 read a flat `rsi_period` off the
        profile, so it belongs to the DEFAULT (V4_Legacy) mode."""
        profile = profile or {}
        if name == self.default:
            rsi = profile.get("rsi_period")
            if rsi is not None:
                return rsi
        return settings.rsi_window

    def portfolio_settings(self):
        """Account-level settings (cash reserve) for the whole run. These cannot be
        per-ticker — one budget can't honor 24 different reserves — so Auto uses
        the default mode's account policy."""
        name = self.active_mode if self.active_mode in self.modes else self.default
        return self.modes[name]

    def _resolve_windows(self, settings, name, profile):
        """MA-window precedence:
        1. Phase-4 per-mode researched windows: profile['best_windows'][name].
        2. The legacy flat optimized windows (mode-agnostic, free-searched in V4.0)
           belong to the DEFAULT (V4_Legacy) mode, so V4_Legacy == V4.0 exactly.
           This is a permanent branch, not transitional: V4_Legacy is defined as
           "whatever the legacy free search chose", and it is excluded from
           MODE_GRIDS so nothing ever writes best_windows['V4_Legacy'] to shadow it.
        3. Otherwise the mode's own default windows."""
        profile = profile or {}
        per_mode = (profile.get("best_windows") or {}).get(name)
        if per_mode:
            return (per_mode.get("short", settings.ma_short),
                    per_mode.get("long", settings.ma_long))
        if name == self.default:
            short = profile.get("best_short_window")
            long = profile.get("best_long_window")
            if short is not None and long is not None:
                return short, long
        return settings.ma_short, settings.ma_long