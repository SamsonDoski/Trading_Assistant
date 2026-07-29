"""
V5.0 trading modes: named bundles of signal parameters + behavior flags, plus a
resolver that picks the active bundle per ticker.

Nothing imports this yet (Phase 1). Phase 3 threads a resolved ModeSettings
through the controller/executioner/allocator in place of hardcoded config
constants. Backward-compat: "Swing" == deployed V4.0 and is the SHIP-DARK safety anchor,
not the destination. The intended production end-state is "Auto" (each ticker's
researched best mode), which fixes V4.0's incoherence of applying one uniform
swing-like behavior to windows that actually span aggressive -> long-term families.
"""
from dataclasses import dataclass, replace

DEFAULT_MODE = "Swing"


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


TRADING_MODES = {
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
    "Swing": ModeSettings(          # == deployed V4.0 (ship-dark anchor; production target is Auto)
        name="Swing",
        ma_short=20, ma_long=50, rsi_window=14, rsi_buy_threshold=55,
        allow_multi_entry=False, reentry_cooldown_days=0,
        exit_on_trend_reversal=True, trailing_stop_percent=15.0,
        sell_on_overbought=False, rsi_sell_threshold=70,
        sentiment_enabled=True, conviction_min=0.5, conviction_max=1.5,
        cash_reserve_pct=0.15, allow_fractional=True,
        # Swing:       after rsi_sell_threshold=70,
        signal_stop_loss_pct=-0.15,      # V4.0 anchor;
    ),
    "Long_Term": ModeSettings(      # hold until the 50/200 trend reverses; no stops
        name="Long_Term",
        ma_short=50, ma_long=200, rsi_window=14, rsi_buy_threshold=40,
        allow_multi_entry=False, reentry_cooldown_days=0,
        exit_on_trend_reversal=True, trailing_stop_percent=None,
        sell_on_overbought=False, rsi_sell_threshold=70,
        sentiment_enabled=False, conviction_min=1.0, conviction_max=1.0,
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

    active_mode is a mode name ("Aggressive"/"Swing"/"Long_Term"/"Volatile") or
    "Auto" (use each ticker's researched best_mode). Unknown names fall back to
    the default (Swing), matching the old strategy_config.get_profile behavior.
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
        """TRANSITIONAL bridge, same rule as the window bridge: V4.0 read a flat
        `rsi_period` off the profile, so it belongs to the DEFAULT (Swing) mode."""
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
        2. TRANSITIONAL backward-compat bridge: the legacy flat optimized windows
           (mode-agnostic, free-searched in V4.0) are treated as the DEFAULT
           (Swing) mode's windows, so Swing == V4.0 with today's profile schema.
           Retire this branch once Phase 4 migrates those windows into
           best_windows['Swing'].
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