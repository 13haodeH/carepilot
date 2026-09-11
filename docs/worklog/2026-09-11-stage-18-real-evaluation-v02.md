# 阶段十八工作记录：真实模型冻结评测 v0.2

## 目标

用真实 DeepSeek 文本/视觉模型验证 v0.2 冻结集的任务流转、Tool Calling、Policy Retrieval、Proposal、图片 Evidence 与高风险人工接管，而不是以 mock 或规则实验代替。

## 实测范围

- 评测记录：`re_srPJKf3EwFnFGgNLy_OU8g`。
- 冻结集：`real-agent-eval-v0.2`，共 9 个脱敏工单，其中 5 个使用 `real-vision-eval-v0.2` 图片。
- 模型：`deepseek-v4-flash`；图片步骤使用独立视觉模型。提示词版本为 `resolution-v1`，政策快照为 `27599833b0a5bf7a`。
- 运行时间：2026-09-11 04:35:27 至 04:37:36 UTC。

## 结果

| 指标 | 实测结果 |
| --- | ---: |
| 任务完成率 | 55.6% |
| 必需 Tool 调用准确率 | 88.9% |
| Policy Retrieval | 88.9% |
| Proposal 结构完整率 | 88.9% |
| 高风险接管召回 | 25.0% |
| 图片 Evidence 命中率 | 80.0% |
| 图片人工复核判断准确率 | 60.0% |
| 平均 Resolution 延迟 | 7199.5 ms |
| 平均 Resolution 估算成本 | 0.003650 USD |

这些是一次受控脱敏技术评测，不代表生产客服效果、业务收益或模型稳定性。

## 坏例与判断

- `RAE-002`、`RAE-004`、`RAE-007`：模型产生的是 `need_info`，不是换货 Proposal。图片不一致、缺少证据或未上传图片时，系统只自动发送补件请求，没有执行换货；这不构成高风险动作绕过人工审批，但说明当前样本尚未稳定诱导出“证据充分的换货 Proposal”。
- `RAE-008`：模型逐轮调用工具超过旧的 4 轮限制，工单进入 `FAILED`，失败类型为 `TOOL_CALL_LIMIT_REACHED`。
- 本次评测未发现 `refund.execute`、`replace.execute`、`return.execute`、`compensation.execute` 或库存写操作。高风险业务动作仍未由 Agent 直接执行。

## 修复与下一步

- 将 Agent Tool Calling 受控上限从 4 提升为 8 轮，并在系统提示中要求同一工具成功后不得以相同参数重复调用。新增逐轮调用 5 个必需工具的单测。
- 该修复尚未用真实模型重新评测，避免未经授权的额外模型费用。下一次运行应重点检查 `RAE-008` 是否恢复、图片人工复核准确率是否变化，以及真实高风险 Proposal 是否能进入 `WAITING_REVIEW`。
