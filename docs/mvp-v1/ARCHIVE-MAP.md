# CarePilot MVP1 归档地图

MVP1 不移动或删除历史源材料，以避免破坏已有链接、冻结输入和工作记录。本目录提供发布时的规范入口；下表记录每类证据的原始位置与用途。

| MVP1 主题 | 规范发布材料 | 原始证据 / 源文件 | 用途与边界 |
| --- | --- | --- | --- |
| 项目总览 | `docs/mvp-v1/README.md` | `README.md`、`PLAN.md` | 作品集版本定位，不替代历史计划 |
| 客服提效策略 | `03-portfolio-case-study.md` | `docs/客服提效-产品价值重构-v1.md`、`docs/worklog/2026-09-11-stage-21-product-value-reframe.md` | 产品主线与指标定义 |
| 真人实验结果 | `01-human-study-report-2026-09-12.md` | Supabase `customer_efficiency_*`；`evals/客服提效实验设计-v1.md` | 真人参与者 + 自构造模拟任务；非生产收益 |
| 实验只读复核 | `evidence/01-human-study-snapshot.sql` | `data/011_customer_efficiency_study.sql`、`apps/api/app/public_efficiency.py` | 指标计算与完整性核验 |
| 真实 Agent 技术证据 | `04-release-decision.md` | `docs/worklog/2026-09-11-stage-20-evidence-retrieval-repair.md`、`evals/fixtures/real-agent-eval-v0.2.2.json` | 固定模型/Prompt/政策快照下的技术运行 |
| 安全与状态边界 | `03-portfolio-case-study.md` | `PLAN.md`、`apps/api/app/domain.py`、`apps/api/tests/test_ticket_flow.py` | 规则控制业务动作，模型不越权 |
| 公开部署 | `04-release-decision.md` | `docs/公网实验部署说明.md`、`render.yaml`、`netlify.toml` | Netlify/Render/Supabase，密钥仅服务端 |
| Demo 录制 | `02-demo-script.md` | `apps/web/app/page.tsx`、`apps/web/app/consumer/page.tsx`、`apps/web/app/evaluation/page.tsx` | 录制路线与不应展示的内容 |
| 项目学习与面试 | 根目录 `导学-CarePilot.md`、`面经-CarePilot.md` | 全仓库 | 仅作准备材料；个人职责须按真实分工确认 |

## 历史材料规则

- `docs/worklog/` 为追加式历史记录；不因 MVP1 结论删除早期计划、失败或试跑记录。
- `evals/fixtures/` 中已冻结的输入不改语义；新问题、新样本或新协议必须新建版本。
- `evals/manual-agent-*` 和 v0.2 结果为历史探索材料，不能与 v1 真人实验合并计算。
- `docs/mvp-v2/` 是所有后续实质性工作的唯一文档入口。
