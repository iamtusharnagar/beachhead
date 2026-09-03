"""A minimal GitHub API client.

Talks JSON over HTTPS using only `urllib` from the standard library --
beachhead has zero runtime dependencies, so nothing here can break because
a dependency's dependency shipped a bad release.

Every network call goes through `_request`, which is the one seam the test
suite patches. Nothing else in this module touches a socket directly, so a
test that patches `_request` sees every API interaction beachhead makes.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

API_ROOT = "https://api.github.com"
USER_AGENT = "beachhead-cli"

# A fresh fork briefly 404s while GitHub finishes copying it. 20 tries at
# 2s apart is 40s of headroom -- generous for a fork of anything under a
# few hundred MB, the overwhelming majority of what a first-time
# contributor forks.
FORK_POLL_ATTEMPTS = 20
FORK_POLL_INTERVAL_SECONDS = 2.0


class GitHubError(RuntimeError):
    """Raised when the GitHub API returns an error response."""

    def __init__(self, status: int, message: str):
        super().__init__(f"GitHub API error {status}: {message}")
        self.status = status


class ForkNotReadyError(RuntimeError):
    """Raised when a fork does not become available within the poll budget."""


@dataclass(frozen=True)
class Issue:
    """The subset of a GitHub issue beachhead actually uses."""

    number: int
    title: str
    state: str
    html_url: str


def _request(
    method: str,
    path: str,
    token: str,
    body: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    """Makes one authenticated request to the GitHub REST API.

    Returns the HTTP status and the parsed JSON body. A non-2xx status is
    returned rather than raised, so callers that expect a 404 (checking
    whether a fork exists yet) do not have to catch an exception for an
    entirely ordinary outcome.
    """
    url = f"{API_ROOT}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("User-Agent", USER_AGENT)
    request.add_header("Accept", "application/vnd.github+json")
    if data is not None:
        request.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(request) as response:
            payload = response.read()
            return response.status, (json.loads(payload) if payload else {})
    except urllib.error.HTTPError as error:
        payload = error.read()
        parsed = json.loads(payload) if payload else {}
        return error.code, parsed


def get_repo(owner: str, repo: str, token: str) -> dict[str, Any] | None:
    """Returns the repo's metadata, or None if it does not exist (yet)."""
    status, payload = _request("GET", f"/repos/{owner}/{repo}", token)
    if status == 200:
        return payload
    if status == 404:
        return None
    raise GitHubError(status, payload.get("message", "unknown error"))


def get_issue(owner: str, repo: str, number: int, token: str) -> Issue:
    """Fetches one issue's number, title, state, and URL."""
    status, payload = _request("GET", f"/repos/{owner}/{repo}/issues/{number}", token)
    if status != 200:
        raise GitHubError(status, payload.get("message", "unknown error"))
    return Issue(
        number=payload["number"],
        title=payload["title"],
        state=payload["state"],
        html_url=payload["html_url"],
    )


def fork_repo(owner: str, repo: str, token: str) -> dict[str, Any]:
    """Creates a fork of `owner/repo` under the authenticated user's account.

    Forking an already-forked repo is not an error on GitHub's side -- it
    returns the existing fork -- so callers do not need to check first.
    """
    status, payload = _request("POST", f"/repos/{owner}/{repo}/forks", token)
    if status not in (200, 202):
        raise GitHubError(status, payload.get("message", "unknown error"))
    return payload


def wait_for_fork(
    fork_owner: str,
    repo: str,
    token: str,
    attempts: int = FORK_POLL_ATTEMPTS,
    interval: float = FORK_POLL_INTERVAL_SECONDS,
    sleep=time.sleep,
) -> dict[str, Any]:
    """Polls until a freshly created fork is readable, then returns it.

    GitHub queues the actual copy after `fork_repo` returns, so the fork
    404s for a short window. `sleep` is a parameter (defaulting to
    `time.sleep`) so tests can pass a no-op and run in milliseconds instead
    of `attempts * interval` seconds.
    """
    last_status = None
    for attempt in range(attempts):
        repo_data = get_repo(fork_owner, repo, token)
        if repo_data is not None:
            return repo_data
        last_status = attempt
        if attempt < attempts - 1:
            sleep(interval)

    raise ForkNotReadyError(
        f"{fork_owner}/{repo} did not become available after "
        f"{last_status + 1 if last_status is not None else 0} attempts "
        f"({attempts * interval:.0f}s budget)"
    )


def authenticated_login(token: str) -> str:
    """Returns the login of the user the token belongs to."""
    status, payload = _request("GET", "/user", token)
    if status != 200:
        raise GitHubError(status, payload.get("message", "unknown error"))
    return payload["login"]
