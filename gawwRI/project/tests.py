"""
Unit tests for KVDatabase.
Run with:  python -m pytest tests.py -v
       or: python tests.py
"""

import time
import unittest

from db import KVDatabase


class TestBasicOperations(unittest.TestCase):
    def setUp(self):
        self.db = KVDatabase(cleanup_interval=0.1)

    def tearDown(self):
        self.db.close()

    # --- set / get ---

    def test_set_and_get(self):
        self.db.set("name", "alice")
        self.assertEqual(self.db.get("name"), "alice")

    def test_get_missing_key_returns_none(self):
        self.assertIsNone(self.db.get("ghost"))

    def test_set_overwrites_existing(self):
        self.db.set("x", 1)
        self.db.set("x", 2)
        self.assertEqual(self.db.get("x"), 2)

    def test_set_clears_ttl(self):
        self.db.set("k", "v")
        self.db.ttl("k", 0.2)
        self.db.set("k", "v2")          # re-set should clear the TTL
        time.sleep(0.3)
        self.assertEqual(self.db.get("k"), "v2")   # still alive

    # --- delete ---

    def test_delete_existing_key(self):
        self.db.set("a", 1)
        self.assertTrue(self.db.delete("a"))
        self.assertIsNone(self.db.get("a"))

    def test_delete_missing_key_returns_false(self):
        self.assertFalse(self.db.delete("nope"))

    # --- ttl / expiry ---

    def test_key_expires_after_ttl(self):
        self.db.set("temp", "data")
        self.db.ttl("temp", 0.15)
        self.assertEqual(self.db.get("temp"), "data")
        time.sleep(0.25)
        self.assertIsNone(self.db.get("temp"))

    def test_ttl_on_missing_key_returns_false(self):
        self.assertFalse(self.db.ttl("no_such_key", 5))

    def test_remaining_ttl_no_expiry(self):
        self.db.set("k", "v")
        self.assertIsNone(self.db.remaining_ttl("k"))

    def test_remaining_ttl_counts_down(self):
        self.db.set("k", "v")
        self.db.ttl("k", 10)
        remaining = self.db.remaining_ttl("k")
        self.assertIsNotNone(remaining)
        self.assertLessEqual(remaining, 10)
        self.assertGreater(remaining, 9)

    def test_remaining_ttl_missing_key(self):
        self.assertEqual(self.db.remaining_ttl("ghost"), -1.0)

    def test_remaining_ttl_after_expiry(self):
        self.db.set("k", "v")
        self.db.ttl("k", 0.1)
        time.sleep(0.2)
        self.assertEqual(self.db.remaining_ttl("k"), -1.0)

    # --- keys / flush ---

    def test_keys_returns_only_live_keys(self):
        self.db.set("a", 1)
        self.db.set("b", 2)
        self.db.set("c", 3)
        self.db.ttl("c", 0.1)
        time.sleep(0.2)
        self.assertCountEqual(self.db.keys(), ["a", "b"])

    def test_flush_clears_everything(self):
        self.db.set("a", 1)
        self.db.set("b", 2)
        self.db.flush()
        self.assertEqual(self.db.keys(), [])

    # --- dunder helpers ---

    def test_len(self):
        self.db.set("a", 1)
        self.db.set("b", 2)
        self.assertEqual(len(self.db), 2)

    def test_contains(self):
        self.db.set("x", "hello")
        self.assertIn("x", self.db)
        self.assertNotIn("y", self.db)

    # --- background cleanup ---

    def test_background_cleanup_removes_expired_keys(self):
        self.db.set("expiring", "soon")
        self.db.ttl("expiring", 0.1)
        time.sleep(0.4)          # wait for cleanup loop to run
        with self.db._lock:
            self.assertNotIn("expiring", self.db._store)

    # --- value types ---

    def test_supports_various_value_types(self):
        cases = [
            ("int", 42),
            ("float", 3.14),
            ("list", [1, 2, 3]),
            ("dict", {"a": 1}),
            ("none_val", None),
        ]
        for key, val in cases:
            self.db.set(key, val)
        for key, val in cases:
            self.assertEqual(self.db.get(key), val)


if __name__ == "__main__":
    unittest.main(verbosity=2)
