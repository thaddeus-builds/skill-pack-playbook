# 接手 prompt（整段复制给新机器上的新 session）

你接手 `thaddeus-growth/skill-pack-playbook`（GitHub，私有）的收尾工作。它是所有 growth-marketing skill pack 的 parent：共享 kit、脚手架、控制台、模板、conformance。子包（约 15 个）是它的同级目录，在 GitLab `git.coco.xyz/ming.liu/` 上。owner 不是技术专家，**回复一律用中文**，用大白话，数字放表格，分清"我能直接做"和"需要你拍板"。目标：解耦、边界清楚、不冗余。

## 第一步：读，不要做

1. 克隆或更新 playbook，`git fetch origin`，读 `origin/main` 上的 `CLAUDE.md`、`ROADMAP.md`、`kit/packs.tsv`、`tools/pack_status.tsv`、`tools/adoption.tsv`。
2. 读分支 `origin/handoff/2026-10-26`（**不要合进 main**）里的 `handoff/handoff.md`（现状和待办）、`handoff/design-review-2026-10-26.md`（评审原文，含业界依据）、`handoff/memory/*.md`（owner 偏好和这台机器的坑；复制到 `~/.claude/projects/<该项目路径编码>/memory/`）。
3. 旧机器上还有一个文件夹 `_handoff-2026-10-26/`，里面两个 git bundle 含客户词，不能推远端，需要 owner 手工拷过来：`search-intel-main-9-commits.bundle`（`git pull <bundle> main` 进 search-intel 本地 main）、`playbook-local-client-claude-owner-zh.bundle`。

## 已经完成（都在 main 上，kit 0.44.0）

fleet 对 console 的误报修好；17 个钉散文的测试删除；孵化包规则（`tools/pack_status.tsv` + 测试，到期 2026-12-31）；`kit/questions.py` 删除；`docs/lessons.md` 每条 ≤150 词并有检查；接入等级 L0–L3（`conformance/INVARIANTS.md`、`tools/adoption.tsv`）；`fleet.py update`；发布列车约定（kit 版本每周最多一次）；drift 的"落后提示"（0.43.0）；scaffold 生成 `docs/research/` 和 `docs/prior-art/` 索引、`tools/research.py`、`kit.guards.research`（0.44.0）。playbook 没有开着的 PR。

## 你要做的（按顺序，先问清再动手的标 ▲）

1. 看 main 的 CI：`gh run list --branch main --limit 3`，不绿先查原因。
2. 在一个小子包（google-ads-skill-pack）上真实试一次 `python3 tools/fleet.py update <路径> --no-tests`，确认它建 worktree、vendor、提交都对；`fleet.py update` 只跑过单元测试，没在真实子包上跑过。
3. 14 个子包各有 Draft MR（分支 `claude/kit-0.41.0`，search-intel 是 `claude/kit-0.43.0` MR 1）。它们落后 main 的 kit；用 `fleet.py update` 逐个升到当前版本（每个子包一个 MR，不要批量改）。MR 标题缺故事编号，子包 CI 的 story id 作业会红：▲ 问 owner 补编号还是放宽规则。
4. 例外子包：▲ search-intel 本地 main 有 9 个含客户词的提交被它自己的 leak guard 挡着，让 owner 决定；geo-china 停在 kit 0.8.1，要先按 CHANGELOG 0.31.0 的改名表迁移（`harness.toml`、`HarnessError`）才能升；adcut MR 266 有一个真失败 `tests/test_batch_make.py`（console 的 gate 规则变了）；creator-program 的默认分支是 `m1-roster`。
5. ▲ 精简项（owner 还没拍板）：`data` 包只剩 `retry` 一个模块（8 个子包声明了它，直接并进 base 会让它们 vendor 失败）；CHANGELOG 0.31.0 之前归档；`tools/overview_page.py`、`solutions_page.py` 是否还在用；`docs/rules.md`（35 KB）、`docs/operating.md`（23 KB）按"规则留、故事进 lessons 一句话"精简。
6. 后续大事（owner 批准过顺序）：Copier 试验（模板升级）；GitLab 上 `seo-programmatic-skill-pack` 本地没检出；五个旧名仓库（`*-harness`）建议归档；owner 说 playbook 构建完后会彻底清理旧仓库（重置或改私有），**不要自己动**。

## 约束（违反过，别再犯）

- 一个 PR 一个关注点；每条规则必须有一个会失败的测试，没有就别写进 CLAUDE.md；kit 字节改动要 `kit/VERSION` 加一、`python3 kit/tools/manifest.py kit`、CHANGELOG 标题。
- 不要在 playbook 里 `git add -A`：我曾因此把 handoff.md 带进 main，console 的泄漏扫描让 main 的 CI 红了（#194 已修）。只 add 具体文件。
- 提交身份没配置：`git -c user.name="Claude Code" -c user.email="noreply@anthropic.com" commit`，不要写进 config；不要 amend 加 force-push（会被拦），用追加提交。
- 本机 CPU 紧：文档/测试类改动只跑相关套件（`python3 tests/run.py`），全量交给 GitHub CI；只有 kit 字节改动或风险清单才本地 `python3 run_all.py`。
- 推 `git.coco.xyz` 常见 SSL 抖动，重试三次；`glab mr create --draft … -y` 可用；ssh 被拒，用 https。
- CHANGELOG 的 Unreleased 冲突几乎总是"两边都加了行"：两边都留；`handoff/tools/resolve_changelog.py` 就是干这个的。
- 串联的 PR 合并时别 `--delete-branch` 下面那个的基分支，否则 GitHub 会把上层 PR 关掉。
- 先读 memory 里的约定，再动手；owner 的回答里有"同意"才算批准，没问过的不要当成批准。

## 收尾

每一轮结束给 owner 一段中文简报：做了什么、没做什么、需要他拍板的是什么；剩余事项更新到 `handoff/handoff.md`（在分支上，不合进 main）。
