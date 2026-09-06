# v0.1.0 交付验收记录

验收日期：2026-09-06（Asia/Shanghai）

## 自动化门禁

- Catalog：36 tests passed
- AI：28 tests passed
- Data：6 tests passed
- Web：45 tests passed
- ESLint、TypeScript 与 Next.js production build：passed
- Web production dependency audit：0 known vulnerabilities
- Docker Compose 配置、环境密钥预检与镜像构建：passed

统一入口：`scripts/release-check.ps1`。

## 运行态验收

- PostgreSQL、MinIO、Catalog、AI、Web 五个常驻服务均为 healthy。
- 未登录访问草稿 Catalog 详情与图片均返回 404；公众纹样页不包含草稿名称。
- 匿名注册 AI 参考资产、匿名创建 internal 分析均返回 401。
- 后台登录、审核队列、审核详情和真实文件选择控件通过浏览器验收，无错误浮层或控制台错误。
- 登录连续失败触发 429；跨站登录请求返回 403。
- 私有凭证在隔离 Catalog + MinIO 前缀中完成真实上传、SHA-256 核对、鉴权下载与匿名 401 验证，随后清理。
- 隔离 Catalog + AI 完成图片上传、参考注册、任务分配、审核批准、发布与撤回：发布后两服务公共接口均为 200，撤回后均为 404，随后清理。
- Catalog 与 AI 的 100 条现有候选状态一致；均保持 `draft/internal_only`，未发生测试误发布。
- PostgreSQL 8 张表和 MinIO 100 个对象已完成带逐对象 SHA-256 的备份及隔离恢复演练。

运行态入口：`scripts/health-check.ps1`。数据一致性入口：`scripts/check-catalog-ai-consistency.ps1`。

## 已完成的交付边界

本版本完成了静态原型到单机可交付系统的技术闭环：真实 API 与数据库、私有对象存储、数据迁移、审核与发布门禁、发布/撤回跨服务补偿、审计、后台会话与 CSRF、上传分析、色板、可解释图像特征与相似检索、任务恢复、备份恢复、环境预检、CI 和运行态安全检查。

## 外部上线前提

以下事项不能由本地代码替代，需项目负责人提供或确认后才能完成公网生产上线：

1. 逐条提供并审核 100 条候选的可信来源、版权凭证与文化释义；当前正式发布数量为 0。
2. 提供域名、HTTPS 证书、托管环境、密钥托管、异机加密备份位置和告警接收人。
3. 确认多人审核职责分离规则，并选择正式身份提供方。
4. 提供上传图片的隐私政策、保存期限与删除流程。
5. 如需语义分类或生成，选择模型、预算与密钥，并提供标注/评测数据和准确率验收标准；当前系统如实声明这些能力不可用，不返回伪造结果。
6. 如需多实例水平扩容，部署独立分布式任务队列；v0.1.0 提供的是单实例持久任务恢复与安全重试。

