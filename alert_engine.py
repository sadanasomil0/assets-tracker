"""
alert_engine.py — Core alert logic with state-machine deduplication,
alert cooldown, and in-memory alert history.

State machine per asset:
    OUTSIDE  — price is outside the user-defined range
    INSIDE   — price has entered the range (alert was already sent)

Transitions:
    OUTSIDE → INSIDE  → triggers an alert (subject to cooldown)
    INSIDE  → INSIDE  → no-op (dedup)
    INSIDE  → OUTSIDE → resets state so next entry can trigger again
    OUTSIDE → OUTSIDE → no-op

Cooldown:
    After an alert fires for an asset, the same asset cannot fire again
    for ALERT_COOLDOWN_SECONDS seconds, even if it leaves and re-enters
    the range. This prevents spam when price oscillates at a boundary.
"""

import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Callable, Deque, Optional

import config
from logger import get_logger

log = get_logger("alert_engine")


class RangeState(Enum):
    OUTSIDE = auto()
    INSIDE = auto()


@dataclass
class AssetAlert:
    """Tracked state for a single asset."""
    name: str
    min_price: float
    max_price: float
    state: RangeState = RangeState.OUTSIDE
    last_price: Optional[float] = None
    last_alert_time: Optional[datetime] = None
    # Whether alerts for this asset are paused by the user
    paused: bool = False


@dataclass
class AlertEvent:
    """Data object passed to the alert callback and stored in history."""
    asset_name: str
    price: float
    min_price: float
    max_price: float
    timestamp: datetime


class AlertEngine:
    """
    Thread-safe alert engine that evaluates price updates against
    user-defined ranges and fires callbacks on state transitions.

    Features:
    - Deduplication via INSIDE/OUTSIDE state machine
    - Per-asset alert cooldown (configurable via config.ALERT_COOLDOWN_SECONDS)
    - In-memory alert history (capped at config.ALERT_HISTORY_MAX)
    - Per-asset pause/resume
    - save/load via persistence module
    """

    def __init__(self, on_alert: Callable[[AlertEvent], None]) -> None:
        self._lock = threading.Lock()
        self._assets: dict[str, AssetAlert] = {}
        self._on_alert = on_alert
        self._history: Deque[AlertEvent] = deque(maxlen=config.ALERT_HISTORY_MAX)
        # Global pause flag — silences ALL alerts when True
        self._globally_paused: bool = False

    # ── Pause / Resume ───────────────────────────────────────────────────

    def pause_all(self) -> None:
        """Pause all alert notifications globally."""
        with self._lock:
            self._globally_paused = True
        log.info("All alerts paused globally")

    def resume_all(self) -> None:
        """Resume all alert notifications globally."""
        with self._lock:
            self._globally_paused = False
        log.info("All alerts resumed globally")

    def is_paused(self) -> bool:
        with self._lock:
            return self._globally_paused

    # ── Asset management ─────────────────────────────────────────────────

    def add_asset(self, name: str, min_price: float, max_price: float) -> None:
        """Add or update a tracked asset with a price range."""
        name = name.upper()
        with self._lock:
            if name in self._assets:
                existing = self._assets[name]
                existing.min_price = min_price
                existing.max_price = max_price
                existing.state = RangeState.OUTSIDE  # reset on range change
                log.info("Updated range for %s: $%.4f – $%.4f", name, min_price, max_price)
            else:
                self._assets[name] = AssetAlert(
                    name=name, min_price=min_price, max_price=max_price
                )
                log.info("Added asset %s: $%.4f – $%.4f", name, min_price, max_price)

    def remove_asset(self, name: str) -> bool:
        """Remove a tracked asset. Returns True if it existed."""
        name = name.upper()
        with self._lock:
            if name in self._assets:
                del self._assets[name]
                log.info("Removed asset %s", name)
                return True
            return False

    def get_tracked_assets(self) -> dict[str, tuple[float, float]]:
        """Return {name: (min, max)} for all tracked assets."""
        with self._lock:
            return {
                name: (a.min_price, a.max_price)
                for name, a in self._assets.items()
            }

    def get_asset_details(self) -> list[dict]:
        """Return detailed info for all tracked assets (for /list command and persistence)."""
        with self._lock:
            result = []
            for a in self._assets.values():
                result.append({
                    "name": a.name,
                    "min": a.min_price,
                    "max": a.max_price,
                    "state": a.state.name,
                    "last_price": a.last_price,
                    "last_alert": a.last_alert_time.isoformat() if a.last_alert_time else None,
                    "paused": a.paused,
                })
            return result

    def get_asset_price(self, name: str) -> Optional[float]:
        """Return the latest known price for an asset, or None if unavailable."""
        name = name.upper()
        with self._lock:
            asset = self._assets.get(name)
            return asset.last_price if asset else None

    # ── Alert History ────────────────────────────────────────────────────

    def get_alert_history(self, limit: int = 10) -> list[AlertEvent]:
        """Return up to `limit` most-recent alert events (newest first)."""
        with self._lock:
            events = list(self._history)
        events.reverse()
        return events[:limit]

    # ── Price evaluation ─────────────────────────────────────────────────

    def on_price_update(self, name: str, price: float) -> None:
        """
        Called by fetchers whenever a new price is received.
        Evaluates the state machine and fires the alert callback if needed.
        """
        name = name.upper()
        with self._lock:
            asset = self._assets.get(name)
            if asset is None:
                return  # not tracked

            asset.last_price = price
            in_range = asset.min_price <= price <= asset.max_price

            if in_range and asset.state == RangeState.OUTSIDE:
                # Check global pause
                if self._globally_paused or asset.paused:
                    log.debug("%s would alert at $%.4f but is paused", name, price)
                    asset.state = RangeState.INSIDE  # still update state
                    return

                # Check cooldown
                if asset.last_alert_time is not None:
                    now_utc = datetime.now(timezone.utc)
                    elapsed = (now_utc - asset.last_alert_time).total_seconds()
                    if elapsed < config.ALERT_COOLDOWN_SECONDS:
                        remaining = int(config.ALERT_COOLDOWN_SECONDS - elapsed)
                        log.debug(
                            "%s in range but cooldown active (%ds remaining)", name, remaining
                        )
                        asset.state = RangeState.INSIDE
                        return

                # Price just entered the range → fire alert
                asset.state = RangeState.INSIDE
                now = datetime.now(timezone.utc)
                asset.last_alert_time = now
                event = AlertEvent(
                    asset_name=name,
                    price=price,
                    min_price=asset.min_price,
                    max_price=asset.max_price,
                    timestamp=now,
                )
                self._history.append(event)
                log.info(
                    "🔔 ALERT: %s entered range [$%.4f – $%.4f] at $%.4f",
                    name, asset.min_price, asset.max_price, price,
                )
                # Release lock before callback to avoid deadlocks
                self._lock.release()
                try:
                    self._on_alert(event)
                finally:
                    self._lock.acquire()

            elif not in_range and asset.state == RangeState.INSIDE:
                # Price exited the range → reset for re-alerting
                asset.state = RangeState.OUTSIDE
                log.debug(
                    "%s exited range at $%.4f — state reset to OUTSIDE", name, price
                )
