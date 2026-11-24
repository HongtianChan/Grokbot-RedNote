#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Canonical chat/API note URLs for Grokbot-RedNote.

Chat-facing `url` values are https://www.xiaohongshu.com/explore/{id}
plus official share query params when the scraped href already has them
(`xsec_token`, and `xsec_source` when it is non-empty). Tokens are never
invented: a note with no token stays a bare explore URL.

The scraped href is kept as `source_url` so the logged-in Chrome session
can still open the rednote.com page it already knows.

Public write-ups of official share links use the same path and require
xsec_token; stripping it leads to a security 404 (404/sec_...) or the
app error 获取信息失败.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, quote, urlparse

CANONICAL_PREFIX = "https://www.xiaohongshu.com/explore/"
SESSION_PREFIX = "https://www.rednote.com/discovery/item/"

# Confirmed official share / web note params. xsec_token is the access
# pass; xsec_source is the official channel marker (app_share, pc_feed,
# pc_search, ...). Tracking-only share_* / track_* fields are omitted.
_SHARE_PARAM_NAMES = ("xsec_token", "xsec_source")

# Same id shapes the extractors already accept: /explore/{id},
# /discovery/item/{id}, /search_result/{id} with a 16+ char id.
_NOTE_ID_IN_URL = re.compile(
    r"/(?:explore|discovery/item|search_result)/([0-9a-z]{16,})",
    re.IGNORECASE,
)
_BARE_ID = re.compile(r"^[0-9a-z]{16,}$", re.IGNORECASE)
_HTTP_HOSTS = ("xiaohongshu.com", "rednote.com")


def extract_note_id(href_or_id: str = "", note_id: str = "") -> str:
    """Return a note id from an explicit id, a bare id, or a note href."""
    explicit = (note_id or "").strip()
    if explicit and _BARE_ID.fullmatch(explicit):
        return explicit
    text = (href_or_id or "").strip()
    if not text:
        return ""
    if _BARE_ID.fullmatch(text):
        return text
    parsed = urlparse(text)
    if parsed.path.rstrip("/").endswith("/go"):
        params = dict(parse_qsl(parsed.query, keep_blank_values=True))
        qid = (params.get("id") or "").strip()
        if _BARE_ID.fullmatch(qid):
            return qid
        return extract_note_id(params.get("url") or "")
    match = _NOTE_ID_IN_URL.search(text)
    return match.group(1) if match else ""


def official_share_query(*hrefs: str) -> str:
    """Build xsec_token[&xsec_source=...] from scraped hrefs, or "".

    Does not invent tokens. Empty xsec_source values (common on rednote
    search cards) are omitted; a non-empty xsec_token is required before
    any query is returned. Token characters are preserved (including a
    trailing =) rather than percent-encoded.
    """
    collected = {}
    for href in hrefs:
        text = (href or "").strip()
        if not text:
            continue
        for key, value in parse_qsl(urlparse(text).query, keep_blank_values=True):
            if key not in _SHARE_PARAM_NAMES:
                continue
            if key not in collected:
                collected[key] = value
    token = collected.get("xsec_token") or ""
    if not token:
        return ""
    parts = ["xsec_token=" + quote(token, safe="=-_~")]
    source = collected.get("xsec_source") or ""
    if source:
        parts.append("xsec_source=" + quote(source, safe="=-_~"))
    return "&".join(parts)


def _with_share_query(base: str, *hrefs: str) -> str:
    query = official_share_query(*hrefs)
    if not query:
        return base
    return base + "?" + query


def canonical_web_url(href_or_id: str = "", note_id: str = "", source_url: str = "") -> str:
    """https://www.xiaohongshu.com/explore/{id} plus official share params."""
    nid = extract_note_id(href_or_id, note_id) or extract_note_id(source_url, note_id)
    if not nid:
        return ""
    return _with_share_query(CANONICAL_PREFIX + nid, source_url, href_or_id)


GO_BASE = "http://127.0.0.1:18765/go"

# Recent official share URLs, so /go?id= still works after a scan even if
# the chat link omits the token. Tokens are never invented here.
_NOTE_CACHE = {}


def remember_note(note_id: str, web_url: str = "", source_url: str = "") -> None:
    nid = extract_note_id(note_id, note_id)
    official = canonical_web_url(web_url or source_url, nid, source_url=source_url)
    if nid and official:
        _NOTE_CACHE[nid] = official


def cached_web_url(note_id: str) -> str:
    nid = extract_note_id(note_id, note_id)
    return _NOTE_CACHE.get(nid) or ""


def _is_go_url(url: str) -> bool:
    text = (url or "").strip()
    if not text:
        return False
    parsed = urlparse(text)
    host = (parsed.hostname or "").lower()
    return host in ("127.0.0.1", "localhost") and parsed.path.rstrip("/").endswith("/go")


def click_url(href_or_id: str = "", note_id: str = "", source_url: str = "") -> str:
    """Local /go link for Grok Bot chat, so macOS Universal Links do not claim it."""
    nid = extract_note_id(href_or_id, note_id) or extract_note_id(source_url, note_id)
    if not nid:
        return ""
    query = official_share_query(source_url, href_or_id, cached_web_url(nid))
    if query:
        return "%s?id=%s&%s" % (GO_BASE, nid, query)
    return "%s?id=%s" % (GO_BASE, nid)


def resolve_go_location(query: dict) -> str:
    """Turn /go query params into an official https://www.xiaohongshu.com/explore/{id} URL.

    Raises ValueError if no note id can be found. Does not invent tokens.
    """
    def first(key: str) -> str:
        values = query.get(key) or []
        if not values:
            return ""
        return str(values[0] or "").strip()

    raw_url = first("url")
    nid = first("id") or extract_note_id(raw_url)
    token = first("xsec_token")
    source = first("xsec_source")
    synthetic = ""
    if nid or token:
        parts = []
        if token:
            parts.append("xsec_token=" + token)
        if source:
            parts.append("xsec_source=" + source)
        synthetic = "https://www.xiaohongshu.com/explore/%s" % (nid or "missing")
        if parts:
            synthetic += "?" + "&".join(parts)
    official = canonical_web_url(
        raw_url or synthetic,
        nid,
        source_url=cached_web_url(nid) if nid else "",
    )
    if not official or not nid:
        raise ValueError("Missing note id")
    return official


def _is_http_note_url(url: str) -> bool:
    text = (url or "").strip()
    if not text.lower().startswith(("http://", "https://")):
        return False
    if not any(host in text for host in _HTTP_HOSTS):
        return False
    if "/user/profile/" in text:
        return False
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False
    return True


def session_open_url(href_or_id: str = "", source_url: str = "", note_id: str = "") -> str:
    """URL to open in the already-logged-in Chrome session.

    Prefer the original rednote.com href (tokens and all). If all we have
    is a canonical www.xiaohongshu.com/explore/{id} link, map it back to
    https://www.rednote.com/discovery/item/{id} and keep any official
    share params already on the canonical URL.
    """
    for candidate in (source_url, href_or_id):
        text = (candidate or "").strip()
        if _is_http_note_url(text) and "rednote.com" in text:
            return text
    nid = extract_note_id(href_or_id, note_id) or extract_note_id(source_url, note_id)
    if nid:
        return _with_share_query(SESSION_PREFIX + nid, source_url, href_or_id)
    for candidate in (source_url, href_or_id):
        text = (candidate or "").strip()
        if _is_http_note_url(text):
            return text
    return (source_url or href_or_id or "").strip()


def publicize_note(note: dict, url_key: str = "url") -> dict:
    """Set chat-facing url to a local /go link; keep official web_url and source_url."""
    if not isinstance(note, dict):
        return note
    candidates = (
        note.get("source_url"),
        note.get("web_url"),
        note.get(url_key),
    )
    original = ""
    for candidate in candidates:
        text = str(candidate or "").strip()
        if _is_http_note_url(text):
            original = text
            break
    if not original:
        original = str(note.get(url_key) or "").strip()
    nid = (note.get("id") or "").strip() or extract_note_id(original)
    official = canonical_web_url(original, nid)
    if not official:
        return note
    if original and _is_http_note_url(original) and original != official:
        note["source_url"] = original
    note["web_url"] = official
    note[url_key] = click_url(original, nid)
    if nid and not note.get("id"):
        note["id"] = nid
    remember_note(nid, official, original)
    return note


def publicize_payload(data: dict) -> dict:
    """Rewrite note URLs on /search, /explore, and /note-style payloads."""
    if not isinstance(data, dict):
        return data
    for item in data.get("notes") or []:
        publicize_note(item)
    if data.get("url") or data.get("source_url"):
        publicize_note(data)
    if isinstance(data.get("enriched_note"), dict):
        publicize_note(data["enriched_note"])
    for portrait in data.get("portraits") or []:
        if isinstance(portrait, dict) and (portrait.get("note_url") or portrait.get("source_url")):
            publicize_note(portrait, url_key="note_url")
    return data
