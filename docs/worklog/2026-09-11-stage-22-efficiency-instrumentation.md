# 阶段二十二工作记录：客服提效 v1 题库与运行器

- 记录日期：2026-09-11
- 交付阶段：**本地实验工具与数据契约已验证；未招募、未运行人工实验、未产生客服提效结果**

## 1. 目标

把阶段二十一冻结的“客服 AI 决策准备工作台”价值口径转为可运行的本地研究工具：比较客服自行查找订单、物流、政策和凭证信息，与直接获得同一事实的 Decision Package 后仅按需复核之间的过程差异。

## 2. 决策与实现

1. 新增 `evals/fixtures/customer-efficiency-tasks-v1.json`：12 组自构造、无个人信息的配对情境，其中低风险 4 组、需补充材料 3 组、高风险人工审核 5 组。两个条件共享相同底层事实；Decision Package 只重新组织已有字段，不增加 Manual 无法获得的业务信息。
2. 新增 `evals/fixtures/customer-efficiency-assignment-v1.json`：`P01`–`P08` 各完成 6 题，Manual 与 Decision Package 各 3 题；每个条件任务由两人完成，且同一参与者不重复同一 pair。
3. 新增 `/efficiency-experiment`：Manual 显示分散信息入口；Decision Package 预展示诉求、订单、物流、政策、凭证、风险和下一步字段，并允许按需打开同一原始来源。
4. 高风险任务只能记录“打开人工审核”与 `WAITING_REVIEW`；Decision Package 高风险题还必须记录 Proposal 的采纳、修改、不采用或人工接手。页面不执行退款、退货、补件、换货、补偿或库存动作。
5. 使用独立的 `carepilot.customer-efficiency-records.v1` 浏览器键与 `customer-efficiency-record-v1` CSV schema；不读取、覆盖或混入 v0.2 的 key、CSV 和结果。
6. 在 Evaluation 页新增“进入客服提效 v1”入口，并将旧 `/experiment` 明确标为历史 v0.2 实验。

## 3. 可采集字段

- 任务条件、风险、轮次、开始/完成时间、停止/完成状态和是否符合冻结处置口径；
- 实际打开的原始来源、来源字段、Manual 信息操作数或 Decision Package 后的额外核验数；
- Decision Package 首次展示时的已就绪/缺失字段；
- 高风险人工审核门槛与 Proposal 处理结果；
- 单题 1–7 易用性评分和不含个人信息的观察备注。

上述字段支持后续按低风险处理时间、高风险决策准备时间、信息操作变化、信息完整度和 Proposal 分布进行描述性汇总；不支持直接推断生产 SLA、GMV、满意度或真实客服效率。

## 4. 验证证据

- 新增后端契约测试 `test_customer_efficiency_v1_fixture_and_assignment_are_balanced`：检查 12 组任务、4/3/5 风险覆盖、8 个槽位、48 条分配、每人 3/3 条件平衡、轮次和每个条件任务双人覆盖。
- 在 `apps/api` 执行 `.venv/bin/python -m unittest discover -s tests -v`：**23/23 通过**。
- 在 `apps/web` 执行 `npm run build`：**通过**，构建路由中包含 `/efficiency-experiment`。

## 5. 边界与待补证据

- 这是自构造模拟任务与本地浏览器记录；本阶段没有参与者、CSV 原始记录、汇总结果或业务效果。
- 此页不调用真实模型、视觉模型、真实订单、真实政策接口或真实 Tool；Stage 20 的真实模型验证仍只属于可靠性附录。
- 在两名内部试运行者完成任务质量检查、至少 8 个匿名槽位完成且导出 CSV 后，才可新建 `evals/customer-efficiency-results-v1.md` 并更新业务指标展示、Demo 讲稿或简历表述。
