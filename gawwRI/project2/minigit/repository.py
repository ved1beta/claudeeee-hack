"""
Core repository operations.

Directory layout
----------------
<root>/
└── .minigit/
    ├── HEAD          one-liner: current commit hash (empty for fresh repo)
    ├── index         JSON staging area
    └── objects/
        └── <xx>/     first two hex chars of the object hash
            └── <yy…> remaining 38 chars, zlib-compressed object
"""

import os
import time

from index import Index
from objects import Blob, Commit, ObjectStore, Tree
from utils import read_file, sha1_hash

MINIGIT_DIR = ".minigit"


class Repository:
    def __init__(self, root: str = "."):
        self.root = os.path.abspath(root)
        self.git_dir = os.path.join(self.root, MINIGIT_DIR)
        self._head_file = os.path.join(self.git_dir, "HEAD")

    # ------------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------------

    @classmethod
    def init(cls, path: str = ".") -> "Repository":
        """Create a new, empty repository."""
        repo = cls(path)
        if os.path.exists(repo.git_dir):
            raise FileExistsError(f"Repository already exists at {repo.git_dir}")
        os.makedirs(os.path.join(repo.git_dir, "objects"), exist_ok=True)
        with open(repo._head_file, "w") as f:
            f.write("")
        print(f"Initialized empty minigit repository in {repo.git_dir}")
        return repo

    @classmethod
    def find(cls, start: str | None = None) -> "Repository":
        """Walk up from *start* (default: cwd) until .minigit is found."""
        path = os.path.abspath(start or os.getcwd())
        while True:
            if os.path.isdir(os.path.join(path, MINIGIT_DIR)):
                return cls(path)
            parent = os.path.dirname(path)
            if parent == path:
                raise FileNotFoundError("Not a minigit repository (no .minigit found)")
            path = parent

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _store(self) -> ObjectStore:
        return ObjectStore(self.git_dir)

    def _index(self) -> Index:
        return Index(self.git_dir)

    def _get_head(self) -> str | None:
        """Return the current HEAD commit hash, or None if repo is empty."""
        if not os.path.exists(self._head_file):
            return None
        with open(self._head_file, "r") as f:
            h = f.read().strip()
        return h or None

    def _set_head(self, commit_hash: str):
        with open(self._head_file, "w") as f:
            f.write(commit_hash)

    def _head_tree(self) -> dict:
        """Return the tree entries ({name: (mode, hash)}) from HEAD, or {} for first commit."""
        head = self._get_head()
        if not head:
            return {}
        store = self._store()
        commit = Commit.read(store, head)
        return Tree.read(store, commit["tree"])

    def _blob_hash_for_path(self, abs_path: str) -> str:
        """Hash current on-disk content WITHOUT storing to object store."""
        content = read_file(abs_path)
        header = f"blob {len(content)}\x00".encode()
        return sha1_hash(header + content)

    # ------------------------------------------------------------------
    # Core commands
    # ------------------------------------------------------------------

    def add(self, filepath: str):
        """
        Stage *filepath* (relative to repo root).
        Stores a blob object and records the mapping in the index.
        """
        abs_path = os.path.join(self.root, filepath)
        if not os.path.isfile(abs_path):
            raise FileNotFoundError(f"pathspec '{filepath}' did not match any files")
        content = read_file(abs_path)
        store = self._store()
        blob_hash = Blob.create(store, content)
        idx = self._index()
        idx.add(filepath, blob_hash)
        print(f"added '{filepath}'")

    def commit(self, message: str, author: str = "Unknown") -> str | None:
        """
        Create a commit from whatever is staged in the index.
        Returns the new commit hash, or None if nothing was staged.
        """
        idx = self._index()
        staged = idx.get_entries()
        if not staged:
            print("nothing to commit, working tree clean")
            return None

        store = self._store()
        tree_entries = {fp: ("100644", bh) for fp, bh in staged.items()}
        tree_hash = Tree.create(store, tree_entries)
        parent = self._get_head() or ""
        commit_hash = Commit.create(store, tree_hash, parent, message, author)

        self._set_head(commit_hash)
        idx.clear()

        print(f"[{commit_hash[:7]}] {message}")
        return commit_hash

    def log(self):
        """Print the commit history starting from HEAD."""
        head = self._get_head()
        if not head:
            print("fatal: your current branch has no commits yet")
            return

        store = self._store()
        current = head
        while current:
            data = Commit.read(store, current)
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(data["timestamp"]))
            print(f"commit {current}")
            print(f"Author: {data['author']}")
            print(f"Date:   {ts}")
            print(f"\n    {data['message']}\n")
            current = data.get("parent") or None

    def status(self):
        """
        Show three sections:
            1. Staged changes (index vs HEAD tree)
            2. Unstaged changes (working dir vs index)
            3. Untracked files
        """
        idx = self._index()
        staged = idx.get_entries()          # {path: blob_hash}
        head_tree = self._head_tree()       # {path: (mode, blob_hash)}
        head_blobs = {p: bh for p, (_, bh) in head_tree.items()}

        # ---- section 1: staged ----------------------------------------
        print("Changes to be committed:")
        has_staged = False
        for path, blob_hash in sorted(staged.items()):
            if path not in head_blobs:
                print(f"\tnew file:   {path}")
            elif head_blobs[path] != blob_hash:
                print(f"\tmodified:   {path}")
            else:
                print(f"\tno change:  {path}")
            has_staged = True
        # deleted-from-index is an advanced feature we skip for now
        if not has_staged:
            print("\t(nothing staged)")

        # ---- section 2: not staged ------------------------------------
        print("\nChanges not staged for commit:")
        has_unstaged = False
        ref_blobs = {**head_blobs, **staged}  # staged takes precedence
        for filepath in sorted(ref_blobs):
            abs_path = os.path.join(self.root, filepath)
            if not os.path.exists(abs_path):
                print(f"\tdeleted:    {filepath}")
                has_unstaged = True
            else:
                current_hash = self._blob_hash_for_path(abs_path)
                if current_hash != ref_blobs[filepath]:
                    print(f"\tmodified:   {filepath}")
                    has_unstaged = True
        if not has_unstaged:
            print("\t(nothing to report)")

        # ---- section 3: untracked ------------------------------------
        print("\nUntracked files:")
        tracked = set(ref_blobs)
        untracked = []
        for entry in sorted(os.listdir(self.root)):
            if entry.startswith("."):
                continue
            if entry not in tracked and os.path.isfile(os.path.join(self.root, entry)):
                untracked.append(entry)
        if untracked:
            for f in untracked:
                print(f"\t{f}")
        else:
            print("\t(nothing to report)")

    def checkout(self, commit_ref: str):
        """
        Restore working directory to the state recorded in *commit_ref*.
        *commit_ref* may be a full or abbreviated (≥4 chars) commit hash.

        Safety: only overwrites tracked files; does NOT delete files that
        exist in the working directory but are absent from the target tree.
        """
        store = self._store()

        # Resolve short hashes
        try:
            full_hash = store.resolve_prefix(commit_ref)
        except KeyError as exc:
            raise SystemExit(f"error: {exc}") from exc

        # Validate it is actually a commit
        obj_type, _ = store.read_object(full_hash)
        if obj_type != "commit":
            raise SystemExit(f"error: {full_hash[:7]} is a {obj_type}, not a commit")

        commit_data = Commit.read(store, full_hash)
        tree_entries = Tree.read(store, commit_data["tree"])

        # Restore every file recorded in the target tree
        for filepath, (_, blob_hash) in tree_entries.items():
            abs_path = os.path.join(self.root, filepath)
            parent_dir = os.path.dirname(abs_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            content = Blob.read(store, blob_hash)
            with open(abs_path, "wb") as f:
                f.write(content)

        self._set_head(full_hash)
        self._index().clear()

        print(f"HEAD is now at {full_hash[:7]} {commit_data['message']}")
