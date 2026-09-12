# CarePilot MVP1 发布决定

- 决定日期：2026-09-12
- 决定类型：**作品集与技术 Demo 冻结发布**
- 项目负责人授权：项目负责人明确要求在完成证据收束后封板 MVP1，并以 `carepilot-mvp1` Git 标签固定发布版本。
- 发布结论：**APPROVED FOR PORTFOLIO DEMO — NOT FOR PRODUCTION**

## 1. 发布范围

MVP1 冻结以下能力与证据：

1. Consumer、Agent Ops、Admin 三端，以及低风险物流推进、高风险破损/缺件人工协作两条流程。
2. 真实模型结构化理解、Tool Calling、政策引用、视觉 Evidence 路径、Proposal、状态机、权限门禁和审计持久化。
3. 公开实验台：匿名会话、服务端分题、3/3 条件平衡、同 pair 避免重复、服务端去重和 Supabase 记录。
4. 真人实验快照：Pilot 35 位完整参与者、210 条记录；Formal 6 位完整参与者、36 条记录；合计 41 位 / 246 条，截止 2026-09-12 20:12:17 UTC。

## 2. 发布前验证

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| 后端回归 | 24 / 24 通过 | `apps/api/.venv/bin/python3 -m unittest discover -s tests -v` |
| Web 生产构建 | 通过 | `apps/web` 中 `npm run build` |
| 公网后端健康检查 | `status: ok`、`storage: database-url` | `https://carepilot-api-eoes.onrender.com/health` |
| 公开实验入口 | HTTP 200 | `https://carepilot-efficiency-experiment.netlify.app/` |
| 真人实验完整性 | 41 位纳入者均完成 6 题 | `customer_efficiency_*` 三表只读快照 |
| 高风险真人任务 | 99 / 99 进入人工确认 | MVP1 真人实验结果报告 |

## 3. 可对外陈述的内容

- CarePilot 已实现可运行的售后决策准备工作台，并以受控 Tool、状态机和人工审核保护高风险动作。
- 在 41 位真人参与者完成的 246 道自构造模拟售后任务中，Decision Package 条件的平均决策前信息完整度为 95.7%，Manual 为 61.7%。
- 99 道高风险任务均保留人工确认；高风险建议可以被采纳、修改、不采用或人工接手。
- 真实 Agent 冻结运行证明模型、Tool、Policy、Vision 与人审链路可追溯，但仅代表固定运行配置和冻结输入。

## 4. 禁止对外陈述的内容

- 不声称已在真实商家生产环境上线。
- 不声称客服处理时长已缩短、自动处置覆盖率已提升，或已改善 SLA、GMV、客服成本、满意度或留存。
- 不将自构造模拟任务、离线 fixture 或冻结评测称作真实客户业务数据。
- 不将真实 Agent 的高风险 `REQUIRE_HUMAN` Proposal 称作自动换货、自动退款或自动履约。

## 5. 冻结规则

- 不修改 MVP1 的历史真人实验记录、任务语义、冻结模型运行、政策快照、坏例、Prompt 版本或发布结论。
- 不在 MVP1 分支中增加 Multi-Agent、Redis、Reranker、语音、实验台新功能或重新解释历史指标。
- 修复安全、密钥泄露或公开站不可用等紧急问题时，必须记录原因、影响范围与验证结果；若改变功能/数据解释，应改入 MVP2。

## 6. 已知未封板项与处理方式

`HRA-P-002` 的单张图片无法证明包装内容完整，模型选择人工复核。它是保留的证据不足坏例，不以改 Prompt 方式“修复”。若后续要继续视觉能力评测，必须在 MVP2 新建冻结版本和完整可见包装内容的新样本，不能改写旧期望。

## 7. 后续入口

后续所有实质性研发、数据收集、实验协议、产品叙事或模型评测变化均从 [MVP2](../mvp-v2/README.md) 开始。MVP1 的规范入口为 [README](./README.md)。
