# 智绣乡村数据子工程

本目录把旧站的“展示卡片、物理文件、纹样实体、别名和衍生版本”拆开管理。所有工具默认只读输入；生成物只写入 `data/output/` 或 `--output` 指定目录。

## 目录

- `migrations/001_core.sql`：PostgreSQL 15+ 核心模型。
- `dictionaries/`：受控词表与字段字典；旧站自由文本只能作为待审核候选。
- `scripts/asset_inventory.py`：扫描目录或ZIP，输出资产清单、SHA-256与完全重复组，不解压ZIP。
- `scripts/extract_legacy.py`：抽取两个公开旧站的硬编码纹样卡片/manifest。
- `scripts/audit_legacy_content.py`：审计两个旧站的顶层页面、可见文本块和素材引用，生成站点级迁移候选清单。
- `scripts/clean_candidates.py`：标准化候选数据并生成审核队列。
- `scripts/reconcile_legacy_assets.py`：下载并哈希旧站引用的唯一资产，与本地ZIP清单交叉对账。
- `scripts/select_mvd_candidates.py`：按唯一SHA、可解码和类别轮转选出最多100条首批候选，并生成catalog-service seed。
- `scripts/materialize_mvd_assets.py`：按seed白名单从ZIP精确物化原图并用Pillow生成WebP缩略图；校验路径与哈希，拒绝覆盖哈希不符的既有文件。
- `samples/`：导入manifest示例。
- `tests/`：纯标准库自动测试。

## 快速运行

在项目根目录执行：

```powershell
python data/scripts/asset_inventory.py "<path-to-legacy-archive.zip>"
python data/scripts/extract_legacy.py
python data/scripts/audit_legacy_content.py --tianma C:\path\to\tianmawenku --zhixiu C:\path\to\zhixiuxiangcun
python data/scripts/clean_candidates.py data/output/legacy/legacy_candidates.csv
python data/scripts/reconcile_legacy_assets.py data/output/local-zip/assets.csv data/output/legacy/legacy_candidates.csv
python data/scripts/select_mvd_candidates.py data/output/local-zip/assets.csv --duplicates data/output/local-zip/duplicates.json
python data/scripts/materialize_mvd_assets.py "<path-to-legacy-archive.zip>" data/output/mvd/catalog_seed.csv
python -m unittest discover -s data/tests -v
```

也可以审计已下载的仓库目录：

```powershell
python data/scripts/asset_inventory.py C:\path\to\zhixiuxiangcun --output data/output/zhixiu-repo
python data/scripts/extract_legacy.py --tianma C:\path\to\tianmawenku\library.html --zhixiu C:\path\to\zhixiuxiangcun\assets\js\pattern-manifest.js
```

工具不会删除重复文件。`duplicates.json` 只是人工合并队列；视觉近似图还需后续使用pHash或向量工具复核。

站点级迁移规则和栏目映射见 `LEGACY_CONTENT_MIGRATION.md`。其输出同样只是内部候选，不能直接作为公开网页内容。

## 数据闸门

1. 新资产先登记SHA-256、原文件名、来源定位符和采集时间。
2. SHA-256相同只代表二进制完全相同；同图异格式、裁切、压缩图需视觉近重复复核。
3. 旧站名称、寓意、颜色和工艺均为候选字段，未经专家审核不得成为正式陈述。
4. `rights_record` 默认所有许可为 `false`。权利基础、合同附件及权利人未核验时，只能保持 `private/internal_only`。
5. AI生成图、传统原纹样及其裁切/矢量/衍生图必须用 `origin_claim`、`asset.role` 和 `pattern_relation` 区分。
6. 训练集切分前按SHA-256及视觉近重复聚类，同源变体不得跨训练/验证/测试集。

## 对象存储建议

源文件使用不可变键：`original/{sha256前2位}/{sha256}.{ext}`；缩略图、裁切与矢量文件分别放在 `derived/{asset_uuid}/{variant}`。数据库只保存键、哈希和元数据，不把二进制存进PostgreSQL。桶默认为私有，通过服务端鉴权生成短时访问链接。

## 最小可发布标准

一个公开纹样实体至少需要：稳定UUID、审核后的规范名称、来源记录、一个可解码且哈希已登记的资产、民族/地域的“已确认或待考”状态、母题标签、文化审核记录和允许公开展示的版权记录。仅有文件名或旧站卡片不满足发布条件。

建议首批目标为100个满足上述标准的实体。业务统计以 `pattern` 实体数为准，同时单独披露资产文件数、唯一SHA-256数、衍生版本数和版权已核验数。

`catalog_seed.csv/json` 只是待审核种子：`canonical_name` 和 `description` 故意留空，旧文件名只进入 `candidate_name`；全部记录固定为 `draft/internal_only`，所有授权布尔值固定为 `false`。类别轮转只保证候选覆盖，不代表旧目录分类已经获得文化确认。

资产物化要求Pillow。原图以 `{sha256}.{原扩展名}` 保存，内容不转码；缩略图最长边默认512像素并保存为WebP。`asset_manifest` 同时记录原图和缩略图的路径、尺寸、字节数、哈希、处理动作与错误。脚本拒绝绝对路径、反斜杠、`..`、盘符路径、ZIP中缺失/重名条目、源哈希不一致以及目标文件哈希冲突。

## PostgreSQL迁移

迁移依赖 `pgcrypto`：

```powershell
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -f data/migrations/001_core.sql
```

生产环境应由数据库角色管理扩展；若应用迁移角色无权创建扩展，先由管理员执行 `CREATE EXTENSION pgcrypto`。
