import unittest

from beachhead.naming import IssueRef, ParseError, branch_name, parse_reference, slugify


class ParseReferenceTests(unittest.TestCase):
    def test_full_issue_url(self):
        ref = parse_reference("https://github.com/owner/repo/issues/123")
        self.assertEqual(ref, IssueRef("owner", "repo", 123))

    def test_full_issue_url_with_trailing_slash(self):
        ref = parse_reference("https://github.com/owner/repo/issues/123/")
        self.assertEqual(ref, IssueRef("owner", "repo", 123))

    def test_http_scheme_accepted(self):
        ref = parse_reference("http://github.com/owner/repo/issues/123")
        self.assertEqual(ref, IssueRef("owner", "repo", 123))

    def test_shorthand_with_issue_number(self):
        ref = parse_reference("owner/repo#123")
        self.assertEqual(ref, IssueRef("owner", "repo", 123))

    def test_shorthand_without_issue_number(self):
        ref = parse_reference("owner/repo")
        self.assertEqual(ref, IssueRef("owner", "repo", None))

    def test_strips_surrounding_whitespace(self):
        ref = parse_reference("  owner/repo#123  ")
        self.assertEqual(ref, IssueRef("owner", "repo", 123))

    def test_strips_trailing_dot_git_from_shorthand(self):
        ref = parse_reference("owner/repo.git")
        self.assertEqual(ref, IssueRef("owner", "repo", None))

    def test_strips_trailing_dot_git_from_url_repo(self):
        ref = parse_reference("https://github.com/owner/repo.git/issues/123")
        self.assertEqual(ref, IssueRef("owner", "repo", 123))

    def test_repo_names_with_dots_and_hyphens(self):
        ref = parse_reference("owner/my-repo.js#7")
        self.assertEqual(ref, IssueRef("owner", "my-repo.js", 7))

    def test_rejects_a_bare_url_with_no_path(self):
        with self.assertRaises(ParseError):
            parse_reference("https://github.com")

    def test_rejects_a_non_github_url(self):
        with self.assertRaises(ParseError):
            parse_reference("https://gitlab.com/owner/repo/issues/123")

    def test_rejects_a_pull_request_url(self):
        with self.assertRaises(ParseError):
            parse_reference("https://github.com/owner/repo/pull/123")

    def test_rejects_empty_string(self):
        with self.assertRaises(ParseError):
            parse_reference("")

    def test_rejects_a_lone_slash(self):
        with self.assertRaises(ParseError):
            parse_reference("/")

    def test_rejects_three_path_segments_without_issues_keyword(self):
        with self.assertRaises(ParseError):
            parse_reference("owner/repo/123")


class SlugifyTests(unittest.TestCase):
    def test_simple_title(self):
        self.assertEqual(slugify("Fix the login bug"), "fix-the-login-bug")

    def test_strips_punctuation(self):
        self.assertEqual(slugify("Bug: can't log in!"), "bug-can-t-log-in")

    def test_collapses_repeated_punctuation(self):
        self.assertEqual(slugify("weird---title!!!  here"), "weird-title-here")

    def test_caps_at_max_word_count(self):
        title = "one two three four five six seven eight"
        slug = slugify(title)
        self.assertEqual(slug, "one-two-three-four-five-six")

    def test_truncates_without_cutting_a_word_in_half(self):
        title = "a " * 30  # forces truncation mid-list
        slug = slugify(title)
        self.assertLessEqual(len(slug), 40)
        self.assertNotEqual(slug[-1], "-")

    def test_empty_title_gives_empty_slug(self):
        self.assertEqual(slugify(""), "")

    def test_all_punctuation_title_gives_empty_slug(self):
        self.assertEqual(slugify("!!! ??? ---"), "")

    def test_non_ascii_characters_are_dropped_not_kept(self):
        # Guards against silently producing a slug with characters some
        # git hosts or shells choke on in a branch name.
        slug = slugify("Fix café \u2014 caf\u00e9 login")
        self.assertEqual(slug, "fix-caf-caf-login")
        self.assertTrue(all(ord(c) < 128 for c in slug))

    def test_lowercases_the_result(self):
        self.assertEqual(slugify("ADD CI Pipeline"), "add-ci-pipeline")


class BranchNameTests(unittest.TestCase):
    def test_issue_with_title(self):
        ref = IssueRef("owner", "repo", 123)
        self.assertEqual(branch_name(ref, "Fix the login bug"), "issue-123-fix-the-login-bug")

    def test_issue_with_no_title_supplied(self):
        ref = IssueRef("owner", "repo", 123)
        self.assertEqual(branch_name(ref, None), "issue-123")

    def test_issue_with_a_title_that_slugs_to_nothing(self):
        ref = IssueRef("owner", "repo", 123)
        self.assertEqual(branch_name(ref, "!!!"), "issue-123")

    def test_no_issue_number_falls_back_to_repo_scoped_branch(self):
        ref = IssueRef("owner", "repo", None)
        self.assertEqual(branch_name(ref, "irrelevant"), "beachhead/repo")


if __name__ == "__main__":
    unittest.main()
