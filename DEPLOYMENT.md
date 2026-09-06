# 单机容器部署

该编排用于本地验收或单机部署，包括 Web、Catalog、AI、PostgreSQL 和 MinIO。Catalog 与 AI 的元数据实际写入 PostgreSQL；AI 原始图片实际写入 MinIO 私有桶，本地卷只保存可重建的图片读取缓存。

## 启动

要求 Docker Engine 及 Compose v2。

```powershell
.\scripts\init-compose-env.ps1
# 脚本首次运行会生成随机强密钥；已有 .env 不会被覆盖
docker compose config --quiet
docker compose up --build -d
docker compose ps
```

发布或升级前必须先通过配置预检；它会拒绝缺失项、示例占位符和过短密钥：

```powershell
.\scripts\preflight.ps1
.\scripts\release-check.ps1
```

紧急情况下可以用 `-SkipContainerBuild` 只执行配置、测试、lint 和 Web 生产构建，但正式发布验收不得跳过镜像构建。

访问地址：Web `http://localhost:3000`，Catalog API `http://localhost:8001/docs`，AI API `http://localhost:8002/docs`，MinIO Console `http://localhost:9001`。端口默认只绑定到本机回环地址；对外提供服务时应由 HTTPS 反向代理转发 Web/API，不要直接暴露数据库或对象存储端口。

首次启动时 Catalog 与 AI 会分别幂等创建自己所需的 PostgreSQL 表，`minio-init` 会幂等创建私有桶（默认 `zhixiu-assets`）。不要把 `data/migrations/001_core.sql` 挂到此数据库的自动初始化目录：该文件是领域数据模型草案，不是两个运行时服务的 schema。

本地 MinIO 在容器网络中使用 HTTP，因此模板把 `AI_ENVIRONMENT` 设为 `development`。真正生产环境必须给 S3/MinIO endpoint 配置 HTTPS，再把该值改为 `production`；否则 AI 服务会拒绝启动。

本地 Web 同样通过 HTTP 访问，因此 Compose 显式设置 `AUTH_COOKIE_SECURE=false`。部署 HTTPS 反向代理后必须删除该覆盖或改为 `true`，保证管理会话 Cookie 仅经 HTTPS 发送。

## 状态与日志

```powershell
docker compose ps
docker compose logs --tail 200 catalog ai web
Invoke-RestMethod http://localhost:8001/ready
Invoke-RestMethod http://localhost:8002/ready
```

Catalog 等待 PostgreSQL 就绪，AI 等待 PostgreSQL 就绪且 MinIO 私有桶创建成功，Web 再等待两个业务 API 就绪。当前镜像仍使用单 worker，扩容前还需验证后台任务并发语义和缓存行为。

## 从已有 SQLite 迁移

Compose 首次启动并通过健康检查后，可把已有 SQLite 文件只读挂入一次性迁移容器。以下命令在 PowerShell 中执行；迁移均为幂等操作：

```powershell
docker compose run --rm --no-deps `
  -v "${PWD}/catalog-service/catalog.db:/migration/catalog.db:ro" `
  catalog python -m app.migrate_sqlite_to_postgres --source /migration/catalog.db

docker compose run --rm --no-deps `
  -v "${PWD}/ai-service/data/ai-service.sqlite3:/migration/ai.sqlite3:ro" `
  ai sh -c 'python -m app.migrate_metadata --sqlite /migration/ai.sqlite3 --database-url "$ZHIXIU_AI_DATABASE_URL"'
```

AI 元数据迁移不复制二进制图片。已有本地图片应通过 `python -m app.bulk_index` 的正式 HTTP 流程重新上传，这会同时写入 MinIO 对象与 PostgreSQL 元数据。

日常备份至少覆盖 `postgres-data` 和 `minio-data` 两个权威数据卷。`ai-cache` 仅为可重建缓存，无需作为权威备份；实际使用的 `.env` 应进入密码管理器，不应提交 Git。

查看卷名：

```powershell
docker volume ls --filter label=com.docker.compose.project=zhixiu
```

停止容器但保留数据使用 `docker compose down`。`docker compose down -v` 会删除全部命名卷和数据，不应在有业务数据时执行。

## 上线边界

- `NEXT_PUBLIC_*` 值在 Web 镜像构建时固化；域名变化后需重新构建 Web 镜像。
- 生产环境应为 Web、Catalog、AI 配置 HTTPS、访问日志、指标与异地备份。
- 数据库密码会嵌入 PostgreSQL URL，模板中请使用 URL-safe 的高强度随机值；托管环境优先直接注入完整连接 URL 和工作负载身份。
- MinIO 根凭据目前同时作为 AI 服务凭据，适合单机验收。正式环境应创建只允许目标桶与前缀执行 `HeadBucket`、`PutObject`、`GetObject` 的独立服务账号。
- 当前登录是单一运营账号模型。面向多人运营前应接入正式身份提供方与独立用户审计身份。
