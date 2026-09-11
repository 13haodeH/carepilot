# 阶段十五工作记录：Supabase Auth、三端分权与中文界面

## 目标

以 Supabase Auth 取代演示账号与浏览器伪 Session：普通注册账号只能成为 `user`，客服为 `admin`，全局管理者为 `superadmin`。三种身份分别使用用户端、客服工作台和管理后台。

## 决策与实现

- 新增 `data/008_supabase_auth_rbac.sql`：`profiles` 关联 `auth.users`，注册触发器强制默认角色为 `user`；角色不能从浏览器写入。
- API 仅接受 Supabase Bearer JWT，并经 JWKS 验签后读取 `profiles`。前端隐藏入口不是权限判断；工单、审批、政策、配置和评测接口都有服务端角色校验。
- `user` 只能读取自己的订单/工单并提交材料；`admin` 处理客服工单；`superadmin` 才能访问政策、配置和评测。
- 删除旧 `app_users/app_sessions` 演示身份表，避免在 CarePilot 业务表保存密码哈希或自建 Session。
- 通过 `scripts/provision_demo_auth.py` 使用 Supabase Auth Admin API 创建/更新三组 Demo Auth 账号。初始密码只从忽略的环境变量读取，不被数据库业务表或日志保存。
- 用户端与客服工作台改为浅色中文界面；内部状态在展示时映射为“已提交、正在处理、待补充材料、等待客服确认、已处理”等可理解文案。

## 验证

- API 单元测试：17 项通过，包含 `user/admin/superadmin` 服务端边界检查。
- Web 构建：`npm run build` 通过，包含 `/login`、`/register`、`/consumer`、`/ops`、`/admin` 路由。

## 外部执行门槛

1. 项目负责人执行 `008_supabase_auth_rbac.sql`。
2. 在 Supabase 开启 Email/password，并在 Web 环境填写 publishable key。
3. 项目负责人设置三组 Demo 初始密码后，本地运行预置脚本；随后用三个真实 Auth 账号完成登录与分权冒烟。

## 边界

真实身份、JWT 校验和模型调用已接入；订单与物流 Tool 仍是受控脱敏演示数据，尚未连接真实商家业务系统。高风险真实模型接管与真实图片 Evidence 将在 Auth 端到端验收后单独运行并记录成本。
