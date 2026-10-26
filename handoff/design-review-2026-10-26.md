# Playbook 设计评审（2026-10-26）

写给 owner 的评审：这个 parent 仓库该长成什么样，业界前人怎么做，哪些该精简。数据来自今天对 playbook 和 15 个子包的实查。

## 一句话结论

方向是对的，而且和业界成熟做法高度吻合；问题在于它长得比它保护的东西快。接下来三个月的重点不是加能力，而是：**一个版本、一个节奏、一张接入表、一套调研约定，然后删掉没人用的。**

---

## 1. 它在业界叫什么

你做的不是一个"库"，而是一个**内部平台**：脚手架 + 共享库 + 规则检查 + 控制台和宿主适配。业界的名字：

| 你的做法 | 业界对应 | 出处 |
| --- | --- | --- |
| scaffold 生成一个当天就绿的子包 | Golden Path（金色路径）/ Paved Road（铺好的路） | Spotify 2020；Netflix 2017 |
| "两个子包用到才进 kit" | Rule of Three；Harvested Framework（收割来的框架） | Don Roberts / Martin Fowler《重构》；Fowler bliki 2003 |
| 每条规则一个会失败的测试 | Architecture fitness function（架构适应度函数） | Ford/Parsons/Kua《Building Evolutionary Architectures》 |
| vendor 复制 + sha256 清单 + 漂移测试 | Go 的 vendor/modules.txt 一致性检查；Cargo vendor 的"副本只读" | Go 1.14；cargo vendor |
| 黑盒 conformance 检查半路接入的子包 | 成熟度记分卡（Soundcheck / Cortex scorecards）；cruft link | Spotify Backstage；Cortex |
| ROADMAP 的 R 行、docs/lessons.md | 轻量 ADR（架构决策记录） | Michael Nygard 2011；ThoughtWorks 雷达 Adopt |

这说明你不是在发明，而是在重新发现。好处是：每个张力都有前人踩过的坑可以直接抄答案。

---

## 2. 做对的，别动

1. **宿主零安装、release 就是 `git archive`**。这决定了必须 vendor，不能 pip。坚持。
2. **owner 只签五个门**，决策权写进仓库而不是写进 prompt。
3. **规则必须带测试**。这就是 fitness function，少而硬是对的。
4. **副本从不就地修改**，修在上游。Cargo 对 vendored crate 的要求一模一样。
5. **黑盒 conformance** 让 amazon-ppc 这种老项目不必重写也能被约束。这正是 brownfield 接入的正确起点。

---

## 3. 三个张力，和业界给的答案

### 张力一：共享代码先于第二个使用者

**现状**：`ads-core`（9 个模块）、`creative`（4 个）没有任何子包 import；`generation`、`learning`、`pages`、`autonomy` 只有 adcut 一家。规则说"两个才进"，实践是"先提出来等人用"。

**业界怎么说**：Fowler 的 Harvested Framework 明确反对先造平台再找用户："先做一个应用，再做第二个，重复的部分才抽出来"。Sandi Metz：重复比错误的抽象便宜。反方 Team Topologies 允许平台先行，但要求"最薄可行平台"（thinnest viable platform），并且要有点名的使用者。

**判断**：你的做法介于两者之间，代码是从 video-ads / amazon-ppc 收割来的（不是凭空造），只是第二个使用者还没接。这可以接受，但要有期限。今天已经落地为"孵化包"规则：`tools/pack_status.tsv` 写明每个包是 shared 还是 incubating、到期日；测试在到期次日失败。毕业条件是两个子包的 main 分支 import。

### 张力二：vendor 分发 vs 子包漂移

**现状**：

| 指标 | 数字 |
| --- | --- |
| kit 版本号变化（4 周内） | 52 次 |
| 子包所在的 kit 版本数 | 6 个 |
| 在最新版（0.41.0）的子包 | 0 个 |
| 最旧的子包（geo-china） | 0.8.1，落后 33 个小版本 |

**业界怎么说**：Google 的"一个版本规则"（整个公司每个依赖只允许一个版本）存在的理由就是防止今天这种局面，但 Google 靠的是自动化大规模迁移工具。Abseil 的"live at head"承诺"你跟着最新版，我们不弄坏你"，代价是每次改接口都附带迁移工具。Spotify 的 Fleet Management 用机器人向几千个仓库自动开 PR，内部框架升级从约 200 天缩到 7 天以内。做不到自动化的项目则用"发布列车"：Eclipse 每季度一班，Firefox 曾经六周一班，消费者只需追到固定站点。

**判断**：根因不是 vendoring，是**没有节奏又没有自动化**。建议三件事：

1. **发布列车**：kit 改为每周（或每两周）一次版本号，合并到 main 不等于发布，Unreleased 累积。子包只追列车站点。
2. **一键升级**：`tools/fleet.py update PATH…`，在子包里开分支、re-vendor、跑它的测试、写 CHANGELOG 行。今天我手工做的 15 次就是这个命令该做的事。
3. **落后可见**：子包的 drift 测试旁加一个非阻塞提示，落后超过两个小版本就打印出来。这是 cruft check 的做法。

模板文件（CLAUDE.md、CI 文件）的更新是另一个问题，vendor 工具不管它们。Copier 的 `copier update` 用"上次模板版本"做三方合并，RESTRUCTURE 阶段 6 的 Copier 试验值得做，但排在列车和一键升级之后。

### 张力三：规则和文档的重量

**现状**：文档约 640 KB；51 个文档测试里 17 个在钉死段落措辞；两套结构相近的模板测试；`RESTRUCTURE.md` 和 `ROADMAP.md`/`docs/roadmap.md` 撞名。

**业界怎么说**：fitness function 的每一条要对应一个命名的架构特性（结构、边界、安全），不是措辞。Python doctest 和 Rust doc test 之所以成立，是因为它们执行示例、不比对散文。Nygard 对 ADR 的要求是"一到两页，永不删除只标 superseded"，因为"大文档从来不会被维护"。

**判断**：今天已删掉 17 个钉散文的测试，归档了 RESTRUCTURE，改名了 planning。接下来是第 6 节的精简清单。

---

## 4. 两种接入路径：从零起步 vs 半路接入

**现状**：从零起步走 scaffold；半路接入只有 amazon-ppc 走了 conformance 黑盒；中间态没有定义（ecommerce-seo 只有 adapter，geo-china 停在 0.8.1 且还是旧的 harness.toml）。

**业界怎么说**：Spotify Golden Path 不强制，但离开它就少支持；Soundcheck 和 Cortex 用"累积等级"（铜、银、金）而不是一个通过/不通过。cruft 有 `link` 命令专门把已存在的项目挂到模板上。

**建议**：定义四个累积等级，每个子包一行记录当前级和目标级（可以就放进 `tools/pack_status.tsv` 的姐妹表）：

| 级 | 含义 | 今天在这一级的 |
| --- | --- | --- |
| L0 守不变量 | 通过 conformance 黑盒检查，代码全是自己的 | amazon-ppc |
| L1 接 base | vendor base + testkit，CLI 走 kit.cli | geo-china（旧版） |
| L2 按需接包 | 声明并 vendor 自己要的包，删掉自己的副本（golden diff 为 0） | 大多数新子包 |
| L3 全结构 | scaffold 的目录、ssot、console、宿主适配全部齐 | meta-ads、google-ads 等 |

好处：半路接入的项目有明确的下一步，而不是"要么全接要么不接"。

---

## 5. 调研该不该有统一模式

**现状（实查 15 个子包）**：

| 存放方式 | 子包 |
| --- | --- |
| `docs/prior-art/` 日期文件 + 索引 | geo-china、google-ads、koc-script、measurement、search-intel |
| `docs/research/` 问题索引（有测试） | video-ads |
| `docs/adr/` 决策记录（27 条） | sdr |
| 单文件（prior-art.md、open-source-survey.md、resources.md） | adcut、ad-copy、product-keyframe-video |
| 没有 | 其余 |

三种不同的东西混在一起：**扫描**（这个领域有什么）、**问题**（某个具体问题查到了什么）、**决定**（我们选了什么）。playbook 里已经有前两者的模板（prior-art-scan.md、design-first.md）和"research is kept"的规则，但 scaffold 没有把它们生成到子包里，所以各做各的。同一个 vendor 被重复调研：DataForSEO 在 ecommerce-seo 和 search-intel 各查一次，Meta API 在 video-ads、meta-ads、adcut 各查一次。

**业界怎么说**：Rust 的 RFC 模板有固定的"Prior art"一节；Google 设计文档必须有"考虑过的替代方案"；ADR 要求放在代码旁、短、不删只标替代；Backstage TechDocs 把每个仓库的 docs 汇总到一个门户。共识是：**复用的单位是决定，不是检索过程。**

**建议**：

1. **三个固定位置，scaffold 生成**：`docs/prior-art/`（扫描）、`docs/research/`（问题，带索引和测试，video-ads 的 `test_research_index` 上收到 kit.guards）、ROADMAP 的 R 行（决定，已有 guard）。sdr 的 ADR 可保留，R 行指向它。
2. **跨子包只共享索引**：playbook 加一张 `docs/research-index.tsv`（子包、问题、日期、一句话结论、文件路径），由 `tools/research.py` 从各子包的索引汇总生成，不复制内容。新子包 B0.5 第一步是读它。
3. **每条调研记录三个固定字段**：问题、一句话答案、没查到什么。这是 video-ads 已经在用的格式，推广即可。

---

## 6. 精简清单

原则：**没人用的删，用一次的回到子包，重复的只留一份，历史的归档。** 分三档。

### 6a. 我可以直接做（低风险，有证据）

| 项 | 证据 | 动作 |
| --- | --- | --- |
| `kit/questions.py`（256 行） | 无任何子包 import；ROADMAP P1 已停放 | 删除（规则："两个小版本无人用则删"） |
| `data` 包只剩 `retry` 一个模块 | 8 个子包声明它，只有 video-ads import | 并入 `base`，或删包留模块；需要 kit 小版本 |
| `docs/workbook-and-browser-ops.md`（17 KB） | 标题写"设计稿，未建"，但 workbook 包早已建成 | workbook 部分归档到 docs/history，browser-ops 部分留一段 |
| `docs/overview.md` 第二部分 | 与 README 的"What the kit guarantees"重复 | 第二部分只留表格，叙述指向 README |
| `templates/verify-challenge.md`、`owner-review-loop.md`、`outcome-learning.md`、`doctor-checks.md` | 15 个子包里没有任何引用 | 删除或并入 BUILD.md 一段 |

### 6b. 需要你拍板

| 项 | 证据 | 建议 |
| --- | --- | --- |
| `docs/lessons.md`（45 KB） | 最大两节是 SEO 客户叙事（8 KB、5.5 KB），属于那个子包 | 每条 lesson 限 150 字：规则一句、出处一句、链接；长篇回到子包自己的 docs |
| `docs/rules.md`（35 KB）、`docs/operating.md`（23 KB） | 规则和"paid for"故事混写 | 规则留在 rules.md，故事进 lessons.md 一句话版 |
| `CHANGELOG.md`（94 KB） | 子包升级时要读它，0.31 之前是改名前的世界 | 0.31 之前归档到 docs/history，测试相应放宽 |
| `templates/third-party-consent.md`、`owner-queue-item.md`、`client-handoff.md` | 子包无引用，但可能被客户目录（仓库外）使用 | 你确认是否在用 |
| `tools/overview_page.py`、`solutions_page.py` | 给 owner 看的两张页面 | 你确认是否还打开它们 |

### 6c. 不建议动

- `templates/tests/`（独立测试包）：amazon-ppc 在用，它不 vendor kit。
- `kit/guards/evals.py`：ad-copy、asset-handoff 的 never-table 测试在用。
- `hosts/zylos/`、`conformance/`、`build/`：各有明确使用者。

---

## 7. 建议的顺序

1. 本周：合并今天的四个 PR；把 15 个子包的 re-vendor 分支推上去各开一个 MR。
2. 下周：发布列车 + `fleet.py update`；接入等级表。
3. 之后：6a 精简；scaffold 生成调研目录；6b 逐项定。
4. 再之后：Copier 试验（模板升级）。

---

## 附：业界出处

- Fowler, Harvested Framework: https://martinfowler.com/bliki/HarvestedFramework.html
- Metz, The Wrong Abstraction: https://sandimetz.com/blog/2016/1/20/the-wrong-abstraction
- Team Topologies, Thinnest Viable Platform: https://teamtopologies.com/key-concepts-content/what-is-a-thinnest-viable-platform-tvp
- Bottcher (Thoughtworks), What I talk about when I talk about platforms: https://martinfowler.com/articles/talk-about-platforms.html
- Google One Version Rule: https://opensource.google/docs/thirdparty/oneversion/
- Abseil compatibility / live at head: https://abseil.io/about/compatibility
- Spotify Golden Paths: https://engineering.atspotify.com/2020/8/how-we-use-golden-paths-to-solve-fragmentation-in-our-software-ecosystem
- Spotify Fleet Management: https://engineering.atspotify.com/2023/4/spotifys-shift-to-a-fleet-first-mindset-part-1
- Backstage Soundcheck: https://backstage.spotify.com/docs/plugins/soundcheck/core-concepts
- Cortex scorecards: https://docs.cortex.io/scorecards/create
- Copier update: https://copier.readthedocs.io/en/stable/updating/
- cruft: https://github.com/cruft/cruft/
- Eclipse Simultaneous Release: https://wiki.eclipse.org/SimRel/ChangingProcessAndTiming
- Building Evolutionary Architectures: https://oreilly.com/library/view/building-evolutionary-architectures/9781492097532
- ArchUnit motivation: https://www.archunit.org/motivation
- Nygard, ADRs: https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions
- Ubl, Design Docs at Google: https://www.industrialempathy.com/posts/design-docs-at-google/
- Rust RFC prior art: https://rust-lang.github.io/rfcs/2333-prior-art.html
- Keep a Changelog: https://keepachangelog.com/en/1.0.0/
- Schlawack, SemVer Will Not Save You: https://hynek.me/articles/semver-will-not-save-you/
