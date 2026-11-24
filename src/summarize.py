#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""On-device, deterministic summarization of XHS search/explore note lists.

Group notes by title pattern rules, rank groups and examples by like count.
Also curate a short 5-10 note list for the reader GUI.
No network and no model calls. Safe to attach to /search and /explore.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable, Optional

SRC_DIR = Path(__file__).resolve().parent
ROOT = SRC_DIR.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

try:
    from refine_query import tokenize
except ImportError:  # pragma: no cover - tokenizer is optional
    def tokenize(text: str) -> list[str]:
        return re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+", text or "")


# Most specific patterns first. First match wins.
# keywords are literal substrings checked against a normalized title.
# regexes are also applied to the normalized title.
PATTERNS: list[dict] = [
    {
        "name": "猫式/软开头 vs 疯狗式黄金三秒",
        "takeaway": "高赞内容在对比硬冲的「疯狗式黄金三秒」和更软的「猫式」开场，主张先亲近再进入主题。",
        "keywords": ("猫式", "疯狗式", "疯狗", "软开头"),
        "regexes": (),
    },
    {
        "name": "「黄金三秒已死」反思",
        "takeaway": "一批笔记认为死磕前三秒硬钩已经过时，主张换结构或换节奏，而不是继续堆更冲的开场。",
        "keywords": ("别再死磕黄金", "请别再磕黄金", "别再磕黄金"),
        "regexes": (
            r"(已死|早就死了|不管用|失效|早就不管用)",
        ),
    },
    {
        "name": "音效开头",
        "takeaway": "把爆款或综艺感音效放在片头，先用声音留人。",
        "keywords": ("音效",),
        "regexes": (),
    },
    {
        "name": "口播开场",
        "takeaway": "口播和开场白怎么设计，让前几秒有网感、能留人。",
        "keywords": ("口播", "开场白"),
        "regexes": (),
    },
    {
        "name": "写作/小说开头",
        "takeaway": "这类是小说、剧本或写作开篇，不是短视频视觉钩子。",
        "keywords": ("小说", "开篇", "写作", "人民日报", "悬疑文"),
        "regexes": (),
    },
    {
        "name": "带货开头",
        "takeaway": "可套用的带货、投放或好物开场，按品类或结构直接抄。",
        "keywords": ("带货", "好物", "出单", "千川", "全品类", "投流", "电商不露脸"),
        "regexes": (r"(不露脸.{0,8}(带货|电商)|(带货|电商).{0,8}不露脸)",),
    },
    {
        "name": "剪辑/片头/三种编辑开头",
        "takeaway": "用片头、卡点或剪辑手法做开场，而不只靠文案钩子。",
        "keywords": ("片头", "开幕", "三种开头", "文字卡点", "剪辑常用", "剪辑技巧", "微创意片头"),
        "regexes": (r"剪辑作品",),
    },
    {
        "name": "一秒抓人/视觉片头",
        "takeaway": "用视觉冲击、电影感或「只看开场」在第一秒抓住注意力。",
        "keywords": ("一秒抓人", "抓人注意力", "只看开场", "视觉失焦", "电影感"),
        "regexes": (r"视觉",),
    },
    {
        "name": "七句/公式钩子口诀",
        "takeaway": "可直接套用的钩子口诀、公式和合集，偏文案清单和话术。",
        "keywords": (
            "七句",
            "万能钩子",
            "钩子开头",
            "开头钩子",
            "套公式",
            "直接套",
            "直接抄",
            "直接抱走",
            "套用",
            "套模版",
            "套模板",
            "跑量钩子",
        ),
        "regexes": (
            r"\d+\s*(个|句|类|招|种|条).{0,12}(钩子|开头)",
            r"(钩子|开头).{0,6}合集",
            r"公式",
        ),
    },
    {
        "name": "黄金三秒/前三秒教学",
        "takeaway": "仍在教怎么抓住前三秒：留人结构、素材拍法和开场节奏。",
        "keywords": ("黄金三秒", "前三秒", "三秒留人", "三秒钩子", "前几秒"),
        "regexes": (r"(前|黄金)?三秒",),
    },
    {
        "name": "海外社媒灵感",
        "takeaway": "海外社媒、TK/IG 的爆款灵感和拆解，不完全是可直接套的开头公式。",
        "keywords": ("海外", "tiktok", "tk电商", "ins", "reels", "社媒灵感", "社媒看点"),
        "regexes": (r"\btk\b", r"\big\b"),
    },
]

OTHER_NAME = "其他"
OTHER_TAKEAWAY = "标题未点明具体钩子手法，或只是账号名、泛灵感。"

# Residual / off-topic groups stay out of the curated 5-10 unless there
# are not enough named hook-pattern notes to reach the minimum.
CURATION_SKIP = frozenset({OTHER_NAME, "写作/小说开头"})
DEFAULT_CURATE_LIMIT = 10
DEFAULT_CURATE_MIN = 5


_LIKES_RE = re.compile(
    r"([\d]+(?:\.[\d]+)?)([万wWkK])?",
)
_GO_MARK = "127.0.0.1:18765/go"


def _normalize_title(title: str) -> str:
    text = (title or "").strip().lower()
    text = text.replace("黄金3秒", "黄金三秒").replace("前3秒", "前三秒")
    text = re.sub(r"([黄金前]?)3\s*秒", r"\1三秒", text)
    return text


def _likes_count(note: dict) -> Optional[int]:
    if not isinstance(note, dict):
        return None
    raw = note.get("likes_count")
    if raw is not None and raw != "":
        try:
            return int(raw)
        except (TypeError, ValueError):
            try:
                return int(float(raw))
            except (TypeError, ValueError):
                pass
    text = str(note.get("likes") or "").strip()
    if not text:
        return None
    text = re.sub(r"^(赞|点赞|收藏|评论|likes?)\s*", "", text, flags=re.IGNORECASE).strip()
    text = text.rstrip("+").strip()
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
    return int(number)


def _note_id(note: dict) -> str:
    if not isinstance(note, dict):
        return ""
    nid = str(note.get("id") or "").strip()
    if nid:
        return nid
    url = str(note.get("url") or "")
    match = re.search(r"(?:[?&]id=|/explore/|/search_result/)([0-9a-f]{24})", url, re.I)
    return match.group(1) if match else ""


def _example_url(note: dict) -> str:
    """Prefer the API url (usually a local /go link). Never invent an xsec_token."""
    if not isinstance(note, dict):
        return ""
    url = str(note.get("url") or "").strip()
    if url:
        return url
    return ""


def _prefer_note(current: dict, incoming: dict) -> dict:
    """Keep the higher-like copy; prefer a /go url when likes tie or are equal."""
    cur_likes = _likes_count(current)
    new_likes = _likes_count(incoming)
    cur_key = cur_likes if cur_likes is not None else -1
    new_key = new_likes if new_likes is not None else -1
    if new_key > cur_key:
        chosen = dict(incoming)
    elif new_key < cur_key:
        chosen = dict(current)
    else:
        chosen = dict(current)
        # Fill missing fields from the other copy.
        for key, value in incoming.items():
            if chosen.get(key) in (None, "") and value not in (None, ""):
                chosen[key] = value
    cur_url = str(current.get("url") or "")
    new_url = str(incoming.get("url") or "")
    if _GO_MARK in new_url and _GO_MARK not in str(chosen.get("url") or ""):
        chosen["url"] = new_url
    elif _GO_MARK in cur_url and _GO_MARK not in str(chosen.get("url") or ""):
        chosen["url"] = cur_url
    if chosen.get("likes_count") is None:
        likes = _likes_count(chosen)
        if likes is not None:
            chosen["likes_count"] = likes
    return chosen


def dedupe_notes(notes: Iterable[dict]) -> list[dict]:
    """Drop repeated notes by id (or url if id is missing). Preserve first-seen order."""
    by_key: dict[str, dict] = {}
    order: list[str] = []
    unlabeled = 0
    for raw in notes or []:
        if not isinstance(raw, dict):
            continue
        note = dict(raw)
        if note.get("likes_count") is None:
            likes = _likes_count(note)
            if likes is not None:
                note["likes_count"] = likes
        key = _note_id(note) or str(note.get("url") or "").strip()
        if not key:
            unlabeled += 1
            key = "__anon_%d" % unlabeled
        if key not in by_key:
            by_key[key] = note
            order.append(key)
        else:
            by_key[key] = _prefer_note(by_key[key], note)
    return [by_key[key] for key in order]


def classify_title(title: str) -> str:
    """Return the first matching pattern name, or 其他."""
    text = _normalize_title(title)
    if not text:
        return OTHER_NAME
    tokens = set()
    try:
        tokens = {tok.lower() for tok in tokenize(title or "") if tok}
    except Exception:
        tokens = set()
    for pattern in PATTERNS:
        for keyword in pattern["keywords"]:
            needle = _normalize_title(keyword)
            if needle and (needle in text or needle in tokens):
                return pattern["name"]
        for raw in pattern["regexes"]:
            if re.search(raw, text, flags=re.IGNORECASE):
                return pattern["name"]
    return OTHER_NAME


def _takeaway_for(name: str) -> str:
    if name == OTHER_NAME:
        return OTHER_TAKEAWAY
    for pattern in PATTERNS:
        if pattern["name"] == name:
            return pattern["takeaway"]
    return OTHER_TAKEAWAY


def _rank_key(note: dict) -> tuple:
    likes = _likes_count(note)
    return (likes is None, -(likes or 0))


def _example_payload(note: dict) -> dict:
    likes = _likes_count(note)
    return {
        "title": str(note.get("title") or "").strip(),
        "author": str(note.get("author") or "").strip(),
        "likes_count": likes,
        "url": _example_url(note),
    }


def summarize_notes(notes: Iterable[dict]) -> dict:
    """Group notes by hook pattern and emit a short structured summary.

    Returns:
        {groups: [{name, takeaway, count, example}], total, unique}
    """
    source = [n for n in (notes or []) if isinstance(n, dict)]
    unique_notes = dedupe_notes(source)
    buckets: dict[str, list[dict]] = {}
    order: list[str] = []
    for note in unique_notes:
        name = classify_title(str(note.get("title") or ""))
        if name not in buckets:
            buckets[name] = []
            order.append(name)
        buckets[name].append(note)

    groups = []
    for name in order:
        members = sorted(buckets[name], key=_rank_key)
        example = _example_payload(members[0]) if members else {
            "title": "",
            "author": "",
            "likes_count": None,
            "url": "",
        }
        top_likes = _likes_count(members[0]) if members else None
        like_sum = sum((c or 0) for c in (_likes_count(n) for n in members) if c is not None)
        groups.append({
            "name": name,
            "takeaway": _takeaway_for(name),
            "count": len(members),
            "example": example,
            "top_likes": top_likes,
            "likes_sum": like_sum,
        })

    groups.sort(
        key=lambda g: (
            g.get("name") == OTHER_NAME,
            g.get("top_likes") is None,
            -(g.get("top_likes") or 0),
            -(g.get("likes_sum") or 0),
            -(g.get("count") or 0),
            g.get("name") or "",
        )
    )
    # Keep the documented fields first; extra ranking fields stay for reuse.
    return {
        "groups": groups,
        "total": len(source),
        "unique": len(unique_notes),
    }



def attach_summary(payload: dict) -> dict:
    """Attach summary + curated fields to a /search or /explore payload."""
    if not isinstance(payload, dict):
        return payload
    notes = payload.get("notes") if isinstance(payload.get("notes"), list) else []
    payload["summary"] = summarize_notes(notes)
    payload["curated"] = curate_notes(notes)
    unique = dedupe_notes(notes)
    payload["unique"] = len(unique)
    return payload


def _note_card(note: dict, group: str = "") -> dict:
    card = _example_payload(note)
    nid = _note_id(note)
    if nid:
        card["id"] = nid
    if group:
        card["group"] = group
    return card


def curate_notes(
    notes: Iterable[dict],
    limit: int = DEFAULT_CURATE_LIMIT,
    min_count: int = DEFAULT_CURATE_MIN,
) -> list[dict]:
    """Pick 5-10 highest-quality hook notes for a compact GUI display.

    Named hook-pattern groups win over 其他 and 写作/小说开头. First take
    the top note from each preferred group (already ranked by likes), then
    fill remaining slots by like count. Only dip into skipped groups if
    there are not enough quality notes to reach min_count. Never invent
    URLs or xsec_token values. The full deduped list is not returned here;
    call dedupe_notes(notes) for the complete set.
    """
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = DEFAULT_CURATE_LIMIT
    try:
        min_count = int(min_count)
    except (TypeError, ValueError):
        min_count = DEFAULT_CURATE_MIN
    limit = max(1, min(limit, DEFAULT_CURATE_LIMIT))
    min_count = max(0, min(min_count, limit))

    unique = dedupe_notes(notes)
    if not unique:
        return []

    summary = summarize_notes(unique)
    by_name: dict[str, list[dict]] = {}
    for note in unique:
        name = classify_title(str(note.get("title") or ""))
        by_name.setdefault(name, []).append(note)
    for name in by_name:
        by_name[name].sort(key=_rank_key)

    preferred = [
        group["name"]
        for group in (summary.get("groups") or [])
        if group.get("name") not in CURATION_SKIP
    ]
    skipped = [
        group["name"]
        for group in (summary.get("groups") or [])
        if group.get("name") in CURATION_SKIP
    ]

    curated: list[dict] = []
    seen: set[str] = set()

    def add_note(note: dict, group: str) -> bool:
        if len(curated) >= limit:
            return False
        nid = _note_id(note) or "anon:%s:%s" % (
            note.get("title") or "",
            note.get("author") or "",
        )
        if nid in seen:
            return False
        seen.add(nid)
        curated.append(_note_card(note, group))
        return True

    for name in preferred:
        members = by_name.get(name) or []
        if members:
            add_note(members[0], name)
        if len(curated) >= limit:
            return curated

    if len(curated) < limit:
        rest: list[tuple[dict, str]] = []
        for name in preferred:
            for note in by_name.get(name) or []:
                nid = _note_id(note) or "anon:%s:%s" % (
                    note.get("title") or "",
                    note.get("author") or "",
                )
                if nid not in seen:
                    rest.append((note, name))
        rest.sort(key=lambda item: _rank_key(item[0]))
        for note, name in rest:
            if len(curated) >= limit:
                break
            add_note(note, name)

    if len(curated) < min_count:
        pad: list[tuple[dict, str]] = []
        for name in skipped:
            for note in by_name.get(name) or []:
                nid = _note_id(note) or "anon:%s:%s" % (
                    note.get("title") or "",
                    note.get("author") or "",
                )
                if nid not in seen:
                    pad.append((note, name))
        pad.sort(key=lambda item: _rank_key(item[0]))
        for note, name in pad:
            if len(curated) >= min_count:
                break
            add_note(note, name)

    return curated


def load_notes_from_paths(paths: Iterable[Path]) -> list[dict]:
    notes: list[dict] = []
    for path in paths:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, list):
            notes.extend(item for item in data if isinstance(item, dict))
        elif isinstance(data, dict):
            items = data.get("notes")
            if isinstance(items, list):
                notes.extend(item for item in items if isinstance(item, dict))
    return notes


_NUMBERED_DUMP_RE = re.compile(r"^\d+-")
_NUMBERED_DUMP_CAP = 20
_HOOK_JUNK_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".md"}
_HOOK_JUNK_NAMES = {"summary.json", "local-summary.json", "status-poll.json"}


def is_numbered_search_dump(path: Path) -> bool:
    return path.is_file() and path.suffix == ".json" and bool(_NUMBERED_DUMP_RE.match(path.name))


def cleanup_hook_search_dumps(
    directory: Path,
    *,
    numbered_cap: int = _NUMBERED_DUMP_CAP,
) -> list[Path]:
    """Delete leftover hook-search dumps the reload path does not use.

    The GUI reloads numbered files like ``01-视频开头钩子.json``. When at least
    one of those exists, every other file in the directory is removed
    (screenshots, summaries, live-search copies, and similar leftovers).
    Numbered dumps are kept, except the oldest are dropped if they exceed
    ``numbered_cap``.

    If the directory has no numbered dumps, only obvious junk is removed so
    fallback JSON can still be loaded.
    """
    if not directory.is_dir():
        return []
    try:
        entries = list(directory.iterdir())
    except OSError:
        return []

    deleted: list[Path] = []
    numbered: list[Path] = []
    others: list[Path] = []
    for path in entries:
        if not path.is_file():
            continue
        if is_numbered_search_dump(path):
            numbered.append(path)
        else:
            others.append(path)

    def _unlink(path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            return
        except OSError:
            return
        deleted.append(path)

    if numbered_cap >= 0 and len(numbered) > numbered_cap:
        def _age(path: Path):
            try:
                mtime = path.stat().st_mtime
            except OSError:
                mtime = 0.0
            return (mtime, path.name)

        numbered.sort(key=_age, reverse=True)
        for path in numbered[numbered_cap:]:
            _unlink(path)
        numbered = numbered[:numbered_cap]

    for path in others:
        if numbered or path.suffix.lower() in _HOOK_JUNK_SUFFIXES or path.name in _HOOK_JUNK_NAMES:
            _unlink(path)
    return deleted


def collect_search_paths(source: Path, *, cleanup: bool = True) -> list[Path]:
    if source.is_file():
        return [source]
    if not source.is_dir():
        return []
    if cleanup:
        cleanup_hook_search_dumps(source)
    files = sorted(
        path
        for path in source.iterdir()
        if is_numbered_search_dump(path)
    )
    if files:
        return files
    return sorted(
        path
        for path in source.iterdir()
        if path.is_file() and path.suffix == ".json" and path.name not in {
            "local-summary.json",
            "summary.json",
        }
    )


def render_markdown(summary: dict) -> str:
    lines = [
        "# 本地钩子搜索摘要",
        "",
        "%s notes, %s unique, grouped on-device with no model call."
        % (summary.get("total"), summary.get("unique")),
        "",
    ]
    for index, group in enumerate(summary.get("groups") or [], start=1):
        example = group.get("example") or {}
        likes = example.get("likes_count")
        likes_text = "{:,}".format(likes) if isinstance(likes, int) else "—"
        lines.extend([
            "## %d. %s（%s notes）" % (index, group.get("name"), group.get("count")),
            "",
            group.get("takeaway") or "",
            "",
            "- %s — %s, %s likes, %s"
            % (
                example.get("title") or "(untitled)",
                example.get("author") or "(unknown)",
                likes_text,
                example.get("url") or "",
            ),
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize XHS note lists on-device")
    parser.add_argument("source", help="JSON file or directory of numbered search dumps")
    parser.add_argument("-o", "--out", help="Write JSON summary here")
    parser.add_argument("--md", help="Write a short markdown summary here")
    args = parser.parse_args(argv)
    source = Path(args.source)
    paths = collect_search_paths(source)
    if not paths:
        raise SystemExit("No JSON note files found in %s" % source)
    summary = summarize_notes(load_notes_from_paths(paths))
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.out:
        out = Path(args.out)
        out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    if args.md:
        Path(args.md).write_text(render_markdown(summary), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
