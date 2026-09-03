"""Pure, dependency-free parsing and naming logic.

Nothing in this module makes a network call or touches the filesystem, so it
is the cheapest part of beachhead to test exhaustively -- and the part most
worth getting right, since a wrong parse silently points every later step at
the wrong repo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_ISSUE_URL_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<number>\d+)/?$"
)
_SHORTHAND_RE = re.compile(r"^(?P<owner>[^/\s]+)/(?P<repo>[^/\s#]+)(?:#(?P<number>\d+))?$")

# GitHub repo names allow letters, digits, hyphen, underscore, and dot, but a
# trailing ".git" is a clone-URL artifact rather than part of the name.
_TRAILING_GIT_RE = re.compile(r"\.git$")

_MAX_SLUG_WORDS = 6
_MAX_SLUG_LEN = 40


@dataclass(frozen=True)
class IssueRef:
    """A resolved reference to a repo, and optionally one issue in it."""

    owner: str
    repo: str
    number: int | None = None

    @property
    def full_name(self) -> str:
        """Returns ``owner/repo``, the form the GitHub API expects."""
        return f"{self.owner}/{self.repo}"


class ParseError(ValueError):
    """Raised when a string is not a recognizable issue or repo reference."""


def parse_reference(text: str) -> IssueRef:
    """Parses a GitHub issue URL or an ``owner/repo[#123]`` shorthand.

    Accepts:
      - ``https://github.com/owner/repo/issues/123`` (with or without a
        trailing slash)
      - ``owner/repo#123``
      - ``owner/repo`` (no issue; caller decides what branch name to use)

    Raises:
        ParseError: if `text` matches neither form, or `owner`/`repo` is
            empty once a trailing ``.git`` is stripped.
    """
    text = text.strip()

    match = _ISSUE_URL_RE.match(text)
    if match:
        return IssueRef(
            owner=match["owner"],
            repo=_TRAILING_GIT_RE.sub("", match["repo"]),
            number=int(match["number"]),
        )

    match = _SHORTHAND_RE.match(text)
    if match:
        repo = _TRAILING_GIT_RE.sub("", match["repo"])
        if not match["owner"] or not repo:
            raise ParseError(f"not a valid GitHub issue or repo reference: {text!r}")
        number = int(match["number"]) if match["number"] else None
        return IssueRef(owner=match["owner"], repo=repo, number=number)

    raise ParseError(f"not a valid GitHub issue or repo reference: {text!r}")


def slugify(title: str) -> str:
    """Turns an issue title into a short, branch-name-safe slug.

    Keeps only ASCII letters, digits, and hyphens; collapses runs of
    anything else into a single hyphen; takes at most the first
    `_MAX_SLUG_WORDS` words; and truncates to `_MAX_SLUG_LEN` characters
    without cutting a word in half.
    """
    ascii_only = title.encode("ascii", "ignore").decode("ascii")
    words = re.findall(r"[A-Za-z0-9]+", ascii_only)
    words = [w.lower() for w in words[:_MAX_SLUG_WORDS]]

    slug = ""
    for word in words:
        candidate = word if not slug else f"{slug}-{word}"
        if len(candidate) > _MAX_SLUG_LEN:
            break
        slug = candidate

    return slug


def branch_name(ref: IssueRef, title: str | None = None) -> str:
    """Builds a branch name from an issue reference and optional title.

    With a number and a usable title: ``issue-123-fix-the-thing``.
    With a number but no usable slug (e.g. an empty or all-punctuation
    title): ``issue-123``.
    Without a number at all: ``beachhead/<repo>``, since there is no issue
    to key off of.
    """
    if ref.number is None:
        return f"beachhead/{ref.repo}"

    slug = slugify(title) if title else ""
    if slug:
        return f"issue-{ref.number}-{slug}"
    return f"issue-{ref.number}"
