# 智绣乡村生产平台

本目录用于把现有 GitHub Pages 静态原型升级为可运行、可维护、可审计的生产系统。

## 工程边界

- `web/`：公众端与管理端前端。
- `catalog-service/`：纹样目录、审核、发布门禁与审计日志。
- `ai-service/`：图片上传、分析任务、色彩分析及后续模型适配。
- `data/`：数据库模型、词表、资产审计和迁移工具。
- `contracts/`：各工作流共享的接口与状态约定。

旧站只作为视觉和内容原型，不作为真实数据、AI结果或版权状态的证明。正式系统不得返回硬编码置信度，不得把未经审核的文化释义或授权状态发布给公众。

## 第一阶段闭环

1. 管理人员导入纹样资产并登记来源与权利状态。
2. 审核后发布纹样，公众端通过 API 浏览和检索。
3. 用户上传图片，服务创建异步分析任务。
4. 服务返回真实色板；分类、相似检索由可替换模型提供方逐步接入。
5. 每项结果记录输入哈希、模型/算法版本和审核状态。

## 统一原则

- 纹样实体使用稳定 UUID，旧站 `AR-001` 等编号仅保存为 `legacy_id`。
- 文件资产以 SHA-256 去重，数据库不保存图片二进制。
- 传统纹样、裁片、别名和 AI 衍生设计分别建模。
- AI 结果只作为候选信息，不能直接覆盖正式纹样资料。
- 未核验权利的资产默认仅供内部审核，不得公开下载或商用。

## 当前交付状态

- 100 条 MVD 候选已安全物化并建立内部相似检索索引。
- 运营后台具备签名会话、`reviewer`/`publisher` 权限、CSRF 校验与安全响应头。
- 目录与 AI 服务提供 `/health` 存活检查和 `/ready` 依赖就绪检查。
- Catalog 与 AI 均支持 SQLite/PostgreSQL 双后端，AI 支持本地文件与 S3 兼容对象存储。
- 提供 SQLite 到 PostgreSQL 的幂等迁移工具，以及 PostgreSQL + MinIO 的单机 Compose 编排。
- `scripts/init-compose-env.ps1` 可一次性生成不会提交 Git 的本地随机密钥配置。
- 旧站 14 个页面已形成迁移审计清单，所有候选保持 `draft/internal_only`，高风险声明必须人工复核。

详见 [本地运行手册](RUNBOOK.md)、[容器部署说明](DEPLOYMENT.md) 与 [旧站内容迁移说明](data/LEGACY_CONTENT_MIGRATION.md)。

v0.4.0 的自动化与运行态验收结果、已完成边界及公网上线所需外部条件见 [交付验收记录](ACCEPTANCE.md)。

## 发布门禁

版本号保存在 `VERSION`。提交或打版本前从项目根目录执行：

```powershell
.\scripts\release-check.ps1
```

该命令会验证生产配置、运行 Catalog/AI/Data/Web 全部测试、审计 Python 与前端运行时依赖、在 `artifacts/sbom/` 生成 CycloneDX JSON SBOM、执行前端 lint 与生产构建，并构建三个生产容器镜像。GitHub Actions 会在每次 push 和 pull request 上执行同等检查，并保存 Python SBOM 构件。
本机 Python 不在 PATH 时可传入 `-PythonExecutable C:\path\to\python.exe`；也可准备项目内、已被 Git 忽略的 `.release-venv`，脚本会优先使用它。

本地发布检查不会自动联网安装工具。首次使用时请在联网环境执行 `python -m pip install pip-audit==2.9.0 cyclonedx-bom==7.1.0`；缺少工具时脚本会在运行审计前给出明确提示，不影响日常离线启动与测试。Catalog/AI 镜像只安装各自精确锁定的 `requirements.txt` 运行时依赖；本地测试和 CI 安装 `requirements-dev.txt`。

公网部署请使用 `compose.production.yaml` 与独立的生产环境文件，并执行 `scripts/release-check.ps1 -EnvironmentFile <path> -Production`。该模式会拒绝非 HTTPS 的公开地址或对象存储地址，并强制 AI 生产校验与安全会话 Cookie；详见 [容器部署说明](DEPLOYMENT.md)。
