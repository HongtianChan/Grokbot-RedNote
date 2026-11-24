#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Polite rate limits and a daily cap, stored locally."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Asia/Macau")
except Exception:  # pragma: no cover - macOS 3.9 should have zoneinfo
    TZ = None

STATE_DIR = Path.home() / "Library" / "Application Support" / "Grokbot-RedNote"
STATE_FILE = STATE_DIR / "state.json"
SETTINGS_FILE = STATE_DIR / "settings.json"

# Defaults (also used until settings.json exists). The live values are
# reloaded from SETTINGS_FILE on every remaining()/check call.
DAILY_NOTE_CAP = 40
DAILY_SEARCH_CAP = 50
DAILY_ENRICH_CAP = 20
MIN_DELAY_SEC = 6.0
MAX_DELAY_SEC = 10.0

_DEFAULT_SETTINGS = {
    "search_cap": 50,
    "note_cap": 40,
    "enrich_cap": 20,
    "min_delay_sec": 6.0,
    "max_delay_sec": 10.0,
}


def today_key() -> str:
    if TZ is not None:
        return datetime.now(TZ).date().isoformat()
    return datetime.now().date().isoformat()


def _default_state() -> dict:
    return {
        "date": today_key(),
        "searches": 0,
        "notes": 0,
        "enrichments": 0,
    }


def _clamp_int(value: Any, lo: int, hi: int, default: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _clamp_float(value: Any, lo: float, hi: float, default: float) -> float:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _normalize_settings(raw: Optional[dict]) -> dict:
    data = raw if isinstance(raw, dict) else {}
    # Development: if search_cap is absent or null, there is no daily search cap.
    # Restore the clamp-only line below before launch if you want a default cap.
    if "search_cap" not in data or data.get("search_cap") is None:
        search_cap = None
    else:
        search_cap = _clamp_int(data.get("search_cap"), 1, 1000, 50)
    note_cap = _clamp_int(data.get("note_cap", DAILY_NOTE_CAP), 1, 1000, 40)
    enrich_cap = _clamp_int(data.get("enrich_cap", DAILY_ENRICH_CAP), 1, 1000, 20)
    min_delay = _clamp_float(data.get("min_delay_sec", MIN_DELAY_SEC), 0.5, 120.0, 6.0)
    max_delay = _clamp_float(data.get("max_delay_sec", MAX_DELAY_SEC), 0.5, 120.0, 10.0)
    if max_delay < min_delay:
        max_delay = min_delay
    return {
        "search_cap": search_cap,
        "note_cap": note_cap,
        "enrich_cap": enrich_cap,
        "min_delay_sec": min_delay,
        "max_delay_sec": max_delay,
    }


def _apply_settings(settings: dict) -> dict:
    global DAILY_SEARCH_CAP, DAILY_NOTE_CAP, DAILY_ENRICH_CAP, MIN_DELAY_SEC, MAX_DELAY_SEC
    settings = _normalize_settings(settings)
    if settings["search_cap"] is not None:
        DAILY_SEARCH_CAP = int(settings["search_cap"])
    DAILY_NOTE_CAP = int(settings["note_cap"])
    DAILY_ENRICH_CAP = int(settings["enrich_cap"])
    MIN_DELAY_SEC = float(settings["min_delay_sec"])
    MAX_DELAY_SEC = float(settings["max_delay_sec"])
    return settings


def load_settings() -> dict:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if not SETTINGS_FILE.is_file():
        return _apply_settings(dict(_DEFAULT_SETTINGS))
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _apply_settings(dict(_DEFAULT_SETTINGS))
    return _apply_settings(data if isinstance(data, dict) else dict(_DEFAULT_SETTINGS))


def save_settings(settings: dict) -> dict:
    settings = _apply_settings(settings)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    to_write = dict(settings)
    # Do not write search_cap when it is unset (no daily cap).
    if to_write.get("search_cap") is None:
        to_write.pop("search_cap", None)
    tmp = SETTINGS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(to_write, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(SETTINGS_FILE)
    return settings


def update_settings(payload: dict) -> dict:
    current = load_settings()
    if not isinstance(payload, dict):
        raise ValueError("Settings must be a JSON object.")
    for key in ("search_cap", "note_cap", "enrich_cap", "min_delay_sec", "max_delay_sec"):
        if key in payload:
            current[key] = payload[key]
    return {**save_settings(current), **remaining()}


def load_state() -> dict:
    load_settings()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if not STATE_FILE.is_file():
        return _default_state()
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default_state()
    if not isinstance(data, dict) or data.get("date") != today_key():
        return _default_state()
    data.setdefault("searches", 0)
    data.setdefault("notes", 0)
    data.setdefault("enrichments", 0)
    return data


def save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)


def remaining() -> dict:
    settings = load_settings()
    state = load_state()
    search_cap = settings["search_cap"]  # None means no daily search cap
    note_cap = int(settings["note_cap"])
    enrich_cap = int(settings["enrich_cap"])
    used = int(state["searches"])
    return {
        "date": state["date"],
        "searches_used": used,
        "notes_used": int(state["notes"]),
        "enrichments_used": int(state.get("enrichments", 0)),
        "searches_left": None if search_cap is None else max(0, int(search_cap) - used),
        "notes_left": max(0, note_cap - int(state["notes"])),
        "enrichments_left": max(0, enrich_cap - int(state.get("enrichments", 0))),
        "search_cap": search_cap,
        "note_cap": note_cap,
        "enrich_cap": enrich_cap,
        "min_delay_sec": float(settings["min_delay_sec"]),
        "max_delay_sec": float(settings["max_delay_sec"]),
    }


class RateLimitError(RuntimeError):
    pass


def check_search() -> None:
    # Development: search cap enforcement disabled. Restore before launch.
    return
    info = remaining()
    if info["search_cap"] is None:
        return
    if info["searches_left"] <= 0:
        raise RateLimitError(
            "Daily search cap reached (%d). Try again tomorrow." % info["search_cap"]
        )


def check_note() -> None:
    info = remaining()
    if info["notes_left"] <= 0:
        raise RateLimitError(
            "Daily note cap reached (%d). Try again tomorrow." % info["note_cap"]
        )


def record_search() -> dict:
    state = load_state()
    state["searches"] = int(state.get("searches", 0)) + 1
    save_state(state)
    return remaining()


def record_note() -> dict:
    state = load_state()
    state["notes"] = int(state.get("notes", 0)) + 1
    save_state(state)
    return remaining()


def check_enrich() -> None:
    info = remaining()
    if info["enrichments_left"] <= 0:
        raise RateLimitError(
            "Daily enrichment cap reached (%d). Try again tomorrow." % info["enrich_cap"]
        )


def record_enrich() -> dict:
    state = load_state()
    state["enrichments"] = int(state.get("enrichments", 0)) + 1
    save_state(state)
    return remaining()


def status_text() -> str:
    info = remaining()
    if info["search_cap"] is None:
        search_part = "searches %d used, no daily cap" % info["searches_used"]
    else:
        search_part = "searches %d/%d left" % (info["searches_left"], info["search_cap"])
    return "Today %s  ·  %s  ·  notes %d/%d left  ·  enrich %d/%d left" % (
        info["date"],
        search_part,
        info["notes_left"],
        info["note_cap"],
        info["enrichments_left"],
        info["enrich_cap"],
    )
