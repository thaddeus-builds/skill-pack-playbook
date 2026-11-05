# SSOT 瘦身与开发/运行分开，2026-11-05

owner 在 2026-11-05 问了两件事：一是当初为避免误解和幻觉而先设计的 SSOT 现在还要不要、playbook 要不要改小；二是"我们这里只是开发环境 并非 runtime 生产环境"，并且"为了避免开发环境和生产环境 ... 我希望所有 skill pack 都遵守"。这一页先量，再提两项改动，每个 skill pack 都照做。末尾共五个问题等 owner 回答。回答之前什么都不改：不删文件，不加守卫，不动任何一个包。

怎么量的：本机能拉到的 12 个 GitHub 仓库（`tools/adoption.tsv` 里的包，加上不在表里的 `cloud-drive`），各自的 `origin/main` 完整检出到临时目录，只读。`cloud-drive` 没有 `ssot/`，不计。行数 = 去掉表头、空行和 `#` 注释行之后的行数。"最后改动"是 `git log -1` 的日期。"代码里出现"是指一行的键（第一列）作为字符串出现在包自己的代码里，`ssot/`、`tests/`、`docs/` 和 vendor 目录（`scripts/kit/`、`kit/`、`console/`、`zylos/`）不算。"提到 S 编号的提交"统计的是 2026-10-06 以来提交说明里出现的 `S..` 编号。GitLab 上的包这次没量（同 `docs/design/consolidation-2026-11.md`）。

## owner 的回答（R44，2026-11-05）

已同意："五条都按推荐"。五个问题都按推荐执行，工作记在 `ROADMAP.md` 的 X46：先做 playbook 这一侧（A4 和 B3 的第 0 步），kit 发布之后各包再迁移。

## 一句话结论

- **机器那一半天天在用**：`constants.tsv`、消息码、`fact_keys.tsv`、`decision_keys.tsv` 和各包自己的登记表，几乎每一行都在代码里出现。正是它们让一个值只写在一处。原样保留。
- **给 owner 的那一半，大多数包从没填过**：10 个有 owner 文件的包里，6 个全是 0 行，从建包那天起就没动过；video-recipes 只有 3 条规则，sdr 只有 12 条故事。owner 的决定其实都记在路线图的 `R` 行里，比如 meta-ads 有 60 条，每条都带日期和 owner 的原话。
- **开发和运行现在是混在一起的**：本机上 44 个客户包装脚本全部指向开发检出，没有一个指向打过标签的发布版。11 个 skill pack 里 6 个从没打过发布标签。meta-ads 的早间例程只是一个 `tools/` 脚本，2026-11-05 还在本机建过一个每日定时任务来跑它（当天就删掉了）。

## A. SSOT 瘦身

### A1. 量到的

owner 文件 = `glossary.tsv` / `user-stories.tsv` / `policies.tsv` / `story_checks.tsv`；agent 提议 = 它们的 `.agent.tsv`。

| 包 | owner 文件行数（词/故事/规则/检查） | agent 提议行数（词/故事/规则） | owner 文件最后改动 | 路线图 `R` 行 | 提到 S 编号的提交（不同编号数） |
| --- | --- | --- | --- | --- | --- |
| meta-ads | 0 / 0 / 0 / 0 | 25 / 24 / 1 | 2026-10-26（建包当天） | 60（编号到 R86） | 218（16） |
| sdr | 0 / 12 / 0 / 0 | 29 / 23 / 5 | 2026-10-28 | 66 | 259（9） |
| product-image-to-video | 0 / 0 / 0 / 0 | 9 / 11 / 10 | 2026-10-23（建包当天） | 23 | 20（10） |
| google-ads | 0 / 0 / 0 / 0 | 0 / 1 / 0 | 2026-10-22（建包当天） | 23 | 2（1） |
| ad-copy | 0 / 0 / 0 / 0 | 0 / 1 / 0 | 2026-10-22（建包当天） | 8 | 2（1） |
| proofcut | 0 / 0 / 0 / 0 | 0 / 1 / 0 | 2026-10-30（建包当天） | 6 | 2（1） |
| asset-handoff | 0 / 0 / 0 / 0 | 0 / 1 / 0 | 2026-10-22（建包当天） | 5 | 2（1） |
| video-recipes | 0 / 0 / 3 / 0 | 0 / 2 / 3 | 2026-11-04 | 3 | 1（1） |
| seo | 26 / 301 / 16 / 无 | 无 / 456 / 16 | 2026-11-05 | 0（它的决定写在 owner 文件的 `decided` 列和路线图的 Open decisions） | 906（275） |
| amazon-ppc | 79 / 49 / 22 / 42 | 79 / 64 / 22 | 2026-10-31 | 没有 `docs/ROADMAP.md` | 254（37） |
| adcut | 没有这些文件（更早的布局） | 无 | 无 | 18（根目录 `ROADMAP.md`） | 1（3） |

`ssot/stages.agent.tsv`（建包步骤表）：8 个包里各 13 行，除了 google-ads 在 2026-10-26 动过一次，其余都停在建包那天。playbook 自己的 `ROADMAP.md` 也用同样的方式记了 42 条 `R` 行。

机器登记表（"代码里出现" / 总行数）：

| 包 | `constants.tsv` | 消息码（`message_codes.tsv` 加 `message_codes.d/`） | 包自己的登记表 |
| --- | --- | --- | --- |
| adcut | 227 / 237 | 1,003 / 1,003 | 49 个，3,982 行 |
| seo | 145 / 145 | 487 / 487 | 34 个，1,178 行 |
| meta-ads | 134 / 135 | 284 / 284 | 6 个，235 行 |
| amazon-ppc | 86 / 91 | 417 / 689（含 kit 的 316 行） | 5 个，358 行 |
| sdr | 32 / 32 | 210 / 213 | 20 个，1,870 行 |
| video-recipes | 14 / 14 | 48 / 48 | 无 |
| google-ads | 8 / 8 | 48 / 48 | 6 个，337 行 |
| asset-handoff、ad-copy、proofcut、product-image-to-video | 1 到 4 行，全部出现 | 0 到 48 行，全部出现 | 0 到 1 个 |

`fact_keys.tsv` 和 `decision_keys.tsv` 由 kit 按名字读取，键不一定以字符串形式出现在包的代码里，上面的数法量不准，所以没列进表。

看出来的三点：

1. **owner 文件只在两个老包里活着。** seo 和 amazon-ppc 是在模板出现之前自己长出来的，它们的故事表有人填、有人用，提交里也引用。从模板建出来的 8 个包里，6 个的 owner 文件全空，另外 2 个各只有一个文件有内容（sdr 的故事、video-recipes 的规则）。
2. **故事编号在没有故事表的地方也在用。** meta-ads 有 218 个提交提到 16 个 `S` 编号，而 `user-stories.tsv` 是 0 行：这些编号指的是 agent 提议文件里从没被确认过的行。CI 的 story id 检查只看 PR 标题里有没有编号，不管这个编号背后有没有被确认的故事，所以它没能拦住这种情况。
3. **owner 的决定其实已经有一个家了：路线图的 `R` 行。** `kit/guards/roadmap.py` 已经要求每条 `R` 行用双引号引用 owner 的原话，并写上日期。

### A2. 改什么

1. **机器那一半原样保留。** `constants.tsv`、消息码、`fact_keys.tsv`、`decision_keys.tsv`、各包自己的登记表、`ssot/index.tsv`，以及读它们的 `kit.registry` 和 `kit.facts`，都不动。
2. **owner 的决定只记在一个地方：路线图的 `R` 行。** 每条带日期、用双引号引 owner 的原话（原文照录，不翻译）、写明出处（哪天的聊天）。后来的决定推翻前面的，就新写一条，写明"取代 R12"，不改旧行。
3. **空的 owner 文件删掉，不再用生成的方式补出来。** 按文件来定，规则只有一条：0 行的 owner 文件，连同它的 `.agent.tsv` 和 `ssot/index.tsv` 里对应的行一起删；有内容的留着。这样 ad-copy、asset-handoff、google-ads、meta-ads、product-image-to-video、proofcut 删掉全部 4 个；sdr 留下故事表、删掉另外 3 个；video-recipes 留下规则表、删掉另外 3 个；seo 和 amazon-ppc 不动。8 个包的 `stages.agent.tsv`（7 个停在建包那天）也一起删。从 `R` 行"生成" owner 文件不做：那样只是多出一份副本，还要再写一个守卫去盯着两份一致。
4. **被删文件里的 agent 提议行**（meta-ads 50 行、product-image-to-video 30 行、sdr 34 行，其余包各 0 到 1 行）：已经被某条 `R` 行或某个设计页采纳的，直接删；还有用的，每条变成路线图 "Waiting on owner" 里的一个问题；剩下的删掉，git 历史里还留着。

### A3. 每个守卫和规则要跟着改什么

| 地方 | 现在 | 改成 |
| --- | --- | --- |
| CI 的 story id 检查（`templates/github-ci.yml`、`templates/gitlab-ci.yml`，各包的 `.github/workflows/ci.yml`） | PR 标题要有 `M..`、`S..`、`P..`，或以 `release` 开头 | 再接受路线图条目 `X..`。删掉故事表的包不再用 `S..` |
| `CLAUDE.md` 的不变量 "Owner files"（`templates/AGENT_INSTRUCTIONS.md`） | agent 不改 owner 文件，只在 `.agent.tsv` 里提议 | 换成 **"Decisions"**：owner 的决定只是路线图的 `R` 行，带日期、引原话；一条 `R` 行合进 main 之后，agent 不再改它的引文。保留 owner 文件的包，原来这一条照旧留着 |
| `CLAUDE.md` 的不变量 "Stories" | 每个做完的故事在 `story_checks.tsv` 里有一个只读检查 | 只有留着故事表的包保留这一条（amazon-ppc 有 42 个检查）；其他包删掉这一条和 `compute stories` 动作 |
| `tests/test_ssot.py`（vendor 的薄壳，调 `kit.testing.suites.ssot`） | 检查索引、owner 文件的用词、兄弟文件 id 一致、id 不删、`decided` 留痕、步骤顺序 | 不用改：文件和它在索引里的那一行一起删，就不会再被检查；没有步骤表时，步骤检查本来就跳过 |
| `kit/guards/roadmap.py`（各包 `tests/test_roadmap.py`） | `R` 行必须有引号 | 加一条：在 git HEAD 上已经存在的 `R` 行，引文不能改，编号不能删。kit 升版本、重新生成 `kit/MANIFEST.sha256`、在 `CHANGELOG.md` 加一行 |
| `scaffold/new_skill_pack.py` | 新包带全套 owner 文件和 `stages.agent.tsv` | 新包不再带这些。某个客户的用词或故事确实需要逐条签字的时候，再手动加上（seo 和 amazon-ppc 的形状） |
| `README.md`、`docs/stages.md` | owner 签"含义、故事"两道关 | 这两道关的产物是 `R` 行；故事表变成可选 |
| `build/apply_answers.py` | 把 owner 的回答写进 owner 文件 | 对有 owner 文件的包照旧；没有的包，回答写成一条 `R` 行 |

按 playbook 的规矩，这是四个 PR，每个只管一件事、各带测试：kit（`roadmap.py` 和 `compute stories` 接受没有故事表的包）、模板（`AGENT_INSTRUCTIONS.md` 和两份 CI 模板）、scaffold、文档。

### A4. 每个包要付出什么，按什么顺序迁

| 顺序 | 包 | 要做的事 | 代价 |
| --- | --- | --- | --- |
| 0 | playbook | 上面四个 PR | 一个 kit 小版本 |
| 1 | ad-copy、asset-handoff、google-ads、proofcut | 删 4 个 owner 文件、它们的 `.agent.tsv`、`stages.agent.tsv` 和对应的索引行，换 `CLAUDE.md` 那两条，改 CI 正则 | 每个包一个提交，跟着 X25 重新 vendor 的那一趟一起走 |
| 2 | meta-ads、product-image-to-video | 同上，外加逐行处理 agent 提议（A2 第 4 条） | meta-ads 50 行、product-image-to-video 30 行，各半个会话 |
| 3 | sdr、video-recipes | 只删空的 3 个文件和 `stages.agent.tsv`；有内容的那个和 `CLAUDE.md` 里对应的那条保留；CI 正则接受 `X..` | sdr 要处理 34 行提议，半个会话；video-recipes 一个提交 |
| 4 | seo、amazon-ppc | 不动；以后重新 vendor 时带上新的 CI 正则 | 无 |

### A5. 坑

- **只删行、不删文件，会被拦住。** `kit/guards/ssot.py` 不允许删除索引里文件的 id（"retire a row, never delete"）。所以文件和它的索引行要在同一个提交里一起删。
- **决定散在很多条 `R` 行里，"这个词现在是什么意思"不好查。** 解决办法是"取代 R12"的写法，再加上新的守卫（引文不能改），让最新的那条一眼可见。等真的出现第二次因此查错，再考虑给"取代"加检查；现在不加。
- **旧提交里的 `S16` 会指向被删掉的行。** 历史里还在；在各包路线图的 Links 下写一行说明即可。
- **全队会同时存在两种形状**（留有 owner 文件的 4 个，没有的 7 个，adcut 本来就没有）。现有守卫两种都能处理，不用加代码。

## B. 开发和运行分开

### B1. 量到的

开发机（本机）上：

| 看什么 | 量到的 |
| --- | --- |
| `~/.claude/scheduled-tasks/` 里常驻的定时任务 | 2 个在跑：两个群消息"门铃"，每 2 小时只读地查一次，有新消息就叫醒一个开发会话，不发消息、不跑任何包的动作。另有 1 个提示词目录还留在磁盘上：meta-ads 早间例程的那个任务，2026-11-05 13:07 建，当天从调度器里删掉了（meta-ads R86） |
| `~/.config/claude-openmax/` 里的钩子 | 2 个桥接目录，各自带一份 kit 的副本；还有 4 个连接配置。都是开发会话收消息用的 |
| 客户 hub 的 `bin/` 包装脚本 | 44 个，全部指向 `~/openmax/skill-pack/<包>` 下的开发检出（其中 2 个默认用相对路径找开发检出）；0 个指向发布版 |
| `crontab`、`~/Library/LaunchAgents` | 没有和包相关的 |

各包的 `origin/main` 上：

| 包 | 发布标签 | 定时节奏写成数据 | 只存在于 `tools/` 里的例行步骤 | `tools/` 里对外写或花钱的脚本 | `tools/` 文件数 |
| --- | --- | --- | --- | --- | --- |
| meta-ads | 0 | 没有（有 `zylos/`，但 0 个任务） | `tools/run_routine.py`（早间例程：拉数、入库、每层计算、出页面、和上次对比） | `tools/smartly_upload.py`（用浏览器往客户的 Smartly 素材库上传，代码里前面没有闸门动作） | 13 |
| adcut | 0 | 没有 | 未量 | `tools/smartly_upload.py` | 46 |
| product-image-to-video | 1（v0.2.0） | 没有 | 未量 | `tools/i2v_autodl.py`、`tools/comfy_edit.py`、`tools/run_jobs.py`（租用 GPU，要花钱） | 24 |
| seo | 28（v1.21.0） | 4 个任务，写在 `zylos/manifest.json` 的 `tasks[]` | 无 | 无 | 9 |
| sdr | 5（v0.3.2） | 2 个任务，写在 `zylos/manifest.json` 的 `tasks[]` | 无 | 无 | 0 |
| amazon-ppc | 31（v0.24.0） | 4 个任务，硬编码在它自己的 `zylos/hooks/lib.js` 里 | 无 | 无 | 0 |
| video-recipes | 4（v0.3.1） | 没有 | 无 | 无 | 0 |
| ad-copy、asset-handoff、google-ads、proofcut | 0 | 没有 | 无 | 无 | 0 到 2 |

12 个包都没有在 `.gitattributes` 里写 `tools/ export-ignore`，所以 `tools/` 会被打进发布包。

**那个真实发生的例子（2026-11-05）。** 一个开发会话在本机建了一个每日定时任务，内容是 `python3 <开发检出>/tools/run_routine.py --pack <客户文件夹>`。这一行同时犯了四条：开发机上的常驻任务；跑的是开发检出；用客户的数据做日常运营；调的是 `tools/` 脚本而不是包的动作。owner 当天指出后删掉了（R86）。它是只读的，没有对外发出过任何东西。但如果这样跑下去，本机就成了一个没有发布、没有闸门的生产环境。

### B2. 四条规则，每条配一个守卫

| # | 规则 | 守卫 |
| --- | --- | --- |
| 1 | **每个例行步骤都是包的一个动作，它的节奏写成包里的数据，由运行端（客户的 agent）来调度。开发机上不放常驻任务，只手动跑。** 节奏写在 `zylos/manifest.json` 的 `tasks[]` 里：sdr 和 seo 已经这样做了，安装后的钩子会自动对齐，playbook 目前只有 Zylos 这一种运行端适配器。等出现第二种，再挪到 `skill-pack.toml` | (a) 适配器的清单检查：每个任务的提示词只能通过 `{cli}` 或 `{detach}` 调一个包的动作，出现 `tools/` 或 `python3` 就拒绝。(b) scaffold 给每个包的 `.claude/settings.json` 加一个 PreToolUse 钩子：在包的检出里建定时任务时，如果提示词里有这个包的命令、`tools/` 或客户文件夹，就拒绝。包里有一个测试确认这个钩子在 |
| 2 | **运行端只装打过标签的发布版，不装开发检出** | `doctor` 报告安装来源（发布版 vX.Y.Z，还是检出 + 路径）；在运行端（有 Zylos 数据目录）上，如果是 git 检出就判为不通过。由 kit 的 doctor 测试守住 |
| 3 | **开发机上的客户数据只是调试用的副本。从开发机往外的任何动作（发消息、写客户的账户、花钱）都只能走人工闸门** | `kit.guards.boundary` 加一条：`tools/` 里出现对外调用（POST、浏览器自动化、发邮件、租 GPU）的文件，必须列在 `tools/outward.tsv` 里，写明它要的闸门动作，并且在动手之前通过 `kit.human` 核对批准；没列的就测试失败 |
| 4 | **`tools/` 是给人在终端里用的，运行端的 agent 只用包的 CLI** | `.gitattributes` 写 `tools/ export-ignore`，这样发布包里就没有 `tools/`；再加一个测试：`SKILL.md`、`zylos/manifest.json` 的提示词、`templates/client/` 都不能提到 `tools/` |

两个"门铃"按规则 1 不算包的例行步骤：它们是开发团队自己的收件箱，只读、不跑包的动作、不往外发。这一点会写进规则原文，钩子也不拦它们。

### B3. 每个包要付出什么，按什么顺序迁

| 顺序 | 包 | 要做的事 | 代价 |
| --- | --- | --- | --- |
| 0 | playbook | 四个 PR：kit（doctor 的安装来源、boundary 守卫，升版本）、`hosts/zylos`（任务提示词检查）、scaffold（钩子、`.gitattributes`）、模板（`AGENT_INSTRUCTIONS.md` 加一条不变量 "Development is not runtime"） | 一个 kit 小版本、一个适配器小版本 |
| 1 | meta-ads（就是那个例子） | 把 `tools/run_routine.py` 变成动作 `routine run`；在 `zylos/manifest.json` 里加早间任务；打第一个发布标签；owner 确认后装到客户的 agent 上；删掉本机留下的那个提示词目录 | 一到两个会话，外加一次发布 |
| 2 | meta-ads、adcut 的 Smartly 上传；product-image-to-video 的 GPU 脚本 | 放到闸门动作后面，或者列进 `tools/outward.tsv` 并核对批准 | 每个包一个 PR |
| 3 | sdr、seo | 节奏已经写成数据了，只跟着 X25 重新 vendor，加 `export-ignore` | 每个包一个提交 |
| 4 | amazon-ppc | 最后做：它的任务硬编码在自己的适配器里，要等它换到共享适配器（C3 的顺序） | 跟着 C3 一起 |
| 5 | 其他没有例行步骤的包 | 只是重新 vendor；第一次装到运行端之前打第一个发布标签 | 每个包一个提交 |

### B4. 坑

- **改动要经过一次发布才能到客户那里，会变慢。** 这正是这条规则的目的。owner 本来就签"发布"这道关；一次发布是一个标签加一句确认。
- **运行端没有调度器怎么办。** 节奏照样写在包里，由客户的 agent 按它自己的时钟去跑；开发机不替它跑。
- **在开发机上调试还是可以照常跑**，比如 `mads routine run`，用 owner 自己的 token、只读（meta-ads R74）。规则 1 管的只是"常驻"。
- **钩子只在包的检出里生效。** 在别的目录建任务，它管不到；所以 playbook 的 `tools/fleet.py` 状态报告再加一列，列出本机上提到某个包命令或客户文件夹的定时任务，由人来看。
- **`export-ignore` 以后，hub 包装脚本还能用 `tools/` 吗？** 开发机用的是检出，不受影响；运行端本来就不该用。

## 参照（只写名字，不放链接）

- Michael Nygard, "Documenting Architecture Decisions"（ADR，2011）：决定一条一条记、带日期、只追加，被取代时写明取代谁，不改旧的。`R` 行就是这个做法。
- The Twelve-Factor App，"Build, release, run" 和 "Dev/prod parity"：构建、发布、运行严格分开；发布有编号、发出去之后不改；运行端只跑发布。

## 请 owner 回答的五个问题

**Q1. owner 的决定以后只记在路线图的 `R` 行里吗？**
- 选项：(a) 是，全队都这样；(b) 不是，以 owner 文件为准，以后开始填它；(c) 用 `R` 行生成 owner 文件。
- 依据：6 个包的 owner 文件全是 0 行；meta-ads 有 60 条 `R` 行、sdr 有 66 条、playbook 自己有 42 条，都带原话。
- 推荐：(a)。
- 如果"不"：选 (b) 的话，每个包要把已有的 `R` 行回填成 owner 文件的行，以后每个决定写两处；选 (c) 要多一个生成器，外加一个盯着两份一致的守卫。

**Q2. 空着的 owner 文件（6 个包全部，sdr 和 video-recipes 各 3 个）、它们里面没被确认过的 agent 提议，以及建包步骤表，删掉吗？有内容的文件照旧保留，seo 和 amazon-ppc 完全不动。**
- 选项：(a) 照这样删；(b) 一个都不删；(c) 连 seo 和 amazon-ppc 的也删。
- 依据：A1 表。meta-ads 有 50 行提议、product-image-to-video 有 30 行，从没被确认过；seo 的故事表有 301 行、906 个提交在引用。git 历史里都还在，随时能找回来。
- 推荐：(a)。
- 如果"不"：选 (b) 的话，空文件和守卫照旧留着，新包也照旧带上；选 (c) 会让 seo 和 amazon-ppc 失去正在用的故事检查。

**Q3. "开发机不放常驻任务、只手动跑；每个例行步骤都是包的动作，节奏由运行端调度"，全队都遵守吗？**
- 选项：(a) 是，B2 的四条全部照做；(b) 是，但在一个客户还没有运行端之前，允许开发机每天替它跑；(c) 不定规则，逐个包再说。
- 依据：2026-11-05 那个早间任务的例子；44 个包装脚本全部指向开发检出；两个群门铃算开发团队的收件箱，不受影响。
- 推荐：(a)。
- 如果"不"：选 (b) 的话，在那个客户的运行端就绪之前，本机就是它的生产环境，要有人盯着它的失败；选 (c) 的话，下一个包还会再犯同样的错。

**Q4. 运行端只装打过标签、并且经 owner 确认的发布版吗？**
- 选项：(a) 是；(b) 演示阶段的包可以直接装检出。
- 依据：11 个 skill pack 里 6 个从没打过标签，其中包括 meta-ads；这次要等它的第一次发布，客户的 agent 才能跑早间例程。
- 推荐：(a)。每次发布 owner 只需确认一句 `confirm vX`。
- 如果"不"：运行端跑的是哪一版就说不清了，出了问题也没法退回到一个已知的版本。

**Q5. 从开发机往外的写操作和花钱的操作，都要先过人工闸门吗？**
- 选项：(a) 是，全部变成闸门后面的包动作，或者在动手前核对批准；(b) 留在 `tools/` 里由人手动跑，每次在路线图里记一行；(c) 维持现状。
- 依据：`tools/smartly_upload.py`（meta-ads、adcut）往客户账户里写，代码里前面没有闸门；product-image-to-video 的 3 个 GPU 脚本会花钱。
- 推荐：(a)，按 B3 第 2 步一个包一个 PR 来做。
- 如果"不"：这几处仍然是靠人记得，没有任何测试会在它们被跳过时失败。

回复"五条都按推荐"，就是五个问题全部同意。
