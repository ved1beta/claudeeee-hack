"""
Test suite for the minigit mini version-control system.

Run with:
    python -m pytest tests/          (from inside the minigit/ directory)
    python -m unittest discover tests/
"""

import os
import shutil
import sys
import tempfile
import time
import unittest

# Make sure the package root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from index import Index
from objects import Blob, Commit, ObjectStore, Tree
from repository import Repository
from utils import sha1_hash


# ===========================================================================
# Utils
# ===========================================================================

class TestUtils(unittest.TestCase):
    def test_sha1_returns_40_hex_chars(self):
        self.assertEqual(len(sha1_hash(b"hello")), 40)

    def test_sha1_deterministic(self):
        self.assertEqual(sha1_hash(b"data"), sha1_hash(b"data"))

    def test_sha1_different_inputs(self):
        self.assertNotEqual(sha1_hash(b"aaa"), sha1_hash(b"bbb"))


# ===========================================================================
# ObjectStore / Blob / Tree / Commit
# ===========================================================================

class TestObjectStore(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = ObjectStore(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    # --- Blob ---------------------------------------------------------------

    def test_blob_roundtrip(self):
        h = Blob.create(self.store, b"hello world")
        self.assertEqual(Blob.read(self.store, h), b"hello world")

    def test_blob_binary_content(self):
        data = bytes(range(256))
        h = Blob.create(self.store, data)
        self.assertEqual(Blob.read(self.store, h), data)

    def test_blob_empty_content(self):
        h = Blob.create(self.store, b"")
        self.assertEqual(Blob.read(self.store, h), b"")

    def test_blob_deterministic(self):
        h1 = Blob.create(self.store, b"same")
        h2 = Blob.create(self.store, b"same")
        self.assertEqual(h1, h2)

    def test_object_exists(self):
        h = Blob.create(self.store, b"x")
        self.assertTrue(self.store.object_exists(h))
        self.assertFalse(self.store.object_exists("a" * 40))

    # --- Tree ---------------------------------------------------------------

    def test_tree_roundtrip(self):
        bh = Blob.create(self.store, b"content")
        entries = {"file.txt": ("100644", bh)}
        th = Tree.create(self.store, entries)
        self.assertEqual(Tree.read(self.store, th), entries)

    def test_tree_multiple_entries(self):
        entries = {
            "b.txt": ("100644", Blob.create(self.store, b"b")),
            "a.txt": ("100644", Blob.create(self.store, b"a")),
        }
        th = Tree.create(self.store, entries)
        result = Tree.read(self.store, th)
        self.assertEqual(set(result), {"a.txt", "b.txt"})

    def test_tree_deterministic(self):
        bh = Blob.create(self.store, b"data")
        entries = {"f.txt": ("100644", bh)}
        th1 = Tree.create(self.store, entries)
        th2 = Tree.create(self.store, entries)
        self.assertEqual(th1, th2)

    def test_tree_empty(self):
        th = Tree.create(self.store, {})
        self.assertEqual(Tree.read(self.store, th), {})

    # --- Commit -------------------------------------------------------------

    def test_commit_roundtrip(self):
        bh = Blob.create(self.store, b"file")
        th = Tree.create(self.store, {"f.txt": ("100644", bh)})
        ch = Commit.create(self.store, th, "", "Init", "Alice")
        data = Commit.read(self.store, ch)
        self.assertEqual(data["tree"], th)
        self.assertEqual(data["message"], "Init")
        self.assertEqual(data["author"], "Alice")
        self.assertEqual(data["parent"], "")

    def test_commit_chain(self):
        bh = Blob.create(self.store, b"v1")
        th = Tree.create(self.store, {"f.txt": ("100644", bh)})
        c1 = Commit.create(self.store, th, "", "First")
        c2 = Commit.create(self.store, th, c1, "Second")
        self.assertEqual(Commit.read(self.store, c2)["parent"], c1)

    # --- resolve_prefix -----------------------------------------------------

    def test_resolve_full_hash(self):
        h = Blob.create(self.store, b"resolve me")
        self.assertEqual(self.store.resolve_prefix(h), h)

    def test_resolve_short_hash(self):
        h = Blob.create(self.store, b"short hash test")
        short = h[:7]
        self.assertEqual(self.store.resolve_prefix(short), h)

    def test_resolve_not_found(self):
        with self.assertRaises(KeyError):
            self.store.resolve_prefix("0000000")


# ===========================================================================
# Index
# ===========================================================================

class TestIndex(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.index = Index(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_add_and_get(self):
        self.index.add("a.txt", "deadbeef")
        self.assertEqual(self.index.get_hash("a.txt"), "deadbeef")

    def test_is_staged(self):
        self.assertFalse(self.index.is_staged("x.txt"))
        self.index.add("x.txt", "abc")
        self.assertTrue(self.index.is_staged("x.txt"))

    def test_persistence(self):
        self.index.add("p.txt", "cafebabe")
        idx2 = Index(self.tmpdir)
        self.assertEqual(idx2.get_hash("p.txt"), "cafebabe")

    def test_remove(self):
        self.index.add("r.txt", "123")
        self.index.remove("r.txt")
        self.assertFalse(self.index.is_staged("r.txt"))

    def test_clear(self):
        self.index.add("c.txt", "456")
        self.index.clear()
        self.assertEqual(self.index.get_entries(), {})

    def test_multiple_entries(self):
        self.index.add("a.txt", "aaa")
        self.index.add("b.txt", "bbb")
        entries = self.index.get_entries()
        self.assertEqual(entries["a.txt"], "aaa")
        self.assertEqual(entries["b.txt"], "bbb")


# ===========================================================================
# Repository (integration tests)
# ===========================================================================

class TestRepository(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig_cwd = os.getcwd()
        os.chdir(self.tmpdir)

    def tearDown(self):
        os.chdir(self._orig_cwd)
        shutil.rmtree(self.tmpdir)

    # Helpers

    def _write(self, name: str, content: str = "hello"):
        path = os.path.join(self.tmpdir, name)
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        with open(path, "w") as f:
            f.write(content)

    def _read(self, name: str) -> str:
        with open(os.path.join(self.tmpdir, name), "r") as f:
            return f.read()

    # --- init ---------------------------------------------------------------

    def test_init_creates_git_dir(self):
        Repository.init(".")
        self.assertTrue(os.path.isdir(os.path.join(self.tmpdir, ".minigit")))
        self.assertTrue(os.path.isdir(os.path.join(self.tmpdir, ".minigit", "objects")))

    def test_init_creates_head(self):
        Repository.init(".")
        self.assertTrue(os.path.exists(os.path.join(self.tmpdir, ".minigit", "HEAD")))

    def test_init_twice_raises(self):
        Repository.init(".")
        with self.assertRaises(FileExistsError):
            Repository.init(".")

    # --- add ----------------------------------------------------------------

    def test_add_stages_file(self):
        repo = Repository.init(".")
        self._write("a.txt")
        repo.add("a.txt")
        self.assertTrue(repo._index().is_staged("a.txt"))

    def test_add_missing_file_raises(self):
        repo = Repository.init(".")
        with self.assertRaises(FileNotFoundError):
            repo.add("ghost.txt")

    def test_add_creates_blob_object(self):
        repo = Repository.init(".")
        self._write("blob.txt", "blob content")
        repo.add("blob.txt")
        blob_hash = repo._index().get_hash("blob.txt")
        self.assertTrue(repo._store().object_exists(blob_hash))

    def test_add_multiple_files(self):
        repo = Repository.init(".")
        self._write("x.txt")
        self._write("y.txt")
        repo.add("x.txt")
        repo.add("y.txt")
        idx = repo._index()
        self.assertTrue(idx.is_staged("x.txt"))
        self.assertTrue(idx.is_staged("y.txt"))

    # --- commit -------------------------------------------------------------

    def test_commit_returns_hash(self):
        repo = Repository.init(".")
        self._write("f.txt")
        repo.add("f.txt")
        h = repo.commit("Init")
        self.assertIsNotNone(h)
        self.assertEqual(len(h), 40)

    def test_commit_updates_head(self):
        repo = Repository.init(".")
        self._write("f.txt")
        repo.add("f.txt")
        h = repo.commit("Init")
        self.assertEqual(repo._get_head(), h)

    def test_commit_clears_index(self):
        repo = Repository.init(".")
        self._write("f.txt")
        repo.add("f.txt")
        repo.commit("Init")
        self.assertEqual(repo._index().get_entries(), {})

    def test_commit_nothing_staged_returns_none(self):
        repo = Repository.init(".")
        result = repo.commit("Empty")
        self.assertIsNone(result)

    def test_commit_chain(self):
        repo = Repository.init(".")
        self._write("f.txt", "v1")
        repo.add("f.txt")
        c1 = repo.commit("First")

        self._write("f.txt", "v2")
        repo.add("f.txt")
        c2 = repo.commit("Second")

        store = repo._store()
        self.assertEqual(Commit.read(store, c2)["parent"], c1)

    def test_commit_tree_contains_staged_files(self):
        repo = Repository.init(".")
        self._write("a.txt", "aaa")
        self._write("b.txt", "bbb")
        repo.add("a.txt")
        repo.add("b.txt")
        h = repo.commit("multi")
        store = repo._store()
        tree = Tree.read(store, Commit.read(store, h)["tree"])
        self.assertIn("a.txt", tree)
        self.assertIn("b.txt", tree)

    # --- log ----------------------------------------------------------------

    def test_log_no_commits(self, capsys=None):
        repo = Repository.init(".")
        # Should not raise; just prints a message
        repo.log()

    def test_log_shows_commits(self):
        import io
        from contextlib import redirect_stdout

        repo = Repository.init(".")
        self._write("f.txt")
        repo.add("f.txt")
        repo.commit("First commit")

        buf = io.StringIO()
        with redirect_stdout(buf):
            repo.log()
        output = buf.getvalue()
        self.assertIn("First commit", output)

    # --- checkout -----------------------------------------------------------

    def test_checkout_restores_file_content(self):
        repo = Repository.init(".")
        self._write("f.txt", "version 1")
        repo.add("f.txt")
        c1 = repo.commit("v1")

        self._write("f.txt", "version 2")
        repo.add("f.txt")
        repo.commit("v2")

        repo.checkout(c1)
        self.assertEqual(self._read("f.txt"), "version 1")

    def test_checkout_updates_head(self):
        repo = Repository.init(".")
        self._write("f.txt", "v1")
        repo.add("f.txt")
        c1 = repo.commit("v1")

        self._write("f.txt", "v2")
        repo.add("f.txt")
        repo.commit("v2")

        repo.checkout(c1)
        self.assertEqual(repo._get_head(), c1)

    def test_checkout_short_hash(self):
        repo = Repository.init(".")
        self._write("f.txt", "old")
        repo.add("f.txt")
        c1 = repo.commit("old")

        self._write("f.txt", "new")
        repo.add("f.txt")
        repo.commit("new")

        repo.checkout(c1[:7])
        self.assertEqual(self._read("f.txt"), "old")

    def test_checkout_clears_index(self):
        repo = Repository.init(".")
        self._write("f.txt", "data")
        repo.add("f.txt")
        c1 = repo.commit("c1")
        repo.checkout(c1)
        self.assertEqual(repo._index().get_entries(), {})

    def test_checkout_invalid_hash_raises(self):
        repo = Repository.init(".")
        with self.assertRaises(SystemExit):
            repo.checkout("0000000")

    def test_checkout_multiple_files(self):
        repo = Repository.init(".")
        self._write("a.txt", "a-v1")
        self._write("b.txt", "b-v1")
        repo.add("a.txt")
        repo.add("b.txt")
        c1 = repo.commit("two files")

        self._write("a.txt", "a-v2")
        repo.add("a.txt")
        repo.commit("update a")

        repo.checkout(c1)
        self.assertEqual(self._read("a.txt"), "a-v1")
        self.assertEqual(self._read("b.txt"), "b-v1")

    # --- find ---------------------------------------------------------------

    def test_find_from_repo_root(self):
        Repository.init(".")
        repo = Repository.find()
        self.assertIsNotNone(repo)

    def test_find_outside_repo_raises(self):
        # tmpdir has no .minigit; but if test runner happens to be inside
        # one we need a truly isolated dir.
        isolated = tempfile.mkdtemp()
        try:
            orig = os.getcwd()
            os.chdir(isolated)
            with self.assertRaises(FileNotFoundError):
                Repository.find()
        finally:
            os.chdir(orig)
            shutil.rmtree(isolated)

    # --- status (smoke tests) -----------------------------------------------

    def test_status_runs_without_error(self):
        repo = Repository.init(".")
        self._write("f.txt")
        repo.add("f.txt")
        repo.status()   # Should not raise

    def test_status_after_commit(self):
        repo = Repository.init(".")
        self._write("f.txt")
        repo.add("f.txt")
        repo.commit("Init")
        repo.status()


if __name__ == "__main__":
    unittest.main()
