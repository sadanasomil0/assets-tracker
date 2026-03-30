"""
tests/test_alert_engine.py — Unit tests for the alert engine state machine.

Run with:
    python -m pytest tests/test_alert_engine.py -v
"""

import sys
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alert_engine import AlertEngine, AlertEvent, RangeState
import config


class TestAlertEngine:
    """Tests for AlertEngine state transitions and dedup logic."""

    def setup_method(self):
        """Fresh engine + captured alerts for each test.
        
        Cooldown is patched to 0 for most tests so re-entry is always allowed.
        Use TestAlertEngineCooldown for cooldown-specific tests.
        """
        self.alerts: list[AlertEvent] = []
        self.engine = AlertEngine(on_alert=lambda e: self.alerts.append(e))

    # ── Basic state transitions ──────────────────────────────────────────

    def test_outside_to_inside_triggers_alert(self):
        """Price entering the range should fire exactly one alert."""
        with patch.object(config, "ALERT_COOLDOWN_SECONDS", 0):
            self.engine.add_asset("BTC", 80000, 90000)
            self.engine.on_price_update("BTC", 85000)  # enters range

        assert len(self.alerts) == 1
        assert self.alerts[0].asset_name == "BTC"
        assert self.alerts[0].price == 85000

    def test_inside_to_inside_no_duplicate(self):
        """Price staying inside range should NOT fire additional alerts."""
        with patch.object(config, "ALERT_COOLDOWN_SECONDS", 0):
            self.engine.add_asset("BTC", 80000, 90000)
            self.engine.on_price_update("BTC", 85000)  # enter → alert
            self.engine.on_price_update("BTC", 86000)  # still inside → no alert
            self.engine.on_price_update("BTC", 89999)  # still inside → no alert

        assert len(self.alerts) == 1

    def test_inside_to_outside_resets(self):
        """Price exiting range should reset state so re-entry triggers again."""
        with patch.object(config, "ALERT_COOLDOWN_SECONDS", 0):
            self.engine.add_asset("BTC", 80000, 90000)
            self.engine.on_price_update("BTC", 85000)  # enter → alert
            self.engine.on_price_update("BTC", 95000)  # exit → reset
            self.engine.on_price_update("BTC", 82000)  # re-enter → alert again

        assert len(self.alerts) == 2

    def test_outside_to_outside_no_alert(self):
        """Price staying outside should produce no alerts."""
        with patch.object(config, "ALERT_COOLDOWN_SECONDS", 0):
            self.engine.add_asset("BTC", 80000, 90000)
            self.engine.on_price_update("BTC", 50000)
            self.engine.on_price_update("BTC", 55000)
            self.engine.on_price_update("BTC", 95000)

        assert len(self.alerts) == 0

    # ── Boundary conditions ──────────────────────────────────────────────

    def test_price_at_min_boundary_is_inside(self):
        """Price exactly at min_price should be considered inside."""
        with patch.object(config, "ALERT_COOLDOWN_SECONDS", 0):
            self.engine.add_asset("ETH", 1700, 2200)
            self.engine.on_price_update("ETH", 1700)

        assert len(self.alerts) == 1

    def test_price_at_max_boundary_is_inside(self):
        """Price exactly at max_price should be considered inside."""
        with patch.object(config, "ALERT_COOLDOWN_SECONDS", 0):
            self.engine.add_asset("ETH", 1700, 2200)
            self.engine.on_price_update("ETH", 2200)

        assert len(self.alerts) == 1

    def test_price_just_below_min_is_outside(self):
        """Price just below min should not trigger."""
        with patch.object(config, "ALERT_COOLDOWN_SECONDS", 0):
            self.engine.add_asset("ETH", 1700, 2200)
            self.engine.on_price_update("ETH", 1699.99)

        assert len(self.alerts) == 0

    def test_price_just_above_max_is_outside(self):
        """Price just above max should not trigger."""
        with patch.object(config, "ALERT_COOLDOWN_SECONDS", 0):
            self.engine.add_asset("ETH", 1700, 2200)
            self.engine.on_price_update("ETH", 2200.01)

        assert len(self.alerts) == 0

    # ── Asset management ─────────────────────────────────────────────────

    def test_add_asset(self):
        self.engine.add_asset("GOLD", 2900, 3200)
        tracked = self.engine.get_tracked_assets()
        assert "GOLD" in tracked
        assert tracked["GOLD"] == (2900, 3200)

    def test_remove_asset(self):
        self.engine.add_asset("GOLD", 2900, 3200)
        assert self.engine.remove_asset("GOLD") is True
        assert self.engine.remove_asset("GOLD") is False  # already removed
        assert "GOLD" not in self.engine.get_tracked_assets()

    def test_update_range_resets_state(self):
        """Updating an asset's range should reset state to OUTSIDE."""
        with patch.object(config, "ALERT_COOLDOWN_SECONDS", 0):
            self.engine.add_asset("BTC", 80000, 90000)
            self.engine.on_price_update("BTC", 85000)  # inside → INSIDE state
            assert len(self.alerts) == 1

            # Update range — state resets to OUTSIDE
            self.engine.add_asset("BTC", 80000, 88000)
            self.engine.on_price_update("BTC", 85000)  # re-enters → alert again
            assert len(self.alerts) == 2

    def test_untracked_asset_ignored(self):
        """Price update for an untracked asset should be silently ignored."""
        self.engine.on_price_update("UNKNOWN", 100)
        assert len(self.alerts) == 0

    def test_case_insensitive_names(self):
        """Asset names should be case-insensitive."""
        with patch.object(config, "ALERT_COOLDOWN_SECONDS", 0):
            self.engine.add_asset("btc", 80000, 90000)
            self.engine.on_price_update("Btc", 85000)

        assert len(self.alerts) == 1
        assert self.alerts[0].asset_name == "BTC"

    # ── Multiple assets ──────────────────────────────────────────────────

    def test_multiple_assets_independent(self):
        """Alerts for different assets should be independent."""
        with patch.object(config, "ALERT_COOLDOWN_SECONDS", 0):
            self.engine.add_asset("BTC", 80000, 90000)
            self.engine.add_asset("ETH", 1700, 2200)

            self.engine.on_price_update("BTC", 85000)  # BTC enters
            self.engine.on_price_update("ETH", 1500)   # ETH outside
            self.engine.on_price_update("ETH", 2000)   # ETH enters

        assert len(self.alerts) == 2
        assert self.alerts[0].asset_name == "BTC"
        assert self.alerts[1].asset_name == "ETH"

    def test_get_asset_details(self):
        """get_asset_details should return comprehensive info."""
        with patch.object(config, "ALERT_COOLDOWN_SECONDS", 0):
            self.engine.add_asset("BTC", 80000, 90000)
            self.engine.on_price_update("BTC", 85000)

        details = self.engine.get_asset_details()
        assert len(details) == 1
        d = details[0]
        assert d["name"] == "BTC"
        assert d["state"] == "INSIDE"
        assert d["last_price"] == 85000
        assert d["last_alert"] is not None

    # ── Alert history ────────────────────────────────────────────────────

    def test_alert_stored_in_history(self):
        """Triggered alerts should appear in get_alert_history()."""
        with patch.object(config, "ALERT_COOLDOWN_SECONDS", 0):
            self.engine.add_asset("BTC", 80000, 90000)
            self.engine.on_price_update("BTC", 85000)

        history = self.engine.get_alert_history(limit=10)
        assert len(history) == 1
        assert history[0].asset_name == "BTC"

    def test_history_newest_first(self):
        """get_alert_history should return newest events first."""
        with patch.object(config, "ALERT_COOLDOWN_SECONDS", 0):
            self.engine.add_asset("BTC", 80000, 90000)
            self.engine.add_asset("ETH", 1700, 2200)
            self.engine.on_price_update("BTC", 85000)
            self.engine.on_price_update("ETH", 2000)

        history = self.engine.get_alert_history(limit=10)
        assert history[0].asset_name == "ETH"
        assert history[1].asset_name == "BTC"

    # ── Pause / Resume ───────────────────────────────────────────────────

    def test_pause_suppresses_alerts(self):
        """Paused engine should not fire alert callbacks."""
        with patch.object(config, "ALERT_COOLDOWN_SECONDS", 0):
            self.engine.add_asset("BTC", 80000, 90000)
            self.engine.pause_all()
            self.engine.on_price_update("BTC", 85000)

        assert len(self.alerts) == 0

    def test_resume_re_enables_alerts(self):
        """Resuming after pause should allow alerts to fire again."""
        with patch.object(config, "ALERT_COOLDOWN_SECONDS", 0):
            self.engine.add_asset("BTC", 80000, 90000)
            self.engine.pause_all()
            self.engine.on_price_update("BTC", 85000)  # paused → no alert, state=INSIDE
            self.engine.on_price_update("BTC", 95000)  # exits → OUTSIDE
            self.engine.resume_all()
            self.engine.on_price_update("BTC", 85000)  # re-enters → alert fires

        assert len(self.alerts) == 1


class TestAlertEngineCooldown:
    """Tests specifically for the cooldown behaviour."""

    def setup_method(self):
        self.alerts: list[AlertEvent] = []
        self.engine = AlertEngine(on_alert=lambda e: self.alerts.append(e))

    def test_cooldown_blocks_rapid_reentry(self):
        """Re-entry within cooldown period should NOT fire another alert."""
        with patch.object(config, "ALERT_COOLDOWN_SECONDS", 300):
            self.engine.add_asset("BTC", 80000, 90000)
            self.engine.on_price_update("BTC", 85000)  # alert fires
            self.engine.on_price_update("BTC", 95000)  # exits
            self.engine.on_price_update("BTC", 85000)  # re-enters — blocked by cooldown

        assert len(self.alerts) == 1

    def test_cooldown_zero_allows_immediate_reentry(self):
        """With cooldown=0, re-entry should always fire."""
        with patch.object(config, "ALERT_COOLDOWN_SECONDS", 0):
            self.engine.add_asset("BTC", 80000, 90000)
            self.engine.on_price_update("BTC", 85000)  # alert
            self.engine.on_price_update("BTC", 95000)  # exit
            self.engine.on_price_update("BTC", 85000)  # re-enter → alert

        assert len(self.alerts) == 2

    def test_cooldown_expired_allows_reentry(self):
        """After cooldown expires, re-entry should fire again."""
        with patch.object(config, "ALERT_COOLDOWN_SECONDS", 300):
            self.engine.add_asset("BTC", 80000, 90000)
            self.engine.on_price_update("BTC", 85000)  # alert fires
            # Manually backdate the last_alert_time past cooldown
            asset = self.engine._assets["BTC"]
            asset.last_alert_time = datetime.now(timezone.utc) - timedelta(seconds=301)
            self.engine.on_price_update("BTC", 95000)  # exits
            self.engine.on_price_update("BTC", 85000)  # re-enters after cooldown

        assert len(self.alerts) == 2
