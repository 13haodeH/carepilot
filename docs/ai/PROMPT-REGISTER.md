# Prompt 与行为版本台账

- 审计日期：2026-09-12
- 适用范围：MVP1 及其历史真实运行
- 目的：区分**实际运行过的版本**、仅存在的配置草稿和未来假设；不补造不存在的 V1→V3 效果故事。

## 1. 已知版本

| 版本 | 角色与状态 | 主要约束 | 运行证据 | 可以/不可以说 |
| --- | --- | --- | --- | --- |
| `resolution-v1` | 当前真实 Resolution Prompt；已用于 Stage 16、18、19、20 的 `REAL_AGENT_RUN` | 先查询订单、物流、政策；有图时读 Evidence；成功后不以相同参数重复调用；只引用 `policy.search` 返回的 citation；权益动作只能建议、不可暗示直接执行；输出严格 JSON | `re_srPJKf3EwFnFGgNLy_OU8g`、`re_U_zrcV3_RBlWGdOb1v0wBg`、`re_O-_XIFQK9vRmC0oBZVEqQw` | 可说真实 Prompt 与结构化 Tool loop 已运行；不可说它已在真实业务上达到稳定效果 |
| `vision-evidence-v1` | 当前真实视觉 Prompt；用于真实图片 Evidence | 只提取可见事实；只用投诉与订单标题判断标签是否匹配；模糊、无关、歧义或信息不足时要求人工复核；不判断退款/换货资格 | Stage 16 真实视觉烟测；Stage 18–20 冻结视觉样本 | 可说视觉链路真实运行；不可将人工标签当作视觉准确率 |
| `resolution-v1.1` | 历史 Agent Config 草稿标识；**没有冻结真实运行证据** | 仅作为 Draft 配置的版本字段出现 | 无运行 ID、无独立 Prompt 文本、无前后对照 | 不得写成已发布或已验证的 Prompt 迭代 |

`resolution-v1` 的实际指令与 schema 位于 [`apps/api/app/agent_runtime.py`](../../apps/api/app/agent_runtime.py) 的 `run_resolution`；`vision-evidence-v1` 位于同文件的 `analyze_image`。真实运行在 `AgentRun` 中持久化版本标识、输入输出、Tool、政策、token、延迟和成本。

## 2. 为什么没有“Prompt V1 → V3”成果图

目前仓库没有三次独立、冻结、可比较的 Prompt 实验。因此不能为了作品集格式伪造“V1 很差、V2 加 Few-shot、V3 提升 X%”的叙事。

已发生的真实迭代如下，且修复层并不都是 Prompt：

| 观察到的问题 | 实际处理 | 版本与验证 | 归因边界 |
| --- | --- | --- | --- |
| `RAE-008` 在旧 4 轮 Tool 上限处失败 | Tool 上限改为 8；同时增加“成功后不要以相同参数重复调用”的行为约束 | Stage 18 → Stage 19，`RAE-008` 恢复完成 | 当时仍标记 `resolution-v1`，且没有保存旧指令哈希；不能把结果归因成纯 Prompt 提升 |
| 三条 case 没有政策 citation | 检索词归一化、订单品类约束和 Tool 输出记录 | Stage 20，Policy Retrieval 75.0% → 100.0% | 是检索/上下文修复，不是输出 Prompt 修复 |
| 图片判断混入诉求文本，且订单—图片不匹配被误解释 | 分离模型原始判断与确定性 Evidence 门禁 | Stage 20，新建 v0.2.2，不改写旧标签 | 是 Evidence 评测与门禁修复，不是视觉 Prompt 调参 |
| `HRA-P-002` 单图无法证明包装内容完整 | 保留人工复核和坏例，不强行改 Prompt | Stage 20、MVP1 发布决定 | 未解决但符合安全边界 |

这里存在一项已记录的历史追溯缺口：Stage 18 说明加入了避免重复成功 Tool 调用的指令，但当时没有升级 `resolution-v1` 的版本名或保存内容哈希。因此 v0.2 与 v0.2.1 **不是**严格的 Prompt A/B 对照。本台账保留该缺口，而不事后重命名历史运行。

## 3. 未来 V2/V3 的准入规则

后续版本只有在真正创建、运行并记录后才能命名为 `resolution-v2`、`resolution-v3`。每个版本至少包含：

```text
版本 ID 与完整 Prompt SHA-256
变更来源的坏例 ID 与产品假设
固定模型、Tool allowlist、政策快照、fixture 版本和样本哈希
离线/真实运行 ID、指标、失败样本与成本
是否激活、回滚或继续迭代的人工决定
```

推荐的顺序不是直接写更多 Prompt，而是先为 `HRA-P-002` 建立新的完整可见包装样本；只有新样本确认问题确实属于模型行为，才制定新的 Prompt 假设并在新冻结评测版本中验证。
