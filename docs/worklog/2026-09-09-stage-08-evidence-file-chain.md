# 阶段八工作记录：自构造图片 Evidence 文件链路

- 记录日期：2026-09-09
- 对应计划：`PLAN.md` 的 30 张图片 Evidence 测试集、MIME / 大小检查、EXIF 清除与人工复核
- 交付阶段：**本地与 Supabase 开发库的模拟 Evidence 文件链路已验证**；不是图片模型、对象存储或真实售后图片接入

## 1. 目标

将原先仅改变 `evidence_submitted` 布尔值的演示接口，扩展为可验证的图片文件接收流程；任何无法由当前原型安全分析的图片都不得直接使工单继续处理。

## 2. 决策与取舍

| 决策 | 采用方式 | 未采用方式 | 原因 |
| --- | --- | --- | --- |
| 测试图来源 | 30 张本地脚本生成的抽象 PNG，附 manifest 与 SHA-256 | 抓取商品图或上传真实图片 | 保证来源明确、可复现且不含个人或第三方内容 |
| 文件处理 | 核对实际格式、8 MB 上限、每工单 4 张、重新编码清除 EXIF | 仅信任浏览器 Content-Type 或文件扩展名 | 文件边界必须由服务端决定 |
| 图片理解 | 只为完全匹配 fixture 哈希的文件返回 `FIXTURE_ANNOTATION` | 将模拟标注写成视觉模型判断 | 当前没有视觉模型或真实标注集 |
| 持久化 | 只保存哈希、大小、来源文件名哈希与结构化状态 | 保存图片字节、原始文件名、Supabase Storage 或签名 URL | 后三者尚未实现，且不应在模拟原型中保留可能含隐私的原始内容 |

## 3. 实现

- 新增 `evals/generate_evidence_fixture.py`、`evals/fixtures/evidence-v0.1.json` 与 30 张抽象 PNG；数码 / 服饰 / 家居各 10 张，并在加载时校验文件数、品类分布与每个 SHA-256。
- 新增 `POST /api/tickets/{ticket_id}/evidence-files`。它只接受 `image/jpeg`、`image/png` 或 `image/webp`，要求声明 MIME 与图像实际格式一致，并限制单图不超过 8 MB、单工单不超过 4 张。
- `Pillow` 重新编码图片以清除 EXIF。原型不保存生成后的图片字节，只保存其哈希和大小。
- 非 fixture 图片的 `analysis_origin` 固定为 `UNASSESSED`，`needs_human_review` 固定为真；不允许由 `submit-evidence` 推进工单。匹配 fixture 的模拟标注仍可因低质量标记而转人工。
- 新增 `EvidenceAsset` 与 `data/004_evidence_assets.sql`。该 SQL 仅新增元数据表、索引、RLS 与服务端授权；不创建 Storage bucket，不删除或改写既有数据。
- 远程数据库不再由 API 启动期自动创建新表；SQLite 测试库仍可由 ORM 建表。远程环境必须先审阅并执行迁移，避免代码静默漂移 schema。

## 4. 验证证据

| 检查 | 结果 | 性质 |
| --- | --- | --- |
| `apps/api/.venv/bin/python -m unittest discover -s tests -v` | 12 / 12 通过 | 隔离 SQLite API、fixture 与状态机回归验证 |
| fixture 完整性 | 30 / 30 自构造 PNG，三品类各 10，manifest 校验 SHA-256 | 本地测试输入完整性验证 |
| JPEG EXIF | 构造带 EXIF 的测试 JPEG 后，重新打开清洗结果的 EXIF 为 0 | 本地隐私处理技术验证 |
| 拒绝路径 | 声明 MIME 与实际内容不一致返回 415；超过 8 MB 返回 413；5 张文件返回 409 | 本地文件边界验证 |
| 工单推进 | 未上传 Evidence 或需要人工复核时，`submit-evidence` 返回 409；通过的 fixture 才可进入重新处理 | 本地人工复核闸门验证 |
| Supabase 合格 fixture | 上传返回 201、`FIXTURE_ANNOTATION`；提交后进入 `PROCESSING` | 远程开发库技术验证 |
| Supabase 非 fixture JPEG | 上传返回 201、`UNASSESSED` 且 `needs_human_review=true`；提交返回 409 | 远程人工复核闸门验证 |
| Supabase 匿名访问 | 回滚事务中以 `anon` 查询 `evidence_assets` 被 42501 拒绝 | 远程 RLS / 表权限技术验证 |

## 5. 责任与边界

- 30 张图片与所有结构化字段均为自构造模拟。它们只证明文件处理链路和 fixture 关联，不证明图片模型准确率、欺诈识别能力、真实图片质量或经营效果。
- 图片二进制、原始文件名、地址和电话均未持久化；hash 不是身份认证或真实隐私合规的完整方案。
- 当前没有 Supabase Storage、签名 URL、真实鉴权、真实视觉模型、图片字段准确率评测或生产保留/删除策略。

## 6. 下一步

1. 若要接入真实图片，先单独确定 Storage bucket、签名 URL、服务端鉴权、生命周期删除和合法数据来源；这些不能由当前模拟链路替代。
2. 在招募参与者前，按 `evals/manual-agent-study-v0.1.md` 审阅说明和交叉平衡安排。
