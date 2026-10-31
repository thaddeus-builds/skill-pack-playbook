"""tools/pr_links.py: the closing lines a pull request needs, found by rule from the branch name, the commit messages and
the caller (no model); a description that already names the issue is left alone."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _t
import pr_links as p


def test_the_branch_name_names_the_issue_only_when_it_says_issue():
    assert p.mentioned("claude/issue-4-overlay", [], []) == [4]
    assert p.mentioned("fix/issue-12", [], []) == [12]
    assert p.mentioned("fix/12-caption", [], []) == []                      # a bare number is not an issue
    assert p.mentioned("claude/lessons-2026-10-23", [], []) == []           # a date
    assert p.mentioned("release-v1-15", [], []) == []                       # a version


def test_refs_mentions_an_issue_and_never_closes_it():
    assert p.mentioned("main", ["refs #238 tracking", "Ref #9"], []) == []
    assert p.missing("Refs #4", [4]) == [4]
    assert p.with_closing("Refs #4", [4]) == "Refs #4\n\nCloses #4\n"


def test_commit_messages_and_the_caller_add_issues_once():
    assert p.mentioned("main", ["Fixes #7\n", "refs #9 and closes #7"], [9, 11]) == [7, 9, 11]
    assert p.mentioned("main", ["Resolves #3"], []) == [3]


def test_a_description_without_the_line_is_missing_it_and_one_with_it_is_not():
    assert p.missing("does things", [4, 5]) == [4, 5]
    assert p.missing("done.\n\nCloses #4", [4, 5]) == [5]
    assert p.missing("see #4 is not enough", [4]) == [4]


def test_with_closing_adds_only_what_is_missing():
    assert p.with_closing("body", [4]) == "body\n\nCloses #4\n"
    assert p.with_closing("body\n\nCloses #4\n", [4]) == "body\n\nCloses #4\n"


def test_the_closing_line_reaches_the_description_wherever_it_comes_from():
    import tempfile
    assert p.body_args(["--title", "t", "--body", "text"], [4]) == ["--title", "t", "--body", "text\n\nCloses #4\n"]
    assert p.body_args(["--title", "t"], [4]) == ["--title", "t", "--body", "Closes #4\n"]      # no description at all: the line is it
    assert p.body_args(["--title", "t"], []) == ["--title", "t"]
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "body.md")
        open(f, "w").write("text\n")
        assert p.body_args(["--body-file", f], [4, 5]) == ["--body-file", f]
        assert open(f).read() == "text\n\nCloses #4\nCloses #5\n"
    for bad in (["--body=x"], ["--body-file", "-"], ["--body"]):
        try:
            p.body_args(bad, [4])
        except SystemExit:
            continue
        raise AssertionError(bad)


if __name__ == "__main__":
    _t.main(globals())
