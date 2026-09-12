# CarePilot（售后智策）项目计划书

> 文档状态：这是项目早期的范围与六周规划，保留用于回溯原始取舍。它列出的 Redis、RQ、Multi-Agent、Reranker、语音等不等于 MVP1 已实现能力；当前冻结产品范围与可公开结论以 [`docs/mvp-v1/README.md`](docs/mvp-v1/README.md) 和 [`docs/product/PRD-MVP1.md`](docs/product/PRD-MVP1.md) 为准，后续变更从 [`docs/mvp-v2/`](docs/mvp-v2/README.md) 开始。

## 一、项目目标与产品范围

### 1. 项目名称

**CarePilot（售后智策）｜电商售后 Agent 协同处置工作台**

暂不使用“通用 Agent 平台”作为主要名称；只有 Agent 配置、版本、权限和多个品类真正实现后，才在技术说明中称为“平台能力”。

### 2. 一句话定位

CarePilot 面向电商客服团队，通过 Agent 串联订单、物流、政策、工单和通知系统，自动完成信息核验、材料补充与低风险操作，并将退款、换货、补偿等高风险动作提交人工审批，减少客服在多个系统之间的重复操作。

### 3. 核心问题

传统客服处理一笔售后工单，需要人工完成：

1. 理解用户问题。
2. 查找订单。
3. 查询物流。
4. 核对商品和售后时限。
5. 要求用户补充材料。
6. 检索适用政策。
7. 判断处理方案。
8. 创建或更新工单。
9. 通知用户。
10. 记录处理结果。

CarePilot 的目标不是“回答得更像客服”，而是验证：

> Agent 能否把一笔售后工单从提交推进到解决，并减少人工查询、复制、切换系统和重复录入的步骤。

这一定位对应当前 AI 产品岗位对企业工作流识别、Agentic Workflow、工具调用、沙盒实验和效果指标的要求。[百度企业效能 AI 产品经理](https://talent.baidu.com/jobs/detail/SOCIAL/645aeeb5-f2a7-4df3-b13c-d90a6006aac3)、[百度电商 Agent 产品经理](https://talent.baidu.com/jobs/detail/SOCIAL/bfc48fb5-5eee-46b7-a03f-5e8529b49277)

### 4. 与 Wayly 的组合关系

- Wayly：面向消费者的 AI 决策产品，优化推荐方案和用户决策体验。
- CarePilot：面向企业客服的 Agent 流程产品，优化工单处理效率和人机协作。

CarePilot 的核心产物必须是：

- 工单状态发生变化。
- 业务 Tool 被真实调用。
- 低风险动作被执行。
- 高风险动作进入审批。
- 每一步形成可核验的 Audit Trace。

不能只生成一段“建议客服怎么处理”的文字。

### 5. MVP 与 P1 边界

MVP 包含：

- Consumer、Agent Ops、Admin 三端。
- 文字投诉和图片证据。
- 订单、物流、政策、工单、通知等模拟业务 Tool。
- 单 Agent 工作流。
- Human-in-the-loop。
- Permission/Risk Engine。
- Policy RAG。
- 自动政策同步与人工发布。
- Redis 状态、缓存、幂等和任务队列。
- Agent Config。
- Multi-Agent 对照实验。
- 业务效率和 AI 效果评测。
- Figma 高保真原型与线上 Demo。

P1 包含：

- 按键录音、语音转写和语音播报。
- 更复杂的品类配置。
- 更完善的监控和运营分析。

明确不做：

- 实时电话客服、WebRTC 双工语音和呼叫中心集成。
- 真实支付、退款、库存和电商生产系统写入。
- 无人审核的政策自动发布。
- 任意行业、任意节点的低代码 Agent Builder。
- Agent 动态创建其他 Agent。
- 声音克隆、图片欺诈定性。
- 真实客户隐私数据。

## 二、产品设计与核心业务闭环

### 1. 目标用户

- 消费者：提交售后问题、上传证据、补充信息、查看处理结果。
- 客服：处理需要人工判断的工单，审批或修改 Agent 建议。
- 售后运营管理员：维护政策和 Agent 配置、查看指标和失败案例。

### 2. 代表业务场景

重点打磨两条旗舰流程。

#### 场景 A：物流延迟——低风险自动闭环

用户投诉物流长时间未更新：

1. Intake 识别订单和物流诉求。
2. Order Tool 查询订单。
3. Logistics Tool 查询节点。
4. Policy Tool 检索物流异常说明。
5. Agent 生成带依据的解释。
6. Permission Engine 判定为低风险。
7. 自动更新工单并通知用户。
8. 工单进入 `RESOLVED`。

该场景证明 Agent 能真正自动完成部分工单。

#### 场景 B：商品破损或配件缺失——高风险人机协同

用户反馈耳机配件缺失或商品破损：

1. Agent 查询订单和签收时间。
2. 用户上传商品及包装图片。
3. Evidence 模块提取损坏、配件、包装等可见信息。
4. Policy RAG 检索适用品类和时限。
5. Agent 形成换货或补充材料方案。
6. 创建 Action Proposal。
7. Permission Engine 判定需要人工审批。
8. 客服执行 `Approve / Modify / Reject / Take Over`。
9. 工单 Tool 更新状态并通知用户。

该场景证明多模态 Evidence、政策依据和 Human-in-the-loop。

评测数据同时覆盖数码、服饰和家居，但作品集演示以这两条流程为主。

### 3. 工单状态机

核心状态：

- `NEW`
- `PROCESSING`
- `NEED_INFO`
- `WAITING_REVIEW`
- `RESOLVED`
- `FAILED`

允许的主要变化：

```text
NEW → PROCESSING
PROCESSING → NEED_INFO / WAITING_REVIEW / RESOLVED / FAILED
NEED_INFO → PROCESSING
WAITING_REVIEW → PROCESSING / RESOLVED
FAILED → PROCESSING
```

Agent 只能提出状态变化，后端状态机负责校验。非法跳转必须被拒绝并写入审计日志。

### 4. Tool Calling

Read Tools：

- `order.lookup`
- `logistics.track`
- `policy.search`
- `ticket.history`
- `evidence.read`

Write Tools：

- `ticket.create`
- `ticket.update`
- `task.create`
- `customer.notify`
- `human.assign`

高风险 Proposal：

- `refund.propose`
- `return.propose`
- `replace.propose`
- `compensation.propose`

高风险 Proposal 在 MVP 中只能进入人工审批，不能直接连接执行工具。

每次调用保存：

- Tool 名称和版本。
- 输入参数摘要。
- 调用者和工单。
- 开始与结束时间。
- 成功、失败或超时。
- 返回结果摘要。
- 幂等键。
- 对工单状态的影响。

### 5. Permission/Risk Engine

确定性输出：

- `AUTO_EXECUTE`
- `REQUIRE_HUMAN`
- `BLOCK`

默认规则：

- 查询信息、请求补图、工单分类：`AUTO_EXECUTE`
- 发送有政策依据的普通解释：`AUTO_EXECUTE`
- 退款、换货、退货、补偿：`REQUIRE_HUMAN`
- 修改库存、支付、用户权益或调用未知 Tool：`BLOCK`
- 政策冲突、证据不足、模型低置信度：`REQUIRE_HUMAN`

该模块是 Agent 进入业务流程的基础设施，不作为作品集首页的主要卖点。

### 6. 三端产品

#### Consumer

- 选择模拟订单。
- 文字描述问题。
- 上传最多 4 张图片。
- 查看需要补充的材料。
- 查看工单状态和处理结果。
- 对处理体验进行评价。

#### Agent Ops——Hero Screen

- 左侧：工单队列、风险和状态筛选。
- 中间：用户诉求、订单、物流、Evidence、Policy Citation、Agent Proposal。
- 右侧：风险等级、执行决策、Approve、Modify、Reject、Take Over。
- 底部：Agent Timeline、Tool Calls、状态变化和 Audit Trace。

消费者聊天页不能成为作品集主视觉。

#### Admin

- 政策来源、版本、同步结果、差异和发布。
- Prompt、模型、Tool 白名单、风险规则配置。
- 沙盒运行、版本发布和回滚。
- 业务指标、AI 指标、Bad Case 和基线对照。

### 7. Figma 设计

Figma 是正式交付物。当前 AI 产品岗位也明确要求 PRD、原型、Figma 和 Bad Case 分析能力。[百度 AI 产品经理实习生](https://talent.baidu.com/jobs/detail/INTERN/0ad545f8-07df-42f1-9a10-28e79d5dc407)

Figma 文件包含：

- `00-Cover`
- `01-Foundations`
- `02-Components`
- `03-Consumer`
- `04-Agent Ops`
- `05-Policy Admin`
- `06-Agent Config`
- `07-Evaluation`
- `08-Prototype`

必须使用 Variables、Auto Layout 和组件变体，打通：

1. 物流延迟自动处置。
2. 图片证据不足并请求补充。
3. 商品破损进入人工审批。
4. 客服修改 Agent Proposal。
5. 政策同步、回归和发布。
6. Agent 配置沙盒测试与版本激活。

进入高保真开发前，Figma 六条流程必须无断链，并完成逐屏截图检查。

## 三、实现架构与接口

### 1. 项目结构

新建独立仓库：

`/Users/jacob/Desktop/秋招/carepilot`

建议结构：

- `apps/web`：React、Vite、TypeScript、Tailwind。
- `apps/api`：FastAPI、Pydantic、SQLAlchemy。
- `workers`：政策同步、评测和异步任务。
- `evals`：冻结数据、标注、运行配置和结果。
- `docs`：PRD、Figma、架构、实验和发布证据。

不得修改 Wayly MVP1 的冻结资料，也不得复制 Wayly 的 `.env.local`。新项目只提交 `.env.example`。

### 2. 数据与运行组件

- PostgreSQL/Supabase：工单、状态、配置版本、Tool 记录、审批、审计和评测结果。
- Supabase Storage：图片证据。
- Redis：
  - 工作流短期状态，TTL 24 小时。
  - Tool 查询缓存，TTL 5–30 分钟。
  - 幂等记录，TTL 24 小时。
  - 请求限流。
  - 后台任务队列。
- RQ Worker：政策同步和批量评测。
- LangGraph：Agent Workflow 和状态编排。
- BM25 + 向量召回 + Reranker：政策检索。
- 所有正式 Eval 固定模型、Prompt、政策、配置和数据版本。

PostgreSQL 是最终事实源；最终动作、审批和审计不能只保存在 Redis。

### 3. Agent 架构实验

实现三个可切换版本：

- A：Prompt-only Agent。
- B：Single Agent + RAG + Tools。
- C：Multi-Agent + RAG + Tools。

C 版本固定为：

- Intake Agent：意图、订单、诉求和缺失字段。
- Evidence Agent：图片信息结构化。
- Policy Agent：政策检索和引用。
- Resolution Agent：方案和解释。
- Supervisor：按固定状态调度。

Permission Engine 不属于 Agent。

最终默认架构由评测决定。若 Single Agent 更稳定、更便宜，则采用 B，多 Agent 只保留为实验结果。

### 4. 图片 Evidence

允许 JPG、PNG、WebP，每张不超过 8 MB，单工单最多 4 张。

结构化输出：

- `evidence_type`
- `damage_type`
- `damage_location`
- `packaging_status`
- `missing_parts`
- `label_match`
- `image_quality`
- `confidence`
- `needs_human_review`

图片模型只能描述可见信息，不得直接决定退款资格或给用户贴欺诈标签。

安全要求：

- MIME 和大小检查。
- 移除 EXIF。
- 使用签名 URL。
- 地址和电话脱敏。
- 模糊、无关或低置信度图片转人工或要求补拍。

### 5. Policy RAG 与自动同步

MVP 支持：

- 公开且允许访问的 HTML 页面。
- 管理员上传 PDF/Markdown。

同步流程：

```text
定时/人工同步
→ 校验和检测
→ 生成 Candidate
→ 解析与分块
→ 差异对比
→ 重新建立检索索引
→ 受影响用例回归
→ 管理员发布
→ Active
```

默认每日北京时间 02:00 检查公开来源。

任何新政策都不能自动覆盖 Active 版本。解析失败、回归失败或管理员未批准时，继续使用旧政策。

### 6. Agent Config

仅支持：

- Prompt 和模型版本。
- Tool 白名单。
- 品类及问题类型。
- 路由条件。
- 风险规则。
- 配置草稿、沙盒测试、发布和回滚。

不提供拖拽任意工作流、动态代码和第三方 Tool 市场。

### 7. 主要接口

工单：

- `POST /api/tickets`
- `GET /api/tickets/{id}`
- `POST /api/tickets/{id}/process`
- `POST /api/tickets/{id}/submit-evidence`
- `POST /api/tickets/{id}/review`
- `POST /api/tickets/{id}/take-over`

政策：

- `POST /api/policy-sources`
- `POST /api/policy-sources/{id}/sync`
- `GET /api/policy-versions/{id}/diff`
- `POST /api/policy-versions/{id}/publish`
- `POST /api/policy-versions/{id}/rollback`

Agent 配置与评测：

- `POST /api/agent-configs`
- `POST /api/agent-configs/{id}/sandbox`
- `POST /api/agent-configs/{id}/activate`
- `POST /api/eval-runs`
- `GET /api/eval-runs/{id}`

核心实体：

- `Ticket`
- `Evidence`
- `ActionProposal`
- `ToolExecution`
- `HumanReview`
- `AuditEvent`
- `PolicySource`
- `PolicyVersion`
- `AgentConfigVersion`
- `EvalRun`

## 四、指标、实验与验收

### 1. 指标分层

#### 第一层：业务流程指标

作品集首页优先展示：

- 工单端到端完成率。
- 可自动完成的工单步骤比例。
- 每单平均人工操作步骤数。
- Human Handoff Rate。
- Agent Proposal 人工修改率。
- 工单信息补全率。
- 自动执行成功率。
- 平均处理时间。

#### 第二层：AI 诊断指标

- Retrieval Error。
- Reasoning Error。
- Evidence Error。
- Tool Selection Error。
- Tool Execution Error。
- Permission Error。
- Policy Conflict。
- Human Handoff Error。

#### 第三层：系统指标

- P50/P95 Latency。
- 单工单模型调用次数。
- 单工单估算成本。
- Tool 超时率。
- 后台任务失败率。

### 2. 冻结评测集

建立 80 条模拟工单：

- 数码 32 条。
- 服饰 24 条。
- 家居 24 条。
- 至少 20 条包含图片。
- 至少 20 条涉及高风险 Proposal。
- 至少 12 条包含政策冲突、工具失败、重复请求或提示注入。

另建立：

- 60 条 Query—Policy 标注。
- 30 张图片 Evidence 测试集。
- 20 条 Manual vs Agent 对照任务。

只使用自行构造、获得授权或许可明确的数据，保存来源和生成说明。

### 3. Manual vs Agent 实验

先定义统一的人工原子步骤，例如查询订单、查询物流、检索政策、补充材料、创建任务、修改状态和通知用户。

邀请 5 名参与者，分别完成匹配难度的 Manual Workflow 和 Agent-assisted Workflow，并交叉调整完成顺序，减少学习效应。

记录：

- 人工操作步骤数。
- 完成时间。
- 工单处理正确性。
- 是否需要修改 Agent Proposal。
- 单题易用性评分。
- 关键操作问题。

实验目标：

- 人工步骤中位数下降至少 30%。
- 处理时间中位数下降至少 20%。

这些是待验证目标，不得提前写成简历结果；5 人测试只作为作品集实验，不外推为企业真实收益。

### 4. 发布门槛

- 合法状态转换率：100%。
- Audit Trace 完整率：100%。
- 高风险动作人工接管召回率：100%。
- 未授权 Tool 调用成功次数：0。
- 退款、换货、补偿自动执行次数：0。
- 重复请求产生重复动作次数：0。
- 低风险 Tool 执行成功率：不低于 95%。
- Tool 选择准确率：不低于 95%。
- Policy Top 3 命中率：不低于 90%。
- 图片关键字段准确率：不低于 90%。
- 端到端工单完成率：不低于 90%。
- 未审核政策自动生效次数：0。

Multi-Agent 成为默认配置的额外条件：

- 相比 B 版本，处置决策准确率提升至少 3 个百分点。
- 所有安全指标不下降。
- 单工单平均模型成本增幅不超过 50%。

不满足时默认使用 Single Agent，并把结果写成一次有效的架构取舍实验。

### 5. 异常测试

必须覆盖：

- 订单不存在或订单不属于当前用户。
- 物流 Tool 超时。
- 图片模糊、无关或含敏感信息。
- 政策检索为空或多条政策冲突。
- Agent 尝试调用白名单外 Tool。
- 用户诱导系统直接退款。
- 同一请求重复提交。
- Redis 暂时不可用。
- 政策同步或解析失败。
- 人工审批期间政策版本改变。
- Agent 输出不符合 Schema。
- 通知失败但工单已更新。

异常发生时应保留工单、旧政策和审计记录，并进入重试或人工接管，不得静默完成。

## 五、六周实施计划与交付

### 第 1 周：业务拆解与 Figma

- 绘制 Manual Workflow、服务蓝图和角色权限矩阵。
- 定义两条旗舰场景、状态机、Tool 和指标口径。
- 完成 PRD、Figma 组件库和六条交互原型。
- 建立 80 条评测集框架和 20 条人工流程任务。

验证：Figma 无断链；所有页面能对应具体用户、状态和业务动作。

### 第 2 周：工单状态与 Single Agent 主链路

- 建立 Consumer、Agent Ops、Admin 基础页面。
- 实现订单、物流、工单和通知模拟 Tool。
- 实现工单状态机、Audit Trace 和 Single Agent。
- 跑通物流延迟自动处置。

验证：Tool 调用真实读写数据库；非法状态变化被拒绝。

### 第 3 周：Human-in-the-loop 与 Redis

- 实现 Action Proposal 和 Permission Engine。
- 实现客服审批、修改、拒绝和接管。
- 接入 Redis 状态、缓存、幂等、限流和 RQ。
- 跑通商品破损人工审批流程。

验证：任何高风险动作都不能绕过人工；重复请求不会重复执行。

### 第 4 周：图片、RAG 与政策管理

- 完成图片 Evidence 和隐私处理。
- 完成 BM25、向量召回、Reranker 和引用。
- 完成政策来源、同步、差异、回归、发布和回滚。
- 完成 Agent Config 沙盒。

验证：未审核政策无法生效；低质量图片会补充材料或转人工。

### 第 5 周：Multi-Agent 实验与体验优化

- 实现 A/B/C 三种配置。
- 完成 Eval Dashboard 和错误分类。
- 执行首轮冻结集评测。
- 开展 5 人 Manual vs Agent 可用性测试。
- 根据 Bad Case 优化工作流、Prompt、RAG 或规则。

验证：每次改动有失败原因、修改点和前后结果，不只展示最终高分。

### 第 6 周：冻结发布与求职材料

- 冻结数据、Prompt、模型、政策、配置和代码版本。
- 运行全部业务、AI、安全和异常测试。
- 部署线上 Demo。
- 录制 3–5 分钟演示视频。
- 完成项目说明、实验报告、失败分析和发布结论。
- 根据真实结果整理简历 Bullet 和面试证据链。

验证：所有简历数字均能追溯到运行 ID、原始数据、计算方法或用户测试记录。

### 最终交付物

- 线上三端 Demo。
- 公开 GitHub 仓库。
- Figma 高保真原型。
- PRD、用户流程、服务蓝图和权限矩阵。
- Agent Workflow 与系统架构图。
- Tool、状态机和接口文档。
- 80 条冻结工单及标注说明。
- A/B/C Agent 架构实验。
- Manual vs Agent 对照实验。
- AI、业务、安全和异常评测报告。
- Policy 版本与数据来源记录。
- Release Decision 和限制说明。
- 演示视频及作品集案例页。
- 经证据验证后的简历项目描述。

### 默认假设

- 项目周期为连续 6 周。
- 首版使用模拟电商数据和模拟业务 Tool，但必须产生真实持久化状态。
- 数码是旗舰演示品类，服饰和家居用于验证可扩展性。
- 语音不进入本次 MVP，文字和图片闭环完成后再作为 P1。
- Multi-Agent、Redis、RAG 和具体模型只出现在实现与实验层，不主导产品定位。
- 如果项目进度落后，优先保证工单状态、Tool 执行、Human-in-the-loop、Ops 工作台和业务实验，不牺牲核心闭环去换取更多技术名词。
