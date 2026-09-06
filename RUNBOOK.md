# 本地联调运行手册

需要三个终端，均从本目录进入对应子目录运行。

## 1. 目录服务

```powershell
cd catalog-service
$env:CATALOG_ADMIN_TOKEN="请替换为本地随机值"
$env:CATALOG_ENVIRONMENT="development"
$env:CATALOG_DATABASE_BACKEND="sqlite"
python -m app.import_csv ..\data\output\mvd\catalog_seed.csv --database .\catalog.db
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

导入的100条候选始终是 `draft/internal_only`，公开接口返回空列表属于正确的安全行为。必须经过来源、版权和文化审核后，才能通过管理接口改成 `published/public`。

## 2. AI服务

```powershell
cd ai-service
$env:ZHIXIU_AI_CORS_ORIGINS="http://localhost:3000,http://127.0.0.1:3000"
$env:ZHIXIU_AI_ENVIRONMENT="development"
$env:ZHIXIU_AI_DATABASE_BACKEND="sqlite"
$env:ZHIXIU_AI_ASSET_BACKEND="local"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8002
```

首次启动后，可在另一个终端把100条内部候选建立为相似检索参考索引：

```powershell
cd ai-service
python -m app.bulk_index ..\data\output\mvd\asset_manifest.json --base-url http://127.0.0.1:8002 --report .\data\mvd_index_report.json
```

该命令会强制把候选登记为 `draft/internal_only`；重复执行不会造成资产或索引膨胀。

本机8000端口在联调时被其他程序占用，因此开发示例使用8002。正式部署可按环境调整。

## 3. Web

```powershell
cd web
$env:NEXT_PUBLIC_CATALOG_API_BASE_URL="http://127.0.0.1:8001/api/v1"
$env:NEXT_PUBLIC_AI_API_BASE_URL="http://127.0.0.1:8002/v1"
$env:NEXT_PUBLIC_ALLOW_DEMO_FALLBACK="true"
$env:CATALOG_API_INTERNAL_BASE_URL="http://127.0.0.1:8001/api/v1"
$env:CATALOG_ADMIN_TOKEN="与目录服务相同的本地随机值"
$env:ADMIN_UI_USER="admin"
$env:ADMIN_UI_PASSWORD="请替换为强密码"
$env:ADMIN_UI_ROLE="publisher"
$env:AUTH_SESSION_SECRET="请替换为至少32字节的随机值"
$env:ADMIN_ALLOW_BASIC_AUTH="true"
npm run dev
```

访问：

- 首页：`http://localhost:3000/`
- 纹样库：`http://localhost:3000/patterns`
- AI工作台：`http://localhost:3000/studio`
- 运营审核后台：`http://localhost:3000/admin`
- 目录API文档：`http://127.0.0.1:8001/docs`
- AI API文档：`http://127.0.0.1:8002/docs`

`/admin/login` 会签发 8 小时 HttpOnly 会话。`reviewer` 可以编辑，只有 `publisher` 可以发布。本地可保留 Basic Auth；生产环境应关闭 `ADMIN_ALLOW_BASIC_AUTH`、使用 HTTPS，并接入正式身份提供方。

服务编排应分别探测 `GET /health`（进程存活）和 `GET /ready`（数据库/资产存储可用）。PostgreSQL 与 S3 兼容存储已经实现；完整单机编排、迁移与备份边界见 `DEPLOYMENT.md`。扩展多实例前仍需补可靠任务队列并验证并发语义。

## 验证命令

```powershell
cd web
npm run lint
npm test -- --run
npm run build

cd ..\catalog-service
pytest -q

cd ..\ai-service
pytest -q

cd ..\data
python -m unittest discover -s tests -v
```
