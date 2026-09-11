# 阶段六工作记录：Policy 检索回归发布闸门

- 记录日期：2026-09-09
- 对应计划：`PLAN.md` 的 Policy 回归、人工发布与失败保护
- 交付阶段：**本地与 Supabase 开发库的发布闸门已验证**；不是完整 Policy RAG 或真实政策发布

## 1. 目标

让 Policy Candidate 的回归结果基于当前 60 条自构造 Query–Policy 检索快照决定，而不是无条件写入 `PASSED`；未达到计划规定的 90% Top-3 门槛时必须阻止人工发布。

## 2. 实现

- `run_policy_regression()` 现在读取 `policy_retrieval_snapshot()`，按 90.0% Top-3 门槛写入 `PASSED` 或 `FAILED`。
- 回归摘要记录命中数、总问句数、命中率和发布门槛；审计事件区分 `policy.regression_passed` 与 `policy.regression_failed`。
- 新增 `data/003_allow_failed_policy_regressions.sql`，将远程 `policy_regression_runs.status` 的允许值扩展为 `PENDING / PASSED / FAILED`，不删除或重写任何记录。
- 新增测试：模拟 80.0% Top-3 时，Candidate 回归为 `FAILED` 且 Publish 返回 409。

## 3. 验证证据

| 检查 | 结果 | 性质 |
| --- | --- | --- |
| `apps/api/.venv/bin/python -m unittest discover -s tests -v` | 11 / 11 通过 | 本地 Policy 发布闸门与 API 回归验证 |
| 100.0% 自构造基线 | Policy regression 为 `PASSED` | 同源自构造关键词基线 |
| 80.0% 模拟检索结果 | Policy regression 为 `FAILED`，发布被 409 拦截 | 本地失败路径验证 |
| Supabase 正常回归 | 隔离 Candidate `v3.3` 以 60 / 60、100.0% 写入 `PASSED` | 远程开发库中的同源自构造关键词基线 |
| Supabase `FAILED` 持久化 | 写入一条明确标注“受控验证”的 `FAILED` 记录成功；`POST /publish` 返回 409 | 远程 schema 与发布拦截技术验证 |

## 4. 责任与边界

- 该闸门只处理自构造检索基线，100.0% 或阈值通过均不可表述为真实政策质量。
- 尚未实现 Candidate 政策正文解析、真实来源同步、BM25、向量索引、Reranker 或多版本检索对照。
- Policy 发布仍使用演示 reviewer 字符串；真实身份和角色映射是后续安全工作。
- 远程 `v3.3` 是为验证而保留的失败 Candidate，最新回归为“受控验证”记录；它不代表真实检索失败。Active 仍为 `v3.2`，未发生发布或覆盖。

## 5. 下一步

1. Evidence 文件处理已完成本地与 Supabase 开发库的模拟验证；真实图片接入仍需独立 Storage、鉴权与生命周期设计。
2. 在招募参与者前，按 `evals/manual-agent-study-v0.1.md` 审阅知情边界和交叉平衡安排。
