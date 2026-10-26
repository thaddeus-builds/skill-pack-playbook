# Handoff · 2026-10-26 playbook 评审与落地（给下一个 session）

写给接手的 session。仓库：`thaddeus-growth/skill-pack-playbook`（GitHub），子包在 `git.coco.xyz/ming.liu/`。本文件不入库，读完即可删。

## 已经在 main 上的（合并顺序：#180、#190、#191、#188）

- fleet 对 console 的 VERSION 误报修好；17 个钉散文的测试删除；RESTRUCTURE 归档到 `docs/history/`，`docs/roadmap.md` 改名 `docs/planning.md`。
- 孵化包规则：`CLAUDE.md` 一条、`tools/pack_status.tsv`、`tests/test_pack_status.py`（孵化到期日 2026-12-31，到期测试会红，届时延期、标 shared 或搬回子包）。
- kit 0.42.0：`kit/questions.py` 删除，它的规则进 `docs/lessons.md`。
- 过时设计稿归档、两个无人用的模板删除、overview 的手写状态表删除。
- `docs/lessons.md` 每条 ≤150 词并有检查；SEO 的两段叙事回到 SEO 子包（其 MR 305）。
- 发布列车约定（`docs/maintaining.md`、`kit/README.md`）：kit 版本每周最多一次，子包用 `fleet.py update` 追。
- 注意：#181 到 #186 在 GitHub 上显示为 closed 或"合进了上一个分支"，因为它们是串成链的；内容全部经 #190、#191 到了 main，不用再管。

## 还开着的两个 PR（接手先做）

- **#187 `fleet.py update`**（一键把子包升到当前 kit）：与 main 冲突在 `CHANGELOG.md`（Unreleased 两边都保留）和 `tests/test_fleet.py`（main 的 #180 改了同一个测试文件：`vendor()` 加了 `stamp` 参数、console 副本的断言）。接手：`git merge origin/main`，两处手工合并，`python3 tests/run.py` 过了就推、合。
- **#189 drift 的"落后提示"**（kit 改动）：它把 kit 定成 0.42.0，而 main 已是 0.42.0。接手：合 main 进来，`kit/VERSION` 改 0.43.0，CHANGELOG 里它的 `## [0.42.0]` 标题改成 `## [0.43.0]` 放在 main 的 0.42.0 之上，`python3 kit/tools/manifest.py kit`，跑 `python3 kit/tests/run.py manifest` 和 `python3 tests/test_changelog.py`，本地全量 `python3 run_all.py`（kit 字节改动要全量），再合。

## 两个没完成的并行会话（各在自己的 worktree 分支上）

- 接入等级表 L0–L3：worktree `.claude/worktrees/upbeat-dewdney-cf4ae4`，分支 `claude/goofy-lumiere-47ea3f`。代码、18 行的 `tools/adoption.tsv`、`tests/test_adoption.py` 写好且通过，**未提交未推送**。接手：进去提交、推送、开 PR（基于 main）。
- scaffold 生成调研目录 + 跨 pack 调研索引：worktree `.claude/worktrees/nifty-noether-4bade2`，分支 `claude/nifty-noether-4bade2`，会话状态 failed，进度未知。接手：先看 `git status` 和 `git log`，按原任务分三个 PR：`kit/guards/research.py`（kit 小版本）、scaffold 模板 `docs/research/README.md` + `docs/prior-art/README.md`、`tools/research.py` 汇总索引。

## 子包这边

- 14 个子包各有一个 Draft MR 把 kit 升到 0.41.0（分支 `claude/kit-0.41.0`，worktree 在 `<repo>_worktrees/kit-0.41.0`）。MR 标题缺故事编号（子包 CI 的 story id 作业会红），owner 补编号或放宽该规则。main 现在是 0.42.0，这些合并后可用 `fleet.py update`（#187 合并后）再升一次。
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
