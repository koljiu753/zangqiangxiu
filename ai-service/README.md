# Zhixiu AI Service

FastAPI AI任务服务骨架。当前已经真实实现图片上传、内容校验、SHA-256去重、图片元数据读取、SQLite任务持久化、基于实际像素的主色提取，以及不依赖外部模型的相似检索基线。内置 embedding 复用相似检索的 128 维可解释特征并返回明确算法版本；分类和生成能力使用可替换 Provider 接口，未配置时明确返回 `unavailable`，不会制造固定置信度或伪造结果。

## 启动

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8001
```

访问 `http://127.0.0.1:8001/docs` 查看OpenAPI交互文档。

## API流程

1. `POST /v1/assets`：multipart字段名为`image`，允许JPEG/PNG/WebP，返回`asset_id`、SHA-256和真实尺寸。
2. `POST /v1/analyses`：提交`asset_id`、`tasks`及`palette_colors`，返回202任务。
3. `GET /v1/jobs/{job_id}`：查询任务状态和`result_id`。
4. `GET /v1/analyses/{result_id}`：取得主色及可选Provider输出。
5. `GET /v1/capabilities`：读取当前真实 Provider、版本、维度及可用状态；内置特征明确标记为非语义 embedding。

参考库与相似检索：

1. 先上传参考图，再由可信服务调用`POST /v1/references`提交`asset_id`和可选`label`；必须携带 `X-Service-Token`，浏览器和匿名调用方不能注册或自报公开参考。
2. `GET /v1/references`可检查当前索引。
3. 分析任务加入`"similar"`并设置`top_k`，结果返回动态排序的`asset_id`、`pattern_id`、标签、分数和算法版本。

纹样图片访问与目录关联：

1. `GET /v1/references/by-pattern/{pattern_id}`：按目录纹样 ID 查询已审核且公开的参考资产。
2. `GET /v1/assets/{asset_id}/content`：读取公开原图；增加 `thumbnail=480` 可生成最长边不超过 480 像素的 WebP 缩略图（范围 64–1600）。
3. 两个接口均可增加 `scope=internal` 访问内部候选，但必须携带 `X-Service-Token`，令牌来自 `ZHIXIU_AI_INTERNAL_TOKEN`。内部响应使用 `private, no-store`，公开响应可缓存一小时。

Reference 响应包含相对地址 `content_url` 与 `thumbnail_url`。公开请求即使知道资产 ID，也只能读取同时满足 `review_status=approved` 和 `visibility=public` 的参考资产；不存在与无权访问统一返回 404，避免泄露内部资产是否存在。`GET /v1/references` 同样默认只列出公开已审核资产，内部全量列表需要服务令牌。

Catalog 发布状态可通过内部幂等接口同步到 AI 参考库：

```http
PUT /v1/internal/references/by-pattern/{pattern_id}/publication
X-Service-Token: <ZHIXIU_AI_INTERNAL_TOKEN>
Content-Type: application/json

{"published": true}
```

`published=true` 将该纹样关联的参考资产设为 `approved/public`，`false` 将其撤回为 `draft/internal_only`。相同请求可安全重试；关联不存在时返回 404 和错误码 `REFERENCE_NOT_FOUND`，令牌无效返回 401。该接口是服务间接口，不应由浏览器直接调用。

相似分析的`scope`默认是`public`，只检索同时满足`review_status=approved`和`visibility=public`的参考资产。管理端可显式传`scope=internal`查看内部草稿，但创建请求、后续任务查询和结果查询都必须携带 `X-Service-Token`；公共前端不得使用内部作用域。参考注册本身也需要服务令牌，若不传审核字段，安全默认值为`draft/internal_only`。

相似基线`interpretable-rgbhist4-gray8-v1`使用64维RGB联合直方图和8×8灰度缩略图，共128维。两部分分别归一化，最终分数为颜色余弦相似度和空间灰度余弦相似度的均值。它是可解释且可复现的工程基线，不代表语义或文化含义判断；以后可在保持API契约的前提下替换为经过评测的视觉Embedding。

示例请求体：

```json
{
  "asset_id": "上传返回的UUID",
  "tasks": ["palette", "embedding", "classification"],
  "palette_colors": 5,
  "top_k": 5
}
```

## 批量建立MVD内部索引

先启动服务，再执行：

```powershell
python -m app.bulk_index `
  --manifest ../data/output/mvd/asset_manifest.json `
  --base-url http://127.0.0.1:8001 `
  --report data/mvd_index_report.json
```

批量工具从 `ZHIXIU_AI_INTERNAL_TOKEN` 读取服务令牌，也可显式传入 `--service-token`；不要把真实令牌写入命令历史或报告。

Manifest接受顶层数组或`{"records": [...]}`。每条记录须含`pattern_id`、`candidate_name`，以及`local_path`、`source_path`、`file_path`、`original_relative_path`之一（也兼容`asset.source_path`）；相对路径以manifest所在目录解析。工具通过正式API上传并注册，不直接篡改数据库。上传端按SHA-256去重，注册端按`asset_id`更新，因此重复执行幂等。每条结果写入报告，单条失败不会中断整批。

无论manifest原值为何，此MVD工具都会强制写入`review_status=draft`、`visibility=internal_only`。候选名称不得作为已审核知识公开。

## 持久化与文件

默认数据目录为本目录下`data/`，包含SQLite数据库和`uploads/`。可用环境变量覆盖：

- `ZHIXIU_AI_DATA_DIR`
- `ZHIXIU_AI_DATABASE_BACKEND`：支持 `sqlite`（默认）或 `postgresql`
- `ZHIXIU_AI_DATABASE_URL`：选择 `postgresql` 时必填
- `ZHIXIU_AI_ASSET_BACKEND`：支持 `local`（默认）或 `s3`
- `ZHIXIU_AI_S3_BUCKET`：选择 `s3` 时必填
- `ZHIXIU_AI_S3_REGION`、`ZHIXIU_AI_S3_PREFIX`、`ZHIXIU_AI_S3_ENDPOINT_URL`：S3兼容存储的可选配置
- `ZHIXIU_AI_ENVIRONMENT`：部署环境标识，默认 `development`
- `ZHIXIU_AI_MAX_UPLOAD_BYTES`（默认10 MiB）
- `ZHIXIU_AI_MAX_IMAGE_PIXELS`（默认2500万像素）
- `ZHIXIU_AI_CORS_ORIGINS`（逗号分隔，默认仅允许本机3000端口的localhost与127.0.0.1）
- `ZHIXIU_AI_INTERNAL_TOKEN`：Web 服务端等可信内部调用方使用的独立令牌；生产环境必填，不得加 `NEXT_PUBLIC_` 前缀或发送到浏览器

SQLite和本地文件是最小可运行方案，适合单实例验收。服务现已提供PostgreSQL元数据与S3兼容对象存储后端。分析任务先写入数据库，再由响应后的后台任务执行；服务启动时会把上次异常退出遗留的 `running` 任务重置为 `pending`，并按创建顺序恢复全部未完成任务。领取任务使用条件更新，同一进程中的重复调度不会重复执行。

可信运维方可用 `GET /v1/internal/jobs/stats` 查看各状态数量和本次启动恢复数；失败任务可通过 `POST /v1/internal/jobs/{job_id}/retry` 安全重试。这两个接口都要求 `X-Service-Token`。对已经成功或仍在运行的任务重复调用 retry 不会重新执行。

当前恢复机制面向单个活动 AI 服务实例，启动恢复完成后服务才进入 ready。需要水平扩容、任务超时租约或高吞吐时，仍应引入独立可靠任务队列，不能把本实现描述为分布式队列。

本地二进制文件通过`LocalAssetStore`以临时文件加原子替换方式写入。`S3AssetStore`提供同等的`initialize`、`put`、`resolve`、`check`能力，并为需要本地`Path`的图像算法提供按需下载缓存。系统不会把未知或不可用的后端悄悄回落成本地存储。`GET /ready`会同时探测数据库与对象存储，供编排平台配置readiness probe；`GET /health`保留兼容响应。

## 接入模型

在`app/providers.py`中实现`EmbeddingProvider`、`ClassificationProvider`或`GenerationProvider`，启动时将实例注入`app.state`。Provider必须返回真实模型输出和明确的模型版本；Embedding Provider 还应声明实际 `dimensions` 和是否为 `semantic`。生成Provider已经定义边界，但本阶段没有暴露生成API，避免在没有模型与审核链路时伪装可用。分类 Provider 未配置时只返回 `unavailable`，不得从文件名、颜色或候选标签推断文化类别及置信度。

## 测试

```powershell
pytest -q
```

测试覆盖健康检查、真实图片验证、哈希与去重、非图片拒绝、实际双色主色提取、真实能力声明、未配置Provider的显式降级、动态相似排序、不同查询产生不同结果、公开参考注册绕过防护、内部分析创建/任务/结果全链路鉴权、进程中断任务恢复、失败任务授权重试、任务统计鉴权、CORS、资源不存在及OpenAPI路径。
# Cloud backends

Local SQLite and filesystem storage remain the defaults. PostgreSQL metadata:

```bash
export ZHIXIU_AI_DATABASE_BACKEND=postgresql
export ZHIXIU_AI_DATABASE_URL='postgresql://user:password@host:5432/database?sslmode=require'
```

Private S3-compatible object storage (AWS S3, MinIO and compatible providers):

```bash
export ZHIXIU_AI_ASSET_BACKEND=s3
export ZHIXIU_AI_S3_BUCKET=private-bucket
export ZHIXIU_AI_S3_REGION=ap-southeast-1
export ZHIXIU_AI_S3_PREFIX=production/ai-assets
# Set ZHIXIU_AI_S3_ENDPOINT_URL only for a compatible non-AWS endpoint.
```

Credentials use the standard AWS credential chain; do not put keys in source control.
The bucket must be private and the service identity needs only `HeadBucket`, `PutObject`
and `GetObject` for the configured prefix. Startup fails instead of silently falling
back when a selected cloud backend is unavailable.

To copy existing metadata idempotently (rows already present are retained):

```bash
python -m app.migrate_metadata --sqlite data/ai-service.sqlite3 \
  --database-url "$ZHIXIU_AI_DATABASE_URL"
```

This command does not copy binaries. Upload source assets to the configured object
store before switching, or rebuild both metadata and objects with the existing
`python -m app.bulk_index` HTTP workflow. S3/PostgreSQL code paths have unit coverage;
no external cloud account was exercised by this repository test suite.
