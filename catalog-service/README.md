# 纹样目录服务

FastAPI + SQLite 的最小正式目录 API。公开查询只返回同时满足 `status=published` 和 `visibility=public` 的记录；CSV 和 JSON 批量导入均强制保存为 `draft/internal_only`。

## 启动

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:CATALOG_ADMIN_TOKEN="replace-with-a-long-random-token"
uvicorn app.main:app --reload --port 8000
```

环境变量：

- `CATALOG_DATABASE_PATH`：SQLite 文件路径，默认 `catalog.db`
- `CATALOG_DATABASE_BACKEND`：`sqlite`（默认）或 `postgresql`
- `CATALOG_DATABASE_URL`：选择 PostgreSQL 时必填，例如 `postgresql://user:pass@host/db`

PostgreSQL 会自动初始化等价 schema，JSON 字段使用 JSONB，时间使用 TIMESTAMPTZ。从现有 SQLite 幂等迁移（保留纹样 ID、审计 ID、审核状态和 JSON 语义）：

```bash
CATALOG_DATABASE_BACKEND=postgresql CATALOG_DATABASE_URL=postgresql://... python -m app.migrate_sqlite_to_postgres --source ./catalog.db
```

迁移使用主键 upsert，可安全重复执行；纹样和审计日志在同一 PostgreSQL 事务内提交。
- `CATALOG_ENVIRONMENT`：设为 `production` 时禁止使用默认管理令牌
- `CATALOG_ADMIN_TOKEN`：开发管理令牌；默认值仅供本地开发
- `CATALOG_ACTOR_SIGNING_SECRET`：Web 到 Catalog 的操作者身份签名密钥，生产环境至少 32 字符且必须与管理令牌分离
- `CATALOG_CORS_ORIGINS`：逗号分隔的前端 Origin，默认 `http://localhost:3000`
- `CATALOG_AI_INTERNAL_BASE_URL`：AI 服务内部 API 根地址（包含 `/v1`）
- `CATALOG_AI_SERVICE_TOKEN`：Catalog 调用 AI 内部同步接口的服务令牌
- `CATALOG_AI_SYNC_TIMEOUT_SECONDS`：单次 AI 同步超时，默认 5 秒

生产环境必须覆盖管理令牌，并同时配置 AI 内部地址与服务令牌；不要把任一令牌暴露给浏览器。

当前 SQL 仍包含 SQLite 占位符和 JSON1 查询，因此 PostgreSQL 不能只靠替换连接字符串启用。迁移时应实现 repository/transaction 适配器并运行契约测试；在此之前，选择其他数据库后端会快速失败，避免静默回落 SQLite。SQLite 已启用 WAL、外键和 10 秒 busy timeout，定位仍是单实例部署。

## API

- `GET /health`
- `GET /ready`：实际执行数据库探测，并返回当前持久化后端
- `GET /api/v1/patterns?page=1&pageSize=20&q=云纹&category=自然纹`
- `GET /api/v1/patterns/{id}`
- `POST /api/v1/admin/patterns`
- `POST /api/v1/admin/patterns/import`，最多 500 条且强制草稿/内部
- `PATCH /api/v1/admin/patterns/{id}`，用于普通资料编辑；不能进入或离开公开发布状态
- `PATCH /api/v1/admin/patterns/{id}/evidence`，合并更新来源说明、版权凭证附件元数据、核验事实与内部审核备注
- `POST /api/v1/admin/patterns/{id}/evidence-files`，以 `multipart/form-data` 的 `file` 字段上传真实版权凭证
- `GET /api/v1/admin/patterns/{id}/evidence-files/{evidenceId}`，鉴权后以禁止缓存的附件响应下载凭证
- `GET /api/v1/admin/patterns`，支持 `status`、`visibility`、`risk` 筛选
- `GET /api/v1/admin/patterns/{id}`，读取内部候选详情
- `GET /api/v1/admin/patterns/stats?categoryTop=10`，读取数据治理汇总和高频分类
- `GET /api/v1/admin/review-queues/summary?lowResolutionEdge=256`，汇总低清、名称待核、重复名称、待分类和分类建议数量
- `GET /api/v1/admin/review-queues/patterns?queue=low_resolution&page=1&pageSize=20`，分页读取专项审核队列；`queue` 还支持 `all`、`name_review`、`duplicate_name`、`uncategorized`、`category_suggestion`，并可用 `q` 和 `suggestion` 筛选
- `GET /api/v1/admin/patterns/export.csv?status=draft&visibility=internal_only&risk=rights_unverified&limit=1000`，导出筛选结果
- `POST /api/v1/admin/patterns/{id}/publish`，执行安全发布
- `POST /api/v1/admin/patterns/{id}/withdraw`，先从 AI 撤回，再将 Catalog 恢复为草稿/内部状态
- `POST /api/v1/admin/patterns/batch-review`，逐条写入真实复核人、时间和风险项，最多 100 条
- `POST /api/v1/admin/patterns/batch-publish`，逐条执行门禁与 AI 同步，最多 100 条
- `GET /api/v1/admin/patterns/{id}/audit-logs`

管理员请求需携带：

```http
X-Admin-Token: replace-with-a-long-random-token
```

Web 发起的变更请求还会携带经 `CATALOG_ACTOR_SIGNING_SECRET` 做 HMAC-SHA256 签名的 `X-Admin-Actor`、`X-Admin-Timestamp`、`X-Request-ID` 和 `X-Admin-Signature`。签名覆盖时间戳、HTTP 方法、路径、操作者和请求 ID，Catalog 仅接受五分钟窗口内的完整有效签名并将操作者写入审计日志。仅携带管理令牌的维护脚本保持兼容，其审计身份固定为 `service-admin`。

响应的核心字段兼容 Web `Pattern` 类型，并额外保留 `visibility`、`source`、`rights`、`review` 和时间戳。

来源与版权治理信息继续存放在既有 JSON/JSONB 字段中，因此旧数据无需迁移；缺失的新字段会使用兼容默认值。`source.description` 保存来源说明，`rights.evidence[]` 保存附件元数据（文件 ID、名称、类型、大小、存储键、SHA-256 和备注），真实文件由上传接口写入私有 S3/MinIO 前缀。服务端生成对象键和文件 ID，并以文件魔数校验 PDF/JPEG/PNG，默认大小上限 10 MiB；SHA-256 由服务端对实际字节计算，不能由客户端伪造。`rights.verifiedBy/verifiedAt/verificationNote` 保存版权核验事实，`review.note` 保存内部审核备注。元数据更新接口采用字段合并语义并写入 `evidence_updated`；真实文件上传写入 `evidence_file_uploaded` 审计记录。

审核结论只覆盖审核当时的内容。普通资料、来源与权属元数据或真实凭证文件发生实际变化时，已有 `approved`、`rejected` 或 `needs_more` 任务会原子重置为 `assigned`，清空决定备注、决定人和决定时间，并写入包含任务前后快照的 `review_invalidated` 审计；完全相同的重复提交不会让结论失效。发布流程在最终数据库写入前再次确认任务仍为 `approved`，避免审核后并发修改被公开。系统不会因此自动批准或发布。

下载接口不会暴露预签名地址或对象存储凭证，只允许管理员令牌鉴权后通过 Catalog 代理读取已登记在该纹样下的对象；响应设置 `private, no-store` 和 `nosniff`。Catalog 使用独立于 AI 的 `CATALOG_S3_ACCESS_KEY` 身份，MinIO 策略只允许访问 `CATALOG_S3_PREFIX` 下的对象。可用 `CATALOG_EVIDENCE_MAX_BYTES` 调整上传上限。

公开 API 会清空 `rights.evidence`、`rights.verificationNote` 和 `review.note`，避免泄露内部存储位置与审核意见；管理员 API 保留完整数据。已公开记录不能通过凭证接口把版权状态降为未核验，必须先撤回公开状态。

治理统计包含总数、`draft/published/archived` 数量、各版权状态数量、存在审核风险数、版权未核验数、满足发布门禁数，以及按数量排序的分类分布。`categoryTop` 允许 `0–50`，设为 `0` 时不返回分类排行。统计接口不会把“满足门禁”自动视为已审核或已发布。

## MVD 数据审核准备

审核准备工具读取 `data/output/mvd/catalog_seed.csv` 并与当前 catalog 数据库对照，稳定生成 CSV 和 JSON 报告。报告含原始路径、来源 locator、对象键、SHA-256、字节数、尺寸、分类建议，以及低清、名称待核、同名和相同哈希组风险。默认阈值为任一边小于 256 像素即标记低清。

```powershell
# 默认 dry-run：只写报告，不修改数据库
python -m app.review_readiness --database catalog.db

# 明确申请后才回填可验证的 seed 来源定位信息
python -m app.review_readiness --database catalog.db --apply
```

命令应从 `catalog-service` 目录运行；默认报告目录是 `data/output/mvd/review-readiness/`，也可用 `--seed`、`--output` 和 `--low-res-edge` 覆盖。输出不含生成时间，记录和风险均稳定排序，便于重复运行与版本比较。

`--apply` 仅把 locator、原始路径、对象键、哈希、字节数和尺寸合并到 `source_json.seedProvenance`，且只处理数据库中已存在的 pattern；它不会写分类正式字段，因为当前 schema 没有独立“分类建议”列，也绝不会修改名称、rights、review、状态、可见性、批准或发布。实际变更会写入 `audit_logs`，相同输入再次运行不会重复写入。

专项审核队列是管理员只读接口，不产生审计或数据库写入。低清判断读取 `source.seedProvenance.width/height`（缺失尺寸也进入低清待核），重复名称会忽略空白和大小写；待分类只检查正式分类是否为空、`待分类`、`未分类` 或 `unknown`。分类建议仅从 `seedProvenance.categorySuggestion`、`categorySuggestionCode/Label`、`motifCodeDraft` 或 legacy category 元数据派生并单独返回，绝不覆盖正式 `category`，也不修改 rights、review、status、visibility 或审核任务。

CSV 导出与管理列表共用 `status`、`visibility`、`risk` 筛选定义，默认最多 1000 行、硬上限 5000 行，并通过 `X-Exported-Rows` 返回本次行数。文件采用带 BOM 的 UTF-8，复杂字段序列化为 JSON；以 `= + - @` 或控制字符开头的文本会转义为普通文本，防止 Excel 等表格程序执行公式。导出接口仅接受管理员令牌且响应禁止缓存。

发布属于服务端强约束：名称必须非空、`rights.status` 必须为 `verified`、`review.issues` 必须为空，且对应 `review_tasks.state` 必须为 `approved`。新建和普通 PATCH 都不能把记录置为 `published/public`，也不能把已发布记录直接改回内部状态；这些转换只能经过专用发布/撤回接口。创建、编辑、发布和撤回都会写入审计日志。

批量接口采用逐条结果语义，HTTP 200 不代表全部成功；响应中的 `succeeded`、`failed` 和每个 `items[].code` 才是批次结果。失败条目不会回滚已成功条目，可用原 `patternId` 安全重试。批量审核只记录调用者明确提交的审核事实，不会修改或伪造版权核验状态。

发布时 Catalog 先调用 AI 的幂等接口：

```http
PUT /v1/internal/references/by-pattern/{id}/publication
X-Service-Token: ...
Content-Type: application/json

{"published": true}
```

只有 AI 同步成功后 Catalog 才公开记录。AI 不可用时该条保持原状态并写入 `publish_sync_failed` 审计，随后可重试。若同步后数据库提交异常，Catalog 会尽力发送 `published:false` 补偿。开发环境未配置 AI 地址时保留单服务调试能力并在发布审计中标记 `aiSync=not_configured`；生产环境启动时强制要求完整配置。

撤回使用相反顺序：先向 AI 发送 `published:false`，成功后再把 Catalog 改为 `draft/internal_only`。AI 失败时 Catalog 保持公开并记录 `withdraw_sync_failed`；若 AI 已撤回但数据库提交失败，Catalog 会尽力发送 `published:true` 反向补偿，避免两边长期分裂。

## 导入清洗候选 CSV

在本服务目录执行：

```powershell
python -m app.import_csv ..\data\output\clean\normalized_candidates.csv
```

也可指定数据库：

```powershell
python -m app.import_csv ..\data\output\clean\normalized_candidates.csv --database .\catalog.db
```

命令可重复执行，使用来源信息生成稳定 ID，并做更新式导入。无论 CSV 中原状态为何，最终均为 `draft/internal_only`，必须经人工审核后再通过管理员接口发布。

## 测试

```powershell
pytest -q
```
