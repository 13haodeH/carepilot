# Manual vs Agent 对照实验准备（v0.1）

本协议只定义待开展的作品集可用性实验；不包含参与者、录屏、问卷或结果，也不得据此主张效率提升。

## 输入与分配

- 使用 `fixtures/manual-agent-tasks-v0.1.json` 的 10 个场景对、20 条条件任务。
- 使用 `fixtures/manual-agent-assignment-v0.1.json` 的 5 个匿名槽位与 20 条预分配；每个槽位执行 4 条任务，其中 `MANUAL` 与 `AGENT_ASSISTED` 各 2 条。
- 每个场景对包含同一业务目标的 `MANUAL` 与 `AGENT_ASSISTED` 两个条件；同一参与者不得完成同一场景对的两种条件。
- 四个轮次的条件数按 3:2、2:3、3:2、2:3 交叉平衡，避免系统性地总是先接触同一条件。开始前仅使用脱敏模拟订单与模拟工具。

## 记录字段

| 字段 | 记录规则 |
| --- | --- |
| `participant_id` | 匿名、随机生成，不记录姓名或联系方式 |
| `pair_id` / `task_id` / `condition` | 从 fixture 原样记录 |
| `started_at` / `completed_at` | 任务开始与结束时间 |
| `participant_step_count` | 参与者实际完成的原子步骤数，不用预设步骤数替代 |
| `completion_status` | `COMPLETED` 或 `STOPPED`；停止也必须保留记录 |
| `outcome_correct` | 是否达到 fixture 的 `target_outcome` |
| `high_risk_gate_observed` | 高风险任务是否经由 `proposal_review` 且最终进入人工审核 |
| `proposal_modified` | 高风险任务是否修改了 Agent Proposal；Manual 条件记为不适用 |
| `handoff_or_takeover` | 是否发生人工接管或无法完成 |
| `ease_rating_1_to_7` | 每题易用性评分：1 = 非常困难，7 = 非常容易 |
| `observer_notes` | 仅记录交互问题，不写入个人信息 |

`SUS` 不是单题评分。每位参与者完成其 4 条任务记录后，单独填写一次标准 SUS-10（每题 1–5 分）。原始十题答案以参与者为单位导出，分析阶段再按标准正反向计分；不要把 `ease_rating_1_to_7` 标为或换算为 SUS。

## 运行页与导出

- 在前端打开 `/experiment`，选择已分配的匿名槽位；页面按 assignment fixture 的 Round 顺序加载该槽位的 4 条任务。
- 开始题目即开始计时；页面只记录参与者实际点击的原子步骤、最终状态、是否改写高风险 Agent Proposal、单题易用度和不含个人信息的观察备注。
- 每题完成或停止都会写入当前浏览器的 `localStorage`，不可静默重做；所有任务完成后，页面显示 SUS-10。
- 导出两个文件并一起交付分析：`carepilot-manual-agent-records-v0.1.csv`（一任务一行）与 `carepilot-manual-agent-sus-v0.1.csv`（一参与者一行）。两者均不包含真实订单、图片或个人身份信息。

## 停止与边界

- 不收集真实客户、订单、地址、电话、支付信息或图片。
- 参与者可随时停止；未完成任务记录为未完成，不从数据中删除。
- 5 人实验前不计算或宣传“步骤下降”“耗时下降”“满意度提升”等结论。
