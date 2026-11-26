#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Drive the already-logged-in Google Chrome session via AppleScript.

Read-only: open a dedicated window, navigate, extract visible fields.
Never reads cookie files, never touches the official Xiaohongshu app,
never posts or likes. Profile pages are opened only during an explicit optional enrichment step, and only fields the profile itself shows.
"""
from __future__ import annotations

import json
import random
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
JS_SEARCH = ROOT / "js" / "extract_search.js"
JS_APPLY_SEARCH_SORT = ROOT / "js" / "apply_search_sort.js"
JS_NOTE = ROOT / "js" / "extract_note.js"
JS_EXPLORE = ROOT / "js" / "extract_explore.js"
JS_PROFILE = ROOT / "js" / "extract_profile.js"
STATE_DIR = Path.home() / "Library" / "Application Support" / "Grokbot-RedNote"
WINDOW_STATE = STATE_DIR / "chrome_window.json"

SEARCH_URL = (
    "https://www.rednote.com/search_result?keyword={keyword}"
    "&source=web_search_result_notes"
)
SEARCH_SORT_LIKES_PARAM = "popularity_descending"
_LIKES_SORT_ALIASES = {
    "likes",
    "most_liked",
    "most-liked",
    "mostliked",
    "popularity",
    "popular",
    "最多点赞",
    "最热",
}
_COMPREHENSIVE_SORT_ALIASES = {"comprehensive", "综合", "general", "comp"}
EXPLORE_URL = "https://www.rednote.com/explore"
NOTE_READY_TIMEOUT = 25
SEARCH_READY_TIMEOUT = 25
SEARCH_SORT_SETTLE = 1.8


class ChromeError(RuntimeError):
    pass


def normalize_search_sort(value: Optional[str] = None) -> Optional[str]:
    """Map request aliases to an internal sort key. Default is likes (最多点赞)."""
    if value is None:
        return "likes"
    raw = str(value).strip()
    if not raw:
        return "likes"
    lowered = raw.lower()
    if raw in _COMPREHENSIVE_SORT_ALIASES or lowered in _COMPREHENSIVE_SORT_ALIASES:
        return None
    if raw in _LIKES_SORT_ALIASES or lowered in _LIKES_SORT_ALIASES:
        return "likes"
    return "likes"


def prepare_search_request(keyword: str, sort: Optional[str] = None) -> tuple[str, Optional[str]]:
    """Return (search text, sort key). Default sort is likes unless Comprehensive is explicit."""
    return (keyword or "").strip(), normalize_search_sort(sort)


def build_search_url(keyword: str, sort: Optional[str] = None) -> str:
    url = SEARCH_URL.format(keyword=quote(keyword, safe=""))
    if normalize_search_sort(sort) == "likes":
        return url + "&sort=" + SEARCH_SORT_LIKES_PARAM
    return url


def sort_notes_by_likes(notes: list) -> list:
    """Stable descending like-count order; notes without a count go last."""
    items = [item for item in notes if isinstance(item, dict)]
    indexed = list(enumerate(items))
    indexed.sort(
        key=lambda pair: (
            pair[1].get("likes_count") is None,
            -(pair[1].get("likes_count") or 0),
            pair[0],
        )
    )
    return [item for _, item in indexed]


def _script(*lines: str) -> str:
    return "\n".join(lines)


class ChromeSession:
    def __init__(self) -> None:
        self.window_id: Optional[int] = None

    def _osascript(self, script: str, timeout: int = 60) -> str:
        result = subprocess.run(
            ["/usr/bin/osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "osascript failed").strip()
            raise ChromeError(err)
        return (result.stdout or "").strip()

    def _window_exists(self, window_id: int) -> bool:
        exists = self._osascript(
            _script(
                'tell application "Google Chrome"',
                "    exists window id %d" % window_id,
                "end tell",
            )
        )
        return exists.lower() == "true"

    def _load_saved_window_id(self) -> Optional[int]:
        try:
            data = json.loads(WINDOW_STATE.read_text())
            return int(data["window_id"])
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def _save_window_id(self, window_id: Optional[int]) -> None:
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            if window_id is None:
                if WINDOW_STATE.exists():
                    WINDOW_STATE.unlink()
                return
            WINDOW_STATE.write_text(
                json.dumps({"window_id": window_id}) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass

    def _attach_default_chrome(self) -> None:
        # Use the already-open Default-profile Chrome. Never launch a
        # separate Chrome with --user-data-dir or a fresh profile.
        self._osascript(
            _script(
                'tell application "Google Chrome"',
                "    if it is not running then launch",
                "end tell",
            )
        )

    def ensure_window(self) -> int:
        self._attach_default_chrome()
        candidates = []
        if self.window_id is not None:
            candidates.append(self.window_id)
        saved = self._load_saved_window_id()
        if saved is not None and saved not in candidates:
            candidates.append(saved)
        for window_id in candidates:
            if self._window_exists(window_id):
                self.window_id = window_id
                self._save_window_id(window_id)
                return window_id
        raw = self._osascript(
            _script(
                'tell application "Google Chrome"',
                "    set w to make new window",
                '    set URL of active tab of w to "about:blank"',
                "    return id of w",
                "end tell",
            )
        )
        try:
            self.window_id = int(raw)
        except ValueError as exc:
            raise ChromeError("Could not create a Chrome window: %s" % raw) from exc
        self._save_window_id(self.window_id)
        return self.window_id

    def close_window(self) -> None:
        if self.window_id is None:
            return
        try:
            self._osascript(
                _script(
                    'tell application "Google Chrome"',
                    "    if (exists window id %d) then close window id %d"
                    % (self.window_id, self.window_id),
                    "end tell",
                )
            )
        except ChromeError:
            pass
        self.window_id = None
        self._save_window_id(None)

    def current_url(self) -> str:
        self.ensure_window()
        return self._osascript(
            _script(
                'tell application "Google Chrome"',
                "    get URL of active tab of window id %d" % self.window_id,
                "end tell",
            )
        )

    def current_title(self) -> str:
        self.ensure_window()
        return self._osascript(
            _script(
                'tell application "Google Chrome"',
                "    get title of active tab of window id %d" % self.window_id,
                "end tell",
            )
        )

    def is_loading(self) -> bool:
        self.ensure_window()
        raw = self._osascript(
            _script(
                'tell application "Google Chrome"',
                "    get loading of active tab of window id %d" % self.window_id,
                "end tell",
            )
        )
        return raw.lower() == "true"

    def navigate(self, url: str) -> None:
        self.ensure_window()
        escaped = url.replace("\\", "\\\\").replace('"', '\\"')
        self._osascript(
            _script(
                'tell application "Google Chrome"',
                '    set URL of active tab of window id %d to "%s"'
                % (self.window_id, escaped),
                "end tell",
            )
        )

    def wait_ready(self, timeout: float, extra_settle: float = 1.6) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                loading = self.is_loading()
            except ChromeError:
                time.sleep(0.35)
                continue
            if not loading:
                time.sleep(extra_settle)
                if not self.is_loading():
                    return
            time.sleep(0.35)
        time.sleep(extra_settle)

    def execute_js_file(self, js_path: Path) -> Any:
        self.ensure_window()
        if not js_path.is_file():
            raise ChromeError("Missing extractor: %s" % js_path)
        with tempfile.NamedTemporaryFile(
            "w", suffix=".js", delete=False, encoding="utf-8"
        ) as handle:
            handle.write(js_path.read_text(encoding="utf-8"))
            tmp = handle.name
        try:
            raw = self._osascript(
                _script(
                    'set js to do shell script "/bin/cat " & quoted form of "%s"'
                    % tmp.replace("\\", "\\\\").replace('"', '\\"'),
                    'tell application "Google Chrome"',
                    '    if not (exists window id %d) then error "The reader window was closed"'
                    % self.window_id,
                    "    set theResult to execute active tab of window id %d javascript js"
                    % self.window_id,
                    '    if theResult is missing value then return ""',
                    "    return theResult as text",
                    "end tell",
                ),
                timeout=45,
            )
        finally:
            Path(tmp).unlink(missing_ok=True)
        if not raw:
            raise ChromeError("Chrome returned no data from the page script")
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ChromeError("Page script did not return JSON: %s" % raw[:400]) from exc

    def search(self, keyword: str, sort: Optional[str] = None) -> dict:
        keyword = (keyword or "").strip()
        if not keyword:
            raise ChromeError("Type a keyword first")
        sort = normalize_search_sort(sort)
        url = build_search_url(keyword, sort)
        self.navigate(url)
        self.wait_ready(SEARCH_READY_TIMEOUT, extra_settle=2.0)
        sort_filter = None
        if sort == "likes":
            sort_filter = self._apply_search_sort()
            time.sleep(SEARCH_SORT_SETTLE)
        try:
            self._osascript(
                _script(
                    'tell application "Google Chrome"',
                    '    execute active tab of window id %d javascript "window.scrollTo(0, 900); true;"'
                    % self.window_id,
                    "end tell",
                )
            )
            time.sleep(1.4)
        except ChromeError:
            pass
        data = self.execute_js_file(JS_SEARCH)
        if not isinstance(data, dict):
            raise ChromeError("Unexpected search result")
        data["keyword"] = keyword
        if sort:
            data["sort"] = sort
            if sort_filter is not None:
                data["sort_filter"] = sort_filter
        return data

    def _apply_search_sort(self) -> dict:
        """Select Xiaohongshu's on-page 最多点赞 filter. Never raises."""
        try:
            result = self.execute_js_file(JS_APPLY_SEARCH_SORT)
        except Exception as exc:
            return {"ok": False, "applied": False, "error": str(exc)}
        if isinstance(result, dict):
            return result
        return {"ok": False, "applied": False, "error": "Unexpected filter script result"}

    def _scroll_active(self, y: int) -> None:
        try:
            self._osascript(
                _script(
                    'tell application "Google Chrome"',
                    '    execute active tab of window id %d javascript "window.scrollTo(0, %d); true;"'
                    % (self.window_id, int(y)),
                    "end tell",
                )
            )
        except ChromeError:
            pass

    def sample_explore(self) -> dict:
        """Open the explore feed and extract visible user notes.

        Scrolls past the first screen so the sample is not just the
        platform's opening slots. Promoted cards are flagged, not used
        as official trending input here.
        """
        self.navigate(EXPLORE_URL)
        self.wait_ready(SEARCH_READY_TIMEOUT, extra_settle=2.0)
        for y in (900, 2000, 3200, 4400):
            self._scroll_active(y)
            time.sleep(1.15)
        data = self.execute_js_file(JS_EXPLORE)
        if not isinstance(data, dict):
            raise ChromeError("Unexpected explore result")
        return data

    def open_note(self, url: str) -> dict:
        url = (url or "").strip()
        if not url or not any(host in url for host in ("xiaohongshu.com", "rednote.com")):
            raise ChromeError("That is not a Xiaohongshu note URL")
        if "/user/profile/" in url:
            raise ChromeError("Profile pages are out of scope")
        self.navigate(url)
        self.wait_ready(NOTE_READY_TIMEOUT, extra_settle=2.0)
        data = self.execute_js_file(JS_NOTE)
        if not isinstance(data, dict):
            raise ChromeError("Unexpected note result")
        return data

    def execute_js(self, source: str, timeout: int = 45) -> Any:
        self.ensure_window()
        with tempfile.NamedTemporaryFile(
            "w", suffix=".js", delete=False, encoding="utf-8"
        ) as handle:
            handle.write(source)
            tmp = handle.name
        try:
            raw = self._osascript(
                _script(
                    'set js to do shell script "/bin/cat " & quoted form of "%s"'
                    % tmp.replace("\\", "\\\\").replace('"', '\\"'),
                    'tell application "Google Chrome"',
                    '    if not (exists window id %d) then error "The reader window was closed"'
                    % self.window_id,
                    "    set theResult to execute active tab of window id %d javascript js"
                    % self.window_id,
                    '    if theResult is missing value then return ""',
                    "    return theResult as text",
                    "end tell",
                ),
                timeout=timeout,
            )
        finally:
            Path(tmp).unlink(missing_ok=True)
        return raw

    def _click_label(self, labels: list[str]) -> str:
        payload = json.dumps(list(labels), ensure_ascii=False)
        script = (
            "(() => { const labels = %s;"
            " const nodes = Array.from(document.querySelectorAll('a, button, span, div, li'));"
            " for (const el of nodes) {"
            "   const t = (el.innerText || el.textContent || '').trim().split('\\n')[0];"
            "   if (!t || t.length > 20) continue;"
            "   if (labels.some((l) => t === l || t.startsWith(l + ' ') || t.endsWith(' ' + l))) {"
            "     el.click(); return t;"
            "   }"
            " } return ''; })()"
        ) % payload
        try:
            return (self.execute_js(script) or "").strip()
        except ChromeError:
            return ""

    def _refresh_comments(self) -> dict:
        """Scroll the comment area so more visible rows can be extracted."""
        try:
            self._click_label(["评论", "条评论", "Comments", "Comment"])
            time.sleep(0.6)
            self._scroll_active(1600)
            time.sleep(0.8)
            self.execute_js(
                "(() => { const box = document.querySelector("
                "'.comments-container, .comment-list, #comment-container, .list-container');"
                " if (box) box.scrollTop = box.scrollHeight;"
                " window.scrollBy(0, 500); return 'ok'; })()"
            )
            time.sleep(1.0)
        except ChromeError:
            pass
        data = self.execute_js_file(JS_NOTE)
        return data if isinstance(data, dict) else {}

    def read_profile(self, url: str, max_posts: int = 8, max_follows: int = 12, max_likes: int = 8) -> dict:
        """Read a public user profile from the already-logged-in Chrome window.

        Only used by the optional enrichment path. Does not follow, like, or post.
        Likes and follow lists are included only when the profile shows them.
        """
        url = (url or "").strip()
        if not url or not any(host in url for host in ("xiaohongshu.com", "rednote.com")):
            raise ChromeError("That is not a Xiaohongshu profile URL")
        if "/user/profile/" not in url:
            raise ChromeError("That is not a profile page")
        self.navigate(url)
        self.wait_ready(NOTE_READY_TIMEOUT, extra_settle=1.8)
        data = self.execute_js_file(JS_PROFILE)
        if not isinstance(data, dict):
            raise ChromeError("Unexpected profile result")
        posted = list(data.get("posted") or [])[: max(0, int(max_posts))]
        data["posted"] = posted

        follows: list = list(data.get("follows") or [])
        if not follows and data.get("following_public") is not False:
            clicked = self._click_label(["关注", "Following"])
            if clicked:
                time.sleep(1.4)
                extra = self.execute_js_file(JS_PROFILE)
                if isinstance(extra, dict):
                    follows = list(extra.get("follows") or [])
                    if extra.get("following_public") is False:
                        data["following_public"] = False
        data["follows"] = follows[: max(0, int(max_follows))]
        if data.get("following_public") is None:
            data["following_public"] = bool(data["follows"])

        liked: list = []
        likes_public = data.get("likes_public")
        if likes_public is not False:
            # Return to the profile root, then open the public likes tab if it exists.
            clicked = self._click_label(["赞过", "喜欢", "Likes"])
            if clicked:
                time.sleep(1.6)
                extra = self.execute_js_file(JS_PROFILE)
                if isinstance(extra, dict):
                    if extra.get("likes_public") is False or extra.get("tab_hint") == "likes-private":
                        likes_public = False
                    else:
                        liked = list(extra.get("posted") or [])
                        likes_public = True
            else:
                likes_public = None
        data["liked"] = liked[: max(0, int(max_likes))] if likes_public else []
        data["likes_public"] = bool(likes_public) if likes_public is not None else False
        if likes_public is None:
            data["likes_public"] = False
            data["liked"] = []
        return data

    def enrich_note(
        self,
        url: str,
        max_commenters: int = 3,
        max_posts: int = 8,
        max_follows: int = 12,
        max_likes: int = 8,
        pause=None,
        before_profile=None,
        after_profile=None,
        after_note=None,
    ) -> dict:
        """Open a note, collect visible comments, then optionally read commenter profiles."""
        note = self.open_note(url)
        if after_note:
            after_note()
        refreshed = self._refresh_comments()
        if refreshed.get("comment_items"):
            note["comment_items"] = refreshed["comment_items"]
        elif "comment_items" not in note:
            note["comment_items"] = []
        items = [c for c in (note.get("comment_items") or []) if isinstance(c, dict)]
        unique = []
        seen = set()
        for item in items:
            key = item.get("user_id") or item.get("profile_url") or item.get("author")
            if not key or key in seen:
                continue
            if not item.get("profile_url"):
                continue
            seen.add(key)
            unique.append(item)
        limit = max(0, min(int(max_commenters), 8))
        portraits = []
        skipped = []
        for item in unique[:limit]:
            if before_profile:
                before_profile()
            if pause:
                pause()
            try:
                profile = self.read_profile(
                    item["profile_url"],
                    max_posts=max_posts,
                    max_follows=max_follows,
                    max_likes=max_likes,
                )
            except ChromeError as exc:
                skipped.append({"user": item.get("author") or item.get("user_id"), "error": str(exc)})
                if after_profile:
                    after_profile(ok=False)
                continue
            portraits.append(build_portrait(note, item, profile))
            if after_profile:
                after_profile(ok=True)
        note["portraits"] = portraits
        note["enrichment"] = {
            "comments_visible": len(items),
            "commenters_unique": len(unique),
            "profiles_opened": len(portraits),
            "skipped": skipped,
        }
        return note


def build_portrait(note: dict, comment: dict, profile: dict) -> dict:
    """Combine the note, the comment, and the commenter's public profile."""
    return {
        "user_id": profile.get("user_id") or comment.get("user_id") or "",
        "name": profile.get("name") or comment.get("author") or "",
        "profile_url": profile.get("profile_url") or comment.get("profile_url") or "",
        "bio": profile.get("bio") or "",
        "location": profile.get("location") or "",
        "followers": profile.get("followers") or "",
        "following": profile.get("following") or "",
        "likes_collected": profile.get("likes_collected") or "",
        "notes_count": profile.get("notes_count") or "",
        "comment": {
            "text": comment.get("text") or "",
            "likes": comment.get("likes") or "",
            "note_title": note.get("title") or "",
            "note_url": note.get("url") or "",
        },
        "posted": list(profile.get("posted") or []),
        "follows": list(profile.get("follows") or []),
        "following_public": bool(profile.get("following_public")),
        "liked": list(profile.get("liked") or []),
        "likes_public": bool(profile.get("likes_public")),
    }




def polite_pause(min_seconds: float = 6.0, max_seconds: float = 10.0) -> float:
    delay = random.uniform(min_seconds, max_seconds)
    time.sleep(delay)
    return delay
