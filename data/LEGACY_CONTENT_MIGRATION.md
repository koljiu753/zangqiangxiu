# 旧站内容迁移映射

两个旧站只作为候选来源，不作为事实或版权凭证。脚本生成的文本、栏目和图片记录全部固定为 `draft/internal_only`，图片权利状态固定为 `unverified`。

| 旧站栏目 | 新平台承载位置 | 迁移处理 |
|---|---|---|
| 首页、关于我们 | 内容管理/项目介绍 | 提取文本块；项目成绩、合作单位、数据规模等声明逐条核验 |
| 纹样库 | 纹样候选及素材关系 | 保留来源页、原名称和图片引用；不得自动覆盖规范名称和文化释义 |
| AI识别、创作中心 | 产品能力说明 | 只迁移需求与交互文案；旧站模拟结果、准确率不迁移为真实能力 |
| 文创商城、定制服务 | 商品候选 | 图片、价格、库存、销量和授权状态分别核验，当前不进入公开商品库 |
| 采集标准、文化合规 | 内部运营规范 | 作为制度草案，由项目负责人和文化顾问确认后再发布 |
| 投资、SaaS、版权交易 | 商业规划档案 | 金额、收益、客户与链上存证等均标记为高风险主张 |

生成物为 `page_manifest.csv`、`text_candidates.csv`、`asset_references.csv` 和 `content_audit_report.json`。

```powershell
python data/scripts/audit_legacy_content.py --tianma C:\path\to\tianmawenku --zhixiu C:\path\to\zhixiuxiangcun
```

发布前至少补齐：内容责任人、事实依据或附件、图片权利人及许可范围、文化审核意见、目标栏目和最终编辑稿。
