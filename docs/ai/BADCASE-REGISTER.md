# 坏例、错误与修复台账

- 审计日期：2026-09-12
- 记录范围：仓库中已有工作记录明确记载的异常、限制与修复；不声称可还原未写入 Git 或工作记录的历史细节。
- 原则：坏例保留原始版本和结论。修复后必须新建评测/运行版本，不回写旧输入、运行或指标。

| ID | 问题与影响 | 处理层 | 决定 / 状态 | 可追溯证据 |
| --- | --- | --- | --- | --- |
| BC-001 | 仅在前端显示状态无法证明 Tool/状态真实发生，也不能可靠阻止重复写操作 | 状态机、事务与幂等 | 已处理：状态和 Tool 记录转入后端；重复处理返回 409 | [Stage 1 §3.2](../worklog/2026-09-09-stage-01-ops-admin-evaluation.md) |
| BC-002 | 高风险权益若只由 Prompt 限制，可能越过审批 | Permission/状态机 | 已处理：只有 Proposal，审批前无高风险 execute Tool | [Stage 1 §3.3](../worklog/2026-09-09-stage-01-ops-admin-evaluation.md)、[MVP1 发布决定](../mvp-v1/04-release-decision.md) |
| BC-003 | 硬编码、无 case 标签的 72 条离线输入不可复盘覆盖与异常 | fixture 契约 | 已处理：迁移到版本化 80 条 `tickets-v0.2.json`，保留历史快照 | [Stage 2](../worklog/2026-09-09-stage-02-frozen-eval-fixtures.md) |
| BC-004 | v0.1 实验把预设步骤当成完成门槛，污染实际信息操作记录 | 实验交互与 schema | 已处理：v0.2 只记录实际点击，旧 v0.1 记录不混入 | [Stage 11](../worklog/2026-09-09-stage-11-manual-agent-study-redesign.md) |
| BC-005 | 首次真实视觉上传触发 500；旧数据库 CHECK 不允许 `REAL_VISION_MODEL` | 数据库迁移 | 已处理：`009` 仅扩展允许值；历史记录不回填 | [Stage 16](../worklog/2026-09-10-stage-16-real-agent-smoke.md)、[`009` 迁移](../../data/009_real_vision_evidence_origin.sql) |
| BC-006 | 真实图片文件校验被记成 `fixture-simulation`，审计调用者错误 | 审计记录 | 已处理：后续 `evidence.validate` 记为 `real-agent`；已发生记录保留原样 | [Stage 16](../worklog/2026-09-10-stage-16-real-agent-smoke.md) |
| BC-007 | `RAE-008` 在旧的 4 轮 Tool 上限处失败，工单进入 `FAILED` | Agent tool loop | 已处理：上限改为 8，增加重复成功调用约束；v0.2.1 中该 case 恢复 | [Stage 18](../worklog/2026-09-11-stage-18-real-evaluation-v02.md)、[Stage 19](../worklog/2026-09-11-stage-19-real-evaluation-v021.md) |
| BC-008 | `HRA-003` 等 case 因字面关键词匹配而未获得可用政策 citation | 检索与 Tool 上下文 | 已处理：有限同义词归一化与订单品类约束；v0.2.2 Policy Retrieval 为 100% | [Stage 20](../worklog/2026-09-11-stage-20-evidence-retrieval-repair.md) |
| BC-009 | 图片复核指标混入 `review_reason` 文字；订单—图片不匹配被误判为视觉准确率问题 | Evidence 评测与门禁 | 已处理：分离模型原始复核、订单级充分性与最终门禁原因；旧指标保留为 legacy | [Stage 20](../worklog/2026-09-11-stage-20-evidence-retrieval-repair.md) |
| BC-010 | `HRA-P-002` 单张图片无法证明包装内容完整，模型要求人工复核 | 证据充分性 | **保留未解决**：不改 Prompt 强行通过；MVP2 需新建完整可见包装样本 | [Stage 20](../worklog/2026-09-11-stage-20-evidence-retrieval-repair.md)、[MVP1 发布决定 §6](../mvp-v1/04-release-decision.md) |
| BC-011 | 公开实验的墙钟时长可能包含离开页面，不能代表连续作答/客服处理时间 | 实验测量 | **限制保留**：原始值不回填、不用作提效结论；未来新协议再解决 | [Stage 24](../worklog/2026-09-12-stage-24-efficiency-formal-pilot-review.md)、[真人实验报告](../mvp-v1/01-human-study-report-2026-09-12.md) |
| BC-012 | 公开匿名实验若固定 P01–P08 或只靠前端去重，无法持续平衡且易重复计入 | 服务端分题与数据库约束 | 已处理：匿名 ID、动态 3/3 分配、任务均衡和 `(participant_id, task_id)` 去重 | [Stage 23](../worklog/2026-09-11-stage-23-public-efficiency-study.md)、[部署说明](../公网实验部署说明.md) |
| BC-013 | 登录/注册按钮未提交，Web Supabase 公开配置过期；预置脚本不更新已有账号密码 | 鉴权界面与预置脚本 | 已处理：修正提交属性/公开配置；真实角色登录已验证 | [Stage 19](../worklog/2026-09-11-stage-19-real-evaluation-v021.md) |
| BC-014 | 早期通用 UI lint 有 18 项既有警告，未在阶段一业务改动中处理 | 工程卫生 | 历史已知项；本次文档审计未重新验证当前状态，不把它写成已修复 | [Stage 1 §3.7](../worklog/2026-09-09-stage-01-ops-admin-evaluation.md) |

## 使用方式

- 新问题先新增 ID，再决定是 Prompt、检索、Tool、规则、数据、交互还是测量问题；不要预设“改 Prompt”是唯一答案。
- `已处理` 必须有后续测试、运行 ID 或明确验证；只有设计方案时写 `待验证`。
- `保留未解决` 也是有效结论。它应进入 MVP2 的新版本，而不是在 MVP1 中重写坏例。
- 每条涉及模型行为的记录都要同时更新 [Prompt 版本台账](./PROMPT-REGISTER.md) 或说明为何与 Prompt 无关。
