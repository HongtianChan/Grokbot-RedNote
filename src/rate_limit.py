#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Daily search caps, persisted on this machine and reset at local midnight.

The default (a checkout of the public repo, with no tier flag, no
GROKBOT_REDNOTE_TIER, and no subscription.json) is FREE_SEARCH_CAP searches
per local day. Paid accounts get PAID_SEARCH_CAP. Local development or
testing can set GROKBOT_REDNOTE_DEV=1 or pass --dev for no daily cap.
Presence of a .git directory is not treated as dev mode, because a normal
clone of the public repo has one too.

The count lives outside the git checkout so restarting the app or recloning
the repo does not reset it. A signed shadow copy makes a casual edit or
delete of one file harder to abuse. A determined user who deletes every
copy can still reset a local-only limiter; there is no server.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import socket
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from local_crypto import read_json, read_text, write_json

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - macOS 3.9+ has zoneinfo
    ZoneInfo = None  # type: ignore

FREE_SEARCH_CAP = 10
PAID_SEARCH_CAP = 200

STATE_DIR = Path.home() / "Library" / "Application Support" / "Grokbot-RedNote"
STATE_FILE = STATE_DIR / "state.json"
SHADOW_DIR = Path.home() / "Library" / "Caches" / "Grokbot-RedNote"
SHADOW_FILE = SHADOW_DIR / "usage.json"
SUBSCRIPTION_FILE = STATE_DIR / "subscription.json"
SUBSCRIPTION_KEY = STATE_DIR / "subscription.key"

# Not a server secret: it only flags casual edits of the JSON files.
_APP_SALT = b"grokbot-rednote-usage-v1"
_LOCK = threading.Lock()
_cli_tier: Optional[str] = None
_cli_dev: bool = False


class RateLimitError(RuntimeError):
    def __init__(self, message: str, payload: dict[str, Any]):
        super().__init__(message)
        self.payload = payload


def configure_paths(state_dir: Path, shadow_dir: Optional[Path] = None) -> None:
    """Point storage at a temporary directory (for tests)."""
    global STATE_DIR, STATE_FILE, SHADOW_DIR, SHADOW_FILE
    global SUBSCRIPTION_FILE, SUBSCRIPTION_KEY
    STATE_DIR = Path(state_dir)
    STATE_FILE = STATE_DIR / "state.json"
    SHADOW_DIR = Path(shadow_dir) if shadow_dir is not None else (STATE_DIR / "cache")
    SHADOW_FILE = SHADOW_DIR / "usage.json"
    SUBSCRIPTION_FILE = STATE_DIR / "subscription.json"
    SUBSCRIPTION_KEY = STATE_DIR / "subscription.key"


def set_cli_tier(value: Optional[str]) -> None:
    global _cli_tier
    _cli_tier = _normalize_tier(value)


def set_cli_dev(value: bool = False) -> None:
    global _cli_dev
    _cli_dev = bool(value)


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def dev_mode_enabled() -> bool:
    """True only when local testing opts in. A .git directory is not enough."""
    return _cli_dev or _truthy_env("GROKBOT_REDNOTE_DEV")


def local_tzinfo():
    try:
        tz = datetime.now().astimezone().tzinfo
        if tz is not None:
            return tz
    except Exception:
        pass
    if ZoneInfo is not None:
        return ZoneInfo("Asia/Macau")
    return None


def tz_name() -> str:
    tz = local_tzinfo()
    if tz is None:
        return "local"
    label = getattr(tz, "key", None) or getattr(tz, "zone", None)
    if label:
        return str(label)
    name = datetime.now(tz).tzname()
    return name or "local"


def today_key() -> str:
    tz = local_tzinfo()
    if tz is not None:
        return datetime.now(tz).date().isoformat()
    return datetime.now().date().isoformat()


def machine_fingerprint() -> str:
    raw = _hardware_identity().encode("utf-8")
    return hashlib.sha256(b"grokbot-rednote-machine:" + raw).hexdigest()


def _hardware_identity() -> str:
    try:
        result = subprocess.run(
            ["/usr/sbin/ioreg", "-d2", "-c", "IOPlatformExpertDevice"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "IOPlatformUUID" in line and "=" in line:
                    return line.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass
    return socket.gethostname() or "unknown-host"


def _normalize_tier(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if text in {"paid", "subscribed", "subscription", "pro", "premium"}:
        return "paid"
    if text in {"free", "normal", "default"}:
        return "free"
    return None


def _tier_from_file() -> Optional[str]:
    for path in (SUBSCRIPTION_FILE, SUBSCRIPTION_KEY):
        if not path.is_file():
            continue
        try:
            raw = read_text(path, default="").strip()
        except OSError:
            continue
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = raw
        if isinstance(data, dict):
            return _normalize_tier(data.get("tier") or data.get("plan") or data.get("key"))
        return _normalize_tier(data)
    return None


def current_tier() -> str:
    for candidate in (_cli_tier, os.environ.get("GROKBOT_REDNOTE_TIER"), _tier_from_file()):
        # CLI is already normalized; env and file may not be.
        if candidate in {"free", "paid"}:
            return str(candidate)
        normalized = _normalize_tier(candidate)
        if normalized:
            return normalized
    if dev_mode_enabled():
        return "dev"
    return "free"


def search_cap(tier: Optional[str] = None) -> Optional[int]:
    chosen = tier or current_tier()
    if chosen == "paid":
        return PAID_SEARCH_CAP
    if chosen == "dev":
        return None
    return FREE_SEARCH_CAP


def _sign(machine: str, date: str, searches: int) -> str:
    msg = ("%s|%s|%d" % (machine, date, int(searches))).encode("utf-8")
    return hmac.new(_APP_SALT, msg, hashlib.sha256).hexdigest()


def _valid_record(data: Any, machine: str, today: str, cap: int) -> Optional[dict[str, Any]]:
    if not isinstance(data, dict):
        return None
    date = str(data.get("date") or "")
    try:
        searches = int(data.get("searches") or 0)
    except (TypeError, ValueError):
        return None
    if searches < 0:
        searches = 0
    if data.get("sig") != _sign(str(data.get("machine") or ""), date, searches):
        # Tampered copy: fail closed for this file if it claims to be today
        # on this machine. Other-machine junk is ignored.
        if str(data.get("machine") or "") == machine and date == today:
            return {
                "date": today,
                "searches": cap,
                "machine": machine,
                "tampered": True,
            }
        return None
    if str(data.get("machine") or "") != machine:
        return None
    if date != today:
        return {"date": today, "searches": 0, "machine": machine}
    return {"date": today, "searches": min(searches, 10_000), "machine": machine}


def _read_json(path: Path) -> Any:
    return read_json(path, default=None)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, payload)


def load_state() -> dict[str, Any]:
    machine = machine_fingerprint()
    today = today_key()
    cap = search_cap()
    # Tamper fail-closed needs a numeric cap; unlimited uses the free cap.
    record_cap = FREE_SEARCH_CAP if cap is None else cap
    copies = []
    for path in (STATE_FILE, SHADOW_FILE):
        record = _valid_record(_read_json(path), machine, today, record_cap)
        if record is not None:
            copies.append(record)
    if not copies:
        state = {"date": today, "searches": 0, "machine": machine}
    else:
        searches = max(int(item["searches"]) for item in copies)
        state = {"date": today, "searches": searches, "machine": machine}
    # Rewrite both copies so a deleted or stale file is restored.
    save_state(state)
    return state


def save_state(state: dict[str, Any]) -> dict[str, Any]:
    machine = str(state.get("machine") or machine_fingerprint())
    date = str(state.get("date") or today_key())
    searches = int(state.get("searches") or 0)
    payload = {
        "date": date,
        "searches": searches,
        "machine": machine,
        "sig": _sign(machine, date, searches),
    }
    _write_json(STATE_FILE, payload)
    _write_json(SHADOW_FILE, payload)
    return payload


def remaining() -> dict[str, Any]:
    with _LOCK:
        state = load_state()
        cap = search_cap()
        used = int(state["searches"])
        unlimited = cap is None
        left = None if unlimited else max(0, cap - used)
        return {
            "ok": True,
            "tier": current_tier(),
            "date": state["date"],
            "search_cap": cap,
            "searches_used": used,
            "searches_left": left,
            "limit_reached": False if unlimited else used >= cap,
            "unlimited": unlimited,
            "reset_tz": tz_name(),
            "free_search_cap": FREE_SEARCH_CAP,
            "paid_search_cap": PAID_SEARCH_CAP,
        }


def status_payload() -> dict[str, Any]:
    info = remaining()
    reached = bool(info["limit_reached"])
    info["scene"] = "limit" if reached else ""
    info["status_text"] = "今日搜索次数已用完" if reached else ""
    return info


def consume_search() -> dict[str, Any]:
    """Use one search slot, or raise RateLimitError if the daily cap is already hit."""
    with _LOCK:
        state = load_state()
        cap = search_cap()
        used = int(state["searches"])
        if cap is not None and used >= cap:
            payload = _denied_payload(state, cap)
            raise RateLimitError(payload["error"], payload)
        state["searches"] = used + 1
        save_state(state)
        cap = search_cap()
        used = int(state["searches"])
        unlimited = cap is None
        return {
            "ok": True,
            "accepted": True,
            "tier": current_tier(),
            "date": state["date"],
            "search_cap": cap,
            "searches_used": used,
            "searches_left": None if unlimited else max(0, cap - used),
            "limit_reached": False if unlimited else used >= cap,
            "unlimited": unlimited,
            "reset_tz": tz_name(),
        }


def _denied_payload(state: dict[str, Any], cap: int) -> dict[str, Any]:
    used = int(state["searches"])
    tier = current_tier()
    message = "今日搜索次数已用完，将在当地时间明天零点后重置。"
    return {
        "ok": False,
        "error": message,
        "limit_reached": True,
        "scene": "limit",
        "status_text": "今日搜索次数已用完",
        "tier": tier,
        "date": state["date"],
        "search_cap": cap,
        "searches_used": used,
        "searches_left": 0,
        "reset_tz": tz_name(),
        "free_search_cap": FREE_SEARCH_CAP,
        "paid_search_cap": PAID_SEARCH_CAP,
    }


def check_search() -> dict[str, Any]:
    """Raise RateLimitError if no searches remain, without consuming a slot."""
    with _LOCK:
        state = load_state()
        cap = search_cap()
        if cap is not None and int(state["searches"]) >= cap:
            payload = _denied_payload(state, cap)
            raise RateLimitError(payload["error"], payload)
        return remaining()
