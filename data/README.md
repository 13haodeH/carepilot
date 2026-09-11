# Supabase 数据层准备

`001_supabase_schema.sql` 是基础数据层脚本；`006_real_agent_runtime.sql` 扩展真实 Agent Run 与真实模型评测；`007_action_proposal_auto_executed.sql` 让低风险真实 Proposal 可以在执行前持久化；`008_supabase_auth_rbac.sql` 以 Supabase Auth 和受控 `profiles` 取代本地演示登录，并删除仅用于旧版演示登录的 `app_users/app_sessions` 密码哈希与会话；`009_real_vision_evidence_origin.sql` 允许 Evidence 明确记录真实视觉模型成功或失败结果。它们都不会删除工单、Agent Run、政策或审计数据。

如果已在本修正前执行过 `001_supabase_schema.sql`，还须依序执行 `002_expand_ticket_risk.sql` 至 `007_action_proposal_auto_executed.sql`。其中 `004` 新增不存储图片字节或原始文件名的 Evidence 元数据；`005` 增加公开政策来源的 URL、版本、时间、SHA-256 快照与检索片段；`006` 持久化真实模型的输入/输出、Tool Calls、Policy Evidence、延迟、token、成本，以及冻结的真实模型评测；`007` 允许持久化低风险的 `AUTO_EXECUTED` Proposal。它们都不会删除或重写已有数据。

## 应用前的边界

- 请在独立的 Supabase 开发项目中执行，避免与其他项目共用 `public` schema。
- SQL 只适用于空项目的首次初始化。`create table if not exists` 让重复执行不会删表；为保持更新时间触发器一致，脚本会重建该一个触发器，但不会修复已存在且结构不同的表。
- RLS 已开启，且 `anon` 与 `authenticated` 没有这些表的权限；当前浏览器不应直连 Supabase。
- 现有 FastAPI 的 reviewer 字段仍是演示输入，不是实际身份鉴权。远程演示只允许模拟数据，不应上传真实客户、订单、支付、地址或图片。
- 当前 API 使用 SQLAlchemy 直连 PostgreSQL；`SUPABASE_URL`、publishable key、secret key 和 JWKS URL 不是数据库连接串。若它们存在但 `DATABASE_URL` 缺失，API 会拒绝启动而非静默回退 SQLite。

## 执行顺序

1. 在 Supabase Dashboard 的 SQL Editor 依次执行 `001_supabase_schema.sql` 至 `011_customer_efficiency_study.sql`；若旧项目已经执行过前序脚本，只需补执行尚未执行的编号。`001` 可安全重跑：它会补齐早期 `evaluation_runs` 表缺失的冻结评测字段，不会删除历史记录。`010` 仅新增 Evidence 的模型原始复核判断与确定性门禁原因，不会回写历史记录；`011` 仅新增匿名客服提效研究的参与者、分题和提交记录表。
2. 将 API 的 `DATABASE_URL` 指向 Supabase 的 PostgreSQL 连接字符串；保留 `postgresql+psycopg://` 作为 SQLAlchemy 的驱动前缀，并开启 SSL。若本机不支持 IPv6，请在 Supabase Dashboard 的 Connect 中选择 Shared Pooler 的 **Session mode** 连接串，而非直连 `db.*` 主机或 Transaction mode。
3. 在 `apps/api/.env.local` 填写该变量。应用会优先保留非空的部署环境变量；只有它缺失或为空时才读取该已忽略的本地文件。
4. 在 `apps/api/.env.local` 再填写仅服务端读取的 `OPENAI_API_KEY`。可选地设置 `OPENAI_MODEL`、`OPENAI_VISION_MODEL` 与对应每百万 token 单价；禁止放入 `apps/web`、`NEXT_PUBLIC_*` 或提交版本控制。
5. 在 Supabase Authentication 中启用 Email/password 登录。普通注册用户会自动获得 `user` 角色；`admin` 与 `superadmin` 只能通过 `profiles` 表授权，不能从注册页面选择。
6. 在 `apps/api` 的项目虚拟环境安装更新后的 `requirements.txt`，然后启动 API。启动期的 `seed()` 只会写入当前脱敏模拟工单、公开政策基线和离线评测快照，不会创建或保存业务密码。
7. 若需要预置三组真实 Demo Auth 账号，在忽略的 `apps/api/.env.local` 设置至少 12 位的 `CARE_PILOT_DEMO_USER_PASSWORD`、`CARE_PILOT_DEMO_ADMIN_PASSWORD`、`CARE_PILOT_DEMO_SUPERADMIN_PASSWORD`，然后运行 `PYTHONPATH=. .venv/bin/python scripts/provision_demo_auth.py`。脚本只调用 Supabase Auth Admin API，并在 `profiles` 中授予 `user`、`admin`、`superadmin`；不会记录或输出密码。
8. 检查 `GET /health` 返回的 `storage` 不再是 `sqlite-dev-fallback`，以用户账号创建工单并运行真实 Agent；在超级管理员的评测页面运行冻结集。`REAL_AGENT_RUN` 若没有模型 Key 会显式失败，绝不会回退成 fixture 或规则输出。

## 公开政策 grounding

- `005_public_policy_grounding.sql` 只建立审计结构；启动 API 后会写入一组受控公开来源的 Active 基线，使真实 Agent 在首次运行时可检索已发布 Policy。后续来源变更仍先导入 Candidate、运行回归并人工发布。
- 每次导入保存来源 URL、发布方、版本标识、公开页的发布时间（如可得）、导入时间和由规范化摘录计算的 SHA-256。相同 checksum 不再产生新 Candidate。
- 导入不自动发布。必须在前端运行来源完整性/检索冒烟回归，并由管理员点击发布；Active 版本可以从前端回滚。
- 公开来源只用于政策检索参考。订单、物流、退款、支付、库存、客户信息和实验任务仍是脱敏自构造模拟数据。

## 需要提供的远程信息

只有准备执行第 2 步时，才需要提供 Supabase 项目 URL 与**服务器专用**的 PostgreSQL 连接字符串（或在 Dashboard 中由项目负责人执行 SQL）。要启用真实 Agent 时，还须在 `apps/api/.env.local` 本机填写模型提供方 API Key；服务端密钥绝不能放入 `apps/web` 或提交到仓库。
