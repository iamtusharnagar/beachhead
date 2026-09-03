import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from beachhead import cli, git_ops, github


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _make_origin(tmp: Path) -> Path:
    """Builds a real local bare repo with one commit on `main`."""
    origin = tmp / "origin.git"
    origin.mkdir()
    _git(["init", "--bare", "--initial-branch=main"], cwd=origin)

    seed = tmp / "seed"
    seed.mkdir()
    _git(["init", "--initial-branch=main"], cwd=seed)
    _git(["config", "user.email", "test@example.com"], cwd=seed)
    _git(["config", "user.name", "Test"], cwd=seed)
    (seed / "README.md").write_text("seed\n")
    _git(["add", "README.md"], cwd=seed)
    _git(["commit", "-m", "seed commit"], cwd=seed)
    _git(["remote", "add", "origin", str(origin)], cwd=seed)
    _git(["push", "origin", "main"], cwd=seed)
    return origin


class StartTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="beachhead-cli-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.origin = _make_origin(self.tmp)
        self.dest = self.tmp / "checkout"

        # start() builds real https://github.com/... URLs for logging and
        # for the upstream remote, but the actual clone target is patched
        # to the local bare repo above so the test needs no network.
        real_clone = git_ops.clone
        patcher = patch("beachhead.git_ops.clone")
        self.mock_clone = patcher.start()
        self.addCleanup(patcher.stop)
        self.mock_clone.side_effect = lambda url, dest: real_clone(str(self.origin), dest)

        self.env_patcher = patch.dict("os.environ", {"GITHUB_TOKEN": "fake-token"})
        self.env_patcher.start()
        self.addCleanup(self.env_patcher.stop)

    @patch("beachhead.github.authenticated_login")
    @patch("beachhead.github.wait_for_fork")
    @patch("beachhead.github.fork_repo")
    @patch("beachhead.github.get_issue")
    def test_full_flow_with_an_issue(
        self, mock_get_issue, mock_fork, mock_wait, mock_login
    ):
        mock_login.return_value = "me"
        mock_get_issue.return_value = github.Issue(
            number=42, title="Fix the login bug", state="open", html_url="irrelevant"
        )

        result = cli.start("owner/repo#42", dir_override=str(self.dest))

        self.assertEqual(result, self.dest)
        mock_fork.assert_called_once_with("owner", "repo", "fake-token")
        mock_wait.assert_called_once()
        self.assertEqual(git_ops.current_branch(self.dest), "issue-42-fix-the-login-bug")
        self.assertTrue(git_ops.remote_exists("upstream", cwd=self.dest))

    @patch("beachhead.github.authenticated_login")
    @patch("beachhead.github.wait_for_fork")
    @patch("beachhead.github.fork_repo")
    def test_full_flow_without_an_issue(self, mock_fork, mock_wait, mock_login):
        mock_login.return_value = "me"

        cli.start("owner/repo", dir_override=str(self.dest))

        self.assertEqual(git_ops.current_branch(self.dest), "beachhead/repo")

    @patch("beachhead.github.authenticated_login")
    @patch("beachhead.github.wait_for_fork")
    @patch("beachhead.github.fork_repo")
    @patch("beachhead.github.get_issue")
    def test_branch_override_wins_over_derived_name(
        self, mock_get_issue, mock_fork, mock_wait, mock_login
    ):
        mock_login.return_value = "me"
        mock_get_issue.return_value = github.Issue(
            number=42, title="Fix the login bug", state="open", html_url="irrelevant"
        )

        cli.start("owner/repo#42", dir_override=str(self.dest), branch_override="my-custom-name")

        self.assertEqual(git_ops.current_branch(self.dest), "my-custom-name")

    @patch("beachhead.github.authenticated_login")
    @patch("beachhead.github.wait_for_fork")
    @patch("beachhead.github.fork_repo")
    @patch("beachhead.github.get_issue")
    def test_rerunning_against_an_existing_checkout_reuses_it(
        self, mock_get_issue, mock_fork, mock_wait, mock_login
    ):
        mock_login.return_value = "me"
        mock_get_issue.return_value = github.Issue(
            number=42, title="Fix the login bug", state="open", html_url="irrelevant"
        )

        cli.start("owner/repo#42", dir_override=str(self.dest))
        # Second call: clone must not be attempted again against a
        # directory that already exists, and checking out the same
        # branch a second time must not raise "already exists".
        self.mock_clone.reset_mock()
        cli.start("owner/repo#42", dir_override=str(self.dest))

        self.mock_clone.assert_not_called()
        self.assertEqual(git_ops.current_branch(self.dest), "issue-42-fix-the-login-bug")

    @patch("beachhead.github.authenticated_login")
    @patch("beachhead.github.wait_for_fork")
    @patch("beachhead.github.fork_repo")
    @patch("beachhead.github.get_issue")
    def test_dry_run_makes_no_fork_clone_or_branch(
        self, mock_get_issue, mock_fork, mock_wait, mock_login
    ):
        mock_login.return_value = "me"
        mock_get_issue.return_value = github.Issue(
            number=42, title="Fix the login bug", state="open", html_url="irrelevant"
        )

        result = cli.start("owner/repo#42", dir_override=str(self.dest), dry_run=True)

        self.assertEqual(result, self.dest)
        mock_fork.assert_not_called()
        mock_wait.assert_not_called()
        self.mock_clone.assert_not_called()
        self.assertFalse(self.dest.exists())

    @patch("beachhead.github.authenticated_login")
    @patch("beachhead.github.wait_for_fork")
    @patch("beachhead.github.fork_repo")
    @patch("beachhead.github.get_issue")
    def test_a_closed_issue_warns_but_still_proceeds(
        self, mock_get_issue, mock_fork, mock_wait, mock_login
    ):
        mock_login.return_value = "me"
        mock_get_issue.return_value = github.Issue(
            number=42, title="Already fixed", state="closed", html_url="irrelevant"
        )

        result = cli.start("owner/repo#42", dir_override=str(self.dest))

        self.assertEqual(result, self.dest)
        self.assertEqual(git_ops.current_branch(self.dest), "issue-42-already-fixed")

    def test_missing_token_raises_before_any_network_call(self):
        del __import__("os").environ["GITHUB_TOKEN"]

        with self.assertRaises(cli.BeachheadError) as ctx:
            cli.start("owner/repo#42", dir_override=str(self.dest))
        self.assertIn("GITHUB_TOKEN", str(ctx.exception))

    def test_invalid_reference_raises_before_any_network_call(self):
        with self.assertRaises(cli.BeachheadError):
            cli.start("not a valid reference", dir_override=str(self.dest))

    def test_existing_destination_that_is_not_a_git_repo_is_rejected(self):
        self.dest.mkdir()
        (self.dest / "some-file.txt").write_text("not a git repo")

        with patch("beachhead.github.authenticated_login", return_value="me"), patch(
            "beachhead.github.fork_repo"
        ), patch("beachhead.github.wait_for_fork"):
            with self.assertRaises(cli.BeachheadError):
                cli.start("owner/repo", dir_override=str(self.dest))


class MainTests(unittest.TestCase):
    """Exercises the argparse + error-to-exit-code wiring, not the flow itself."""

    def test_missing_token_exits_1_and_prints_to_stderr(self):
        with patch.dict("os.environ", {}, clear=True), patch("sys.stderr") as mock_stderr:
            exit_code = cli.main(["owner/repo#1"])

        self.assertEqual(exit_code, 1)
        self.assertTrue(mock_stderr.write.called)

    def test_bad_reference_exits_1(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": "tok"}), patch("sys.stderr"):
            exit_code = cli.main(["not-a-valid-ref-at-all-!!"])

        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
