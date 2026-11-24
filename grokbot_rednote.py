#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local macOS GUI for read-only Xiaohongshu access via the logged-in Chrome session."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chrome_session import ChromeError, ChromeSession, polite_pause  # noqa: E402
from note_urls import publicize_payload, resolve_go_location, session_open_url  # noqa: E402
from refine_query import apply_explore_sample, refine_query, should_refine  # noqa: E402
from rate_limit import (  # noqa: E402
    RateLimitError,
    check_enrich,
    check_note,
    check_search,
    load_settings,
    record_enrich,
    record_note,
    record_search,
    remaining,
    status_text,
    update_settings,
)
from learn import safe_record_open, safe_rerank_and_log  # noqa: E402
from summarize import attach_summary, collect_search_paths, load_notes_from_paths, summarize_notes  # noqa: E402

SERVICE_HOST = "127.0.0.1"
SERVICE_PORT = 18765

# Shared Chrome window + rate limits across the GUI and local HTTP service.
_lock = threading.Lock()
_session = ChromeSession()
_last_pause_needed = False
_activity_lock = threading.Lock()
_activity = None  # "search" | "note" | None
_activity_keyword = ""
_results_lock = threading.Lock()
_last_results = {
    "ok": True,
    "revision": 0,
    "source": "",
    "query": "",
    "keyword": "",
    "count": 0,
    "unique": 0,
    "curated": [],
    "notes": [],
    "summary": {"groups": [], "total": 0, "unique": 0},
}
HOOK_SEARCH_DIR = Path("/tmp/xhs-hook-search")


def _set_activity(kind, keyword: str = "") -> None:
    global _activity, _activity_keyword
    with _activity_lock:
        _activity = kind
        _activity_keyword = keyword or ""


def _activity_payload() -> dict:
    with _activity_lock:
        kind = _activity
        keyword = _activity_keyword
    return {
        "busy": kind is not None,
        "searching": kind == "search",
        "activity": kind,
        "keyword": keyword,
    }


def _pause_if_needed() -> None:
    global _last_pause_needed
    if _last_pause_needed:
        info = remaining()
        polite_pause(info["min_delay_sec"], info["max_delay_sec"])



def _bring_gui_forward() -> None:
    """Launch Grokbot-RedNote.app or bring it to the front, same as start.sh."""
    try:
        subprocess.Popen(
            ["open", "./Grokbot-RedNote.app"],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        sys.stderr.write("[Grokbot-RedNote] could not open GUI: %s\n" % exc)



def parse_likes(value) -> Optional[int]:
    """Turn a visible like label into an integer, or None if unparsable.

    万 / w / W mean x10000. k / K mean x1000 (international explore uses this).
    A trailing + is ignored. Bare digits stay as-is.
    Labels like "Like" or empty strings return None.
    """
    text = str(value or "").strip()
    if not text:
        return None
    text = re.sub(r"^(赞|点赞|收藏|评论|likes?)\s*", "", text, flags=re.IGNORECASE).strip()
    text = text.rstrip("+").strip()
    if not text:
        return None
    match = re.fullmatch(r"([\d]+(?:\.[\d]+)?)([万wWkK])?", text)
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



def _hook_search_available() -> bool:
    return HOOK_SEARCH_DIR.is_dir() and any(collect_search_paths(HOOK_SEARCH_DIR))


def _remember_results(payload: dict, source: str) -> dict:
    """Keep the latest search/explore list for the GUI, including curated notes."""
    if not isinstance(payload, dict):
        return payload
    attach_summary(payload)
    notes = payload.get("notes") if isinstance(payload.get("notes"), list) else []
    with _results_lock:
        revision = int(_last_results.get("revision") or 0) + 1
        stored = {
            "ok": True,
            "revision": revision,
            "source": source,
            "query": payload.get("query") or payload.get("keyword") or "",
            "keyword": payload.get("keyword") or payload.get("query") or "",
            "count": payload.get("count") if payload.get("count") is not None else len(notes),
            "unique": payload.get("unique") if payload.get("unique") is not None else len(notes),
            "curated": payload.get("curated") or [],
            "notes": notes,
            "summary": payload.get("summary") or {"groups": [], "total": 0, "unique": 0},
            "saved_available": _hook_search_available(),
        }
        _last_results.clear()
        _last_results.update(stored)
    return payload


def _results_payload() -> dict:
    with _results_lock:
        payload = dict(_last_results)
    payload["saved_available"] = _hook_search_available()
    return payload


def _load_saved_hook_search() -> dict:
    paths = collect_search_paths(HOOK_SEARCH_DIR)
    if not paths:
        raise ValueError("No saved hook-search JSON found in %s" % HOOK_SEARCH_DIR)
    notes = load_notes_from_paths(paths)
    payload = {
        "ok": True,
        "source": "saved",
        "query": "钩子搜索",
        "keyword": "钩子搜索",
        "count": len(notes),
        "notes": notes,
    }
    _remember_results(payload, source="saved")
    return _results_payload()


def _run_explore() -> dict:
    """Browse the public explore page and return notes sorted by like count."""
    _bring_gui_forward()
    _set_activity("search", "探索")
    try:
        with _lock:
            check_search()
            global _last_pause_needed
            # Development: skip inter-search delay. Restore before launch.
            # _pause_if_needed()
            sample = _session.sample_explore()
            if not isinstance(sample, dict):
                raise ChromeError("Unexpected explore result")
            if sample.get("ok") is False:
                raise ChromeError(sample.get("error") or "Explore sample failed")
            notes = []
            for item in sample.get("notes") or []:
                if not isinstance(item, dict):
                    continue
                likes = item.get("likes") or ""
                notes.append({
                    "id": item.get("id") or "",
                    "url": item.get("url") or "",
                    "title": item.get("title") or "",
                    "author": item.get("author") or "",
                    "likes": likes,
                    "likes_count": parse_likes(likes),
                    "promoted": bool(item.get("promoted")),
                })
            notes.sort(key=lambda n: (n["likes_count"] is None, -(n["likes_count"] or 0)))
            # Count an explore scan as a search in /status. Cap enforcement stays off.
            record_search()
            _last_pause_needed = True
            payload = publicize_payload({
                "ok": True,
                "source": "explore",
                "pageUrl": sample.get("pageUrl") or "",
                "pageTitle": sample.get("pageTitle") or "",
                "loginWall": bool(sample.get("loginWall")),
                "count": len(notes),
                "notes": notes,
                "status": status_text(),
            })
            payload["notes"] = safe_rerank_and_log(
                payload.get("notes") or [], source="explore", query=""
            )
            payload["count"] = len(payload["notes"])
            _remember_results(payload, source="explore")
            return payload
    finally:
        _set_activity(None)


def _run_search(keyword: str, refine: bool = True) -> dict:
    original = (keyword or "").strip()
    _bring_gui_forward()
    refinement = refine_query(original) if refine else {
        "query": original,
        "keyword": original,
        "tokens": [],
        "intent": None,
        "changed": False,
        "candidates": [],
        "mode": "precise",
        "needs_explore": False,
    }
    used = (refinement.get("keyword") or original).strip()
    exploring = bool(refine and refinement.get("mode") == "anti_cocoon")
    _set_activity("search", "探索" if exploring else used)
    try:
        with _lock:
            check_search()
            global _last_pause_needed
            # Development: skip inter-search delay. Restore before launch.
            # _pause_if_needed()
            if exploring:
                sample = _session.sample_explore()
                refinement = apply_explore_sample(refinement, sample)
                used = (refinement.get("keyword") or used or original).strip()
                if not used:
                    raise ValueError("Could not infer a search term from the explore feed")
                _set_activity("search", used)
                # Development: skip inter-search delay. Restore before launch.
                # info = remaining()
                # polite_pause(info["min_delay_sec"], info["max_delay_sec"])
            data = _session.search(used)
            record_search()
            _last_pause_needed = True
            data["query"] = original
            data["keyword"] = used
            data["refinement"] = refinement
            notes = data.get("notes") if isinstance(data.get("notes"), list) else []
            for item in notes:
                if isinstance(item, dict) and item.get("likes_count") is None:
                    item["likes_count"] = parse_likes(item.get("likes"))
            data = publicize_payload(data)
            data["notes"] = safe_rerank_and_log(
                data.get("notes") or [], source="search", query=used or original
            )
            _remember_results(data, source="search")
            return data
    finally:
        _set_activity(None)


def _run_note(url: str, source_url: str = "") -> dict:
    open_url = session_open_url(url, source_url=source_url)
    _set_activity("note", open_url)
    try:
        with _lock:
            check_note()
            global _last_pause_needed
            _pause_if_needed()
            data = _session.open_note(open_url)
            record_note()
            _last_pause_needed = True
            data = publicize_payload(data)
            safe_record_open(data, requested_url=open_url)
            return data
    finally:
        _set_activity(None)


def _truthy(value: Optional[str]) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _max_commenters(raw: Optional[str], default: int = 3) -> int:
    try:
        n = int(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        n = default
    return max(1, min(n, 8))


def _run_enrich(url: str, max_commenters: int = 3, source_url: str = "") -> dict:
    """Open one note, collect visible comments, then read a few public commenter profiles."""
    open_url = session_open_url(url, source_url=source_url)
    _set_activity("note", open_url)
    try:
        with _lock:
            check_note()
            global _last_pause_needed
            _pause_if_needed()

            def after_note() -> None:
                record_note()
                global _last_pause_needed
                _last_pause_needed = True

            def before_profile() -> None:
                check_enrich()

            def after_profile(ok: bool = True) -> None:
                if ok:
                    record_enrich()
                global _last_pause_needed
                _last_pause_needed = True

            data = _session.enrich_note(
                open_url,
                max_commenters=max_commenters,
                pause=_pause_if_needed,
                before_profile=before_profile,
                after_profile=after_profile,
                after_note=after_note,
            )
            data["limits"] = remaining()
            data = publicize_payload(data)
            safe_record_open(data, requested_url=open_url)
            return data
    finally:
        _set_activity(None)


def _attach_search_enrichment(data: dict, max_commenters: int) -> dict:
    """Optional: enrich only the first search result, with a tight commenter cap."""
    if not data.get("ok"):
        return data
    notes = data.get("notes") or []
    if not notes:
        data["enrichment"] = {"error": "No search results to enrich"}
        return data
    first = notes[0] or {}
    url = first.get("source_url") or first.get("url") or ""
    if not url:
        data["enrichment"] = {"error": "The first result had no URL"}
        return data
    try:
        extra = _run_enrich(url, max_commenters=max_commenters, source_url=first.get("source_url") or "")
    except (RateLimitError, ChromeError, ValueError) as exc:
        data["enrichment"] = {"error": str(exc)}
        data["limits"] = remaining()
        return data
    data["enriched_note"] = {
        "title": extra.get("title") or "",
        "author": extra.get("author") or "",
        "url": extra.get("url") or url,
        "likes": extra.get("likes") or "",
        "saves": extra.get("saves") or "",
        "comments": extra.get("comments") or "",
        "body": extra.get("body") or "",
    }
    data["comment_items"] = extra.get("comment_items") or []
    data["portraits"] = extra.get("portraits") or []
    data["enrichment"] = extra.get("enrichment") or {}
    data["limits"] = remaining()
    return publicize_payload(data)


class LocalHandler(BaseHTTPRequestHandler):
    """Tiny localhost API so the assistant can be wired in later."""

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        sys.stderr.write("[Grokbot-RedNote] " + (fmt % args) + "\n")

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, path: Path) -> None:
        if not path.is_file():
            return self._send(500, {"ok": False, "error": "Missing UI file: %s" % path})
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, path: Path) -> None:
        path = path.resolve()
        root = (ROOT / "avatar").resolve()
        if root not in path.parents and path != root:
            return self._send(404, {"ok": False, "error": "Unknown route"})
        if not path.is_file():
            return self._send(404, {"ok": False, "error": "Unknown route"})
        suffix = path.suffix.lower()
        types = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml"}
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", types.get(suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid JSON: %s" % exc) from exc
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object.")
        return data

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _send_redirect(self, location: str, head: bool = False) -> None:
        body = b"" if head else ("Redirecting to %s\n" % location).encode("utf-8")
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        if head:
            self.send_header("Content-Length", "0")
        else:
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head and body:
            self.wfile.write(body)

    def _handle_go(self, query: dict, head: bool = False) -> None:
        try:
            location = resolve_go_location(query)
        except ValueError as exc:
            if head:
                self.send_response(400)
                self.send_header("Content-Length", "0")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            return self._send(400, {"ok": False, "error": str(exc)})
        return self._send_redirect(location, head=head)

    def do_HEAD(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        if path == "/go":
            return self._handle_go(query, head=True)
        # curl -I on other routes: send headers only via GET payload path is awkward,
        # so just answer /go (the route that must 302) and 405 otherwise.
        self.send_response(405)
        self.send_header("Allow", "GET, HEAD" if path == "/go" else "GET")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        try:
            if path in ("/", "/index.html", "/ui"):
                return self._send_html(ROOT / "avatar" / "scene.html")
            if path.startswith("/avatar/"):
                return self._send_static(ROOT / "avatar" / path[len("/avatar/"):])
            if path == "/health":
                return self._send(200, {"ok": True, "service": "Grokbot-RedNote", "host": SERVICE_HOST})
            if path == "/go":
                return self._handle_go(query, head=False)
            if path == "/status":
                return self._send(200, {"ok": True, **_activity_payload(), **remaining(), "status": status_text()})
            if path == "/settings":
                return self._send(
                    200,
                    {"ok": True, **load_settings(), **remaining(), "status": status_text()},
                )
            if path == "/refine":
                keyword = (query.get("q") or query.get("keyword") or [""])[0]
                return self._send(200, {"ok": True, **refine_query(keyword)})
            if path == "/explore":
                return self._send(200, _run_explore())
            if path == "/search":
                keyword = (query.get("q") or query.get("keyword") or [""])[0]
                refine_flag = (query.get("refine") or query.get("raw") or [None])[0]
                # raw=1 means skip refinement; refine=0 / false does too.
                if query.get("raw") and (query.get("raw") or [""])[0] in {"1", "true", "yes"}:
                    do_refine = False
                else:
                    do_refine = should_refine(refine_flag)
                data = _run_search(keyword, refine=do_refine)
                if _truthy((query.get("enrich") or [""])[0]):
                    data = _attach_search_enrichment(
                        data,
                        max_commenters=_max_commenters((query.get("max_commenters") or ["3"])[0], 3),
                    )
                return self._send(200, data)
            if path == "/note":
                url = (query.get("url") or [""])[0]
                source_url = (query.get("source_url") or [""])[0]
                if _truthy((query.get("enrich") or [""])[0]):
                    data = _run_enrich(
                        url,
                        max_commenters=_max_commenters((query.get("max_commenters") or ["3"])[0], 3),
                        source_url=source_url,
                    )
                else:
                    data = _run_note(url, source_url=source_url)
                return self._send(200, data)
            if path == "/enrich":
                url = (query.get("url") or [""])[0]
                source_url = (query.get("source_url") or [""])[0]
                data = _run_enrich(
                    url,
                    max_commenters=_max_commenters((query.get("max_commenters") or ["3"])[0], 3),
                    source_url=source_url,
                )
                return self._send(200, data)
            if path == "/results":
                load = (query.get("load") or query.get("saved") or [""])[0].strip()
                if load in {"hook-search", "hooks", "saved", "1", "true"}:
                    return self._send(200, _load_saved_hook_search())
                return self._send(200, _results_payload())
            return self._send(404, {"ok": False, "error": "Unknown route"})
        except RateLimitError as exc:
            return self._send(429, {"ok": False, "error": str(exc)})
        except (ChromeError, ValueError) as exc:
            return self._send(400, {"ok": False, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return self._send(500, {"ok": False, "error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        try:
            if path == "/settings":
                data = update_settings(self._read_json())
                return self._send(200, {"ok": True, **data, "status": status_text()})
            if path == "/summarize":
                body = self._read_json()
                notes = body.get("notes") if isinstance(body.get("notes"), list) else []
                return self._send(200, {"ok": True, **summarize_notes(notes)})
            return self._send(404, {"ok": False, "error": "Unknown route"})
        except ValueError as exc:
            return self._send(400, {"ok": False, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return self._send(500, {"ok": False, "error": str(exc)})


def start_service(background: bool = True) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((SERVICE_HOST, SERVICE_PORT), LocalHandler)
    if background:
        thread = threading.Thread(target=server.serve_forever, name="Grokbot-RedNote-http", daemon=True)
        thread.start()
    return server


def _service_only() -> int:
    server = start_service(background=False)
    print(
        "Grokbot-RedNote service on http://%s:%d  (GET /health /status /settings /refine?q= /search?q= /explore /note?url= /enrich?url= /go?id= /results; add enrich=1 after search/note, load=hook-search on /results; POST /settings /summarize)"
        % (SERVICE_HOST, SERVICE_PORT),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)
    finally:
        _session.close_window()
        server.server_close()
    return 0


def start_gui() -> int:
    """The native app owns the window; this process only runs the local service."""
    return _service_only()


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Xiaohongshu reader for macOS")
    parser.add_argument("--service", action="store_true", help="Run only the localhost HTTP service")
    parser.add_argument("--validate", metavar="KEYWORD", help="Search and open 5-10 notes, then exit")
    parser.add_argument("--count", type=int, default=8, help="Notes to open during --validate (5-10)")
    args = parser.parse_args()
    if args.service:
        return _service_only()
    if args.validate:
        from validate import run_validation

        report = run_validation(args.validate, args.count)
        print(json.dumps({"passed": report.get("passed"), "issues": report.get("issues"), "opened_ok": report.get("opened_ok")}, ensure_ascii=False, indent=2))
        return 0 if report.get("passed") else 1
    return start_gui()


if __name__ == "__main__":
    sys.exit(main())
