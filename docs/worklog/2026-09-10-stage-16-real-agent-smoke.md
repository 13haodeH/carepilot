# 阶段十六工作记录：真实 DeepSeek 视觉与决策 Agent 烟测

## 目标

验证真实 Auth 用户发起的脱敏工单能使用服务器端 DeepSeek 文本和视觉模型，而非 fixture 或规则输出；同时核验模型、提示词、输入/输出、工具调用、政策依据、延迟、token 和成本均被持久化。

## 实现与问题修复

- 使用 `deepseek-v4-flash-vision-exp` 处理一张仓库内自构造、无个人信息的 PNG，视觉结果写入 `REAL_VISION_MODEL`，并关联独立的 `VISION_EVIDENCE` Agent Run。
- 使用 `deepseek-v4-flash` 运行 Resolution Agent。它自主调用 `order.lookup`、`logistics.track`、`policy.search`、`evidence.read` 和 `ticket.history`；最终的状态更新与用户通知由 Permission Engine 决定后执行。
- 首次上传触发 500。根因是 `evidence_assets.analysis_origin` 的旧 CHECK 约束只允许 fixture 值，真实视觉结果无法提交。新增 `data/009_real_vision_evidence_origin.sql`，仅扩展允许值，不删除或回填历史数据。
- 修正真实图片文件校验记录：之后的 `evidence.validate` 使用 `caller=real-agent` 和脱敏结构化 input/output，不再错误标为 `fixture-simulation`。已发生的历史记录保持原样，避免改写审计事实。

## 实测结果

- 视觉 Run 完成：模型为 `deepseek-v4-flash-vision-exp`，延迟 3.308 秒，输入/输出 token 为 700/477，按本地配置估算成本为 0.00093764 USD。
- Resolution Run 完成：模型为 `deepseek-v4-flash`，提示词版本为 `resolution-v1`，延迟 11.346 秒，输入/输出 token 为 6308/1959，按本地配置估算成本为 0.0053614 USD。
- 视觉模型把该抽象栅格测试图判为“无有效售后证据，需人工复核”。因此 Resolution Agent 合理地产生“补充材料”建议，Permission Engine 执行低风险的状态更新与通知，工单进入 `NEED_INFO`。没有生成或执行退款、退货、换货、补偿或库存动作。
- API 回归测试 19 项通过；重启后的本机 `/health` 返回 `storage=database-url`。

## 边界与下一步

- 这是一条真实模型的脱敏技术烟测，不是生产业务、真实订单或真实用户效果证明。订单、物流和政策内容仍为受控演示数据。
- 当前图片 fixture 是用于文件链路的抽象栅格图，不能作为视觉理解准确率基准；模型的“不足以判断”结论是合理失败案例，而不是已验证的损坏识别能力。
- 下一步应先建立一批许可明确、无个人信息且视觉语义清晰的冻结图片样本，再单独验证“换货/退款/补偿 Proposal 必须进入 `WAITING_REVIEW`”的真实模型路径。不得用 fixture 标注替代视觉模型结论。
