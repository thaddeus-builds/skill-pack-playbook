# Chinese glossary for the pages an advertiser reads

The kit's Chinese words (`kit/pagestyle.py` `ZH`, the `label_zh` column of `kit/constants.d/*.tsv`, the `meaning_zh` column of `kit/message_codes.d/*.tsv`) are the words a media buyer says. Seen once, in the Meta pack's watch demo of 2026-10-28 (issue #302): the owner could not read 降权, which to a buyer is a ranking penalty, not "doing worse". A pack that draws a Chinese page takes these words and does not invent its own; `tests/test_glossary_zh.py` fails when a key of `ZH` is missing here or an old word comes back.

| Idea (key) | The word | The word to avoid | Why |
| --- | --- | --- | --- |
| `state_untested` | 未测 | | |
| `state_testing` | 在测 | | |
| `state_promising` | 表现良好 | 有希望 | a result, not a hope |
| `state_down` | 表现下滑 | 降权 | 降权 is a ranking penalty |
| `state_closed` | 已停止 | 关闭 | says it is stopped |
| `warnings` | 需要关注 | 留意 | |
| `if_works`, `if_fails` | 如果有效, 如果无效 | 如果行, 如果不行 | |
| `sep`, `money`, `dots`, `more`, `details`, `owner`, `copy`, `copied`, `selected`, `expand_all`, `collapse_all` | unchanged | | plain words, not in question |
| `flow_person`, `flow_auto`, `flow_skip` | 人来定, 自动, 跳过 | 人工, 手动 | who does a step; a cell may name the person instead (客户选) |
| `flow_stop`, `flow_back` | 停下来问, 退回 | 中断, 回滚 | it stops to ask a person; a step done again, not undone |
| `choice_decided`, `choice_proposed`, `choice_open` | 已定, 推荐, 之后再问 | 待定 | 待定 reads as undecided by the owner; 之后再问 says when it is asked |
| `box_agree`, `box_cost`, `box_worst`, `box_needed` | 同意后, 花费, 最坏的情况, 还需要你 | 风险 | the design page's box in the owner's words |
| `design_reply`, `record` | 全部照这样，回复“同意”, 细节：研究、规则、风险 | | one reply agrees to the page; the detail stays folded |
| a creative in doubt, parked | 待观察, 暂缓 | 存疑, 搁置 | |
| a creative that has enough conversions | 稳定 | 成熟 | |
| a creative that is fading | 衰退 | | stays: the industry's word, and 表现下滑 is the campaign's |
| a campaign above its benchmark | 高于基准 | 赚钱 | the rule compares with a reference; it does not say money is made |
| return on ad spend | ROAS | 回报 | what the platform shows |
