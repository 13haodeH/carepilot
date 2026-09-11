# CarePilot 冻结评测集

## 当前版本

`fixtures/tickets-v0.2.json` 是当前离线评测的唯一输入。它包含 80 条自构造模拟工单：数码 32、服饰 24、家居 24；包含 36 条声明有模拟图片附件的场景、20 条高风险 Proposal 场景，以及 12 条异常场景（政策冲突、Tool 超时、重复请求、提示注入各 3 条）。

该文件不包含任何真实客户、订单、图片、地址、电话、支付或库存数据。`has_image: true` 只表示该测试路径需要图片 Evidence 输入；它不与某一张 Evidence fixture 一一绑定，也不能把该字段视作完成多模态评测。

## 真实 Agent 冻结评测

`fixtures/real-agent-eval-v0.1.json` 是独立于上述离线 80 条 fixture 的真实模型冻结集。它目前包含 6 条脱敏模拟订单场景，覆盖低风险物流闭环、高风险权益 Proposal、补充材料、真实视觉 Evidence 和提示注入失败路径。

在服务端配置 `OPENAI_API_KEY` 后，Admin 的“运行真实冻结评测”会逐条创建 `REAL_AGENT_RUN`：模型实际调用订单、物流、已发布公开 Policy Tool；有图片的样本还实际调用视觉模型。每个运行及汇总都会持久化模型、Prompt、Policy snapshot、Tool Calls、输入/输出、延迟、token、成本和坏例。没有 Key 时接口返回 `REAL_MODEL_NOT_CONFIGURED`，绝不会回退成 fixture 或规则结果。

真实评测输出的任务完成率、Tool Calling、Policy Retrieval、Proposal 结构和高风险人工接管率，只代表该模型、Prompt、Policy 快照和冻结集，不能外推为线上业务效果。

## 单条记录字段

| 字段 | 说明 |
| --- | --- |
| `id` | 稳定的 fixture 标识；冻结后不复用 |
| `category` | `DIGITAL`、`APPAREL` 或 `HOME` |
| `scenario` | 售后场景代码 |
| `risk` | 预期风险等级 |
| `has_image` | 是否需要模拟图片 Evidence 输入 |
| `exception_tag` | `POLICY_CONFLICT`、`TOOL_TIMEOUT`、`DUPLICATE_REQUEST`、`PROMPT_INJECTION` 或 `null` |
| `expected_disposition` | 预期的风险处置结果 |
| `expected_state` | 预期状态机状态 |
| `proposal` | 预期高风险 Proposal；无 Proposal 时为 `null` |
| `proposal_modified` | 离线模拟中人工需要改写方案的标注 |
| `policy_top3_hit` | v0.2 保留的历史固定标注；当前 Evaluation 已不使用它计算 Top-3 |

## 冻结与变更规则

1. 不修改已发布 fixture 的语义；需要变更时创建新版本文件。
2. 每次 Eval Run 记录使用的 `fixture_set`，并从该文件重算汇总指标。
3. 新版本须通过：总数 80、品类分布 32 / 24 / 24、图片路径不少于 20、高风险不少于 20、异常不少于 12、ID 唯一。
4. 离线模拟结果只能称为技术验证或模拟基线；Manual vs Agent 真人实验和线上业务结果必须使用独立数据与运行记录。

## 可执行 Case 契约

API 在加载 v0.2 时会逐条校验 80 条 Case 的 `expected_disposition`、`expected_state` 与 `proposal`：常规高 / 中 / 低风险分别对应人工审批 / 补充材料 / 自动解决；工具超时、提示注入、重复请求和政策冲突分别覆盖失败转人工、阻断、幂等拒绝和人工审核。该检查是固定输入与期望结果的一致性验证，不等同于已对 80 条 Case 运行真实模型、图片 Evidence 或 Policy RAG。

## 自构造 Query–Policy 检索基线

`fixtures/policy-corpus-v0.1.json` 包含 12 条自构造政策片段，`fixtures/query-policy-v0.1.json` 包含 60 条自构造问句与目标政策 ID（三品类各 20 条）。Evaluation 的 Policy Top-3 现在按问句品类过滤政策，再按命中的自构造关键词排序后实际计算。该基线在同源语料和问句上得到 100.0% Top-3 命中，只能说明 fixture、标注和确定性词项检索链路一致，不能作为 BM25、向量检索、Reranker、真实政策或真实用户效果。

## 公开政策 grounding（受控来源包）

`fixtures/public-policy-grounding-v0.1.json` 是与自构造 Policy corpus 分离的公开来源基线；`public-policy-grounding-v0.2.json` 是不修改该冻结基线的增量包，增加一条京东物流延迟处理指引。导入后后端保存发布方、URL、来源时间、导入时间和由规范化摘录计算的 SHA-256。

启动时会一次性写入经审核的公开来源 Active 基线，使首个真实 Agent Run 可以检索带 URL、版本和片段的公开 Policy；后续更新仍先进入 Candidate。系统只校验 checksum 与片段完整性，且必须经人工发布才能替换 Active。这个完整性/检索冒烟校验不证明条款在具体订单上的法律适用性，也不等同于真实政策检索准确率。订单、物流、退款、支付、库存、客户与实验任务仍不接入真实数据。

## Manual vs Agent 任务准备（当前执行规则：v0.2）

`fixtures/manual-agent-tasks-v0.1.json` 定义 10 个业务场景对和 20 条条件任务；每对包含相同目标的 `MANUAL` 与 `AGENT_ASSISTED` 条件，三条高风险场景在两种条件下都要求人工 Proposal 审核。`fixtures/manual-agent-assignment-v0.1.json` 将全部任务预分配给 5 个匿名槽位：每槽位 4 条、两种条件各 2 条，且同一场景对的两个条件分配给不同槽位。重新测试使用 `manual-agent-study-v0.2.md` 与 `manual-agent-participant-kit-v0.2.md`：普通工具点击只记录实际使用，高风险人工审核是唯一硬性安全门槛。v0.1 文档只保留历史准备记录，不能和 v0.2 数据混合。

前端 `/experiment` 是这套自构造任务的本地运行页：按匿名槽位载入任务、自动记录计时/实际信息操作/最终状态/人工接管/单题易用度，并在第 4 条任务后记录一次 SUS-10。它只使用浏览器本地存储，导出 `carepilot-manual-agent-records-v0.2.csv` 和 `carepilot-manual-agent-sus-v0.2.csv` 两份脱敏文件。项目负责人提供的完整 v0.2 导出已核验，描述性结果和限制见 `manual-agent-results-v0.2.md`；它不构成真实业务效果证据。

## 自构造图片 Evidence 文件链路

`fixtures/evidence-v0.1.json` 与 `fixtures/evidence-images-v0.1/` 包含 30 张由 `generate_evidence_fixture.py` 生成的抽象 PNG：数码、服饰、家居各 10 张。它们不含人物、地址、订单、品牌或第三方素材；manifest 保存来源说明、完整性哈希和模拟标注。

API 只接受 JPG、PNG、WebP；每张至多 8 MB、每工单至多 4 张，并以图像实际格式核对声明 MIME。上传时会重新编码清除 EXIF，数据库只记录清洗后的哈希、大小、来源文件名哈希和模拟结果，当前不保存图片字节、不接入 Supabase Storage、也不生成签名 URL。

`FIXTURE_SIMULATION` 工单只有在文件哈希完全一致时才返回 `FIXTURE_ANNOTATION` 模拟标注；任意其他有效图片都会被标为 `UNASSESSED`。`REAL_AGENT_RUN` 则会把清洗后的图片字节发送给服务端配置的视觉模型，并记录 `REAL_VISION_MODEL`、model、prompt、token、延迟和成本；模型不可用时明确记录 `REAL_VISION_FAILED`，而不会套用 fixture 标注。
