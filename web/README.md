# 智绣乡村 Web

生产前端基于 Next.js App Router、TypeScript 和 React。视觉延续旧站的深蓝、金线、博物馆式陈列语言，代码重新拆为页面、组件、API 客户端与领域类型。

## 页面

- `/`：品牌首页、精选纹样和 AI 入口
- `/patterns`：可检索、分类筛选的纹样库
- `/studio`：真实 AI 分析接口入口
- `/admin`：内部候选审核与安全发布后台

## 本地运行

```bash
npm install
copy .env.example .env.local
npm run dev
```

访问 `http://localhost:3000`。

## API 配置

```dotenv
NEXT_PUBLIC_CATALOG_API_BASE_URL=http://localhost:8001/api/v1
NEXT_PUBLIC_AI_API_BASE_URL=http://localhost:8002/v1
NEXT_PUBLIC_ALLOW_DEMO_FALLBACK=true
CATALOG_API_INTERNAL_BASE_URL=http://localhost:8001/api/v1
CATALOG_ADMIN_TOKEN=replace-with-the-catalog-service-token
ADMIN_UI_USER=admin
ADMIN_UI_PASSWORD=replace-with-a-strong-password
ADMIN_UI_ROLE=publisher
AUTH_SESSION_SECRET=replace-with-at-least-32-random-bytes
AUTH_COOKIE_SECURE=false
ADMIN_ALLOW_BASIC_AUTH=true
```

纹样接口支持直接数组或 `{ "items": [...] }`：

```http
GET /api/v1/patterns
POST /api/v1/analysis-jobs
```

纹样 API 不可用且 `NEXT_PUBLIC_ALLOW_DEMO_FALLBACK=true` 时，页面会显示醒目的“演示数据”提示并使用 `src/lib/demo-data.ts`。AI 工作台不伪造结果；未连接后端时明确报错。生产环境建议把回退设为 `false`。

`CATALOG_ADMIN_TOKEN` 只在服务端模块中读取，没有 `NEXT_PUBLIC_` 前缀，不会进入浏览器包。`/admin` 使用 HMAC 签名的 HttpOnly、SameSite 会话 Cookie；`reviewer` 可以编辑审核资料，只有 `publisher` 可以发布。所有写操作均再次检查身份、角色与 CSRF 令牌，管理页面还附加 CSP、防嵌入、MIME 嗅探和权限策略等安全响应头。

Basic Auth 仅作为本地兼容入口：开发环境默认允许，也可设置 `ADMIN_ALLOW_BASIC_AUTH=true`；生产环境默认禁用。本地 HTTP Compose 设置 `AUTH_COOKIE_SECURE=false`，正式 HTTPS 环境必须删除该覆盖或设为 `true`。正式上线还应把 `AUTH_SESSION_SECRET` 设置为至少 32 字节的随机值，并将登录路由替换为 Clerk/Auth0/企业 SSO。业务层只依赖 `AdminPrincipal`（subject、role、expiresAt），因此替换身份提供方不需要改目录服务或审核动作。目录服务自身仍会再次校验 Token 和发布条件。

## 质量检查

```bash
npm run lint
npm test
npm run build
```

## 后端对接注意

- 所有正式记录需由后端返回稳定 ID、发布状态和授权范围。
- 图片建议返回对象存储缩略图 URL，不直接传原始大图。
- AI 接口最终若采用异步任务，应将当前 `submitAnalysis` 扩展为创建任务后轮询 `/analysis-jobs/{id}`。
- 不应把 demo 数据、固定置信度或视觉动效作为真实技术结果。
