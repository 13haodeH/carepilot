# 阶段二十三工作记录：公开客服提效实验与部署准备

- 记录日期：2026-09-11
- 交付阶段：**匿名服务端分题、正式提交去重、公开静态前端与部署配置已实现并本地验证；Supabase 011 迁移已应用并核验，尚未完成 Netlify/Render 账户授权或公网发布。**

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

## 4. 交付边界与待办

- 本阶段没有写入远程研究数据、没有真实参与者或业务结果。
- Netlify 和 Render 均需要账户授权；Render 还需要一个私有 Git 仓库作为源。服务端变量必须在 Render 控制台配置，不能从本地 `.env.local` 提交或复制到前端。
- 公开链接、Render URL 和正式二维码必须在账户授权、迁移、环境变量配置与端到端公网验证后才能记录为已交付地址。
