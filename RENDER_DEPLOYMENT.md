# 免费、无需绑卡的公网预览部署

仓库根目录的 [`render.yaml`](render.yaml) 定义三个 Render Free Web Service：
`zangqiangxiu-web`（Next.js）、`zangqiangxiu-catalog`（FastAPI）和
`zangqiangxiu-ai`（FastAPI）。数据库继续使用既有 Supabase PostgreSQL；
Render 不创建会在 30 天后到期的免费 PostgreSQL。

## 首次部署

1. 用仓库所有者的 GitHub 账号登录 Render，并授予
   `koljiu753/zangqiangxiu` 仓库的部署权限。
2. 在 Render 控制台选择 **New → Blueprint**，连接该仓库的 `main`
   分支，确认三项服务的计划均为 **Free**。不要选择付费计算规格。
3. 首次创建蓝图时，Render 会要求填写三个 `sync: false` 秘密值：
   `ZHIXIU_AI_DATABASE_URL`（现有 Supabase transaction pooler URI）、
   `AWS_ACCESS_KEY_ID` 和 `AWS_SECRET_ACCESS_KEY`。后两项来自
   Supabase 项目的 Storage → S3 配置，必须只保存在 Render 服务端环境中；
   S3 密钥可跨 bucket 访问且绕过 RLS，绝不可放到 GitHub、浏览器变量
   `NEXT_PUBLIC_*` 或聊天记录。Catalog 会由 Render 私密引用同一组凭据，
   不需要重复粘贴。
4. 在 Supabase Storage 创建私有 bucket `zhixiu-assets`；不要设为 public。
   核对项目 S3 页面显示的 endpoint 和 region 与 `render.yaml` 一致。
5. 三项服务部署后，分别检查 Catalog 和 AI 的 `/ready`，再检查网页首页、
   `/patterns`、`/studio` 和后台登录。必须以 Render 实际分配的 URL 为准，
   不能把本机 `localhost` 或 Vercel 旧预览链接当作交付地址。

蓝图自动生成并跨服务引用管理员令牌、审计签名密钥、AI 内部令牌、后台密码和
会话密钥，不在 Git 中保存它们。服务间调用走各自 HTTPS 公网地址，因为 Render
Free Web Service 不能接收私有网络请求。Catalog 与 AI 的写接口仍依赖应用层
鉴权；Supabase RLS 不能约束持有 PostgreSQL 管理 URI 的服务端。

## 上线边界

- 现有 100 条候选纹样全部为 `draft/internal_only`，因此公网纹样库初始
  为空是正确的。不能为“有内容”而跳过版权与文化审核。
- 蓝图默认关闭匿名图片上传/分析，直到补齐隐私政策中的运营联系方式、上传告知、
  保存/删除流程后，再设置合理的公开额度并重新验收。
- Free 服务闲置 15 分钟会休眠，下一次访问唤醒可能约需一分钟；本地文件在
  重启或休眠后会丢失，所以数据库与图片必须放在 Supabase。
- Render 免费用量耗尽后，无付款方式的账号会暂停服务或构建，而不是自动扣费。
  三个服务共享工作区每月的免费实例小时额度。这是可演示的免费预览方案，
  不承诺生产级可用性。
