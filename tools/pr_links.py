#!/usr/bin/env python3
"""Link a pull request to the issue it solves, mechanically (no model): GitHub closes an issue on merge only when the pull
request's description holds `Closes #N`; a description without it leaves the issue open.

An issue number is taken from three places, nothing else: the branch name when it says `issue` (`issue-4-overlay`, `fix/issue-12`; a bare
number is a date or a version, `release-2026-10-23`), a commit message of the branch that says `Closes`, `Fixes` or `Resolves` (`Refs #4` only
mentions an issue and never closes it), and `--issue N`. Only an open issue of this repository counts.

    python3 tools/pr_links.py check [--base origin/main] [--body-file F]   exit 1 and name what is missing
    python3 tools/pr_links.py create [--base main] [gh pr create args]    gh pr create, with the closing lines added
    python3 tools/pr_links.py sweep [--limit 30]                          close open issues that a merged PR names

`check` before a push (a pre-push hook calls it); `create` instead of `gh pr create`; `sweep` after merges made by a click,
when a description lacked the line (it closes the issue with a comment naming the pull request). Needs `git` and `gh`.
"""
import argparse, json, re, subprocess, sys

BRANCH = re.compile(r"(?:^|[/_-])issues?[-_/]?(\d+)(?=[-_/]|$)", re.I)
CLOSING = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", re.I)


def sh(*a):
    r = subprocess.run(a, capture_output=True, text=True)
    if r.returncode: raise SystemExit(f"{' '.join(a[:3])}: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout


def mentioned(branch, messages, extra=()):
    """Issue numbers named by the branch, the commit messages and the caller, in order, once each."""
    nums = [int(n) for n in BRANCH.findall(branch) if len(n) <= 5]
    for m in messages: nums += [int(n) for n in CLOSING.findall(m)]
    nums += [int(n) for n in extra]
    return list(dict.fromkeys(nums))


def missing(body, issues):
    """The issues no `Closes/Fixes/Resolves #N` line of `body` names (`Refs #N` does not close one)."""
    have = {int(n) for n in CLOSING.findall(body or "")}
    return [n for n in issues if n not in have]


def with_closing(body, issues):
    add = "".join(f"Closes #{n}\n" for n in missing(body, issues))
    return (body.rstrip("\n") + "\n\n" + add) if add else body


def body_args(rest, issues):
    """`gh pr create` arguments with the closing lines in the description, wherever it comes from: `--body`, `--body-file` (a file, rewritten),
    or nowhere (then the lines become the whole description). `--body=...` and `--body-file -` are refused, not guessed at."""
    rest = list(rest)
    if any(a.startswith(("--body=", "--body-file=", "-b=", "-F=")) or a == "-" for a in rest):
        raise SystemExit("pr_links create: write --body TEXT or --body-file FILE as two words (not --body=..., not -)")
    for flag, is_file in (("--body-file", True), ("-F", True), ("--body", False), ("-b", False)):
        if flag in rest:
            at = rest.index(flag) + 1
            if at >= len(rest): raise SystemExit(f"pr_links create: {flag} needs a value")
            if is_file:
                with open(rest[at], encoding="utf-8") as f: new = with_closing(f.read(), issues)
                with open(rest[at], "w", encoding="utf-8") as f: f.write(new)
            else:
                rest[at] = with_closing(rest[at], issues)
            return rest
    return rest + ["--body", with_closing("", issues).lstrip("\n")] if issues else rest


def open_issues():
    return {i["number"] for i in json.loads(sh("gh", "issue", "list", "--state", "open", "--limit", "200", "--json", "number"))}


def branch_info(base):
    br = sh("git", "rev-parse", "--abbrev-ref", "HEAD").strip()
    msgs = sh("git", "log", "--format=%B%x00", f"{base}..HEAD").split("\0")
    return br, msgs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "create"):
        p = sub.add_parser(name); p.add_argument("--base", default="origin/main"); p.add_argument("--issue", type=int, action="append", default=[])
    sub.choices["check"].add_argument("--body-file")
    sub.add_parser("sweep").add_argument("--limit", type=int, default=30)
    a, rest = ap.parse_known_args(argv)
    if a.cmd == "sweep":
        opened = open_issues()
        for pr in json.loads(sh("gh", "pr", "list", "--state", "merged", "--limit", str(a.limit), "--json", "number,body,commits")):
            texts = [pr["body"] or ""] + [c.get("messageBody", "") + " " + c.get("messageHeadline", "") for c in pr["commits"]]
            for n in dict.fromkeys(int(x) for t in texts for x in CLOSING.findall(t)):
                if n in opened:
                    sh("gh", "issue", "close", str(n), "--comment", f"Solved by pull request #{pr['number']} (merged).")
                    print(f"closed #{n} (pull request #{pr['number']})")
        return 0
    br, msgs = branch_info(a.base)
    issues = [n for n in mentioned(br, msgs, a.issue) if n in open_issues()]
    if a.cmd == "check":
        body = open(a.body_file, encoding="utf-8").read() if a.body_file else ""
        lack = missing(body, issues)
        if lack: print("the description lacks: " + ", ".join(f"Closes #{n}" for n in lack), file=sys.stderr)
        return 1 if lack else 0
    rest = body_args(rest, issues)
    sys.stdout.write(sh("gh", "pr", "create", "--base", a.base.split("/")[-1], *rest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
