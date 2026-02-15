import time
import unittest

from db import KVStore


class TestSetGet(unittest.TestCase):
    def setUp(self):
        self.db = KVStore()

    def tearDown(self):
        self.db.stop()

    def test_set_and_get(self):
        self.db.set("k", "v")
        self.assertEqual(self.db.get("k"), "v")

    def test_get_missing(self):
        self.assertIsNone(self.db.get("nope"))

    def test_overwrite(self):
        self.db.set("k", 1)
        self.db.set("k", 2)
        self.assertEqual(self.db.get("k"), 2)

    def test_various_types(self):
        self.db.set("list", [1, 2, 3])
        self.db.set("dict", {"a": 1})
        self.assertEqual(self.db.get("list"), [1, 2, 3])
        self.assertEqual(self.db.get("dict"), {"a": 1})


class TestDelete(unittest.TestCase):
    def setUp(self):
        self.db = KVStore()

    def tearDown(self):
        self.db.stop()

    def test_delete_existing(self):
        self.db.set("k", "v")
        self.assertTrue(self.db.delete("k"))
        self.assertIsNone(self.db.get("k"))

    def test_delete_missing(self):
        self.assertFalse(self.db.delete("ghost"))

    def test_delete_removes_from_keys(self):
        self.db.set("a", 1)
        self.db.set("b", 2)
        self.db.delete("a")
        self.assertNotIn("a", self.db.keys())


class TestTTL(unittest.TestCase):
    def setUp(self):
        self.db = KVStore(cleanup_interval=0.05)

    def tearDown(self):
        self.db.stop()

    def test_ttl_expires(self):
        self.db.set("x", "hello")
        self.db.ttl("x", 0.1)
        time.sleep(0.25)
        self.assertIsNone(self.db.get("x"))

    def test_ttl_not_yet_expired(self):
        self.db.set("x", "hello")
        self.db.ttl("x", 5)
        self.assertEqual(self.db.get("x"), "hello")

    def test_ttl_on_missing_key(self):
        self.assertFalse(self.db.ttl("ghost", 1))

    def test_set_clears_ttl(self):
        self.db.set("x", "v")
        self.db.ttl("x", 0.1)
        self.db.set("x", "v2")   # resets TTL
        time.sleep(0.25)
        self.assertEqual(self.db.get("x"), "v2")

    def test_remaining_ttl(self):
        self.db.set("x", "v")
        self.db.ttl("x", 10)
        r = self.db.remaining_ttl("x")
        self.assertIsNotNone(r)
        self.assertGreater(r, 9)

    def test_remaining_ttl_no_expiry(self):
        self.db.set("x", "v")
        self.assertIsNone(self.db.remaining_ttl("x"))

    def test_remaining_ttl_missing(self):
        self.assertEqual(self.db.remaining_ttl("ghost"), -1.0)


class TestKeys(unittest.TestCase):
    def setUp(self):
        self.db = KVStore()

    def tearDown(self):
        self.db.stop()

    def test_keys(self):
        self.db.set("a", 1)
        self.db.set("b", 2)
        self.assertCountEqual(self.db.keys(), ["a", "b"])

    def test_keys_excludes_expired(self):
        self.db.set("live", 1)
        self.db.set("soon", 2)
        self.db.ttl("soon", 0.05)
        time.sleep(0.15)
        self.assertNotIn("soon", self.db.keys())
        self.assertIn("live", self.db.keys())


class TestFlush(unittest.TestCase):
    def setUp(self):
        self.db = KVStore()

    def tearDown(self):
        self.db.stop()

    def test_flush(self):
        self.db.set("a", 1)
        self.db.set("b", 2)
        self.db.flush()
        self.assertEqual(self.db.keys(), [])
        self.assertIsNone(self.db.get("a"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
