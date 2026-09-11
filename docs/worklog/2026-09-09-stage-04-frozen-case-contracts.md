# 阶段四工作记录：冻结 Case 可执行契约

- 记录日期：2026-09-09
- 对应计划：`PLAN.md` 的冻结评测集与异常测试前置验证
- 交付阶段：**固定模拟输入与期望结果的技术验证**；不是真实模型、图片 Evidence 或 Policy RAG 评测

## 1. 目标

让 `tickets-v0.2.json` 中每条 Case 的 `expected_disposition`、`expected_state` 和 `proposal` 由可执行规则校验，而非只作为页面汇总指标的静态标签。

## 2. 决策与取舍

| 决策 | 采用方式 | 未采用方式 | 原因 |
| --- | --- | --- | --- |
| 期望结果来源 | 后端确定性 Case oracle | 让模型生成期望答案 | 冻结集的预期必须可复跑，不能依赖模型波动 |
| 覆盖范围 | 常规高 / 中 / 低风险及四类异常 | 假称 80 条均已跑过真实 Agent | 当前真实 API 仅有三条演示工单，RAG、图片和异常 Tool 尚未实现 |
| 异常分布 | 四类异常各 3 条的强校验 | 只检查异常总数不少于 12 | 防止某个异常类别被悄然删失 |

## 3. 实现

- 在 `apps/api/app/domain.py` 新增 `expected_frozen_case_outcome` 与 `validate_frozen_case_contracts`。
- 常规 Case 的高 / 中 / 低风险分别要求人工审批 / 补充材料 / 自动解决；工具超时、提示注入、重复请求和政策冲突覆盖失败转人工、阻断、幂等拒绝和人工审核。
- `frozen_evaluation_fixture()` 会在 API 启动与 Eval 运行前逐条校验 80 条 Case。
- 自动化测试新增 80 条契约与四类异常各 3 条的覆盖断言；原有 API 测试继续覆盖低风险 Tool 链、高风险人工批准、补材料再处理与重复请求拒绝。

## 4. 验证证据

| 检查 | 结果 | 性质 |
| --- | --- | --- |
| `apps/api/.venv/bin/python -m unittest discover -s tests -v` | 8 / 8 通过 | 本地 API 与 fixture 回归验证 |
| Supabase 进程内 API 启动 | `/health` 为 `database-url`；v0.2、80 条快照可读取 | 远程开发库技术验证 |

## 5. 责任与边界

- 本阶段只证明自构造冻结输入与预期处置标签内部一致，且能够在本地和 Supabase 启动期被拒绝错误配置。
- 它不证明 Agent 对真实用户输入、实际图片、真实政策检索、Tool 超时重试或提示注入的效果。
- Policy Top-3 仍来自 fixture 固定标注；在有 60 条 Query–Policy 标注和真实检索实现前，不可称为检索效果实测。

## 6. 下一步

1. 建立 60 条 Query–Policy 标注集，并把 Top-3 从固定字段改为检索结果的离线测量。
2. 建立合法来源的 Evidence 测试图与文件处理链路；在此之前 `has_image` 仍只是测试路径标志。
3. 定义 20 条 Manual vs Agent 任务的原子步骤与记录表，再决定真人测试安排。
