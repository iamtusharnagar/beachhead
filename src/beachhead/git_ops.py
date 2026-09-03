"""Thin wrappers over `git` subprocess calls.

Every function here is a single git invocation with a clear failure mode.
`run` is the one seam the test suite patches, matching the pattern in
`github.py`: production code always goes through it, so a test that patches
it sees every command beachhead runs.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(RuntimeError):
    """Raised when a git subprocess exits non-zero."""

    def __init__(self, command: list[str], returncode: int, stderr: str):
        super().__init__(f"`{' '.join(command)}` exited {returncode}: {stderr.strip()}")
        self.command = command
        self.returncode = returncode
        self.stderr = stderr


def run(args: list[str], cwd: Path | None = None) -> str:
    """Runs a git command, returning stdout and raising GitError on failure."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GitError(["git", *args], result.returncode, result.stderr)
    return result.stdout


def clone(url: str, dest: Path) -> None:
    """Clones `url` into `dest`, which must not already exist."""
    run(["clone", url, str(dest)])


def remote_exists(name: str, cwd: Path) -> bool:
    """Returns whether a remote named `name` is already configured."""
    output = run(["remote"], cwd=cwd)
    return name in output.splitlines()


def add_remote(name: str, url: str, cwd: Path) -> None:
    """Adds a remote, skipping if one by that name already exists."""
    if remote_exists(name, cwd=cwd):
        return
    run(["remote", "add", name, url], cwd=cwd)


def checkout_new_branch(branch: str, cwd: Path) -> None:
    """Creates and checks out a new branch from the current HEAD."""
    run(["checkout", "-b", branch], cwd=cwd)


def current_branch(cwd: Path) -> str:
    """Returns the name of the currently checked-out branch."""
    return run(["branch", "--show-current"], cwd=cwd).strip()
