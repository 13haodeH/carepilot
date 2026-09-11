# 运行真实 CarePilot Agent

只需要项目负责人完成两件事：执行一次增量 SQL，并在本机 API 环境变量中填写模型 Key。不要把 Key 发到聊天、写进前端或提交 Git。

## 1. 数据库

在专用 Supabase 项目的 SQL Editor 按顺序执行 `data/001_supabase_schema.sql` 到 `data/009_real_vision_evidence_origin.sql`。**空库必须先执行 `001`；不要单独执行 `006`，它会 `ALTER public.tickets`。**已有旧库也先重跑新版 `001`：它会补齐旧 `evaluation_runs` 缺失的字段；随后继续执行 `002` 至 `009`。所有脚本均不删除现有数据。

然后在 `apps/api/.env.local` 写入服务器专用连接串：

\`\`\`dotenv
DATABASE_URL=postgresql+psycopg://<session-pooler-user>:<password>@<host>:6543/postgres?sslmode=require
\`\`\`

本地演示也可以暂时保留 \`DATABASE_URL=sqlite:///./carepilot.db\`，但 SQLite 只适合单机演示，不是多人/线上部署方案。

## 2. 模型 Key

在同一个 **未提交** 的 \`apps/api/.env.local\` 选择一组模型变量。DeepSeek 是当前项目的推荐配置：

\`\`\`dotenv
DEEPSEEK_API_KEY=<your-server-side-key>
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_VISION_MODEL=deepseek-v4-flash-vision-exp
# 当前峰时、缓存未命中的每百万 token 估算；按你的实际账单调整。
DEEPSEEK_INPUT_USD_PER_MILLION=0.44
DEEPSEEK_OUTPUT_USD_PER_MILLION=1.32
\`\`\`

如需改回 OpenAI，再使用：

\`\`\`dotenv
OPENAI_API_KEY=<your-server-side-key>
OPENAI_MODEL=gpt-4.1-mini-2025-04-14
OPENAI_VISION_MODEL=gpt-4.1-mini-2025-04-14
OPENAI_INPUT_USD_PER_MILLION=0.40
OPENAI_OUTPUT_USD_PER_MILLION=1.60
\`\`\`

DeepSeek 的 Responses API 是无状态的，CarePilot 已在服务端补齐每轮 Tool Call 的完整上下文；它不依赖 OpenAI 的 \`previous_response_id\`。所有变量只由 FastAPI 读取；\`apps/web\` 只能使用 \`NEXT_PUBLIC_API_BASE_URL\`，绝不能出现模型 Key。

## 3. 启动与验收

\`\`\`bash
cd apps/api
.venv/bin/uvicorn app.main:app --reload
\`\`\`

另开一个终端：

\`\`\`bash
cd apps/web
npm run dev
\`\`\`

在 Supabase Authentication 中启用 Email/password 登录后，从 \`/register\` 注册普通用户，或使用由本地脚本预置的 Demo Auth 账号登录。普通注册账号只能进入用户端；客服账号进入 \`/ops\`，超级管理员可进入 \`/admin\`。验收点：

1. 新工单是 \`REAL_AGENT_RUN\`，而非 \`FIXTURE_SIMULATION\`。
2. 客服工作台能看到订单查询、物流查询、规则查询；图片工单另有真实视觉模型运行记录。
3. 每次真实运行保存模型、提示词、输入/输出、工具调用、政策依据、延迟、token 和成本。
4. 物流类低风险工单可到“已处理”；退款、退货、换货、补偿建议必须到“等待客服确认”，再由客服同意、修改、不采用或人工接手。
5. 在管理后台运行“真实冻结评测”；它使用 \`real-agent-eval-v0.2.json\`，其中的图片样本来自 \`real-vision-eval-v0.2.json\`。每张图片会先按 SHA-256 校验，再调用真实视觉模型；图片目录标签只用于评测打分，绝不会传给模型。
6. 真实评测产生独立的 \`REAL_AGENT_RUN\` 结果。离线模拟卡片不能替代它。

如果没有 Key，系统会让真实工单进入 \`FAILED\` 并记录 \`REAL_MODEL_NOT_CONFIGURED\`。这是预期的 fail-closed 行为，不是可展示的 AI 结果。
