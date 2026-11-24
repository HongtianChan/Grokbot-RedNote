#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Self-check for preference-log cap, trim, clear, and record listing."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import learn


def _note(nid: str, title: str, author: str, token: str = "TOKEN") -> dict:
    url = "https://www.xiaohongshu.com/explore/%s?xsec_token=%s" % (nid, token)
    return {
        "id": nid,
        "url": url,
        "title": title,
        "author": author,
        "likes_count": 10,
    }


class LearnLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        learn.configure_dir(Path(self._tmp.name))
        # Isolate the module-level set-id counter between tests.
        learn._set_counter = 0

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _queries(self) -> list:
        events = learn._load_events()
        return [event.get("query") for event in events if event.get("event") == "result_set"]

    def test_trim_keeps_newest_50_of_more_than_50(self) -> None:
        for index in range(55):
            learn.record_result_set(
                "search",
                "q-%02d" % index,
                [_note("aaaaaaaaaaaaaaaaaaaaaa%02d" % index, "Title %d" % index, "Author")],
            )
        queries = self._queries()
        self.assertEqual(len(queries), 50)
        self.assertEqual(queries[0], "q-05")
        self.assertEqual(queries[-1], "q-54")
        self.assertNotIn("q-04", queries)

    def test_startup_trim_on_existing_oversized_log(self) -> None:
        # Write past the cap without going through record_result_set's trim.
        events = []
        for index in range(60):
            nid = "bbbbbbbbbbbbbbbbbbbbbb%02d" % index
            events.append({
                "ts": "2026-11-24T18:00:%02d+08:00" % (index % 60),
                "event": "result_set",
                "set_id": "set-%02d" % index,
                "source": "search",
                "query": "old-%02d" % index,
                "count": 1,
                "notes": [_note(nid, "Old %d" % index, "Ann")],
            })
        learn._rewrite_log(events)
        self.assertEqual(len(self._queries()), 60)
        changed = learn.trim_log()
        self.assertTrue(changed)
        queries = self._queries()
        self.assertEqual(len(queries), 50)
        self.assertEqual(queries[0], "old-10")
        self.assertEqual(queries[-1], "old-59")
        self.assertFalse(learn.trim_log())

    def test_trim_keeps_opens_for_retained_sets_only(self) -> None:
        events = []
        for index in range(52):
            nid = "cccccccccccccccccccccc%02d" % index
            events.append({
                "ts": "2026-11-24T18:00:%02d+08:00" % (index % 60),
                "event": "result_set",
                "set_id": "set-%02d" % index,
                "source": "search",
                "query": "s-%02d" % index,
                "count": 1,
                "notes": [_note(nid, "N %d" % index, "Ann")],
            })
        # Open only belonging to a trimmed early set.
        events.append({
            "ts": "2026-11-24T18:01:00+08:00",
            "event": "open",
            "id": "cccccccccccccccccccccc00",
            "url": "https://www.xiaohongshu.com/explore/cccccccccccccccccccccc00?xsec_token=TOKEN",
            "title": "N 0",
            "author": "Ann",
            "likes_count": 10,
        })
        # Open belonging to a retained late set.
        events.append({
            "ts": "2026-11-24T18:01:01+08:00",
            "event": "open",
            "id": "cccccccccccccccccccccc51",
            "url": "https://www.xiaohongshu.com/explore/cccccccccccccccccccccc51?xsec_token=TOKEN",
            "title": "N 51",
            "author": "Ann",
            "likes_count": 10,
        })
        # Orphan open (direct /note), not in any result set.
        events.append({
            "ts": "2026-11-24T18:01:02+08:00",
            "event": "open",
            "id": "dddddddddddddddddddddddd",
            "url": "https://www.xiaohongshu.com/explore/dddddddddddddddddddddddd?xsec_token=TOKEN",
            "title": "Direct",
            "author": "Bob",
            "likes_count": 3,
        })
        learn._rewrite_log(events)
        learn.trim_log()
        loaded = learn._load_events()
        kinds = [event.get("event") for event in loaded]
        self.assertEqual(kinds.count("result_set"), 50)
        opens = [event for event in loaded if event.get("event") == "open"]
        open_ids = {event.get("id") for event in opens}
        self.assertNotIn("cccccccccccccccccccccc00", open_ids)
        self.assertIn("cccccccccccccccccccccc51", open_ids)
        self.assertIn("dddddddddddddddddddddddd", open_ids)
        weights = json.loads(learn.WEIGHTS_FILE.read_text(encoding="utf-8"))
        self.assertEqual(weights["opened_count"], 2)
        self.assertIn("Ann", weights["authors_opened"])
        self.assertIn("Bob", weights["authors_opened"])

    def test_clear_records_wipes_log_and_resets_weights(self) -> None:
        learn.record_result_set("search", "keep-me", [_note("eeeeeeeeeeeeeeeeeeeeeeee", "Hello", "Ann")])
        # Simulate an open so weights are non-empty.
        learn.record_open({
            "id": "eeeeeeeeeeeeeeeeeeeeeeee",
            "url": "https://www.xiaohongshu.com/explore/eeeeeeeeeeeeeeeeeeeeeeee?xsec_token=TOKEN",
            "title": "Hello",
            "author": "Ann",
            "likes_count": 10,
            "ok": True,
        })
        self.assertTrue(learn.LOG_FILE.is_file())
        self.assertGreater(learn.LOG_FILE.stat().st_size, 0)
        self.assertGreater(int(learn.load_weights().get("opened_count") or 0), 0)
        result = learn.clear_records()
        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 0)
        self.assertEqual(learn.LOG_FILE.read_text(encoding="utf-8"), "")
        self.assertEqual(learn._load_events(), [])
        weights = learn.load_weights()
        self.assertEqual(int(weights.get("opened_count") or 0), 0)
        self.assertEqual(weights.get("authors_opened"), {})

    def test_list_result_sets_newest_first_uses_existing_share_urls(self) -> None:
        first = _note("ffffffffffffffffffffffff", "First title", "Ann", token="TOK_A")
        second = _note("gggggggggggggggggggggggg", "Second title", "Bob", token="TOK_B")
        learn.record_result_set("search", "older", [first])
        learn.record_result_set("search", "newer", [second])
        records = learn.list_result_sets(newest_first=True)
        self.assertEqual([row["query"] for row in records], ["newer", "older"])
        self.assertEqual(records[0]["notes"][0]["title"], "Second title")
        self.assertEqual(records[0]["notes"][0]["author"], "Bob")
        self.assertEqual(
            records[0]["notes"][0]["url"],
            "https://www.xiaohongshu.com/explore/gggggggggggggggggggggggg?xsec_token=TOK_B",
        )
        payload = learn.records_payload()
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["cap"], 50)
        self.assertEqual(payload["records"][0]["query"], "newer")


if __name__ == "__main__":
    unittest.main()
