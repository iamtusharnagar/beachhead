import unittest
from unittest.mock import patch

from beachhead import github


class GetRepoTests(unittest.TestCase):
    @patch("beachhead.github._request")
    def test_existing_repo_returns_payload(self, mock_request):
        mock_request.return_value = (200, {"full_name": "owner/repo"})

        result = github.get_repo("owner", "repo", "tok")

        self.assertEqual(result, {"full_name": "owner/repo"})
        mock_request.assert_called_once_with("GET", "/repos/owner/repo", "tok")

    @patch("beachhead.github._request")
    def test_missing_repo_returns_none_not_an_exception(self, mock_request):
        mock_request.return_value = (404, {"message": "Not Found"})

        self.assertIsNone(github.get_repo("owner", "repo", "tok"))

    @patch("beachhead.github._request")
    def test_other_error_status_raises(self, mock_request):
        mock_request.return_value = (403, {"message": "rate limited"})

        with self.assertRaises(github.GitHubError) as ctx:
            github.get_repo("owner", "repo", "tok")
        self.assertEqual(ctx.exception.status, 403)
        self.assertIn("rate limited", str(ctx.exception))


class GetIssueTests(unittest.TestCase):
    @patch("beachhead.github._request")
    def test_parses_the_fields_beachhead_uses(self, mock_request):
        mock_request.return_value = (
            200,
            {
                "number": 42,
                "title": "Fix the thing",
                "state": "open",
                "html_url": "https://github.com/owner/repo/issues/42",
                "body": "irrelevant extra field GitHub also sends",
            },
        )

        issue = github.get_issue("owner", "repo", 42, "tok")

        self.assertEqual(issue.number, 42)
        self.assertEqual(issue.title, "Fix the thing")
        self.assertEqual(issue.state, "open")
        self.assertEqual(issue.html_url, "https://github.com/owner/repo/issues/42")

    @patch("beachhead.github._request")
    def test_missing_issue_raises(self, mock_request):
        mock_request.return_value = (404, {"message": "Not Found"})

        with self.assertRaises(github.GitHubError):
            github.get_issue("owner", "repo", 999, "tok")


class ForkRepoTests(unittest.TestCase):
    @patch("beachhead.github._request")
    def test_202_is_success(self, mock_request):
        mock_request.return_value = (202, {"full_name": "me/repo"})

        result = github.fork_repo("owner", "repo", "tok")

        self.assertEqual(result["full_name"], "me/repo")
        mock_request.assert_called_once_with("POST", "/repos/owner/repo/forks", "tok")

    @patch("beachhead.github._request")
    def test_200_is_also_success(self, mock_request):
        # GitHub returns 200 when forking a repo you have already forked.
        mock_request.return_value = (200, {"full_name": "me/repo"})

        result = github.fork_repo("owner", "repo", "tok")

        self.assertEqual(result["full_name"], "me/repo")

    @patch("beachhead.github._request")
    def test_error_status_raises(self, mock_request):
        mock_request.return_value = (404, {"message": "Not Found"})

        with self.assertRaises(github.GitHubError):
            github.fork_repo("owner", "repo", "tok")


class WaitForForkTests(unittest.TestCase):
    @patch("beachhead.github.get_repo")
    def test_returns_immediately_when_already_available(self, mock_get_repo):
        mock_get_repo.return_value = {"full_name": "me/repo"}
        sleeps = []

        result = github.wait_for_fork("me", "repo", "tok", sleep=sleeps.append)

        self.assertEqual(result, {"full_name": "me/repo"})
        self.assertEqual(mock_get_repo.call_count, 1)
        self.assertEqual(sleeps, [])

    @patch("beachhead.github.get_repo")
    def test_retries_until_available(self, mock_get_repo):
        mock_get_repo.side_effect = [None, None, {"full_name": "me/repo"}]
        sleeps = []

        result = github.wait_for_fork("me", "repo", "tok", attempts=5, sleep=sleeps.append)

        self.assertEqual(result, {"full_name": "me/repo"})
        self.assertEqual(mock_get_repo.call_count, 3)
        # Slept between attempt 1->2 and 2->3, not after the successful 3rd.
        self.assertEqual(len(sleeps), 2)

    @patch("beachhead.github.get_repo")
    def test_gives_up_after_the_attempt_budget(self, mock_get_repo):
        mock_get_repo.return_value = None
        sleeps = []

        with self.assertRaises(github.ForkNotReadyError):
            github.wait_for_fork("me", "repo", "tok", attempts=3, sleep=sleeps.append)

        self.assertEqual(mock_get_repo.call_count, 3)
        # Slept between each attempt but not after the last failed one.
        self.assertEqual(len(sleeps), 2)

    @patch("beachhead.github.get_repo")
    def test_a_get_repo_error_propagates_instead_of_being_swallowed(self, mock_get_repo):
        mock_get_repo.side_effect = github.GitHubError(403, "rate limited")

        with self.assertRaises(github.GitHubError):
            github.wait_for_fork("me", "repo", "tok", attempts=3, sleep=lambda _: None)


class AuthenticatedLoginTests(unittest.TestCase):
    @patch("beachhead.github._request")
    def test_returns_the_login(self, mock_request):
        mock_request.return_value = (200, {"login": "tusharnagar2002"})

        self.assertEqual(github.authenticated_login("tok"), "tusharnagar2002")

    @patch("beachhead.github._request")
    def test_bad_token_raises(self, mock_request):
        mock_request.return_value = (401, {"message": "Bad credentials"})

        with self.assertRaises(github.GitHubError):
            github.authenticated_login("bad-tok")


if __name__ == "__main__":
    unittest.main()
