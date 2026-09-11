# 阶段二十三工作记录：公开客服提效实验与部署准备

- 记录日期：2026-09-11
- 交付阶段：**匿名服务端分题、正式提交去重、公开静态前端与部署配置已实现并验证；Supabase 011 迁移已应用，Render API 与 Netlify 正式实验入口已发布。**

## 1. 目标

将只适用于内部固定槽位的 v1 实验台改为一个可公开分享的模拟客服小实验：每位测试者通过同一链接进入，系统自动生成匿名编号并公平分配 6 道题；正式数据由服务端保存到 Supabase，不再依赖浏览器 localStorage 导出。

## 2. 实现

- 新增 `customer_efficiency_participants`、`customer_efficiency_assignments` 和 `customer_efficiency_records` 数据模型及 `011_customer_efficiency_study.sql`。三表独立于 v0.2 和既有业务表，`FORMAL` 与 `PILOT` 明确分开。
- 新增公开 API：创建/恢复匿名会话、服务端开始计时、服务端正式提交。任务的冻结目标处置不会返回给浏览器；提交时服务端复核来源操作、高风险人工确认、Decision Package 的建议处理结果，并以 `(participant_id, task_id)` 唯一约束拒绝重复计入。
- 分题规则保持每人 Manual/Decision Package 为 3/3、pair 不重复，并按已完成数、已分配未完成数和稳定哈希补齐题目平衡。
- `/efficiency-experiment` 改为自动匿名分题体验；移除 P01–P08、CSV 下载和技术术语。正式测试者只看到短说明、当前要做什么、开始做题、提交这一题、下一题和完成后的感谢页。
- 新增 `apps/experiment-public` 作为 Netlify 静态公开页，和本地原型使用同一公开 API 语义；新增 `netlify.toml` 与 `render.yaml`。

## 3. 验证

- FastAPI 全量测试：**24/24 通过**，包括匿名会话、6 题 3/3 平衡、同 pair 不重复、高风险门槛、六题完成和重复提交 `409`。
- 原型前端 `npm run build` 通过；公开静态页 `node --check app.js` 通过。
- 用隔离 SQLite、本地 FastAPI 和静态页实走：首次说明 → 自动首题 → 服务端开始计时 → 选择处理方式与评分 → 提交 → 下一题。页面没有显示正确答案或技术指标。
- 已将 `011_customer_efficiency_study.sql` 应用到现有 Supabase，并以只读查询确认三张 `customer_efficiency_*` 实验表存在；没有创建正式参与者或记录。
- Render 健康检查返回 `storage: database-url`；CORS 预检只允许唯一 Netlify 正式入口。Netlify 公开页已核验为用户可读的说明页，且公开站点的 `.env.local`、内部文档和 `.git` 路径均返回 `404`。

## 4. 交付边界与待办

- 本阶段没有写入远程研究结果、没有真实参与者或业务结果；公网核验只创建了未提交的匿名会话。
- 已发布地址：Netlify `https://carepilot-efficiency-experiment.netlify.app/`；Render `https://carepilot-api-eoes.onrender.com`。唯一二维码为项目根目录的 `carepilot-efficiency-experiment.png`，只编码正式根链接。
- 服务端目前只配置正式实验必需的 `DATABASE_URL` 与 `CORS_ALLOWED_ORIGINS`。若要使用内部 `PILOT` 数据或完整真实 Agent API，项目负责人仍需在 Render 安全配置中分别添加 `EFFICIENCY_PILOT_ACCESS_CODE`、Supabase Auth 与模型变量；这些变量不能提交或写入前端。
