#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Open 5-10 notes through the logged-in Chrome session and write a report."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chrome_session import ChromeError, ChromeSession, polite_pause  # noqa: E402
from rate_limit import (  # noqa: E402
    check_note,
    check_search,
    record_note,
    record_search,
    remaining,
)

REPORT_PATH = ROOT / "validation.json"


def _remote_fetch(keyword: str, host: str = "www.rednote.com") -> dict:
    """Fetch the public search URL without the logged-in session, for freshness contrast."""
    url = (
        "https://%s/search_result?keyword=%s"
        "&source=web_search_result_notes" % (host, quote(keyword, safe=""))
    )
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    started = time.time()
    try:
        req = Request(url, headers=headers)
        with urlopen(req, timeout=20) as resp:
            body = resp.read(8000)
            return {
                "ok": True,
                "status": getattr(resp, "status", None) or 200,
                "url": url,
                "bytes": len(body),
                "elapsed_sec": round(time.time() - started, 2),
                "snippet": body[:500].decode("utf-8", "replace"),
                "looks_like_login_or_block": _looks_blocked(body),
            }
    except HTTPError as exc:
        body = exc.read(2000) if exc.fp else b""
        return {
            "ok": False,
            "status": exc.code,
            "url": url,
            "bytes": len(body),
            "elapsed_sec": round(time.time() - started, 2),
            "error": str(exc),
            "looks_like_login_or_block": True,
        }
    except (URLError, TimeoutError, OSError) as exc:
        return {
            "ok": False,
            "status": None,
            "url": url,
            "elapsed_sec": round(time.time() - started, 2),
            "error": str(exc),
            "looks_like_login_or_block": True,
        }


def _looks_blocked(body: bytes) -> bool:
    text = body.decode("utf-8", "replace").lower()
    return any(
        token in text
        for token in ("403", "captcha", "访问异常", "登录", "forbidden", "just a moment")
    ) and b"/explore/" not in body


def run_validation(keyword: str, count: int) -> dict:
    count = max(5, min(10, int(count)))
    session = ChromeSession()
    report = {
        "keyword": keyword,
        "requested": count,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "timezone": "Asia/Macau",
        "login_ok": None,
        "search": None,
        "notes": [],
        "issues": [],
        "remote_unauthenticated": None,
        "rate_limit": remaining(),
        "passed": False,
    }
    try:
        check_search()
        search = session.search(keyword)
        record_search()
        report["search"] = {
            "ok": bool(search.get("ok", True)),
            "loginWall": bool(search.get("loginWall")),
            "pageUrl": search.get("pageUrl"),
            "pageTitle": search.get("pageTitle"),
            "count": search.get("count"),
            "notes_preview": [
                {
                    "id": n.get("id"),
                    "title": n.get("title"),
                    "author": n.get("author"),
                    "likes": n.get("likes"),
                    "url": n.get("url"),
                }
                for n in (search.get("notes") or [])[:count]
            ],
        }
        if search.get("loginWall"):
            report["login_ok"] = False
            report["issues"].append("Search page looks like a login wall. Session may have expired.")
            return report
        notes = search.get("notes") or []
        if len(notes) < 5:
            report["issues"].append(
                "Search returned only %d note cards; selectors may be stale." % len(notes)
            )
        if not notes:
            report["login_ok"] = True if not search.get("loginWall") else False
            return report

        report["login_ok"] = True
        opened = 0
        for item in notes:
            if opened >= count:
                break
            try:
                check_note()
            except Exception as exc:
                report["issues"].append(str(exc))
                break
            polite_pause()
            try:
                detail = session.open_note(item.get("url") or "")
                record_note()
            except ChromeError as exc:
                report["issues"].append("Failed to open %s: %s" % (item.get("id"), exc))
                report["notes"].append(
                    {
                        "id": item.get("id"),
                        "url": item.get("url"),
                        "ok": False,
                        "error": str(exc),
                    }
                )
                continue
            if detail.get("loginWall"):
                report["login_ok"] = False
                report["issues"].append("Note page showed a login wall after opening %s." % item.get("id"))
                report["notes"].append({"id": item.get("id"), "ok": False, "loginWall": True})
                break
            missing = [
                field
                for field in ("title", "author", "body")
                if not (detail.get(field) or "").strip()
            ]
            report["notes"].append(
                {
                    "id": item.get("id"),
                    "ok": True,
                    "title": detail.get("title"),
                    "author": detail.get("author"),
                    "body_preview": (detail.get("body") or "")[:400],
                    "body_len": len(detail.get("body") or ""),
                    "likes": detail.get("likes"),
                    "saves": detail.get("saves"),
                    "comments": detail.get("comments"),
                    "url": detail.get("url") or item.get("url"),
                    "missing_fields": missing,
                    "loginWall": False,
                }
            )
            if missing:
                report["issues"].append(
                    "Note %s missing visible fields: %s" % (item.get("id"), ", ".join(missing))
                )
            opened += 1

        report["remote_unauthenticated"] = {
            "rednote.com": _remote_fetch(keyword, host="www.rednote.com"),
            "xiaohongshu.com": _remote_fetch(keyword, host="www.xiaohongshu.com"),
        }
        ok_notes = [n for n in report["notes"] if n.get("ok")]
        titles = [n.get("title") for n in ok_notes if n.get("title")]
        report["opened"] = len(report["notes"])
        report["opened_ok"] = len(ok_notes)
        report["unique_titles"] = len(set(titles))
        # Pass if we opened at least 5 notes with titles and no login wall.
        report["passed"] = (
            report["login_ok"] is True
            and len(ok_notes) >= 5
            and len([n for n in ok_notes if n.get("title")]) >= 5
        )
        if report["passed"] and any(n.get("missing_fields") for n in ok_notes):
            report["passed_with_warnings"] = True
        return report
    finally:
        report["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        report["rate_limit_after"] = remaining()
        REPORT_PATH.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        session.close_window()


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Grokbot-RedNote on 5-10 notes")
    parser.add_argument("keyword", nargs="?", default="Mac 快捷键")
    parser.add_argument("--count", type=int, default=8)
    args = parser.parse_args()
    report = run_validation(args.keyword, args.count)
    print(json.dumps({
        "passed": report.get("passed"),
        "login_ok": report.get("login_ok"),
        "opened_ok": report.get("opened_ok"),
        "issues": report.get("issues"),
        "report": str(REPORT_PATH),
        "titles": [n.get("title") for n in report.get("notes") or [] if n.get("ok")],
        "remote_status": {
            k: (v or {}).get("status")
            for k, v in ((report.get("remote_unauthenticated") or {}).items() if isinstance(report.get("remote_unauthenticated"), dict) else [])
        },
    }, ensure_ascii=False, indent=2))
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    sys.exit(main())
