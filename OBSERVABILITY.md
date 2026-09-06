# 可观测性与现场诊断

项目提供两个 PowerShell 入口，适用于本地 Docker Compose 部署。脚本不会打印 Compose 展开配置或容器环境变量，避免把数据库、MinIO、后台登录和会话密钥写入日志。

## 快速健康检查

在项目根目录运行：

```powershell
.\scripts\health-check.ps1
```

脚本检查以下项目：

- Docker daemon 可访问；
- PostgreSQL、MinIO、Catalog、AI、Web 五个常驻容器均在运行且健康；
- PostgreSQL 可通过 `pg_isready` 接受连接；
- MinIO readiness 端点可访问；
- Web 首页、Catalog `/ready`、AI `/ready` 返回成功 HTTP 状态。
- Web、Catalog、AI 都会回送 `X-Request-ID`，健康检查会用自定义 ID 验证原值传播。

## 请求关联与结构化日志

三个 HTTP 服务统一使用 `X-Request-ID`。入站值仅在由 1–100 个字母、数字、`.`、`_`、`:` 或 `-` 组成时被保留，否则生成 UUID；响应始终携带最终 ID。Web Studio 调用 AI、Catalog 发布同步调用 AI 时会继续传递该 ID。

访问日志为单行 JSON，关键字段包括 `level`、`event`、`service`、`request_id`、`method`、`path`、`status` 和 `duration_ms`。未处理异常另外输出 `request.failed` 事件和 `error_type`，不记录请求体、令牌或 Cookie。可使用请求 ID 在 Compose 日志中关联检索：

```powershell
docker compose logs web catalog ai | Select-String 'health-<request-id>'
```

全部通过时退出码为 `0`；任一检查失败时退出码为 `1`，可直接接入 CI、部署脚本或定时任务：

```powershell
.\scripts\health-check.ps1
if ($LASTEXITCODE -ne 0) { throw "部署健康检查失败" }
```

## 采集诊断包

出现服务不可用、容器重启或磁盘压力时运行：

```powershell
.\scripts\diagnose.ps1
```

默认在 `diagnostics/<时间戳>/` 保存：容器状态、镜像列表、每个容器的运行状态、各服务最近 120 行带时间戳日志、Docker 磁盘占用，以及完整健康检查结果。诊断脚本沿用健康检查的退出码。

可调整日志行数和输出目录：

```powershell
.\scripts\diagnose.ps1 -Tail 300 -OutputDirectory C:\temp\zhixiu-diagnostics
```

分享诊断包前仍应人工检查业务日志中是否包含用户提交内容。不要把项目 `.env`、`docker compose config` 输出或容器环境变量加入诊断包。

## 日常检查建议

### Catalog 与 AI 状态一致性

发布后可运行只读检查：

```powershell
.\scripts\check-catalog-ai-consistency.ps1
```

脚本通过 Catalog 管理 API 和 AI 内部 API 分页读取数据，报告三类漂移：Catalog 记录缺少 AI reference（`missing`）、发布状态不一致（`mismatch`）、AI reference 找不到 Catalog 记录（`orphan`）。一致时退出码为 `0`，发现漂移时为 `2`，请求或配置失败时为 `1`。令牌只从进程环境或项目 `.env` 读取，不会写入输出。

该检查适合在批量导入、审核发布和恢复操作后运行。`missing` 与 `orphan` 需要人工核对资产映射；不要自动创建或删除资产。

- 发布后立即运行一次健康检查。
- 将健康检查设为 1–5 分钟一次；连续失败再告警，降低短暂重启导致的噪声。
- 关注 `docker system df` 的持续增长，并为宿主机磁盘空间设置告警。
- 故障发生后先采集诊断包，再重启容器，以保留现场日志与健康状态。
