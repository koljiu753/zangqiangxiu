# 备份与恢复

生产数据由 PostgreSQL 数据库和 MinIO 对象存储共同组成，必须在同一维护窗口内备份两者。脚本不会停止服务，也不会直接复制 Docker 数据卷。

## 创建备份

在项目根目录执行：

```powershell
.\scripts\backup.ps1
```

默认输出到 `backups/<时间戳>/`，其中包含 PostgreSQL custom-format dump、MinIO 全量对象副本和 `manifest.json` 校验清单。清单记录数据库和每个对象的 SHA-256、大小及相对路径；恢复前会逐项验证。`backups/` 已被 Git 忽略。也可通过 `-OutputRoot D:\secure-backups` 指定受保护的外部目录。

备份成功后，应将整个时间戳目录复制到异机或受版本保护的对象存储，并按组织要求加密。仅保留同一主机上的备份不能防范磁盘损坏或勒索软件。

## 隔离恢复演练

```powershell
.\scripts\restore-drill.ps1 -BackupDirectory .\backups\20260903-170000
```

脚本会先验证数据库备份的 SHA-256，再恢复到随机命名的临时 PostgreSQL 数据库和临时 MinIO bucket，检查数据库存在业务表且对象数与清单一致，最后删除这些临时目标。在线数据库、在线 bucket 和数据卷不会被覆盖或删除。

仅在需要人工检查演练结果时使用 `-KeepTemporaryTargets`；使用后需人工清理脚本输出中明确列出的临时数据库和 bucket。

## 建议节奏

- 每日自动备份，至少保留 7 个日备份和 4 个周备份。
- 每月执行一次隔离恢复演练，并保存命令输出作为证据。
- 应用升级、数据库迁移和批量导入前额外创建一次备份。
- 定期检查备份目录容量、异机副本、加密和访问权限。

每次计划发布都应保存以下命令输出作为验收证据：

```powershell
.\scripts\release-check.ps1
.\scripts\backup.ps1
.\scripts\restore-drill.ps1 -BackupDirectory <上一条命令输出的目录>
.\scripts\health-check.ps1
```

## Catalog 与 AI 状态修复

先运行默认的只读检查：

```powershell
.\scripts\check-catalog-ai-consistency.ps1
```

确认报告后，才可显式修复 AI 发布状态：

```powershell
.\scripts\check-catalog-ai-consistency.ps1 -Repair
```

`-Repair` 只处理 `mismatch`：以 Catalog 的 `published/public` 状态为唯一事实来源，调用 AI 幂等 publication 接口，将对应 reference 对齐为 `approved/public`，其余情况对齐为 `draft/internal_only`。它不会修改 Catalog 的名称、版权、审核事实或发布状态，也不会自动处理 `missing`、`orphan`。修复后脚本会重新读取两端并再次报告；仍有漂移时退出码为 `2`。

脚本默认从项目 `.env` 读取 `CATALOG_ADMIN_TOKEN` 和 `AI_INTERNAL_TOKEN`，也接受进程环境中的 `CATALOG_ADMIN_TOKEN` 与 `ZHIXIU_AI_INTERNAL_TOKEN`/`AI_INTERNAL_TOKEN`。不要在命令行、工单或日志中粘贴令牌。
