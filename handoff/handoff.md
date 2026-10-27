# Handoff · 2026-10-26 playbook 评审与落地（给下一个 session）

写给接手的 session。仓库：`thaddeus-growth/skill-pack-playbook`（GitHub），子包在 `git.coco.xyz/ming.liu/`。本文件不入库，读完即可删。

## 已经在 main 上的（合并顺序：#180、#190、#191、#188、#189、#192、#194、#187）

- fleet 对 console 的 VERSION 误报修好；17 个钉散文的测试删除；RESTRUCTURE 归档到 `docs/history/`，`docs/roadmap.md` 改名 `docs/planning.md`。
- 孵化包规则：`CLAUDE.md` 一条、`tools/pack_status.tsv`、`tests/test_pack_status.py`（孵化到期日 2026-12-31，到期测试会红，届时延期、标 shared 或搬回子包）。
- kit 0.42.0：`kit/questions.py` 删除，它的规则进 `docs/lessons.md`。
- 过时设计稿归档、两个无人用的模板删除、overview 的手写状态表删除。
- `docs/lessons.md` 每条 ≤150 词并有检查；SEO 的两段叙事回到 SEO 子包（其 MR 305）。
- 发布列车约定（`docs/maintaining.md`、`kit/README.md`）：kit 版本每周最多一次，子包用 `fleet.py update` 追。
- kit 0.43.0：drift 的"落后提示"（#189）。合并时 CHANGELOG 曾带着冲突标记进了 main，#192 已修正。
- `fleet.py update`（#187）。
- 注意：#181 到 #186 在 GitHub 上显示为 closed 或"合进了上一个分支"，因为它们是串成链的；内容全部经 #190、#191 到了 main，不用再管。

## playbook 这边：没有开着的 PR

#187、#188、#189、#193、#195、#196、#197 都已合并，main 是 kit 0.44.0。接手先做两件小事：

- `gh run list --branch main --limit 3` 看 main 的 CI 是否绿（#192 那次红过，原因是 handoff.md 误入 main，已由 #194 移除）。
- `fleet.py update PATH…` 已合并但没在真实子包上完整跑过（只跑过 `status` 和 `--help`）；先挑 google-ads-skill-pack 试 `--no-tests`，worktree 建在 `<repo>_worktrees/kit-0.44.0`。

## 子包这边

- 14 个子包各有一个 Draft MR 把 kit 升到 0.41.0（分支 `claude/kit-0.41.0`，worktree 在 `<repo>_worktrees/kit-0.41.0`）。MR 标题缺故事编号（子包 CI 的 story id 作业会红），owner 补编号或放宽该规则。main 现在是 0.44.0，这些合并后可用 `fleet.py update` 再升一次。
- search-intel：推送被它自己的 leak guard 拦下，`docs/prior-art/evidence/2026-10-26/probe/*.json` 含客户词，在它未推送的 main 上。owner 决定怎么处理那些文件。
- geo-china：停在 kit 0.8.1，还是 `harness.toml` 和 `HarnessError`，要先按 CHANGELOG 0.31.0 的改名表迁移才能升。
- adcut：MR 266，一个真失败 `tests/test_batch_make.py`（console 的 gate 规则在 0.33→0.41 之间变了，adcut 的期望要跟）；另两个失败是环境缺 numpy。
- creator-program：默认分支是 `m1-roster` 不是 main，MR 2 基于它；它有一个本来就红的测试 `test_ads_docs.py`，与 kit 无关。
- GitLab 上 `seo-programmatic-skill-pack` 本地没有检出；五个旧名仓库（`geo-china-harness`、`commerce-ads-harness`、`douyin-ads-creative-harness`、`seo-tools-harness`、`social-marketing-harness`）建议归档。

## 等 owner 拍板的精简项（6b）

- `data` 包只剩 `retry`：直接并进 base 会让 8 个声明了 `data` 的子包 vendor 失败；可选：vendor 工具容忍已退役的包名并提示，或留到 2026-12-31 孵化到期再定。
- CHANGELOG 0.31.0 之前归档到 `docs/history/`（`tests/test_changelog.py` 要求版本连续，需放宽）。
- `tools/overview_page.py`、`solutions_page.py` 是否还在用。
- `docs/rules.md`（35 KB）、`docs/operating.md`（23 KB）按"规则留、故事进 lessons 一句话"精简。

## 约定（owner 已说）

- 回复用中文；owner 非技术背景，数字用表格，分清"我能直接做"和"你拍板"。
- 文档/测试类改动本地只跑相关套件，全量交给 CI；kit 字节或风险清单才本地全量。
- 提交身份用 `git -c user.name="Claude Code" -c user.email="noreply@anthropic.com"`；不要 amend+force-push（会被拦）。
- 推 git.coco.xyz 常见 SSL 抖动，重试三次；`glab mr create --draft … -y` 可用。
- 设计评审原文在临时目录 `/private/tmp/claude-501/-Users-a1-openmax-skill-pack-skill-pack-playbook--claude-worktrees-kit-ads-engines-e66e1a/d994ec77-cfab-4c70-a65c-b182cbce8499/scratchpad/设计评审-2026-10-26.md`（可能已清理；要点都在上文和 `ROADMAP.md`）。

## 换机器（这个文件夹整个拷走）

`/Users/a1/openmax/skill-pack/_handoff-2026-10-26/` 里有：本文件；`memory/`（5 个记忆文件，新机器上复制到 `~/.claude/projects/<该项目路径编码>/memory/`）；两个 git bundle（含客户词，不能推到远端）：`search-intel-main-9-commits.bundle`（search-intel 本地 main 比远端多的 9 个提交，`git pull <bundle> main`）和 `playbook-local-client-claude-owner-zh.bundle`（playbook 的 `local/client-claude-owner-zh` 一个提交）。

已经在远端、新机器 `git fetch` 就有：所有 playbook 的 PR 分支；14 个子包的 `claude/kit-0.41.0`（search-intel 是 `claude/kit-0.43.0`，MR 1）；sdr 的 `wip/roadmap-ts-to-python`（TS 改 Python 计划的 ROADMAP 编辑）；adcut 的 `review-fixes-2026-10-22`；playbook 旧的 hub-* 和 client-hub-design 分支。

只在旧机器、不用搬：geo-china 的 `claude/kit-0.41.0`（测试是红的，旧 harness 名；迁移 0.31.0 改名后用 `fleet.py update` 重新生成）。

没动：video-ads 主检出里未跟踪的 `STATUS.json`（看似生成物）；measurement 本地 main 比远端多 3 个提交（已包含在它的 `claude/kit-0.41.0` 分支里）。

## 更新 · 2026-10-27(第二个 session)

- main CI 绿,kit 0.44.0,playbook 无开着的 PR。
- 11 个 kit 0.41.0 的 Draft MR 已按 owner 同意合并(ad-copy、asset-handoff、google-ads、koc-script、measurement、meta-ads、outbound、product-feed、product-keyframe-video、sdr、video-ads)。合并时只有"故事编号/roadmap id"一项红,用 GitLab API 合的(glab 因流水线红拒绝)。
- `fleet.py update` 已在真实子包上跑通(建 worktree、vendor、提交、测试都对)。子包测试只要几秒,以后不要加 `--no-tests`。
- 9 个子包已升到 0.44.0,各自 Draft MR(分支 `claude/kit-0.44.0`):google-ads !3、ad-copy !2、asset-handoff !2、measurement !2、meta-ads !2、product-feed !4、product-keyframe-video !3、sdr !21、outbound !4、video-ads !92。(共 10 个;koc-script 还没升。)
- outbound !4 和 video-ads !92 各有一个红测试,在 main 上同样红,与 kit 无关(outbound 缺 pydantic_settings;video-ads 的 close_milestone.sh --dry-run)。
- 12 个子包已克隆到 `/Volumes/1T/openmax/skill-pack/<repo>`。
- 没动:koc-script(待升)、adcut(MR 266 冲突+真失败)、search-intel(9 个含客户词提交)、geo-china(先迁移 0.31.0)、creator-program(默认分支 m1-roster)。
- 仍待 owner:MR 标题补编号还是放宽规则;精简项(data 包、CHANGELOG 归档、两张页面工具、rules/operating 精简)。
