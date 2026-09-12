# CarePilot 文档总索引

- 文档治理整理日期：2026-09-12
- 当前发布基线：[`carepilot-mvp1`](./mvp-v1/README.md)
- 原则：**历史运行、实验原始记录和冻结样本不改写；新增文档只补充索引、解释与后续追溯规则。**

## 先按用途阅读

| 想回答的问题 | 先读 | 证据等级 / 状态 |
| --- | --- | --- |
| CarePilot 为谁解决什么问题 | [根 README](../README.md)、[MVP1 PRD](./product/PRD-MVP1.md) | 当前产品规范 |
| MVP1 能公开说什么、不能说什么 | [MVP1 总览](./mvp-v1/README.md)、[发布决定](./mvp-v1/04-release-decision.md) | 冻结发布事实 |
| 为什么模型不直接执行权益动作 | [MVP1 PRD](./product/PRD-MVP1.md)、[作品集案例页](./mvp-v1/03-portfolio-case-study.md) | 当前实现与产品判断 |
| Prompt、模型、工具和策略如何演进 | [AI 文档入口](./ai/README.md)、[Prompt 版本台账](./ai/PROMPT-REGISTER.md)、[坏例台账](./ai/BADCASE-REGISTER.md) | 真实运行 / 明确的待验证项 |
| 一次修复或功能改动在哪里发生 | [可追溯性入口](./traceability/README.md)、[变更总台账](./traceability/CHANGE-REGISTER.md)、[阶段工作记录](./worklog/README.md) | 变更与验证记录 |
| 真人实验结果能如何解读 | [MVP1 真人实验报告](./mvp-v1/01-human-study-report-2026-09-12.md)、[实验设计](../evals/客服提效实验设计-v1.md) | 真人参与的自构造模拟任务 |
| 真实 Agent 是否实际运行过 | [Stage 16](./worklog/2026-09-10-stage-16-real-agent-smoke.md)、[Stage 18–20](./worklog/2026-09-11-stage-18-real-evaluation-v02.md) | `REAL_AGENT_RUN` 技术验证 |
| 如何运行、部署或迁移数据 | [真实 Agent 运行说明](./REAL_AGENT_SETUP.md)、[公开实验部署说明](./公网实验部署说明.md)、[数据迁移说明](../data/README.md) | 运维说明；密钥仅服务端 |
| 下一步能改什么 | [MVP2 入口](./mvp-v2/README.md) | 后续工作，不回写 MVP1 |

## 文档分层

### 当前规范

- [`product/PRD-MVP1.md`](./product/PRD-MVP1.md)：将已冻结的 MVP1 能力整理为可审阅 PRD；不把原始计划中的未实现项写成现状。
- [`ai/`](./ai/README.md)：真实 Prompt/配置版本、坏例、评测与后续版本规则。
- [`traceability/`](./traceability/README.md)：文档、工作记录与 Git 的映射。
- [`worklog/`](./worklog/README.md)：按阶段追加的决策、问题、修复、验证和边界。

### 冻结发布材料

`mvp-v1/` 是作品集发布基线：其中的人类实验、真实运行、数据口径和结论不得被新材料覆盖。对其进行说明性补充时，必须标明补充日期、不得改变原结论，并将任何实质性改动放入 `mvp-v2/`。

### 历史计划与研究材料

- [`PLAN.md`](../PLAN.md) 是原始范围和六周规划，其中 Redis、Multi-Agent、Reranker、语音等是历史计划项，不是 MVP1 已交付项。
- [`客服提效-产品价值重构-v1.md`](./客服提效-产品价值重构-v1.md) 与 [`客服提效实验设计-v1.md`](../evals/客服提效实验设计-v1.md) 保留协议和当时的判断；最终样本结论以 MVP1 实验报告为准。
- `导学-售后智策.md`、`面经-售后智策.md` 是 2026-09-11 快照；当前学习与面试材料使用根目录的 `导学-CarePilot.md`、`面经-CarePilot.md`。

## 证据标签

所有新文档、表格和简历表述应使用下列其中一种标签，不混用：

| 标签 | 含义 |
| --- | --- |
| `REAL_AGENT_RUN` | 真实服务端模型调用；保留模型、Prompt、输入输出、Tool、政策、成本等运行记录 |
| `真人模拟任务` | 真人参与者完成自构造、脱敏售后任务；不等于真实客服生产数据 |
| `离线固定 fixture` | 可复跑的自构造输入与规则契约；不等于模型或用户效果 |
| `技术验证` | 测试、构建、迁移或接口检查通过；不等于业务收益 |
| `计划 / 待验证` | 尚未运行或尚未达到结论门槛；不得写成结果 |

## 每次变更如何留痕

1. 先在 `docs/mvp-v2/` 或新的阶段工作记录写清问题、假设、范围、成功标准和失败边界。
2. 涉及 Prompt、模型、Tool、策略、样本或指标时，先更新 `ai/` 台账；Prompt 还必须记录内容哈希和冻结输入。
3. 发现异常、失败、回退或不确定结论时，新增或更新坏例台账；不能删除坏例来换取更高分。
4. 完成修改后，在工作记录中写明改动文件、验证命令/运行 ID、结果和仍然不能声称的结论。
5. 使用独立 Git 提交保存该批改动；变更总台账只链接可验证的工作记录和提交，不补造不可恢复的历史细节。
