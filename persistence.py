"""
persistence.py — Save and restore alert engine state to/from a JSON file.

Called from main.py on startup (load) and graceful shutdown (save),
so tracked asset ranges survive bot restarts.
"""

import json
import os
from typing import TYPE_CHECKING

import config
from logger import get_logger

if TYPE_CHECKING:
    from alert_engine import AlertEngine

log = get_logger("persistence")


def save_state(engine: "AlertEngine") -> None:
    """
    Serialise the alert engine's tracked assets to PERSISTENCE_FILE.
    Writes atomically via a temp file to avoid corruption on crash.
    """
    details = engine.get_asset_details()
    payload = {
        "version": 1,
        "assets": [
            {
                "name": d["name"],
                "min_price": d["min"],
                "max_price": d["max"],
            }
            for d in details
        ],
    }

    tmp_path = config.PERSISTENCE_FILE + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp_path, config.PERSISTENCE_FILE)
        log.info("State saved → %s (%d assets)", config.PERSISTENCE_FILE, len(details))
    except OSError as exc:
        log.error("Failed to save state: %s", exc)
    finally:
        # Clean up temp file if replace failed
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def load_state(engine: "AlertEngine") -> int:
    """
    Load tracked assets from PERSISTENCE_FILE into the alert engine.
    Returns the number of assets restored.
    Silently skips the file if it doesn't exist or is malformed.
    """
    if not os.path.exists(config.PERSISTENCE_FILE):
        log.info("No persistence file found at %s — starting fresh", config.PERSISTENCE_FILE)
        return 0

    try:
        with open(config.PERSISTENCE_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)

        assets = payload.get("assets", [])
        restored = 0
        for entry in assets:
            name = entry.get("name", "").upper()
            min_p = float(entry["min_price"])
            max_p = float(entry["max_price"])
            if name and min_p < max_p:
                engine.add_asset(name, min_p, max_p)
                restored += 1
            else:
                log.warning("Skipping invalid entry in state file: %s", entry)

        log.info("Restored %d asset(s) from %s", restored, config.PERSISTENCE_FILE)
        return restored

    except (json.JSONDecodeError, KeyError, ValueError, OSError) as exc:
        log.error("Failed to load state from %s: %s", config.PERSISTENCE_FILE, exc)
        return 0
