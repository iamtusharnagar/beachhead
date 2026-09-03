# beachhead

Fork, wait, clone, branch — the setup before your first line of a
contribution, in one command.

```
$ beachhead https://github.com/octocat/Hello-World/issues/42
forking octocat/Hello-World to you/Hello-World ...
waiting for the fork to become available ...
cloning https://github.com/you/Hello-World.git into Hello-World ...
checking out branch issue-42-fix-the-thing ...

ready: Hello-World
issue:  octocat/Hello-World#42 -- Fix the thing
branch: issue-42-fix-the-thing

next steps:
  cd Hello-World
  # make your changes, run the project's tests
  git push https://<token>@github.com/you/Hello-World.git issue-42-fix-the-thing
  # then open a PR: https://github.com/octocat/Hello-World/compare/main...you:Hello-World:issue-42-fix-the-thing
```

## Why this exists

Every open-source contribution starts with the same four mechanical steps:
fork the repo, wait for GitHub to finish copying it (forks 404 for a few
seconds right after creation — long enough to catch you if you `cd` too
fast), clone your fork, and check out a sensibly named branch. None of that
is the interesting part of contributing. beachhead does it in one call so
you can get straight to the diff.

## Install

```bash
pip install beachhead
```

Requires Python 3.10+.

## Use

```bash
export GITHUB_TOKEN=ghp_...   # needs the public_repo scope, nothing broader
beachhead <reference>
```

`<reference>` can be:

- a full issue URL — `https://github.com/owner/repo/issues/123`
- shorthand — `owner/repo#123`
- just a repo, with no issue — `owner/repo`

Branch names are derived from the issue: `issue-123-fix-the-login-bug`. With
no issue number, you get `beachhead/<repo>`. Override with `--branch` if you
want something else.

```
beachhead <reference> [--dir PATH] [--branch NAME] [--dry-run]
```

- `--dir` — where to clone (default: `./<repo>`)
- `--branch` — branch name (default: derived from the issue title)
- `--dry-run` — print what would happen without forking, cloning, or
  branching anything

Re-running beachhead against a reference you've already started is safe: it
reuses the existing checkout and branch instead of erroring.

## What it deliberately does not do

beachhead stops once you have a ready checkout on a new branch. It does not
push, and it does not open a pull request. Both of those need your token to
leave this process — either landing in a `git remote` URL or making a
network call beachhead otherwise never makes — and that's a bigger trust
boundary than "read a public repo and fork it." Pushing and opening the PR
stay manual and deliberate: you look at the diff, you decide it's ready, you
push it.

`GITHUB_TOKEN` is only ever read from the environment. beachhead never
accepts it as a command-line argument, because that leaks into shell history
and process listings. It's never written to `.git/config` — the clone is
plain HTTPS, since reading a public repo needs no auth at all.

## Why zero dependencies

beachhead imports only the Python standard library — `urllib` for the
GitHub API, `subprocess` for git, `argparse` for the CLI. No dependency
tree means no dependency's dependency can break your `pip install`, and
nothing here has a supply-chain surface beyond Python itself and git.

## Contributing

Pull requests welcome. The test suite has three layers, matched to how
trustworthy a mock would be for that layer:

- `naming.py` (pure functions, no I/O) — tested directly, no mocking needed.
- `github.py` (HTTP) — tests patch the one function (`_request`) that
  actually opens a socket, so every API interaction is covered without
  hitting the network.
- `git_ops.py` and the `cli.py` orchestration — tested against real,
  throwaway local git repos rather than a mocked `subprocess.run`, since a
  mock would only prove the code calls git the way the same code expects,
  not that git actually behaves that way.

```bash
git clone https://github.com/tusharnagar2002/beachhead.git
cd beachhead
python -m venv .venv && source .venv/bin/activate
pip install -e .
python -m unittest discover -s tests -v
```

## License

MIT
