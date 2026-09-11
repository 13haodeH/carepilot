# 阶段五工作记录：自构造 Query–Policy 检索基线

- 记录日期：2026-09-09
- 对应计划：`PLAN.md` 的 60 条 Query–Policy 标注与 Policy Top-3 离线测量前置工作
- 交付阶段：**自构造语料上的确定性离线检索技术验证**；不是 BM25、向量检索、Reranker、真实政策或真实用户效果

## 1. 目标

将 Evaluation 的 Policy Top-3 从 80 条工单 fixture 中的固定布尔标签，改为对版本化 Query–Policy 标注集执行实际检索后计算的结果。

## 2. 决策与取舍

| 决策 | 采用方式 | 未采用方式 | 原因 |
| --- | --- | --- | --- |
| 政策语料 | 12 条自构造、无真实条款的政策片段 | 把模拟 UI 文案包装为真实政策 | 当前仓库没有可授权、可标注的正式政策正文 |
| 标注集 | 60 条自构造问句、每条标注目标政策 ID，三品类各 20 条 | 只保留 `policy_top3_hit` 静态字段 | 需要逐条可追溯的检索输入与正确答案 |
| 检索器 | 品类路由后的关键词排序 | 声称已完成 BM25 / 向量 / Reranker | 先验证数据、标注与计算链路，避免夸大当前技术能力 |

## 3. 实现

- 新增 `evals/fixtures/policy-corpus-v0.1.json`：12 条自构造政策片段，数码 / 服饰 / 家居各 4 条。
- 新增 `evals/fixtures/query-policy-v0.1.json`：60 条自构造 Query–Policy 标注，数码 / 服饰 / 家居各 20 条。
- `apps/api/app/domain.py` 新增 corpus 与 annotation 校验、品类过滤后的关键词 Top-3 排序，以及 `policy_retrieval_snapshot()`。
- `offline_evaluation_snapshot()` 改为从该检索结果计算 `policy_top3_hit_rate`；80 条工单 fixture 的历史 `policy_top3_hit` 字段保留但不再参与当前指标计算。
- Evaluation 的 `source_note` 显式写明指标来自 60 条自构造问句和关键词基线。

## 4. 验证证据

| 检查 | 结果 | 性质 |
| --- | --- | --- |
| `apps/api/.venv/bin/python -m unittest discover -s tests -v` | 9 / 9 通过 | 本地 API、80 条 Case 与 60 条 Query–Policy 回归验证 |
| 60 条检索计算 | 60 / 60 的目标政策位于 Top-3，100.0% | 同源自构造语料上的确定性词项基线 |
| Supabase Eval Run | 运行 ID 2，Top-3 为 100.0%，最新快照包含自构造关键词基线说明 | 远程开发库技术验证 |

## 5. 责任与边界

- 项目负责人确认采用自构造、明确标注为模拟的政策语料。
- 100.0% 仅说明问句和政策片段共享受控关键词时，当前检索与标注链路一致；不能写成真实政策命中、模型效果或业务收益。
- 尚未实现公开政策采集、Policy Candidate 解析、BM25、向量索引、Reranker、语义泛化测试或政策冲突的真实检索处理。

## 6. 下一步

1. 为该自构造语料加入独立的候选版本与解析失败测试，再决定是否实现 BM25、向量检索与 Reranker。
2. 建立合法来源的 Evidence 测试图、文件限制和隐私处理链路；目前 `has_image` 仍只是固定 Case 标志。
3. 定义 20 条 Manual vs Agent 任务的原子步骤与记录表，再开展真人测试。
