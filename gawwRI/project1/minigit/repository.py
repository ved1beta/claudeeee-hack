"""Core repository operations: init, add, commit, log, status, checkout."""
import os
import time

from utils import find_repo_root, get_minigit_path, sha1_hash, read_file
from objects import (
    write_object,
    read_object,
    write_tree,
    read_tree,
    write_commit,
    read_commit,
)
from index import IndexManager


class Repository:
    # ------------------------------------------------------------------
    # Construction / init
    # ------------------------------------------------------------------

    def __init__(self, repo_root: str = None) -> None:
        if repo_root:
            self.repo_root = os.path.abspath(repo_root)
            if not os.path.isdir(os.path.join(self.repo_root, ".minigit")):
                raise Exception(
                    f"Not a minigit repository: {self.repo_root}"
                )
        else:
            self.repo_root = find_repo_root()
            if not self.repo_root:
                raise Exception(
                    "Not a minigit repository (no .minigit directory found)"
                )
        self.minigit_path = get_minigit_path(self.repo_root)
        self.index = IndexManager(self.minigit_path)

    @classmethod
    def init(cls, path: str = None) -> "Repository":
        """Initialise a new (or re-initialise an existing) repository."""
        path = os.path.abspath(path or os.getcwd())
        minigit_path = os.path.join(path, ".minigit")

        if os.path.isdir(minigit_path):
            print(f"Reinitialized existing minigit repository in {minigit_path}")
            return cls(path)

        os.makedirs(os.path.join(minigit_path, "objects"), exist_ok=True)
        # Empty HEAD — no commits yet
        open(os.path.join(minigit_path, "HEAD"), "w").close()
        print(f"Initialized empty minigit repository in {minigit_path}")
        return cls(path)

    # ------------------------------------------------------------------
    # HEAD helpers
    # ------------------------------------------------------------------

    def _get_head(self) -> str | None:
        head_file = os.path.join(self.minigit_path, "HEAD")
        if not os.path.exists(head_file):
            return None
        content = open(head_file).read().strip()
        return content or None

    def _set_head(self, commit_hash: str) -> None:
        with open(os.path.join(self.minigit_path, "HEAD"), "w") as f:
            f.write(commit_hash)

    # ------------------------------------------------------------------
    # add
    # ------------------------------------------------------------------

    def add(self, file_path: str) -> None:
        """Stage *file_path* (relative to cwd or absolute)."""
        abs_path = os.path.abspath(file_path)
        rel_path = os.path.relpath(abs_path, self.repo_root)

        if not os.path.exists(abs_path):
            raise FileNotFoundError(
                f"pathspec '{file_path}' did not match any files"
            )

        if os.path.isdir(abs_path):
            for dirpath, dirnames, filenames in os.walk(abs_path):
                # Never descend into .minigit or hidden dirs
                dirnames[:] = [
                    d for d in dirnames
                    if d != ".minigit" and not d.startswith(".")
                ]
                for fname in filenames:
                    full = os.path.join(dirpath, fname)
                    self._stage_file(full, os.path.relpath(full, self.repo_root))
        else:
            self._stage_file(abs_path, rel_path)

    def _stage_file(self, abs_path: str, rel_path: str) -> None:
        blob_hash = write_object(self.minigit_path, read_file(abs_path))
        self.index.add(rel_path, blob_hash)
        print(f"Added '{rel_path}'")

    # ------------------------------------------------------------------
    # commit
    # ------------------------------------------------------------------

    def commit(self, message: str) -> str | None:
        """Create a commit from the current index. Returns commit hash or None."""
        staged = self.index.get_entries()
        if not staged:
            print("Nothing to commit (empty index)")
            return None

        head = self._get_head()
        if head:
            prev_tree = read_tree(self.minigit_path, read_commit(self.minigit_path, head)["tree"])
            if prev_tree == staged:
                print("Nothing to commit (working tree clean)")
                return None

        tree_hash = write_tree(self.minigit_path, staged)
        commit_hash = write_commit(
            self.minigit_path, tree_hash, head, message, time.time()
        )
        self._set_head(commit_hash)
        print(f"[{commit_hash[:7]}] {message}")
        return commit_hash

    # ------------------------------------------------------------------
    # log
    # ------------------------------------------------------------------

    def log(self) -> None:
        """Print commit history starting from HEAD."""
        head = self._get_head()
        if not head:
            print("No commits yet")
            return

        current = head
        while current:
            c = read_commit(self.minigit_path, current)
            ts = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(c.get("timestamp", 0))
            )
            print(f"commit {current}")
            print(f"Date:   {ts}")
            print(f"\n    {c.get('message', '')}\n")
            current = c.get("parent")

    # ------------------------------------------------------------------
    # status
    # ------------------------------------------------------------------

    def status(self) -> None:
        """Show staging area and working-directory differences."""
        head = self._get_head()
        staged = self.index.get_entries()

        committed: dict = {}
        if head:
            committed = read_tree(
                self.minigit_path, read_commit(self.minigit_path, head)["tree"]
            )

        # Changes staged for commit
        staged_new, staged_modified, staged_deleted = [], [], []
        for fname, fhash in staged.items():
            if fname not in committed:
                staged_new.append(fname)
            elif committed[fname] != fhash:
                staged_modified.append(fname)
        for fname in committed:
            if fname not in staged:
                staged_deleted.append(fname)

        # Changes in working directory vs index
        unstaged_modified, unstaged_deleted, untracked = [], [], []
        seen: set = set()
        for dirpath, dirnames, filenames in os.walk(self.repo_root):
            dirnames[:] = [
                d for d in dirnames
                if d != ".minigit" and not d.startswith(".")
            ]
            for fname in filenames:
                full = os.path.join(dirpath, fname)
                rel = os.path.relpath(full, self.repo_root)
                seen.add(rel)
                if rel in staged:
                    if sha1_hash(read_file(full)) != staged[rel]:
                        unstaged_modified.append(rel)
                else:
                    untracked.append(rel)

        for fname in staged:
            if fname not in seen:
                unstaged_deleted.append(fname)

        print("On branch main")
        if not head:
            print("\nNo commits yet\n")

        if staged_new or staged_modified or staged_deleted:
            print("Changes to be committed:")
            for f in staged_new:
                print(f"  new file:   {f}")
            for f in staged_modified:
                print(f"  modified:   {f}")
            for f in staged_deleted:
                print(f"  deleted:    {f}")
            print()

        if unstaged_modified or unstaged_deleted:
            print("Changes not staged for commit:")
            for f in unstaged_modified:
                print(f"  modified:   {f}")
            for f in unstaged_deleted:
                print(f"  deleted:    {f}")
            print()

        if untracked:
            print("Untracked files:")
            for f in untracked:
                print(f"  {f}")
            print()

        if not any([
            staged_new, staged_modified, staged_deleted,
            unstaged_modified, unstaged_deleted, untracked,
        ]):
            print("nothing to commit, working tree clean")

    # ------------------------------------------------------------------
    # checkout
    # ------------------------------------------------------------------

    def checkout(self, commit_ref: str) -> None:
        """Restore working directory and index to *commit_ref*."""
        commit_hash = (
            commit_ref if len(commit_ref) == 40
            else self._resolve_short_hash(commit_ref)
        )
        if not commit_hash:
            raise Exception(f"No commit found matching '{commit_ref}'")

        target = read_commit(self.minigit_path, commit_hash)
        target_tree = read_tree(self.minigit_path, target["tree"])
        current_staged = self.index.get_entries()

        # Warn about files that will be overwritten with local modifications
        for fname, blob_hash in target_tree.items():
            full = os.path.join(self.repo_root, fname)
            if os.path.exists(full) and sha1_hash(read_file(full)) != blob_hash:
                print(f"Warning: overwriting modified file '{fname}'")

        # Restore target tree files
        for fname, blob_hash in target_tree.items():
            full = os.path.join(self.repo_root, fname)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "wb") as f:
                f.write(read_object(self.minigit_path, blob_hash))

        # Remove tracked files that don't belong in the target commit
        for fname in current_staged:
            if fname not in target_tree:
                full = os.path.join(self.repo_root, fname)
                if os.path.exists(full):
                    os.remove(full)

        self.index.write(target_tree)
        self._set_head(commit_hash)
        print(f"HEAD is now at {commit_hash[:7]} {target.get('message', '')}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_short_hash(self, short: str) -> str | None:
        """Expand a short hash prefix to a full 40-char hash."""
        objects_dir = os.path.join(self.minigit_path, "objects")
        if not os.path.isdir(objects_dir):
            return None

        prefix_dir = os.path.join(objects_dir, short[:2])
        if not os.path.isdir(prefix_dir):
            return None

        rest = short[2:]
        matches = [
            short[:2] + fname
            for fname in os.listdir(prefix_dir)
            if fname.startswith(rest)
        ]

        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise Exception(f"Ambiguous short hash '{short}'")
        return None
