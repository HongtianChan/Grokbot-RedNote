#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Daily search cap, persistence, machine binding, and tier tests."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
import sys
from unittest import mock

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import rate_limit


class RateLimitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        rate_limit.configure_paths(root / "state", root / "shadow")
        rate_limit.set_cli_tier(None)
        rate_limit.set_cli_dev(False)
        os.environ.pop("GROKBOT_REDNOTE_TIER", None)
        os.environ.pop("GROKBOT_REDNOTE_DEV", None)
        self.machine_patch = mock.patch.object(
            rate_limit, "machine_fingerprint", return_value="machine-test-aaa"
        )
        self.today_patch = mock.patch.object(rate_limit, "today_key", return_value="2026-11-27")
        self.machine_patch.start()
        self.today_patch.start()

    def tearDown(self) -> None:
        self.machine_patch.stop()
        self.today_patch.stop()
        rate_limit.set_cli_tier(None)
        rate_limit.set_cli_dev(False)
        os.environ.pop("GROKBOT_REDNOTE_TIER", None)
        os.environ.pop("GROKBOT_REDNOTE_DEV", None)
        self.tmpdir.cleanup()

    def test_free_cap_is_10_and_eleventh_is_denied(self) -> None:
        for i in range(10):
            info = rate_limit.consume_search()
            self.assertTrue(info["accepted"])
            self.assertEqual(info["searches_used"], i + 1)
            self.assertEqual(info["search_cap"], 10)
            self.assertEqual(info["tier"], "free")
        with self.assertRaises(rate_limit.RateLimitError) as caught:
            rate_limit.consume_search()
        self.assertTrue(caught.exception.payload["limit_reached"])
        self.assertEqual(caught.exception.payload["searches_used"], 10)
        self.assertEqual(rate_limit.remaining()["searches_left"], 0)

    def test_paid_cap_is_200(self) -> None:
        rate_limit.set_cli_tier("paid")
        for _ in range(200):
            rate_limit.consume_search()
        with self.assertRaises(rate_limit.RateLimitError) as caught:
            rate_limit.consume_search()
        self.assertEqual(caught.exception.payload["search_cap"], 200)
        self.assertEqual(caught.exception.payload["tier"], "paid")

    def test_count_survives_reload(self) -> None:
        rate_limit.consume_search()
        rate_limit.consume_search()
        # New load from disk, as if the process restarted.
        self.assertEqual(rate_limit.load_state()["searches"], 2)
        self.assertEqual(rate_limit.remaining()["searches_used"], 2)

    def test_midnight_reset(self) -> None:
        for _ in range(10):
            rate_limit.consume_search()
        self.today_patch.stop()
        self.today_patch = mock.patch.object(rate_limit, "today_key", return_value="2026-11-28")
        self.today_patch.start()
        info = rate_limit.remaining()
        self.assertEqual(info["searches_used"], 0)
        self.assertEqual(info["date"], "2026-11-28")
        self.assertFalse(info["limit_reached"])
        rate_limit.consume_search()
        self.assertEqual(rate_limit.remaining()["searches_used"], 1)

    def test_shadow_survives_primary_delete(self) -> None:
        for _ in range(4):
            rate_limit.consume_search()
        self.assertTrue(rate_limit.STATE_FILE.is_file())
        rate_limit.STATE_FILE.unlink()
        self.assertEqual(rate_limit.remaining()["searches_used"], 4)
        self.assertTrue(rate_limit.STATE_FILE.is_file())

    def test_tampered_primary_fails_closed_without_shadow(self) -> None:
        rate_limit.consume_search()
        rate_limit.SHADOW_FILE.unlink()
        from local_crypto import read_json
        data = read_json(rate_limit.STATE_FILE)
        data["searches"] = 0
        rate_limit.STATE_FILE.write_text(json.dumps(data), encoding="utf-8")
        info = rate_limit.remaining()
        self.assertEqual(info["searches_used"], 10)
        self.assertTrue(info["limit_reached"])

    def test_other_machine_file_is_ignored(self) -> None:
        rate_limit.consume_search()
        alien = {
            "date": "2026-11-27",
            "searches": 9,
            "machine": "other-machine",
            "sig": rate_limit._sign("other-machine", "2026-11-27", 9),
        }
        rate_limit.STATE_FILE.write_text(json.dumps(alien), encoding="utf-8")
        rate_limit.SHADOW_FILE.write_text(json.dumps(alien), encoding="utf-8")
        self.assertEqual(rate_limit.remaining()["searches_used"], 0)

    def test_subscription_file_selects_paid(self) -> None:
        rate_limit.SUBSCRIPTION_FILE.parent.mkdir(parents=True, exist_ok=True)
        rate_limit.SUBSCRIPTION_FILE.write_text('{"tier": "paid"}\n', encoding="utf-8")
        self.assertEqual(rate_limit.current_tier(), "paid")
        self.assertEqual(rate_limit.search_cap(), 200)

    def test_env_tier_selects_paid(self) -> None:
        os.environ["GROKBOT_REDNOTE_TIER"] = "paid"
        self.assertEqual(rate_limit.current_tier(), "paid")
        self.assertEqual(rate_limit.search_cap(), 200)

    def test_default_without_flags_is_ten(self) -> None:
        self.assertEqual(rate_limit.current_tier(), "free")
        self.assertEqual(rate_limit.search_cap(), 10)
        # A git checkout of the public repo must still be capped; .git is not dev mode.
        self.assertTrue((Path(__file__).resolve().parents[1] / ".git").is_dir())
        self.assertFalse(rate_limit.dev_mode_enabled())

    def test_dev_env_is_unlimited(self) -> None:
        os.environ["GROKBOT_REDNOTE_DEV"] = "1"
        self.assertEqual(rate_limit.current_tier(), "dev")
        self.assertIsNone(rate_limit.search_cap())
        for _ in range(15):
            info = rate_limit.consume_search()
            self.assertTrue(info["accepted"])
            self.assertTrue(info["unlimited"])
            self.assertIsNone(info["search_cap"])
            self.assertIsNone(info["searches_left"])
            self.assertFalse(info["limit_reached"])
        remaining = rate_limit.remaining()
        self.assertEqual(remaining["searches_used"], 15)
        self.assertTrue(remaining["unlimited"])
        self.assertFalse(remaining["limit_reached"])

    def test_dev_flag_is_unlimited(self) -> None:
        rate_limit.set_cli_dev(True)
        self.assertTrue(rate_limit.dev_mode_enabled())
        self.assertIsNone(rate_limit.search_cap())
        rate_limit.consume_search()
        self.assertTrue(rate_limit.remaining()["unlimited"])

    def test_explicit_paid_wins_over_dev(self) -> None:
        os.environ["GROKBOT_REDNOTE_DEV"] = "1"
        rate_limit.set_cli_tier("paid")
        self.assertEqual(rate_limit.current_tier(), "paid")
        self.assertEqual(rate_limit.search_cap(), 200)

    def test_explicit_free_wins_over_dev(self) -> None:
        os.environ["GROKBOT_REDNOTE_DEV"] = "1"
        rate_limit.set_cli_tier("free")
        self.assertEqual(rate_limit.current_tier(), "free")
        self.assertEqual(rate_limit.search_cap(), 10)


if __name__ == "__main__":
    unittest.main()
