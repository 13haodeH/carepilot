# 阶段二工作记录：冻结评测集 v0.2

- 记录日期：2026-09-09
- 对应计划：`PLAN.md` 的“冻结评测集”与第 5 周 Eval Dashboard 前置数据
- 交付阶段：**本地技术验证**；不是真人可用性实验、生产评测或线上业务实验

## 1. 问题背景

阶段一的 Evaluation 使用代码内 72 条分段数据生成汇总指标。它可以证明页面、API 和指标计算链路可运行，但不能逐条说明：每个样本属于什么品类、是否包含图片路径、风险等级、预期状态、异常类型和人工改写标注。因此既不满足计划中 80 条冻结集的结构要求，也无法为后续 Bad Case、异常测试和架构对照提供稳定输入。

## 2. 方案决策

将离线评测输入从 `domain.py` 中的硬编码分段迁移到版本化 JSON：`evals/fixtures/tickets-v0.2.json`。每条记录保存稳定 ID、品类、场景、风险、模拟图片路径标志、异常标签、预期处置、预期状态、Proposal 与模拟评测标注。

采用“新建 v0.2 而不覆写 v0.1 运行结果”的方式：已有 72 条历史快照继续留在本地数据库；启动新版 API 后，自动登记新的 v0.2 快照，最新接口返回 v0.2。

## 3. 实现与问题解决

| 问题 | 解决方案 | 可追溯位置 |
| --- | --- | --- |
| 72 条分段数据没有 Case 级标签 | 新增 80 条独立固定 Case 与字段说明 | `evals/fixtures/tickets-v0.2.json`、`evals/README.md` |
| 评测输入可能在不知情情况下被破坏 | 后端运行前校验总量、唯一 ID、32 / 24 / 24 品类、至少 20 图片路径、至少 20 高风险、至少 12 异常 | `apps/api/app/domain.py` 的 `frozen_evaluation_fixture` |
| 汇总指标无法说明其样本覆盖 | API 返回 `fixture_coverage`，Evaluation 页面展示品类、图片路径、高风险与异常数量 | `apps/api/app/main.py`、`apps/web/app/evaluation/page.tsx` |
| 旧快照会掩盖新版基线 | API 启动时检查当前 `fixture_set` 是否已有快照；缺失时新增 v0.2 | `apps/api/app/domain.py` 的 `seed` |

## 4. 冻结集范围

| 维度 | v0.2 结果 | 证据性质 |
| --- | --- | --- |
| 总样本 | 80 | 固定模拟数据 |
| 数码 / 服饰 / 家居 | 32 / 24 / 24 | 固定模拟数据 |
| `has_image: true` | 36 | 模拟图片路径标注，不是 36 个真实图片文件 |
| 高风险 Proposal 场景 | 20 | 固定模拟数据 |
| 异常场景 | 12 | 政策冲突、Tool 超时、重复请求、提示注入各 3 条 |
| 人工改写 Proposal 标注 | 13 | 离线模拟标注 |

## 5. 运行结果与验证

- 自动化测试：`python -m unittest discover -s tests -v`，6 项通过。
- 前端构建：`npm run build` 通过，`/evaluation` 路由保持可用。
- 本地 API：`GET /api/evaluations/latest` 返回 `synthetic-ticket-set-v0.2`、80 条样本及覆盖统计。
- 本轮模拟快照：Manual / Agent 平均时长 14.4m / 4.8m，Policy Top-3 95.0%，Tool 失败率 0.9%，P95 1.9s，平均成本 $0.0179。

这些数值是从固定模拟标签和风险级别计算出的技术验证基线，不是 5 人测试、真实模型评测或线上经营结果。

## 6. 责任与交付边界

- 项目负责人确定了 80 条、三品类分布和异常覆盖的验收目标，以及不将模拟数据包装为线上效果的边界。
- 本阶段在 AI 辅助下完成 fixture 文件、加载校验、API / UI 接入与本地验证。
- 未完成：30 张真实 / 合法来源的 Evidence 测试图、60 条 Query–Policy 标注、20 条 Manual vs Agent 任务、5 人实验、模型 / Prompt 冻结与 A / B / C 架构对照。

## 7. 下一步与待补证据

1. 为 80 条 Case 增加可执行的单条预期断言，先覆盖现有状态机、幂等和高风险审批路径。
2. 建立 60 条 Query–Policy 标注集，并把 Policy Top-3 从固定标注改为检索结果的离线测量。
3. 建立合法来源的图片 Evidence 集与文件处理链路；在此之前，`has_image` 只能代表待接入的测试路径。
4. 定义 20 条 Manual vs Agent 任务的原子步骤和记录表，再开展真人测试。

## 可追溯入口

- [冻结集说明](../../evals/README.md)
- [80 条固定 Case](../../evals/fixtures/tickets-v0.2.json)
- [离线评测加载与校验](../../apps/api/app/domain.py)
- [API 输出](../../apps/api/app/main.py)
- [Evaluation 页面](../../apps/web/app/evaluation/page.tsx)
