#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for default Most Liked (最多点赞) search sort. No live Xiaohongshu traffic."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from chrome_session import (  # noqa: E402
    SEARCH_SORT_LIKES_PARAM,
    SEARCH_URL,
    build_search_url,
    normalize_search_sort,
    prepare_search_request,
    sort_notes_by_likes,
)


class NormalizeSearchSortTests(unittest.TestCase):
    def test_default_is_likes(self):
        for value in (None, "", "likes", "LIKES", "most_liked", "popularity", "最多点赞", "最热", "newest"):
            self.assertEqual(normalize_search_sort(value), "likes", msg=repr(value))

    def test_comprehensive_opt_out(self):
        for value in ("comprehensive", "综合", "GENERAL", "comp"):
            self.assertIsNone(normalize_search_sort(value), msg=repr(value))


class BuildSearchUrlTests(unittest.TestCase):
    def test_default_url_uses_likes_sort(self):
        url = build_search_url("关键词")
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        self.assertEqual(query["keyword"], ["关键词"])
        self.assertEqual(query["source"], ["web_search_result_notes"])
        self.assertEqual(query["sort"], [SEARCH_SORT_LIKES_PARAM])
        self.assertTrue(url.startswith("https://www.rednote.com/search_result?"))
        self.assertTrue(url.startswith(SEARCH_URL.format(keyword="%E5%85%B3%E9%94%AE%E8%AF%8D")))

    def test_comprehensive_omits_sort_param(self):
        url = build_search_url("hello", sort="综合")
        self.assertNotIn("sort=", url)
        self.assertEqual(url, SEARCH_URL.format(keyword="hello"))

    def test_likes_adds_sort_param(self):
        url = build_search_url("hello", sort="likes")
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        self.assertEqual(query["keyword"], ["hello"])
        self.assertEqual(query["source"], ["web_search_result_notes"])
        self.assertEqual(query["sort"], [SEARCH_SORT_LIKES_PARAM])
        self.assertTrue(url.startswith("https://www.rednote.com/search_result?"))


class PrepareSearchRequestTests(unittest.TestCase):
    def test_default_is_likes_without_a_phrase(self):
        text, sort = prepare_search_request("澳门咖啡店")
        self.assertEqual(sort, "likes")
        self.assertEqual(text, "澳门咖啡店")

    def test_does_not_strip_keyword_text(self):
        text, sort = prepare_search_request("按点赞排的澳门咖啡")
        self.assertEqual(sort, "likes")
        self.assertEqual(text, "按点赞排的澳门咖啡")

    def test_explicit_comprehensive_opt_out(self):
        text, sort = prepare_search_request("澳门咖啡店", sort="综合")
        self.assertIsNone(sort)
        self.assertEqual(text, "澳门咖啡店")


class SortNotesByLikesTests(unittest.TestCase):
    def test_descending_and_missing_last_stable(self):
        notes = [
            {"id": "a", "likes_count": 10},
            {"id": "b", "likes_count": 40},
            {"id": "c"},
            {"id": "d", "likes_count": 40},
            {"id": "e", "likes_count": None},
        ]
        ordered = sort_notes_by_likes(notes)
        self.assertEqual([item["id"] for item in ordered], ["b", "d", "a", "c", "e"])


if __name__ == "__main__":
    unittest.main()
