#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lightweight local preference learning for search and explore ranking.

Logs each result set and each observable open (GET /note or /enrich).
Clicks on links in Grok Bot chat are not visible and are not inferred.
Never drops notes; only re-orders when there is open history.
"""
from __future__ import annotations

import json
import re
import threading
import traceback
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Asia/Macau")
except Exception:  # pragma: no cover
    TZ = None

from note_urls import extract_note_id as _id_from_href
from refine_query import INTENT_WORDS, PLACES, STOPWORDS, tokenize

STATE_DIR = Path.home() / "Library" / "Application Support" / "XHSReader"
LOG_FILE = STATE_DIR / "learn.jsonl"
WEIGHTS_FILE = STATE_DIR / "weights.json"

# Scoring knobs. Opens outweigh skips; skips stay light and need repetition.
AUTHOR_OPEN_WEIGHT = 3.0
TOPIC_OPEN_UNIT = 0.5
TOPIC_OPEN_CAP = 2.0
LIKES_BAND_WEIGHT = 0.7
LIKES_BAND_FACTOR = 3.0
AUTHOR_SKIP_WEIGHT = 0.6
TOPIC_SKIP_UNIT = 0.2
TOPIC_SKIP_CAP = 0.6
REPEAT_SKIP = 2

_LIKES_RE = re.compile(r"([\d]+(?:\.[\d]+)?)([万wWkK])?")

_lock = threading.Lock()


def _now_iso() -> str:
    if TZ is not None:
        return datetime.now(TZ).replace(microsecond=0).isoformat()
    return datetime.now().replace(microsecond=0).isoformat()


def _write_json(path: Path, payload: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _parse_likes(value: Any) -> Optional[int]:
    text = str(value or "").strip()
    if not text:
        return None
    text = re.sub(r"^(赞|点赞|收藏|评论|likes?)\s*", "", text, flags=re.IGNORECASE).strip()
    text = text.rstrip("+").strip()
    if not text:
        return None
    match = _LIKES_RE.fullmatch(text)
    if not match:
        return None
    try:
        number = float(match.group(1))
    except ValueError:
        return None
    unit = match.group(2)
    if unit in ("万", "w", "W"):
        number *= 10000
    elif unit in ("k", "K"):
        number *= 1000
    if number < 0:
        return None
    return int(number)


def extract_note_id(*values: Any) -> str:
    """Pull a note id from an explicit id or a known public note URL."""
    for value in values:
        found = _id_from_href(str(value or "").strip())
        if found:
            return found.lower()
    return ""


def configure_dir(path: Path) -> None:
    """Point the log and weights at another folder (tests only)."""
    global STATE_DIR, LOG_FILE, WEIGHTS_FILE
    STATE_DIR = Path(path)
    LOG_FILE = STATE_DIR / "learn.jsonl"
    WEIGHTS_FILE = STATE_DIR / "weights.json"


def _note_url(note: dict) -> str:
    for key in ("web_url", "source_url", "url"):
        value = str(note.get(key) or "").strip()
        if value:
            return value
    return ""


def topic_tokens(title: str) -> list[str]:
    """Chinese-safe title tokens, minus query stopwords and 1-char noise."""
    tokens: list[str] = []
    seen = set()
    for raw in tokenize(title or ""):
        token = (raw or "").strip()
        if not token:
            continue
        key = token.lower()
        if key in STOPWORDS or token in STOPWORDS:
            continue
        if len(token) < 2 and token not in INTENT_WORDS and token not in PLACES:
            continue
        if key in seen:
            continue
        seen.add(key)
        tokens.append(key)
    return tokens


def _likes_of(note: dict) -> Optional[int]:
    if note.get("likes_count") is not None:
        try:
            return int(note["likes_count"])
        except (TypeError, ValueError):
            pass
    return _parse_likes(note.get("likes"))


def compact_note(note: dict, extra_urls: Iterable[str] = ()) -> dict:
    url = _note_url(note)
    note_id = extract_note_id(note.get("id"), url, *extra_urls)
    item = {
        "id": note_id,
        "url": url,
        "title": str(note.get("title") or "").strip(),
        "author": str(note.get("author") or "").strip(),
        "likes_count": _likes_of(note),
    }
    source_url = str(note.get("source_url") or "").strip()
    if source_url and source_url != url:
        item["source_url"] = source_url
    return item


def _append_event(event: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, ensure_ascii=False) + "\n"
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()


def _load_events() -> list[dict]:
    if not LOG_FILE.is_file():
        return []
    events: list[dict] = []
    try:
        raw = LOG_FILE.read_text(encoding="utf-8")
    except OSError:
        return []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and item.get("event"):
            events.append(item)
    return events


def _median(values: list[int]) -> Optional[int]:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return int(round((ordered[mid - 1] + ordered[mid]) / 2.0))


def _empty_weights() -> dict:
    return {
        "updated_at": _now_iso(),
        "opened_count": 0,
        "skipped_count": 0,
        "authors_opened": {},
        "authors_skipped": {},
        "topics_opened": {},
        "topics_skipped": {},
        "likes_opened": [],
        "likes_median": None,
    }


def _finalize_skips(pending: dict, opened_ids: set, skipped: dict) -> None:
    if pending.get("finalized"):
        return
    if not pending.get("opened_ids"):
        return
    for note in pending.get("notes") or []:
        note_id = note.get("id") or ""
        if not note_id or note_id in opened_ids:
            continue
        skipped[note_id] = note
    pending["finalized"] = True


def rebuild_weights() -> dict:
    """Derive author/topic/like weights from the on-disk log."""
    events = _load_events()
    pending: list[dict] = []
    pending_by_id: dict[str, dict] = {}
    opened_ids: set[str] = set()
    authors_opened: Counter = Counter()
    topics_opened: Counter = Counter()
    likes_opened: list[int] = []
    skipped: dict[str, dict] = {}
    opened_count = 0

    for event in events:
        kind = event.get("event")
        if kind == "result_set":
            for item in pending:
                if item.get("opened_ids"):
                    _finalize_skips(item, opened_ids, skipped)
            notes = []
            for raw in event.get("notes") or []:
                if not isinstance(raw, dict):
                    continue
                note = compact_note(raw)
                if note["id"]:
                    notes.append(note)
            set_id = str(event.get("set_id") or "set-%d" % (len(pending) + 1))
            entry = {
                "set_id": set_id,
                "notes": notes,
                "opened_ids": set(),
                "finalized": False,
            }
            pending.append(entry)
            pending_by_id[set_id] = entry
            continue

        if kind != "open":
            continue

        note = compact_note(event)
        note_id = note["id"]
        if not note_id:
            continue
        opened_count += 1
        opened_ids.add(note_id)
        skipped.pop(note_id, None)
        if note["author"]:
            authors_opened[note["author"]] += 1
        for token in topic_tokens(note["title"]):
            topics_opened[token] += 1
        if note["likes_count"] is not None:
            likes_opened.append(int(note["likes_count"]))

        matched = [item for item in pending if any(n.get("id") == note_id for n in item["notes"])]
        if not matched and event.get("set_id") in pending_by_id:
            matched = [pending_by_id[str(event.get("set_id"))]]
        for item in matched:
            item["opened_ids"].add(note_id)
            # Conservative skip: only after a later open of a different note
            # from the same result set (or a later session, handled above).
            if len(item["opened_ids"]) >= 2:
                _finalize_skips(item, opened_ids, skipped)

    authors_skipped: Counter = Counter()
    topics_skipped: Counter = Counter()
    for note in skipped.values():
        if note.get("author"):
            authors_skipped[note["author"]] += 1
        for token in topic_tokens(note.get("title") or ""):
            topics_skipped[token] += 1

    weights = {
        "updated_at": _now_iso(),
        "opened_count": opened_count,
        "skipped_count": len(skipped),
        "authors_opened": dict(authors_opened),
        "authors_skipped": dict(authors_skipped),
        "topics_opened": dict(topics_opened),
        "topics_skipped": dict(topics_skipped),
        "likes_opened": likes_opened,
        "likes_median": _median(likes_opened),
    }
    _write_json(WEIGHTS_FILE, weights)
    return weights


def load_weights() -> dict:
    if not WEIGHTS_FILE.is_file():
        return _empty_weights()
    try:
        data = json.loads(WEIGHTS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_weights()
    if not isinstance(data, dict):
        return _empty_weights()
    data.setdefault("opened_count", 0)
    data.setdefault("skipped_count", 0)
    data.setdefault("authors_opened", {})
    data.setdefault("authors_skipped", {})
    data.setdefault("topics_opened", {})
    data.setdefault("topics_skipped", {})
    data.setdefault("likes_opened", [])
    data.setdefault("likes_median", None)
    return data


def has_history() -> bool:
    weights = load_weights()
    return int(weights.get("opened_count") or 0) > 0


_set_counter = 0


def _set_id() -> str:
    global _set_counter
    _set_counter += 1
    stamp = _now_iso().replace("-", "").replace(":", "")
    return "%s-%02d" % (stamp, _set_counter % 100)


def record_result_set(source: str, query: str, notes: list) -> Optional[str]:
    """Log a /search or /explore result list, then refresh weights."""
    compact = [compact_note(item) for item in notes if isinstance(item, dict)]
    event = {
        "ts": _now_iso(),
        "event": "result_set",
        "set_id": _set_id(),
        "source": source or "search",
        "query": (query or "").strip(),
        "count": len(compact),
        "notes": compact,
    }
    with _lock:
        _append_event(event)
        rebuild_weights()
    return event["set_id"]


def record_open(data: dict, requested_url: str = "") -> None:
    """Log an observable open from /note or /enrich, then refresh weights."""
    if not isinstance(data, dict) or data.get("ok") is False:
        return
    note = compact_note(data, extra_urls=(requested_url,))
    if not note["id"] and not note["url"] and not requested_url:
        return
    if not note["url"] and requested_url:
        note["url"] = requested_url.strip()
    if not note["id"]:
        note["id"] = extract_note_id(requested_url, note["url"])
    event = {
        "ts": _now_iso(),
        "event": "open",
        **note,
    }
    with _lock:
        _append_event(event)
        rebuild_weights()


def _author_score(author: str, weights: dict) -> tuple[float, str]:
    author = (author or "").strip()
    if not author:
        return 0.0, ""
    opened = int((weights.get("authors_opened") or {}).get(author) or 0)
    skipped = int((weights.get("authors_skipped") or {}).get(author) or 0)
    score = 0.0
    reason = ""
    if opened:
        score += AUTHOR_OPEN_WEIGHT * opened / (opened + 1)
        reason = "opened author %s" % author
    if skipped >= REPEAT_SKIP and skipped > opened:
        score -= AUTHOR_SKIP_WEIGHT
        reason = (reason + "; " if reason else "") + "skipped author %s" % author
    return score, reason


def _topic_score(title: str, weights: dict) -> tuple[float, str]:
    opened = weights.get("topics_opened") or {}
    skipped = weights.get("topics_skipped") or {}
    tokens = topic_tokens(title)
    boost = 0.0
    hit = []
    demote = []
    for token in tokens:
        open_n = int(opened.get(token) or 0)
        skip_n = int(skipped.get(token) or 0)
        if open_n:
            boost += TOPIC_OPEN_UNIT * min(open_n, 3)
            hit.append(token)
        elif skip_n >= REPEAT_SKIP:
            demote.append(token)
    boost = min(TOPIC_OPEN_CAP, boost)
    if demote:
        boost -= min(TOPIC_SKIP_CAP, TOPIC_SKIP_UNIT * len(demote))
    parts = []
    if hit:
        parts.append("title tokens " + ",".join(hit[:6]))
    if demote:
        parts.append("skipped topics " + ",".join(demote[:4]))
    return boost, "; ".join(parts)


def _likes_score(likes_count: Optional[int], weights: dict) -> tuple[float, str]:
    median = weights.get("likes_median")
    opened = weights.get("likes_opened") or []
    if likes_count is None or median in (None, 0) or len(opened) < 2:
        return 0.0, ""
    try:
        median_n = float(median)
        likes_n = float(likes_count)
    except (TypeError, ValueError):
        return 0.0, ""
    if median_n <= 0 or likes_n < 0:
        return 0.0, ""
    lo = median_n / LIKES_BAND_FACTOR
    hi = median_n * LIKES_BAND_FACTOR
    if lo <= likes_n <= hi:
        return LIKES_BAND_WEIGHT, "similar like count"
    return 0.0, ""


def score_note(note: dict, weights: dict) -> tuple[float, str]:
    author_s, author_r = _author_score(str(note.get("author") or ""), weights)
    topic_s, topic_r = _topic_score(str(note.get("title") or ""), weights)
    likes_s, likes_r = _likes_score(_likes_of(note), weights)
    total = round(author_s + topic_s + likes_s, 3)
    reasons = [part for part in (author_r, topic_r, likes_r) if part]
    return total, "; ".join(reasons) if reasons else "no matching preference"


def rerank(notes: list, source: str = "search") -> list:
    """Re-order notes using learned weights. No history: return as-is.

    Explore should already be sorted by like count; this keeps that order
    when scores tie. Search keeps its original page order on ties.
    Notes are never dropped. ``source`` is accepted for callers; ranking
    rules are the same for search and explore.
    """
    del source  # same additive model for both paths
    if not isinstance(notes, list) or not notes:
        return notes
    with _lock:
        weights = load_weights()
    if int(weights.get("opened_count") or 0) <= 0:
        return notes
    scored = []
    for index, note in enumerate(notes):
        item = dict(note) if isinstance(note, dict) else {"title": str(note)}
        total, reason = score_note(item, weights)
        item["score"] = total
        item["rank_reason"] = reason
        scored.append((total, index, item))
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [row[2] for row in scored]


# --- helpers used by xhs_reader; never raise into the HTTP path ---

def safe_rerank_and_log(notes: list, source: str, query: str = "") -> list:
    try:
        ranked = rerank(notes, source=source)
    except Exception:
        traceback.print_exc()
        ranked = notes
    try:
        record_result_set(source=source, query=query, notes=ranked)
    except Exception:
        traceback.print_exc()
    return ranked


def safe_record_open(data: dict, requested_url: str = "") -> None:
    try:
        record_open(data, requested_url=requested_url)
    except Exception:
        traceback.print_exc()
