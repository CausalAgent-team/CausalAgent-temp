# 官网 Vue 前端

文档职责：记录官网 Vue 3 工程的页面清单、认证页面与回跳规则、内容组织、构建、开发与验收边界。

适用范围：`website-frontend/`、Flask 的官网页面入口和登录注册页面；不覆盖普通用户应用、RAG 评测台、管理员前端或后端认证实现。

## 入口与页面

`app/main/routes.py` 的 `main_bp` 提供全部官网页面：`/`、`/product`、`/about`、`/docs`、`/changelog` 以及 `/auth/sign-in`、`/auth/sign-up`。这些路径都返回同一份构建产物，页面由浏览器按 `location.pathname` 选择（`src/routes.ts`）；未登记的路径不返回官网页面，访问得到 404。

登录后的普通用户应用在 `/dashboard`，RAG 评测台在 `/rag-eval`，管理员系统在 `/admin`，都不属于本工程。

## 认证页面与回跳

登录页面调用 `POST /api/login` 并原样回传查询参数里的 `next`；注册页面调用 `POST /api/register`，成功后提示去登录。服务端只接受白名单内的站内路径作为回跳目标，登录成功后返回 `redirect_to`：管理员默认 `/admin/database`，普通用户默认 `/dashboard`。

客户端在跳转前还会用 `src/api/auth.ts` 的 `isAllowedInternalPath` 再校验一次 `redirect_to` 与 `next`，只接受 `/dashboard*`、`/admin*` 和 `/rag-eval`，其余回落到 `/dashboard`。服务端仍是权威判定，客户端校验只用于避免把浏览器送到未登记地址。

`?notice=admin_required` 会在登录页显示“当前账号没有管理员权限”的提示；页面挂载时会调用 `/api/check_auth`，已登录时在认证卡片上方提示当前账号，并提供直接进入工作区的链接。

## 内容组织

产品、文档和更新日志内容放在 `src/content/` 的类型化数据模块中（`product.ts`、`docs.ts`、`changelog.ts`），页面组件只负责排版。`/docs` 面向使用者，`/changelog` 只记录影响使用方式的变化；仓库内部的 `Document/` 与 `CHANGELOG.md` 不通过官网发布。

## 构建与部署

构建产物由 Flask 在同源路径提供：页面入口是 `main_bp` 的官网路径，静态资源使用 `/site-assets/<path:filename>`。构建目录默认是 `website-frontend/dist/`，Docker 运行时使用 `/opt/causalagent-website`，也可由 `WEBSITE_FRONTEND_DIST_DIR` 指定；目录缺少 `index.html` 时页面入口和资源路径统一返回带 request ID 的 503 和 `website_frontend_missing`。Vite base 是 `/site-assets/`，入口 HTML 不缓存，`assets/` 下的带 hash 资源使用长期 `public, immutable` 缓存。

## 开发与测试

```powershell
Push-Location website-frontend
npm ci
npm run dev
Pop-Location
```

开发服务器使用 5175 端口并把 `/api` 代理到 `http://127.0.0.1:5001`；依赖使用 `.npmrc` 固定的 `legacy-peer-deps`，安装请用 `npm ci`。`npm run check` 依次执行类型检查、Vitest 单元测试和生产构建，单元测试覆盖路由解析、登录回跳白名单、认证客户端和登录表单交互。单独执行时使用 `npm run typecheck`、`npm run test:unit` 和 `npm run build`。

## 验收边界

自动化检查只证明路由解析、客户端校验、表单交互和构建成功，不证明真实 Flask、Cookie Session、MySQL、worker、模型或浏览器人工验收。发布前需要人工确认：官网各页面可直接访问和刷新、`/auth/sign-in` 与 `/auth/sign-up` 可刷新、登录后按角色回到 `/dashboard`、`/rag-eval` 或 `/admin/database`、外部 `next` 被忽略、未登录访问 `/dashboard` 会回到登录页。

