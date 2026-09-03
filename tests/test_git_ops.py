"""Exercises git_ops against real, throwaway local repos rather than mocking
subprocess. git's own behavior (what "remote add" does when a remote already
exists, what branch a fresh clone lands on, etc.) is exactly the thing worth
verifying for real -- a mock of `subprocess.run` would only prove the code
calls git with the arguments the same code expects it to call, which proves
nothing.
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from beachhead import git_ops


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class GitOpsTestCase(unittest.TestCase):
    """Base class that builds a bare 'origin' and a clone of it per test."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="beachhead-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.origin = self.tmp / "origin.git"
        self.origin.mkdir()
        _git(["init", "--bare", "--initial-branch=main"], cwd=self.origin)

        # A bare repo has no commits, and git needs at least one to clone
        # somewhere meaningful. Push one from a scratch working copy.
        seed = self.tmp / "seed"
        seed.mkdir()
        _git(["init", "--initial-branch=main"], cwd=seed)
        _git(["config", "user.email", "test@example.com"], cwd=seed)
        _git(["config", "user.name", "Test"], cwd=seed)
        (seed / "README.md").write_text("seed\n")
        _git(["add", "README.md"], cwd=seed)
        _git(["commit", "-m", "seed commit"], cwd=seed)
        _git(["remote", "add", "origin", str(self.origin)], cwd=seed)
        _git(["push", "origin", "main"], cwd=seed)

        self.dest = self.tmp / "clone"


class CloneTests(GitOpsTestCase):
    def test_clone_creates_a_working_checkout(self):
        git_ops.clone(str(self.origin), self.dest)

        self.assertTrue((self.dest / ".git").is_dir())
        self.assertTrue((self.dest / "README.md").exists())

    def test_clone_raises_on_a_bad_url(self):
        with self.assertRaises(git_ops.GitError):
            git_ops.clone(str(self.tmp / "does-not-exist"), self.dest)


class RemoteTests(GitOpsTestCase):
    def setUp(self):
        super().setUp()
        git_ops.clone(str(self.origin), self.dest)

    def test_remote_exists_true_for_origin(self):
        self.assertTrue(git_ops.remote_exists("origin", cwd=self.dest))

    def test_remote_exists_false_for_unconfigured_name(self):
        self.assertFalse(git_ops.remote_exists("upstream", cwd=self.dest))

    def test_add_remote_adds_a_new_one(self):
        git_ops.add_remote("upstream", str(self.origin), cwd=self.dest)

        self.assertTrue(git_ops.remote_exists("upstream", cwd=self.dest))

    def test_add_remote_is_a_no_op_when_already_present(self):
        # Would raise "remote upstream already exists" if this weren't
        # idempotent -- the whole point of add_remote over a bare `git
        # remote add` is that beachhead can re-run against a checkout
        # that already has the remote from a previous run.
        git_ops.add_remote("upstream", str(self.origin), cwd=self.dest)
        git_ops.add_remote("upstream", str(self.origin), cwd=self.dest)

        self.assertTrue(git_ops.remote_exists("upstream", cwd=self.dest))


class BranchTests(GitOpsTestCase):
    def setUp(self):
        super().setUp()
        git_ops.clone(str(self.origin), self.dest)

    def test_current_branch_on_a_fresh_clone(self):
        self.assertEqual(git_ops.current_branch(self.dest), "main")

    def test_checkout_new_branch_switches_to_it(self):
        git_ops.checkout_new_branch("feature-x", cwd=self.dest)

        self.assertEqual(git_ops.current_branch(self.dest), "feature-x")

    def test_checkout_new_branch_raises_if_it_already_exists(self):
        git_ops.checkout_new_branch("feature-x", cwd=self.dest)
        _git(["checkout", "main"], cwd=self.dest)

        with self.assertRaises(git_ops.GitError) as ctx:
            git_ops.checkout_new_branch("feature-x", cwd=self.dest)
        self.assertIn("already exists", ctx.exception.stderr)


if __name__ == "__main__":
    unittest.main()
