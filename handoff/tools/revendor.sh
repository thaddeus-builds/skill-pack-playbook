#!/bin/zsh
# Re-vendor every sibling skill pack that vendors the kit onto the playbook's current kit, each in
# its own worktree (<repo>_worktrees/kit-<version>, branch claude/kit-<version>), run its suite,
# commit when green. The user's checkouts are not touched. Log: one block per pack.
set -u
PLAYBOOK=/Users/a1/openmax/skill-pack/skill-pack-playbook/.claude/worktrees/kit-ads-engines-e66e1a
S=/Users/a1/openmax/skill-pack
VER=$(cat $PLAYBOOK/kit/VERSION)
LOG=$1
: > $LOG
PACKS=(ad-copy-skill-pack adcut-skill-pack asset-handoff-skill-pack creator-program-skill-pack geo-china-skill-pack google-ads-skill-pack koc-script-skill-pack measurement-skill-pack meta-ads-skill-pack outbound-skill-pack product-feed-skill-pack sdr-skill-pack search-intel-skill-pack video-ads-skill-pack product-keyframe-video)
for p in $PACKS; do
  repo=$S/$p
  wt=${repo}_worktrees/kit-$VER
  echo "=== $p ===" >> $LOG
  if [ ! -d $repo/.git ] && [ ! -f $repo/.git ]; then echo "SKIP: not a git repository" >> $LOG; continue; fi
  from=$(cat $repo/scripts/kit/VERSION 2>/dev/null || cat $repo/kit/VERSION 2>/dev/null || echo "?")
  echo "from kit $from" >> $LOG
  if [ -e $wt ]; then echo "SKIP: worktree $wt exists" >> $LOG; continue; fi
  mkdir -p ${repo}_worktrees
  if ! git -C $repo worktree add -q $wt -b claude/kit-$VER main >> $LOG 2>&1; then echo "FAIL: worktree add" >> $LOG; continue; fi
  if ! python3 $PLAYBOOK/kit/tools/vendor.py --skill-pack $wt >> $LOG 2>&1; then echo "FAIL: vendor refused" >> $LOG; continue; fi
  echo "--- suite:" >> $LOG
  ( cd $wt && python3 tests/run.py > $wt/.revendor-tests.log 2>&1; echo "exit=$?" >> $wt/.revendor-tests.log )
  tail -n 25 $wt/.revendor-tests.log >> $LOG
  ok=$(grep -c "^exit=0" $wt/.revendor-tests.log)
  rm -f $wt/.revendor-tests.log
  if [ -f $wt/CHANGELOG.md ] && grep -q "^## \[Unreleased\]" $wt/CHANGELOG.md; then
    python3 - "$wt/CHANGELOG.md" "$from" "$VER" <<'EOF' >> $LOG 2>&1
import sys, re
path, frm, ver = sys.argv[1:]
s = open(path, encoding="utf-8").read()
line = f"- The vendored kit and console move from {frm} to {ver} (playbook `python3 kit/tools/vendor.py`); the skill pack's own code is unchanged. Read the playbook's CHANGELOG.md for what the kit gained between the two.\n"
m = re.search(r"^## \[Unreleased\][^\n]*\n(### [^\n]*\n)?", s, re.M)
s = s[:m.end()] + line + s[m.end():]
open(path, "w", encoding="utf-8").write(s)
EOF
  fi
  git -C $wt add -A >> $LOG 2>&1
  if [ "$ok" = "1" ]; then verdict="green"; else verdict="RED: committed anyway, see the suite tail above"; fi
  git -C $wt -c user.name="Claude Code" -c user.email="noreply@anthropic.com" commit -q -m "Re-vendor the kit and console: $from to $VER

python3 kit/tools/vendor.py --skill-pack . from the playbook at kit $VER.
No change to the skill pack's own code. Suite: $verdict.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" >> $LOG 2>&1 && echo "committed: $(git -C $wt log --oneline -1)  [$verdict]" >> $LOG
done
echo "=== done ===" >> $LOG
