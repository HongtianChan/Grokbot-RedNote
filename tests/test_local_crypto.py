#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import local_crypto  # noqa: E402


class LocalCryptoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="grne-crypto-"))

    def test_roundtrip_json(self):
        path = self.tmp / "settings.json"
        payload = {"search_cap": 10, "note": "你好"}
        local_crypto.write_json(path, payload)
        raw = path.read_bytes()
        self.assertTrue(raw.startswith(b"GRNE1"))
        self.assertNotIn(b"search_cap", raw)
        self.assertEqual(local_crypto.read_json(path), payload)

    def test_plaintext_still_readable(self):
        path = self.tmp / "legacy.json"
        path.write_text('{"tier": "paid"}\n', encoding="utf-8")
        self.assertEqual(local_crypto.read_json(path)["tier"], "paid")

    def test_migrate_encrypts_plaintext_in_place(self):
        path = self.tmp / "state.json"
        path.write_text('{"date": "2026-11-27", "searches": 2}\n', encoding="utf-8")
        self.assertEqual(local_crypto.migrate_file(path), "encrypted")
        raw = path.read_bytes()
        self.assertTrue(raw.startswith(b"GRNE1"))
        self.assertEqual(local_crypto.read_json(path)["searches"], 2)
        self.assertEqual(local_crypto.migrate_file(path), "already")

    def test_corrupt_is_quarantined(self):
        path = self.tmp / "weights.json"
        path.write_bytes(b"GRNE1" + b"\x00" * 80)
        self.assertIsNone(local_crypto.read_json(path, default=None))
        self.assertFalse(path.exists())
        self.assertTrue(path.with_suffix(path.suffix + ".corrupt").exists())

    def test_missing_file_returns_default(self):
        path = self.tmp / "nope.json"
        self.assertEqual(local_crypto.read_json(path, default={"ok": True}), {"ok": True})
        self.assertEqual(local_crypto.read_text(path, default=""), "")

    def test_hmac_tamper_fails_closed(self):
        path = self.tmp / "state.json"
        local_crypto.write_json(path, {"searches": 3})
        blob = bytearray(path.read_bytes())
        blob[-1] ^= 0xFF
        path.write_bytes(bytes(blob))
        self.assertIsNone(local_crypto.read_json(path, default=None))
        self.assertTrue(path.with_suffix(".json.corrupt").exists() or (self.tmp / "state.json.corrupt").exists())


if __name__ == "__main__":
    unittest.main()
