"""tools/pr_links.py: the closing lines a pull request needs, found by rule from the branch name, the commit messages and
the caller (no model); a description that already names the issue is left alone."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _t
import pr_links as p


def test_the_branch_name_names_the_issue():
    assert p.mentioned("claude/issue-4-overlay", [], []) == [4]
    assert p.mentioned("fix/12-caption", [], []) == [12]


def test_commit_messages_and_the_caller_add_issues_once():
    assert p.mentioned("main", ["Fixes #7\n", "refs #9 and closes #7"], [9, 11]) == [7, 9, 11]


def test_a_description_without_the_line_is_missing_it_and_one_with_it_is_not():
    assert p.missing("does things", [4, 5]) == [4, 5]
    assert p.missing("done.\n\nCloses #4", [4, 5]) == [5]
    assert p.missing("see #4 is not enough", [4]) == [4]
    assert p.missing("Refs #4", [4]) == []


def test_with_closing_adds_only_what_is_missing():
    assert p.with_closing("body", [4]) == "body\n\nCloses #4\n"
    assert p.with_closing("body\n\nCloses #4\n", [4]) == "body\n\nCloses #4\n"


if __name__ == "__main__":
    _t.main(globals())
