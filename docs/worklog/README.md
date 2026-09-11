# CarePilot 工作记录

本目录保存阶段性、可回溯的工作记录；它不替代 `PLAN.md`，而是记录计划在本地原型与技术验证中的实际进展。

## 索引

| 日期 | 阶段 | 状态 | 记录 |
| --- | --- | --- | --- |
| 2026-09-11 | 公开客服提效实验与部署准备 | 匿名服务端分题、去重和部署配置已本地验证；未执行远程迁移或公网发布 | [阶段二十三记录](./2026-09-11-stage-23-public-efficiency-study.md) |
| 2026-09-11 | 客服提效 v1 题库与运行器 | 本地实验工具与数据契约已验证；未招募、未产生结果 | [阶段二十二记录](./2026-09-11-stage-22-efficiency-instrumentation.md) |
| 2026-09-11 | 客服提效产品价值重构与实验设计 | 产品价值、指标口径与 v1 实验协议已冻结；未改代码、未采集新结果 | [阶段二十一记录](./2026-09-11-stage-21-product-value-reframe.md) |
| 2026-09-09 | 公开政策 grounding 与前端评审包 | 本地 API / 前端技术验证；远程库等待 005 迁移 | [阶段十三记录](./2026-09-09-stage-13-public-policy-grounding.md) |
| 2026-09-09 | Manual vs Agent v0.2 结果复盘 | 匿名 CSV 已核验；描述性结果已记录 | [阶段十二记录](./2026-09-09-stage-12-manual-agent-results.md) |
| 2026-09-09 | Manual vs Agent 重新设计 | v0.2 本地规则与导出格式技术验证 | [阶段十一记录](./2026-09-09-stage-11-manual-agent-study-redesign.md) |
| 2026-09-09 | Manual vs Agent 实验运行页 | 本地匿名运行与导出格式技术验证 | [阶段十记录](./2026-09-09-stage-10-manual-agent-runner.md) |
| 2026-09-09 | Manual vs Agent 招募前执行准备 | 本地匿名分配与执行说明技术验证 | [阶段九记录](./2026-09-09-stage-09-manual-agent-recruitment-prep.md) |
| 2026-09-09 | 图片 Evidence 文件链路 | 本地与 Supabase 开发库技术验证 | [阶段八记录](./2026-09-09-stage-08-evidence-file-chain.md) |
| 2026-09-09 | Manual vs Agent 实验准备 | 本地任务协议技术验证 | [阶段七记录](./2026-09-09-stage-07-manual-agent-study-preparation.md) |
| 2026-09-09 | Policy 检索回归发布闸门 | 本地与 Supabase 开发库技术验证 | [阶段六记录](./2026-09-09-stage-06-policy-regression-gate.md) |
| 2026-09-09 | 自构造 Query–Policy 检索基线 | 本地与 Supabase 开发库技术验证 | [阶段五记录](./2026-09-09-stage-05-self-authored-policy-retrieval.md) |
| 2026-09-09 | 冻结 Case 可执行契约 | 本地与 Supabase 开发库技术验证 | [阶段四记录](./2026-09-09-stage-04-frozen-case-contracts.md) |
| 2026-09-09 | Supabase 数据层准备 | Supabase 开发库已验证 | [阶段三记录](./2026-09-09-stage-03-supabase-schema-preparation.md) |
| 2026-09-09 | 冻结评测集 v0.2 | 本地技术验证 | [阶段二记录](./2026-09-09-stage-02-frozen-eval-fixtures.md) |
| 2026-09-09 | Agent Ops 与 Admin 闭环 | 本地原型 / 技术验证 | [阶段一记录](./2026-09-09-stage-01-ops-admin-evaluation.md) |
| 2026-09-10 | Supabase Auth、三端分权与中文界面 | 待 Supabase 迁移后的真实登录验收 | [阶段十五记录](./2026-09-10-stage-15-supabase-auth-rbac.md) |
| 2026-09-10 | 真实 DeepSeek 视觉与决策 Agent 烟测 | 脱敏技术验证完成；高风险人工审批仍待专门的真实视觉样本验证 | [阶段十六记录](./2026-09-10-stage-16-real-agent-smoke.md) |
| 2026-09-11 | 真实视觉冻结集 v0.2 | 20 张图片已冻结并接入真实评测；待项目负责人授权执行真实模型评测 | [阶段十七记录](./2026-09-11-stage-17-real-vision-fixture.md) |
| 2026-09-11 | 真实模型冻结评测 v0.2 | 9 样本已实测；已记录坏例与工具轮次修复，待授权重跑 | [阶段十八记录](./2026-09-11-stage-18-real-evaluation-v02.md) |
| 2026-09-11 | 真实模型冻结评测 v0.2.1 | 12 样本真实实测；RAE-008 已恢复，但高风险验收 1/3，未满足封板 | [阶段十九记录](./2026-09-11-stage-19-real-evaluation-v021.md) |
| 2026-09-11 | 检索归一化与订单级 Evidence 复核 | 010 已执行；v0.2.2 真实评测完成，Policy 100%，配对图片观察 3/3 | [阶段二十记录](./2026-09-11-stage-20-evidence-retrieval-repair.md) |

## 后续追加规则

每个阶段新增一份独立文件，不覆盖历史记录；至少写明：目标、决策、实现、问题与解决方案、验证证据、交付边界、待补证据和下一步。指标必须标注为实测、技术验证、离线模拟或估算之一。
