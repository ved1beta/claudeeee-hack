"""Comprehensive test suite for the minigit VCS."""
import io
import os
import shutil
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout

# Make sibling modules importable when running from any directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from objects import (
    object_path,
    read_commit,
    read_object,
    read_tree,
    write_commit,
    write_object,
    write_tree,
)
from index import IndexManager
from repository import Repository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tmpdir():
    return tempfile.mkdtemp()


def _write(root, name, content="test content"):
    path = os.path.join(root, name)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _read(root, name):
    with open(os.path.join(root, name), "r", encoding="utf-8") as f:
        return f.read()


def _capture(fn, *args, **kwargs) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        fn(*args, **kwargs)
    return buf.getvalue()


# ===========================================================================
# 1. Object storage
# ===========================================================================

class TestObjectStorage(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmpdir()
        self.mg = os.path.join(self.tmp, ".minigit")
        os.makedirs(os.path.join(self.mg, "objects"))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_write_returns_40_char_hex(self):
        h = write_object(self.mg, b"hello")
        self.assertEqual(len(h), 40)
        self.assertTrue(all(c in "0123456789abcdef" for c in h))

    def test_read_roundtrip(self):
        data = b"\x00\xff binary \n data"
        h = write_object(self.mg, data)
        self.assertEqual(read_object(self.mg, h), data)

    def test_content_addressable_deduplication(self):
        h1 = write_object(self.mg, b"same")
        h2 = write_object(self.mg, b"same")
        self.assertEqual(h1, h2)

    def test_different_content_different_hash(self):
        h1 = write_object(self.mg, b"aaa")
        h2 = write_object(self.mg, b"bbb")
        self.assertNotEqual(h1, h2)

    def test_object_split_into_2_char_subdirectory(self):
        h = write_object(self.mg, b"test")
        path = object_path(self.mg, h)
        # first-level dir should be exactly 2 hex chars
        first_dir = os.path.basename(os.path.dirname(path))
        self.assertEqual(first_dir, h[:2])
        self.assertEqual(os.path.basename(path), h[2:])

    def test_object_file_exists_on_disk(self):
        h = write_object(self.mg, b"exists?")
        self.assertTrue(os.path.isfile(object_path(self.mg, h)))


# ===========================================================================
# 2. Tree objects
# ===========================================================================

class TestTreeObjects(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmpdir()
        self.mg = os.path.join(self.tmp, ".minigit")
        os.makedirs(os.path.join(self.mg, "objects"))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_empty_tree_roundtrip(self):
        h = write_tree(self.mg, {})
        self.assertEqual(read_tree(self.mg, h), {})

    def test_tree_roundtrip(self):
        entries = {"a.txt": "a" * 40, "src/b.py": "b" * 40}
        h = write_tree(self.mg, entries)
        self.assertEqual(read_tree(self.mg, h), entries)

    def test_tree_is_sorted(self):
        """Two dicts with same content but different insertion order → same hash."""
        h1 = write_tree(self.mg, {"z": "1" * 40, "a": "2" * 40})
        h2 = write_tree(self.mg, {"a": "2" * 40, "z": "1" * 40})
        self.assertEqual(h1, h2)


# ===========================================================================
# 3. Commit objects
# ===========================================================================

class TestCommitObjects(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmpdir()
        self.mg = os.path.join(self.tmp, ".minigit")
        os.makedirs(os.path.join(self.mg, "objects"))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_commit_roundtrip_no_parent(self):
        tree = write_tree(self.mg, {})
        ts = time.time()
        h = write_commit(self.mg, tree, None, "init", ts)
        c = read_commit(self.mg, h)
        self.assertEqual(c["tree"], tree)
        self.assertIsNone(c["parent"])
        self.assertEqual(c["message"], "init")
        self.assertAlmostEqual(c["timestamp"], ts, places=3)

    def test_commit_roundtrip_with_parent(self):
        tree = write_tree(self.mg, {})
        c1 = write_commit(self.mg, tree, None, "first", time.time())
        c2 = write_commit(self.mg, tree, c1, "second", time.time())
        self.assertEqual(read_commit(self.mg, c2)["parent"], c1)

    def test_commit_hash_is_deterministic(self):
        tree = write_tree(self.mg, {})
        ts = 1_700_000_000.0
        h1 = write_commit(self.mg, tree, None, "msg", ts)
        h2 = write_commit(self.mg, tree, None, "msg", ts)
        self.assertEqual(h1, h2)

    def test_different_messages_different_hash(self):
        tree = write_tree(self.mg, {})
        ts = 1_700_000_000.0
        h1 = write_commit(self.mg, tree, None, "msg1", ts)
        h2 = write_commit(self.mg, tree, None, "msg2", ts)
        self.assertNotEqual(h1, h2)


# ===========================================================================
# 4. Index / staging area
# ===========================================================================

class TestIndex(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmpdir()
        self.mg = os.path.join(self.tmp, ".minigit")
        os.makedirs(self.mg)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_empty_index(self):
        self.assertEqual(IndexManager(self.mg).get_entries(), {})

    def test_add_and_read(self):
        idx = IndexManager(self.mg)
        idx.add("file.txt", "a" * 40)
        self.assertEqual(idx.get_entries()["file.txt"], "a" * 40)

    def test_overwrite_entry(self):
        idx = IndexManager(self.mg)
        idx.add("f", "old" + "0" * 37)
        idx.add("f", "new" + "0" * 37)
        self.assertTrue(idx.get_entries()["f"].startswith("new"))

    def test_remove_existing(self):
        idx = IndexManager(self.mg)
        idx.add("x.txt", "a" * 40)
        self.assertTrue(idx.remove("x.txt"))
        self.assertNotIn("x.txt", idx.get_entries())

    def test_remove_nonexistent_returns_false(self):
        self.assertFalse(IndexManager(self.mg).remove("ghost"))

    def test_persistence_across_instances(self):
        IndexManager(self.mg).add("p.txt", "b" * 40)
        self.assertIn("p.txt", IndexManager(self.mg).get_entries())

    def test_multiple_files(self):
        idx = IndexManager(self.mg)
        idx.add("a", "1" * 40)
        idx.add("b", "2" * 40)
        idx.add("c", "3" * 40)
        self.assertEqual(len(idx.get_entries()), 3)


# ===========================================================================
# 5. Repository — init
# ===========================================================================

class TestRepoInit(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmpdir()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_creates_minigit_dir(self):
        Repository.init(self.tmp)
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, ".minigit")))

    def test_creates_objects_dir(self):
        Repository.init(self.tmp)
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, ".minigit", "objects")))

    def test_creates_head_file(self):
        Repository.init(self.tmp)
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, ".minigit", "HEAD")))

    def test_head_initially_empty(self):
        repo = Repository.init(self.tmp)
        self.assertIsNone(repo._get_head())

    def test_reinit_does_not_raise(self):
        Repository.init(self.tmp)
        Repository.init(self.tmp)  # should not raise
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, ".minigit")))

    def test_no_minigit_raises(self):
        empty = _tmpdir()
        try:
            with self.assertRaises(Exception):
                Repository(empty)
        finally:
            shutil.rmtree(empty)


# ===========================================================================
# 6. Repository — add
# ===========================================================================

class TestRepoAdd(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmpdir()
        self.repo = Repository.init(self.tmp)
        self._orig = os.getcwd()
        os.chdir(self.tmp)

    def tearDown(self):
        os.chdir(self._orig)
        shutil.rmtree(self.tmp)

    def test_add_stages_file(self):
        _write(self.tmp, "hello.txt", "hi")
        self.repo.add("hello.txt")
        self.assertIn("hello.txt", self.repo.index.get_entries())

    def test_add_computes_correct_blob_hash(self):
        from utils import sha1_hash
        content = b"unique content"
        _write(self.tmp, "f.txt", content.decode())
        self.repo.add("f.txt")
        expected = sha1_hash(content)
        self.assertEqual(self.repo.index.get_entries()["f.txt"], expected)

    def test_add_stores_blob_in_objects(self):
        _write(self.tmp, "f.txt", "data")
        self.repo.add("f.txt")
        blob_hash = self.repo.index.get_entries()["f.txt"]
        self.assertTrue(os.path.exists(object_path(self.repo.minigit_path, blob_hash)))

    def test_add_nonexistent_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.repo.add("nope.txt")

    def test_add_updates_existing_entry(self):
        _write(self.tmp, "f.txt", "v1")
        self.repo.add("f.txt")
        h1 = self.repo.index.get_entries()["f.txt"]

        _write(self.tmp, "f.txt", "v2")
        self.repo.add("f.txt")
        h2 = self.repo.index.get_entries()["f.txt"]
        self.assertNotEqual(h1, h2)


# ===========================================================================
# 7. Repository — commit
# ===========================================================================

class TestRepoCommit(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmpdir()
        self.repo = Repository.init(self.tmp)
        self._orig = os.getcwd()
        os.chdir(self.tmp)

    def tearDown(self):
        os.chdir(self._orig)
        shutil.rmtree(self.tmp)

    def test_commit_returns_40_char_hash(self):
        _write(self.tmp, "f.txt", "x")
        self.repo.add("f.txt")
        h = self.repo.commit("first")
        self.assertIsNotNone(h)
        self.assertEqual(len(h), 40)

    def test_commit_updates_head(self):
        _write(self.tmp, "f.txt", "x")
        self.repo.add("f.txt")
        h = self.repo.commit("first")
        self.assertEqual(self.repo._get_head(), h)

    def test_commit_empty_index_returns_none(self):
        self.assertIsNone(self.repo.commit("nothing"))

    def test_commit_no_change_returns_none(self):
        _write(self.tmp, "f.txt", "x")
        self.repo.add("f.txt")
        self.repo.commit("first")
        # Re-add same content → index unchanged → nothing to commit
        self.repo.add("f.txt")
        self.assertIsNone(self.repo.commit("again"))

    def test_parent_chain(self):
        _write(self.tmp, "f.txt", "v1")
        self.repo.add("f.txt")
        c1 = self.repo.commit("first")

        _write(self.tmp, "f.txt", "v2")
        self.repo.add("f.txt")
        c2 = self.repo.commit("second")

        self.assertEqual(read_commit(self.repo.minigit_path, c2)["parent"], c1)

    def test_first_commit_has_no_parent(self):
        _write(self.tmp, "f.txt", "x")
        self.repo.add("f.txt")
        c1 = self.repo.commit("init")
        self.assertIsNone(read_commit(self.repo.minigit_path, c1)["parent"])

    def test_commit_tree_matches_staged_files(self):
        _write(self.tmp, "a.txt", "A")
        _write(self.tmp, "b.txt", "B")
        self.repo.add("a.txt")
        self.repo.add("b.txt")
        h = self.repo.commit("two files")
        tree = read_tree(
            self.repo.minigit_path,
            read_commit(self.repo.minigit_path, h)["tree"],
        )
        self.assertIn("a.txt", tree)
        self.assertIn("b.txt", tree)


# ===========================================================================
# 8. Repository — log
# ===========================================================================

class TestRepoLog(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmpdir()
        self.repo = Repository.init(self.tmp)
        self._orig = os.getcwd()
        os.chdir(self.tmp)

    def tearDown(self):
        os.chdir(self._orig)
        shutil.rmtree(self.tmp)

    def test_log_no_commits(self):
        out = _capture(self.repo.log)
        self.assertIn("No commits yet", out)

    def test_log_shows_commit_hash(self):
        _write(self.tmp, "f.txt", "x")
        self.repo.add("f.txt")
        h = self.repo.commit("test msg")
        out = _capture(self.repo.log)
        self.assertIn(h, out)

    def test_log_shows_message(self):
        _write(self.tmp, "f.txt", "x")
        self.repo.add("f.txt")
        self.repo.commit("my message here")
        out = _capture(self.repo.log)
        self.assertIn("my message here", out)

    def test_log_multiple_commits_newest_first(self):
        for i in range(3):
            _write(self.tmp, "f.txt", str(i))
            self.repo.add("f.txt")
            self.repo.commit(f"commit {i}")
        out = _capture(self.repo.log)
        pos2 = out.index("commit 2")
        pos1 = out.index("commit 1")
        pos0 = out.index("commit 0")
        self.assertLess(pos2, pos1)
        self.assertLess(pos1, pos0)


# ===========================================================================
# 9. Repository — status
# ===========================================================================

class TestRepoStatus(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmpdir()
        self.repo = Repository.init(self.tmp)
        self._orig = os.getcwd()
        os.chdir(self.tmp)

    def tearDown(self):
        os.chdir(self._orig)
        shutil.rmtree(self.tmp)

    def test_status_untracked_file(self):
        _write(self.tmp, "new.txt", "hi")
        out = _capture(self.repo.status)
        self.assertIn("new.txt", out)

    def test_status_staged_new_file(self):
        _write(self.tmp, "new.txt", "hi")
        self.repo.add("new.txt")
        out = _capture(self.repo.status)
        self.assertIn("new file", out)
        self.assertIn("new.txt", out)

    def test_status_staged_modified_file(self):
        _write(self.tmp, "f.txt", "v1")
        self.repo.add("f.txt")
        self.repo.commit("first")
        _write(self.tmp, "f.txt", "v2")
        self.repo.add("f.txt")
        out = _capture(self.repo.status)
        self.assertIn("modified", out)
        self.assertIn("f.txt", out)

    def test_status_unstaged_modification(self):
        _write(self.tmp, "f.txt", "v1")
        self.repo.add("f.txt")
        self.repo.commit("first")
        _write(self.tmp, "f.txt", "v2")  # modify but don't stage
        out = _capture(self.repo.status)
        self.assertIn("modified", out)

    def test_status_clean_after_commit(self):
        _write(self.tmp, "f.txt", "v1")
        self.repo.add("f.txt")
        self.repo.commit("first")
        out = _capture(self.repo.status)
        self.assertIn("nothing to commit", out)


# ===========================================================================
# 10. Repository — checkout
# ===========================================================================

class TestRepoCheckout(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmpdir()
        self.repo = Repository.init(self.tmp)
        self._orig = os.getcwd()
        os.chdir(self.tmp)

    def tearDown(self):
        os.chdir(self._orig)
        shutil.rmtree(self.tmp)

    def test_checkout_restores_file_content(self):
        _write(self.tmp, "f.txt", "version 1")
        self.repo.add("f.txt")
        c1 = self.repo.commit("v1")

        _write(self.tmp, "f.txt", "version 2")
        self.repo.add("f.txt")
        self.repo.commit("v2")

        self.repo.checkout(c1)
        self.assertEqual(_read(self.tmp, "f.txt"), "version 1")

    def test_checkout_updates_head(self):
        _write(self.tmp, "f.txt", "v1")
        self.repo.add("f.txt")
        c1 = self.repo.commit("v1")

        _write(self.tmp, "f.txt", "v2")
        self.repo.add("f.txt")
        self.repo.commit("v2")

        self.repo.checkout(c1)
        self.assertEqual(self.repo._get_head(), c1)

    def test_checkout_short_hash(self):
        _write(self.tmp, "f.txt", "data")
        self.repo.add("f.txt")
        c1 = self.repo.commit("init")

        _write(self.tmp, "f.txt", "data2")
        self.repo.add("f.txt")
        self.repo.commit("second")

        self.repo.checkout(c1[:7])
        self.assertEqual(self.repo._get_head(), c1)

    def test_checkout_removes_files_added_later(self):
        _write(self.tmp, "a.txt", "a")
        self.repo.add("a.txt")
        c1 = self.repo.commit("only a")

        _write(self.tmp, "b.txt", "b")
        self.repo.add("b.txt")
        self.repo.commit("added b")

        self.repo.checkout(c1)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "a.txt")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "b.txt")))

    def test_checkout_restores_multiple_files(self):
        _write(self.tmp, "a.txt", "aa")
        _write(self.tmp, "b.txt", "bb")
        self.repo.add("a.txt")
        self.repo.add("b.txt")
        c1 = self.repo.commit("two files")

        _write(self.tmp, "a.txt", "aa modified")
        self.repo.add("a.txt")
        self.repo.commit("mod a")

        self.repo.checkout(c1)
        self.assertEqual(_read(self.tmp, "a.txt"), "aa")
        self.assertEqual(_read(self.tmp, "b.txt"), "bb")

    def test_checkout_updates_index(self):
        _write(self.tmp, "f.txt", "v1")
        self.repo.add("f.txt")
        c1 = self.repo.commit("v1")

        _write(self.tmp, "f.txt", "v2")
        self.repo.add("f.txt")
        self.repo.commit("v2")

        self.repo.checkout(c1)
        # After checkout, index should reflect c1's tree
        staged = self.repo.index.get_entries()
        blob = read_object(
            self.repo.minigit_path, staged["f.txt"]
        )
        self.assertEqual(blob, b"v1")

    def test_checkout_invalid_hash_raises(self):
        _write(self.tmp, "f.txt", "x")
        self.repo.add("f.txt")
        self.repo.commit("init")
        with self.assertRaises(Exception):
            self.repo.checkout("0" * 40)

    def test_checkout_binary_file(self):
        binary = bytes(range(256))
        path = os.path.join(self.tmp, "bin.dat")
        with open(path, "wb") as f:
            f.write(binary)
        self.repo.add("bin.dat")
        c1 = self.repo.commit("binary")

        with open(path, "wb") as f:
            f.write(b"modified")
        self.repo.add("bin.dat")
        self.repo.commit("modified binary")

        self.repo.checkout(c1)
        with open(path, "rb") as f:
            self.assertEqual(f.read(), binary)


# ===========================================================================
# 11. End-to-end workflow
# ===========================================================================

class TestEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmpdir()
        self._orig = os.getcwd()
        os.chdir(self.tmp)

    def tearDown(self):
        os.chdir(self._orig)
        shutil.rmtree(self.tmp)

    def test_full_workflow(self):
        repo = Repository.init(self.tmp)

        # First commit
        _write(self.tmp, "README.md", "# My Project")
        _write(self.tmp, "src/main.py", "print('hello')")
        repo.add("README.md")
        repo.add("src/main.py")
        c1 = repo.commit("Initial commit")
        self.assertIsNotNone(c1)

        # Second commit
        _write(self.tmp, "src/main.py", "print('hello world')")
        repo.add("src/main.py")
        c2 = repo.commit("Update main.py")
        self.assertNotEqual(c1, c2)

        # Log shows both commits
        out = _capture(repo.log)
        self.assertIn(c1, out)
        self.assertIn(c2, out)
        self.assertIn("Initial commit", out)
        self.assertIn("Update main.py", out)

        # Checkout first commit
        repo.checkout(c1)
        self.assertEqual(_read(self.tmp, "src/main.py"), "print('hello')")
        self.assertEqual(repo._get_head(), c1)

        # Back to second commit
        repo.checkout(c2)
        self.assertEqual(_read(self.tmp, "src/main.py"), "print('hello world')")


if __name__ == "__main__":
    unittest.main(verbosity=2)
