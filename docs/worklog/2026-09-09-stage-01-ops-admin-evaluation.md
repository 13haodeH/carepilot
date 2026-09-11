# 阶段一工作记录：Agent Ops 与 Admin 闭环

- 记录日期：2026-09-09
- 对应计划：`PLAN.md` 的第 2–5 周核心闭环，以及 Admin 的 Policy、Config、Evaluation 范围
- 交付阶段：**本地可运行原型 / 技术验证**，不是生产落地、内部试点或真实电商系统接入
- 本阶段原则：用模拟业务 Tool 产生真实持久化状态；高风险动作只形成 Proposal 并等待人工；模拟指标不得写成线上经营结果

## 0. 阶段结论

已完成可演示的 Agent Ops 主工作台，以及 Policy、Agent Config、Evaluation 三个 Admin 页面和对应本地 API。低风险物流场景可自动推进到 `RESOLVED`；换货类高风险场景只创建 `replace.propose` 并进入人工审批；政策发布和配置激活均有前置闸门；Evaluation 使用 72 条固定脱敏模拟工单生成可复跑快照。

当前本地预览路由为 `/`、`/policy`、`/config`、`/evaluation`。数据存储使用 SQLite 开发回退，不等同于计划中的 PostgreSQL / Redis 生产架构。

---

## 1. 问题背景

电商售后处置通常需要客服跨订单、物流、政策、工单和通知系统完成查询与更新。仅生成处理建议无法证明 Agent 能推进业务流程；项目需要验证以下闭环：

1. 低风险工单能够在受控 Tool 调用后自动完成；
2. 退款、换货、退货和补偿等高风险动作不能绕过人工；
3. 政策和 Agent 配置不能未经验证直接进入 Active；
4. 运营端看到的是影响当前工单优先级与决策的紧凑信息，而不是脱离处置流程的 BI 大屏；
5. 指标、坏例和测试结果能被后续回溯，而非只展示最终界面。

约束包括：不接入真实支付、库存、退款或真实客户数据；当前没有 PostgreSQL / Redis 运行配置；所有效率与成本数据只可作为离线模拟或技术验证。

## 2. 方案决策与取舍

| 决策 | 采用方式 | 放弃或延后 | 原因 |
| --- | --- | --- | --- |
| Ops 主视觉 | 当前工单的处置闭环 + 顶部 Shift Health | 单独的 Ops BI 大屏 | 让客服优先完成当前工单，而非切换到报表阅读 |
| 风险控制 | 后端状态机 + `REQUIRE_HUMAN` Proposal | Agent 直接执行换货 / 退款 | 高风险写操作必须经过人工审批 |
| Policy 发布 | `Candidate → Regression → 人工 Publish → Active` | 同步后自动覆盖 Active | 防止未验证政策改变线上处置依据 |
| Config 激活 | `Draft → Sandbox → 人工 Activate`，保留回滚 | 直接编辑 Active | 保留版本、审计和明确的人工闸门 |
| Evaluation | 固定的 72 条模拟工单 + 可复跑快照 | 将模拟指标写成业务收益 | 先建立可解释的评测口径；正式 80 条冻结集与真人实验仍待完成 |
| 本地数据 | SQLite 开发回退 | 把浏览器状态当作事实源 | 需保证本地重启后工单、审计和版本记录仍可追溯 |

## 3. 实现过程、问题与解决方案

### 3.1 Figma 与工作台布局校验

**目标**：让高保真原型和网页实现都以 Agent Ops 的工单处置闭环为中心。

**发现的问题**：早期截图出现顶部内容被截断、框体边界不稳定的视觉信号；若直接沿用，Policy / Config 页面会失去可读性，也无法支撑演示流程。

**解决方案**：完成 Figma Frame 与原型连线检查，并将 Ops 顶部数据压缩为 Shift Health：待审批与超时风险、低风险自动处置率、审批耗时 / SLA、近 24 小时待审积压趋势。详细指标移到 Admin Evaluation，不在 Ops 新建重复 BI 页面。

**验证证据**：本轮 Figma 原型已覆盖 Consumer 起点、Ops 审批、Policy、Config、补材料、人工接管和上传证据；此前检查结果未发现同页断链、越界或零高度 Frame。网页端随后在 1440px 与 390px 继续做了布局验证，见 3.7。

**边界**：本记录只确认原型与本地页面的交互、布局状态；不代表真实客服团队已使用该界面。

### 3.2 工单状态机、Tool 调用与低风险自动处置

**目标**：让“物流延迟”不止生成文本，而是完成 Tool 调用、写入 Audit Trace 并进入 `RESOLVED`。

**实现**：

- 在 `apps/api/app/domain.py` 定义 `NEW / PROCESSING / NEED_INFO / WAITING_REVIEW / RESOLVED / FAILED` 的合法迁移；非法迁移返回 409。
- `order.lookup`、`logistics.track`、`policy.search` 等读取 Tool 与 `task.create`、`customer.notify` 等低风险写 Tool 写入 `ToolExecution` 和 `AuditEvent`。
- `CP-240917` 物流延迟场景在 `PROCESSING` 时执行工具链后进入 `RESOLVED`；重复处理被拒绝。

**遇到的问题**：如果只在前端改变标签，无法证明状态与 Tool 调用真实发生，也无法阻止重复写操作。

**解决方案**：状态变化和 Tool 记录只在后端事务中发生；处理接口接受幂等键，重复请求不重复创建动作。

**验证证据**：自动化测试断言低风险流程按顺序记录 5 个 Tool，首次处理后为 `RESOLVED`，重复处理返回 409。

**边界**：Tool 为模拟业务系统，未连接真实订单、物流或通知服务。

### 3.3 高风险 Proposal 与人工接管

**目标**：商品配件缺失和补证据场景能进入人工协作，而不是由 Agent 直接执行换货。

**实现**：

- 高风险路径创建 `replace.propose`，工单进入 `WAITING_REVIEW`。
- 客服可执行 `APPROVE / MODIFY / REJECT / TAKE_OVER`；审批与接管写入 `HumanReview` 和审计事件。
- 代码中没有 `replace.execute`；人工批准后创建后续任务并通知用户，保留人工决策痕迹。

**遇到的问题**：仅靠 Prompt 约束无法可靠保证高风险动作不会越过审批。

**解决方案**：将控制点放在后端状态机和 Proposal 路径上，审批前没有可调用的高风险执行 Tool。

**验证证据**：自动化测试确认高风险工单初始为 `WAITING_REVIEW`，人工批准后才进入 `RESOLVED`，Tool 记录中不存在 `replace.execute`。

**边界**：当前是单 Agent 与固定规则驱动的技术验证；尚未完成计划中的 A / B / C Agent 对照实验。

### 3.4 Policy 生命周期

**目标**：实现政策同步、差异、回归、人工发布与回滚，避免新政策自动覆盖 Active。

**实现**：

- Policy Source 初始化 `v3.2 Active`；同步后生成 `v3.3 Candidate`。
- Candidate 运行固定的 60 条 Query–Policy 与 12 条异常用例回归。
- 回归通过前 Publish 返回 409；通过后仍须提供具名 reviewer 才可发布；归档版本可回滚。

**遇到的问题**：如果同步完成即切换 Active，解析或引用错误会直接影响当前工单。

**解决方案**：把同步、回归和发布拆为独立状态；后台不能替代管理员签发发布动作。

**验证证据**：本地接口曾验证“发布前回归”返回 409；回归后生成 `PASSED`，自动化测试验证带 reviewer 的发布路径与审计事件。

**边界**：目前政策内容、同步和回归用例均为模拟；未实现计划中的 BM25、向量召回、Reranker 或正式政策解析流水线。

### 3.5 Agent Config：Sandbox、Activate 与 Rollback

**目标**：将模型、Prompt、Tool 白名单与风险边界纳入受控版本流程。

**实现**：

- `v1.3` 初始化为 Active，`v1.4` 为 Draft；Draft 展示模型、Prompt、允许 Tool 和“退款、换货、退货、补偿始终 REQUIRE_HUMAN”边界。
- Sandbox 固定验证 `CP-SBX-018`：图片质量不足时只能推进 `NEED_INFO` 与用户通知，不得产生退款、换货或补偿写操作。
- 未通过 Sandbox 的激活请求返回 409；通过后才允许人工 Activate；旧 Active 归档后可 Rollback。

**遇到的问题**：直接修改 Active 会使 Prompt、模型与 Tool 权限的变更不可审计，也难以恢复。

**解决方案**：新增 `AgentConfigVersion`、`ConfigSandboxRun` 和 `ConfigAuditEvent`，把激活前置条件写到 API，而非只把按钮置灰。

**验证证据**：本地真实 API 先返回 `409 A passed Sandbox run is required before activation`；随后 `v1.4` Sandbox 记录为 `PASSED`，但没有自动激活。自动化测试覆盖 Sandbox → Activate → Rollback 的完整路径。

**边界**：当前 Sandbox 是确定性模拟用例；不是完整 Prompt 回归平台，也没有接入真实模型服务。

### 3.6 Evaluation：离线模拟基线与 Bad Case 回流

**目标**：把详细指标留在 Admin Evaluation，提供效率、质量、稳定性、成本和坏例的统一回溯入口。

**实现**：

- 新增 `EvaluationRun` 持久化实体，以及 `/api/evaluations/latest`、`/api/evaluations/run` 接口。
- 固定模拟集 `synthetic-ticket-set-v0.1` 共 72 条：配件缺失 24、物流延迟 20、证据不足 16、错发商品 12。
- 每次运行生成相同口径的可追溯快照，并返回 Manual / Agent 单均时长、Proposal 修改率、Policy Top-3 命中、Tool 失败率、P95 延迟、平均成本和坏例分类。
- Evaluation 页面明确显示 `SIMULATED OFFLINE` 与“非线上经营结果”的边界说明。

**遇到的问题**：若直接在页面写一组漂亮指标，数字没有样本、运行 ID 和口径，无法复盘，也容易被误解为真实业务结果。

**解决方案**：将固定分段、失败集合和计算公式放在后端；运行结果写入 `EvaluationRun`；页面只读取 API 返回的快照。坏例按“证据模糊 / 信息缺失、政策排序歧义、工具超时、方案需人工改写”分类，并附回流动作。

**本轮离线模拟结果**：

| 指标 | 结果 | 证据性质 |
| --- | --- | --- |
| 样本量 | 72 条固定模拟工单 | 技术验证 |
| Manual / Agent 平均时长 | 15.3m / 5.0m | 离线模拟基线 |
| Proposal 修改率 | 15.3% | 离线模拟基线 |
| Policy Top-3 命中率 | 91.7% | 离线模拟基线 |
| Tool 失败率 | 1.4% | 离线模拟基线 |
| P95 延迟 | 1.9s | 离线模拟基线 |
| 平均成本 / 单 | $0.0178 | 离线模拟估算 |

**边界**：这不是 5 人可用性实验、企业生产数据或真实 GMV / 留存 / 满意度提升。计划要求的 80 条冻结集、20 条 Manual vs Agent 对照任务、图片 Evidence 集和 5 人测试仍待完成。

### 3.7 页面编译、预览与布局问题

**目标**：保证新增 Config 与 Evaluation 页面能编译、加载并在桌面和窄屏正常排版。

**遇到的问题**：Evaluation 新路由加入后，已经运行的本地开发预览未重新扫描新增页面中的 Tailwind 响应式类。在 1440px 检查时，指标和内容区错误地保持单列。

**解决方案**：重启本地开发预览，使 Tailwind 重新收集路由样式；不需要改动页面布局源代码。

**验证证据**：

- 重启后 1440px 计算样式为 3 列指标卡（每列约 450.7px）和 2 列内容区（约 886.6px / 477.4px），页面宽度与 viewport 同为 1440px。
- 390px 下两个 Grid 均为单列 350px，`bodyWidth = viewportWidth = 390px`，无横向溢出。
- 页面标题均只渲染一次；新页面构建成功并被路由识别为 `/evaluation`。

**遗留问题**：`npm run lint` 目前仍报 18 项既有通用组件问题，集中在 `apps/web/components/ui/*` 和 `apps/web/hooks/use-mobile.ts`。新增的 `app/config/page.tsx` 与 `app/evaluation/page.tsx` 未出现在报错列表；本阶段不改动第三方 / 通用 UI 组件。

## 4. 交付状态

| 模块 | 当前状态 | 说明 |
| --- | --- | --- |
| Figma 原型 | 已完成当前流程检查 | 高保真原型与路由页面对应；仍需在最终发布前再次截图验收 |
| Agent Ops | 本地可运行 | 工单队列、处置详情、Shift Health 与 Audit Trace |
| 工单与高风险审批 | 本地技术验证 | 模拟 Tool + 持久化状态 + 人工审核路径 |
| Policy Admin | 本地技术验证 | Candidate、回归、人工发布、回滚 |
| Agent Config | 本地技术验证 | Draft、Sandbox、人工激活、回滚 |
| Evaluation | 本地技术验证 | 72 条固定模拟工单的可复跑快照 |
| 线上 Demo | 未完成 | 未部署 |
| 生产系统集成 | 未开始 | 不在本阶段范围 |

## 5. 落地范围与技术边界

- **运行环境**：本地 FastAPI + React / Vinext 开发预览。
- **事实源**：SQLite 开发回退数据库，保存 Ticket、ToolExecution、Proposal、HumanReview、Audit、Policy、Config 和 EvaluationRun。
- **未实现的计划组件**：PostgreSQL / Supabase、Redis、RQ、Policy RAG、图片上传与 EXIF 处理、真实异步任务、A / B / C Agent 实验、线上部署。
- **数据范围**：当前为自构造 / 脱敏模拟场景；未接触真实客户订单、图片、地址、电话、支付或库存数据。

## 6. 效果证据与验证命令

| 证据 | 结果 | 性质 |
| --- | --- | --- |
| `python -m unittest discover -s tests -v` | 6 项测试通过 | 自动化技术验证 |
| `npm run build` | `/`、`/config`、`/evaluation`、`/policy` 均成功构建 | 前端技术验证 |
| `GET /api/evaluations/latest` | 返回 72 条模拟集、评测快照、坏例与边界说明 | 本地接口验证 |
| Config 激活前置检查 | 未 Sandbox 时返回 409；Sandbox 后记录为 `PASSED` | 本地接口验证 |
| 1440px / 390px 页面检查 | 桌面分列、窄屏无横向溢出、标题不重复 | 视觉技术验证 |

测试运行中存在 FastAPI / Starlette 的依赖弃用提示，但不影响本阶段 6 项测试通过；该提示不应被表述为已解决的问题。

## 7. 责任边界

- **产品决策与范围**：由项目负责人确定，包括 Ops 不做独立 BI 大屏、Admin 承担详细 Evaluation、审批与发布均保留人工闸门、模拟数据不得包装为线上效果。
- **本阶段协作实现**：在 AI 辅助下完成本地页面、FastAPI 生命周期、测试与验证；记录中不得把 AI 辅助的编码过程改写为真实客服团队、真实用户或生产系统成果。
- **尚未主张的责任**：未主张真实电商系统接入、真实策略运营、真实用户研究、线上指标增长或生产发布。

## 8. 待补证据与下一阶段优先级

1. 将当前 72 条固定模拟工单扩展并冻结为计划中的 80 条，补齐来源 / 生成说明、预期结果、风险标签、图片覆盖与异常标签。
2. 建立 20 条 Manual vs Agent 对照任务，并在完成后开展 5 人测试；在此之前不可把 15.3m / 5.0m 作为真实可用性结论。
3. 实现图片 Evidence 流程、文件限制、EXIF 移除、低质量图补拍和人工复核，补齐 30 张 Evidence 测试集。
4. 完成 Policy RAG、政策解析失败路径、工具超时与策略冲突等异常测试；目前的 Policy 回归仍是确定性模拟。
5. 明确 A / B / C Agent 实验配置、冻结模型 / Prompt / Policy / Config 版本，并记录前后运行结果后再决定默认架构。
6. 在进入发布前，用 PostgreSQL 替代本地 SQLite 回退，并按实际需要接入 Redis、异步 Worker 和部署环境。
7. 评估并处理既有 UI lint 报错；因其在通用组件中，不应与本阶段业务改动混在同一修复中。

## 9. 后续追问与复盘迁移

可基于现有证据回答的问题：

1. 为什么 Ops 只放 Shift Health，而把详细图表留在 Admin？
2. 为什么高风险动作的限制不能只依赖 Prompt？当前后端在哪些位置建立了闸门？
3. Candidate 政策为何不能同步后自动发布？回归与人工发布各解决什么问题？
4. 72 条评测集可以证明什么，又不能证明什么？
5. 为什么本地 SQLite 只能算开发回退，不能算最终事实源方案？
6. 本阶段出现响应式单列问题时，如何区分“源代码布局错误”和“开发预览缓存未更新”？

**升维迁移（非简历表述）**：本阶段的核心事实不是“做了四个页面”，而是将售后 Agent 的自动处置、人工闸门、受控发布和离线评测串为一条可验证的本地闭环；其可证明范围止于模拟数据与技术验证，后续需要用冻结集、异常测试和用户实验补齐效果证据。

## 可追溯代码入口

- 工单状态、Tool、Policy、Config 与 Evaluation 逻辑：`apps/api/app/domain.py`
- 持久化实体：`apps/api/app/models.py`
- HTTP 接口与序列化：`apps/api/app/main.py`
- 工单、Policy、Config、Evaluation 自动化测试：`apps/api/tests/test_ticket_flow.py`
- Agent Ops 页面：`apps/web/app/page.tsx`
- Policy / Config / Evaluation 页面：`apps/web/app/policy/page.tsx`、`apps/web/app/config/page.tsx`、`apps/web/app/evaluation/page.tsx`
- 原始范围与验收目标：`PLAN.md`
