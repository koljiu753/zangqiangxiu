# 跨服务契约

## 资源标识

- `pattern_id`：独立纹样实体 UUID。
- `asset_id`：图片或文档资产 UUID。
- `job_id`：异步任务 UUID。
- `legacy_id`：旧站临时编号，不得作为主键。

## 分析任务状态

`queued -> processing -> succeeded | failed | cancelled`

前端必须展示服务端返回的真实状态。网络失败、模型失败或非法文件不得降级为固定成功结果。

## 最小接口

- `POST /v1/assets`：上传图片，返回 `asset_id`、SHA-256、尺寸和权利状态。
- `POST /v1/analyses`：创建分析任务，返回 `job_id`。
- `GET /v1/jobs/{job_id}`：查询进度和错误。
- `GET /v1/analyses/{analysis_id}`：读取色板、分类候选、相似纹样与算法版本。
- `GET /api/v1/patterns`：公众端读取已发布纹样。
- `GET /api/v1/patterns/{pattern_id}`：读取纹样详情。

## 结果约束

- 分类候选必须包含 `taxonomy_id`、`label`、`confidence` 和 `model_version`。
- 低置信度返回 `unknown` 或 `review_required`，不允许强行给出文化结论。
- 色板项包含 `hex`、`ratio` 和算法版本。
- 相似结果包含 `pattern_id`、相似分数和缩略图地址。
- 文化寓意来自已审核数据库，不由视觉模型凭图生成。

