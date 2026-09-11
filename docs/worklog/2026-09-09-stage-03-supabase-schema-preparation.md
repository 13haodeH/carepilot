# 阶段三工作记录：Supabase 数据层准备

- 记录日期：2026-09-09
- 对应计划：`PLAN.md` 的 PostgreSQL / Supabase 最终事实源要求
- 交付阶段：**Supabase 开发库已完成 API 连通性、演示 seed 与匿名访问边界验证**；不是生产部署或真实业务数据接入

## 1. 目标

将当前 SQLite 开发回退中已经实现的持久化实体写成可审阅的 Supabase / PostgreSQL 初始化脚本。在取得任何项目 URL、连接字符串或服务端密钥之前，项目负责人应能检查表、约束、RLS 和远程接入边界。

## 2. 决策与取舍

| 决策 | 采用方式 | 未做的内容 | 原因 |
| --- | --- | --- | --- |
| 初始结构 | `data/001_supabase_schema.sql` | 运行期让 SQLAlchemy 自动猜测远程结构 | 先审阅、后执行，避免远程环境成为不可见的架构事实源 |
| 迁移范围 | 12 张已有实体表、索引和 `tickets.updated_at` 触发器 | Evidence Storage、RAG、Redis、认证表 | 后三者在当前原型尚未实现，不能伪造为已落地能力 |
| 浏览器访问 | 全表启用 RLS，并撤销 `anon`、`authenticated` 权限 | 前端直连或宽泛 RLS policy | 工单、审批和审计由 FastAPI 服务端承载，当前没有已实现的用户身份模型可安全写入 policy |
| 测试数据 | 不迁移 `carepilot.db` | 把本地模拟数据复制到远程 | 远程环境应由应用启动期的既有脱敏 seed 产生可追溯演示数据 |

## 3. 实现

- 新增 `data/001_supabase_schema.sql`，覆盖 `Ticket`、Proposal、Tool、Human Review、Audit、Policy、Config 和 Evaluation 的现有持久化实体。
- 该脚本只包含创建、索引、RLS、精确表级授权与一个更新时间触发器；没有 `DROP TABLE`、`TRUNCATE`、数据导入或客户端 RLS policy。
- `apps/api/requirements.txt` 新增 `psycopg[binary]`，使 `DATABASE_URL` 可使用 SQLAlchemy 的 `postgresql+psycopg://` 前缀。
- 更新 `apps/api/.env.example`，明确 Supabase 连接字符串仅能在 API 服务端环境使用，不能将 service-role key 放入 Web 端。
- `apps/api/.gitignore` 新增 `.env`，避免服务器连接字符串或服务端密钥被本地 API 配置意外纳入版本控制。
- 新增已忽略的 `apps/api/.env.local` 连接串占位文件，供项目负责人本机填写服务器端 Supabase PostgreSQL 连接。
- 新增 `data/README.md`，记录空项目适用范围、执行顺序、验证条件和所需的远程信息。
- 项目负责人已报告在 Supabase 中完成建表；当前终端尚未配置 `DATABASE_URL`，因此尚未执行远程 API 验证。
- 已在 `apps/api/.venv` 安装 `psycopg` 及其二进制包，为 PostgreSQL 连接做好本地运行时准备。
- 发现 Supabase REST / JWT 变量本身不会驱动现有 SQLAlchemy 数据层；新增 fail-closed 检查，防止缺少 `DATABASE_URL` 时误把 SQLite 回退表述为远程连接成功。
- 发现 `uvicorn --env-file` 在本机空环境变量存在时未传入连接串；数据层现改为系统环境优先、否则读取已忽略的 `.env.local`，使本地服务器配置可重复生效。
- 首次远程 seed 暴露出 001 的 `tickets_risk_check` 漏掉合法的 `MEDIUM`；新增无数据删除的 `data/002_expand_ticket_risk.sql`，并让 ORM 与回归测试使用同一风险集合。远程迁移须由项目负责人先执行。

## 4. 验证证据

| 检查 | 结果 | 性质 |
| --- | --- | --- |
| `apps/api/.venv/bin/python -m unittest discover -s tests -v` | 7 / 7 通过（安装 psycopg 与新增配置安全断言后复跑） | 本地 API 回归验证 |
| Supabase 变量缺少 `DATABASE_URL` | 新增独立导入断言，必须启动失败 | 配置安全验证 |
| SQL 表覆盖核对 | 12 / 12 `models.py` 表名与 SQL 建表名一致；未定义 client policy | 本地结构验证 |
| Supabase SQL Editor 执行 | 项目负责人报告已完成；后续 API 启动与 seed 已验证表可用 | 远程 schema 初始化 |
| 远程 API 读写验证 | `/health` 返回 `database-url`；`/api/tickets` 返回 3 条演示工单；`/api/evaluations/latest` 返回 v0.2、80 条快照 | Supabase 开发库技术验证 |
| 匿名访问边界 | 在可回滚事务中 `SET LOCAL ROLE anon` 后读取 `tickets` 被 PostgreSQL 以 `42501` 拒绝 | RLS / 表权限技术验证 |
| 直连 PostgreSQL 启动 | 连接串被应用正确读取，但当前主机无法解析 IPv6 直连主机；未发生远程 seed 或 API 验证 | 网络兼容性诊断 |
| Session Pooler 启动 | 首次 seed 暴露 `tickets_risk_check` 不一致；执行 002 后成功启动、seed 与 API 读取 | 远程 schema 一致性验证 |

测试运行仍会出现既有 FastAPI / Starlette 的依赖弃用提示；它不影响本轮 6 项业务断言通过，也不应表述为已解决。

## 5. 责任与边界

- 项目负责人决定远程 Supabase 是否启用，并在远程执行前审阅 SQL。
- 当前脚本不能证明远程网络连通性、PostgreSQL 执行成功、RLS 实际拦截、远程 seed 成功或生产安全性。
- 现有 `reviewer` 请求字段是演示输入，不是远程部署可用的身份鉴权；在增加真实用户或任何非模拟数据前，必须先实现服务端身份与角色映射。

## 6. 下一步

1. 保留 Session Pooler 作为当前本机 API 的开发连接方式；将 `.env.local` 保持为未提交的服务器端配置。
2. 在远程连接验证后，继续冻结集的单条处置断言、Query–Policy 标注与 Evidence 流程；这些仍是阶段二列出的未完成项。
