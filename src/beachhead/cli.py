"""The `beachhead` command: fork, wait, clone, branch. Nothing else.

Deliberately stops short of pushing or opening a pull request. Both need
your token to leave this process and land in a `git remote` URL or a
network call beachhead doesn't otherwise make, and that is a bigger trust
boundary than "read a public repo and fork it." You review the diff, you
decide when it is ready, you push it yourself.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import git_ops, github
from .naming import IssueRef, ParseError, branch_name, parse_reference

TOKEN_ENV_VAR = "GITHUB_TOKEN"


class BeachheadError(RuntimeError):
    """Raised for any beachhead-specific failure with a user-facing message."""


def _read_token() -> str:
    token = os.environ.get(TOKEN_ENV_VAR)
    if not token:
        raise BeachheadError(
            f"{TOKEN_ENV_VAR} is not set. Beachhead never accepts a token as a "
            f"command-line argument -- that leaks into shell history and process "
            f"lists. Export {TOKEN_ENV_VAR} instead."
        )
    return token


def _resolve_title(ref: IssueRef, token: str) -> str | None:
    """Fetches the issue title for slugging, if the reference names an issue."""
    if ref.number is None:
        return None
    issue = github.get_issue(ref.owner, ref.repo, ref.number, token)
    if issue.state != "open":
        print(
            f"warning: {ref.full_name}#{ref.number} is already {issue.state}; "
            f"continuing anyway",
            file=sys.stderr,
        )
    return issue.title


def _clone_or_reuse(clone_url: str, dest: Path) -> None:
    if dest.exists():
        if not (dest / ".git").is_dir():
            raise BeachheadError(f"{dest} already exists and is not a git checkout")
        return
    git_ops.clone(clone_url, dest)


def _checkout_branch(branch: str, dest: Path) -> str:
    """Checks out `branch`, creating it if needed. Returns the branch actually active."""
    current = git_ops.current_branch(dest)
    if current == branch:
        return branch
    try:
        git_ops.checkout_new_branch(branch, cwd=dest)
    except git_ops.GitError as error:
        if "already exists" not in error.stderr:
            raise
        git_ops.run(["checkout", branch], cwd=dest)
    return branch


def start(
    reference: str,
    *,
    dir_override: str | None = None,
    branch_override: str | None = None,
    dry_run: bool = False,
) -> Path:
    """Runs the full fork -> wait -> clone -> branch flow for one reference.

    Returns the path to the ready checkout. Raises BeachheadError (or an
    error from `github`/`git_ops`) on any failure.
    """
    try:
        ref = parse_reference(reference)
    except ParseError as error:
        raise BeachheadError(str(error)) from error

    token = _read_token()
    title = _resolve_title(ref, token)
    branch = branch_override or branch_name(ref, title)
    dest = Path(dir_override) if dir_override else Path(ref.repo)

    fork_owner = github.authenticated_login(token)

    if dry_run:
        print(f"would fork:   {ref.full_name} -> {fork_owner}/{ref.repo}")
        print(f"would clone:  https://github.com/{fork_owner}/{ref.repo}.git -> {dest}")
        print(f"would branch: {branch}")
        if title:
            print(f"issue title:  {title}")
        return dest

    print(f"forking {ref.full_name} to {fork_owner}/{ref.repo} ...")
    github.fork_repo(ref.owner, ref.repo, token)

    print("waiting for the fork to become available ...")
    github.wait_for_fork(fork_owner, ref.repo, token)

    clone_url = f"https://github.com/{fork_owner}/{ref.repo}.git"
    print(f"cloning {clone_url} into {dest} ...")
    _clone_or_reuse(clone_url, dest)

    upstream_url = f"https://github.com/{ref.full_name}.git"
    git_ops.add_remote("upstream", upstream_url, cwd=dest)

    print(f"checking out branch {branch} ...")
    _checkout_branch(branch, dest)

    print()
    print(f"ready: {dest}")
    if title:
        print(f"issue:  {ref.full_name}#{ref.number} -- {title}")
    print(f"branch: {branch}")
    print()
    print("next steps:")
    print(f"  cd {dest}")
    print("  # make your changes, run the project's tests")
    print(f"  git push https://<token>@github.com/{fork_owner}/{ref.repo}.git {branch}")
    print(
        f"  # then open a PR: https://github.com/{ref.full_name}/compare/"
        f"main...{fork_owner}:{ref.repo}:{branch}"
    )

    return dest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="beachhead",
        description=(
            "Fork, wait for the fork, clone, and branch -- the mechanical setup "
            "before your first line of a contribution, in one command."
        ),
    )
    parser.add_argument(
        "reference",
        help=(
            "an issue URL (https://github.com/owner/repo/issues/123), "
            "owner/repo#123, or owner/repo"
        ),
    )
    parser.add_argument("--dir", dest="dir_override", help="clone destination (default: ./<repo>)")
    parser.add_argument(
        "--branch", dest="branch_override", help="branch name (default: derived from the issue)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print what would happen without doing it"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        start(
            args.reference,
            dir_override=args.dir_override,
            branch_override=args.branch_override,
            dry_run=args.dry_run,
        )
    except (BeachheadError, github.GitHubError, github.ForkNotReadyError, git_ops.GitError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
