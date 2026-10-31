"""tools/roster.py: the GitHub topics against tools/adoption.tsv, said in three lines (new, untagged, gitlab);
it reads and never writes."""
import json, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _t
import roster as r

TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools", "roster.py")


def repo(name, *topics, archived=False):
    return {"name": name, "repositoryTopics": [{"name": t} for t in topics] or None, "isArchived": archived}


def test_a_tagged_repository_without_a_row_is_new():
    got = r.compare([repo("a-skill-pack", "skill-pack"), repo("b-skill-pack", "skill-pack")], ["a-skill-pack"])
    assert got == {"new": ["b-skill-pack"], "untagged": [], "gitlab": []}


def test_a_library_topic_counts_and_an_unrelated_topic_does_not():
    got = r.compare([repo("lib", "skill-pack-library"), repo("site", "website")], [])
    assert got["new"] == ["lib"]


def test_a_row_on_github_without_the_topic_is_untagged_and_a_row_not_on_github_is_gitlab():
    got = r.compare([repo("a-skill-pack")], ["a-skill-pack", "old-skill-pack"])
    assert got == {"new": [], "untagged": ["a-skill-pack"], "gitlab": ["old-skill-pack"]}


def test_an_archived_repository_is_not_new_and_a_repository_without_topics_is_read():
    assert r.compare([repo("gone", "skill-pack", archived=True)], [])["new"] == []
    assert r.topics_of({"name": "x", "repositoryTopics": None}) == set()


def test_gitlab_alone_does_not_fail_and_new_or_untagged_does():
    assert not r.failed({"new": [], "untagged": [], "gitlab": ["x"]})
    assert r.failed({"new": ["x"], "untagged": [], "gitlab": []})
    assert r.failed({"new": [], "untagged": ["x"], "gitlab": []})


def test_the_table_names_come_from_the_pack_column():
    assert r.table_names("pack\tlevel\nsdr-skill-pack\tL1\nfilmkit\tL0\n") == ["sdr-skill-pack", "filmkit"]


def test_the_real_table_is_read_and_a_run_from_a_file_exits_by_the_result():
    names = r.table_names(open(r.TABLE, encoding="utf-8").read())
    assert "sdr-skill-pack" in names and len(names) == len(set(names)) > 10
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "repos.json")
        json.dump([repo(n, "skill-pack") for n in names], open(f, "w"))
        ok = subprocess.run([sys.executable, TOOL, "--from-json", f], capture_output=True, text=True)
        assert ok.returncode == 0 and "agree" in ok.stdout, ok.stdout + ok.stderr
        json.dump([repo(n, "skill-pack") for n in names] + [repo("fresh-skill-pack", "skill-pack")], open(f, "w"))
        bad = subprocess.run([sys.executable, TOOL, "--from-json", f, "--json"], capture_output=True, text=True)
        assert bad.returncode == 1 and json.loads(bad.stdout)["new"] == ["fresh-skill-pack"], bad.stdout


if __name__ == "__main__":
    _t.main(globals())
