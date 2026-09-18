# 普通用户 Vue 前端

文档职责：记录普通用户主应用 Vue 3 工程的目录边界、唯一入口、Session—Job—SSE 状态约束、构建、测试、发布与回退事实。

适用范围：`chat-frontend/`、Flask 普通端入口和其 Docker 构建集成；不覆盖管理员前端、RAG 工作台、数据库 schema 或 worker 业务规则。

## 当前状态与入口


Vue 构建产物由 Flask 在同源路径提供：入口为 `/chat-assets/` 对应的 `index.html`，静态资源使用 `/chat-assets/<path:filename>`。入口 HTML 使用不缓存策略，`assets/` 下的带 hash 资源使用长期 `public, immutable` 缓存。构建目录默认是 `chat-frontend/dist/`；Docker 运行时使用 `/opt/causalagent-chat`，也可由 `CHAT_FRONTEND_DIST_DIR` 指定。缺少 `index.html` 时 Vue 入口返回带 request ID 的 503，不回退到旧版或返回半成品资源。

本地 Vite 开发服务器使用 5174 端口和 `/chat-assets/` base。设置 `CHAT_VITE_DEV_SERVER_URL=http://127.0.0.1:5174` 后，Flask 的 `/` 或 `/chat-next` 会跳转到 `http://127.0.0.1:5174/chat-assets/`，并保留 `next` 查询参数。

## 工程边界

`chat-frontend/src/` 按 API schema、Pinia store、Job runtime、组件、渲染器和设计样式分域。后端响应先以 `unknown` 接收，再由 Zod schema 解析；Store 只保存可序列化领域状态。`AbortController`、ReadableStream reader、定时器和 vis-network 实例由 controller 或 Vue 生命周期持有，不放入 Pinia。

普通端 Vue 化不改变 Flask 业务 API、Session/文件/Job 数据规则、数据库、worker 或 SSE 路径。旧版静态文件已经退出路由、配置和部署契约；由于仓库规则禁止 agent 删除重要文件，其物理清理由用户按本文“旧文件清理边界”执行。

## SSE 与 Job 状态

Vue 的 Job 传输层使用 `fetch()` 和 `ReadableStream`，不使用原生 `EventSource`。`src/api/events.schemas.ts` 自行解析标准 `id`、`event`、`data` 字段，支持分块、CRLF/LF、多行 `data`、注释和 UTF-8 边界；Flask SSE 路径仍为 `/api/agent/jobs/<job_id>/events`，公共事件内容不变。

首个订阅从历史阶段的 `last_event_id` 使用查询参数 `last_event_id` 开始；断线重连通过 `Last-Event-ID` 请求头显式传递当前 `transport_cursor`。传输游标、可见渲染游标和活动接口的 `last_event_id` 观测值分别保存，活动 Job 查询不能覆盖历史恢复起点。未知但结构合法且带有效 ID 的事件只推进传输游标，不进入可见投影；非法 JSON、字段不完整、ID 无效或 `event` 与 `data.type` 不一致会进入稳定协议错误路径，不推进坏包游标，也不会无限重试。网络错误和 5xx 使用有界退避重连，4xx 和协议错误不重试。

JobController 为每个 Job 管理订阅 generation，切换 Session、取消、登出或卸载时使旧回调失效。`waiting_input` 是可恢复暂停态；`final_result`、`error` 和 `canceled` 进入终态并停止订阅，终态保留已渲染结果但释放原始文本拼接和语义去重缓冲。创建、恢复、取消分别使用独立幂等键，取消的 409 终态冲突按后端状态对账。运行态不显示独立取消按钮；发送键变为带旋转进度环和中心方块的停止键，再次点击调用相同的取消 API。

## 阶段明细、公开决策与展示节奏

阶段明细只挂在同一个 `step_id` 下：`node_start` 创建阶段，`progress`、`decision`、`tool_call_start`、`tool_call_result` 和 `decision_delta` 作为明细追加，`node_end` 结束阶段。明细早于父 `node_start` 到达时先按 `step_id` 暂存，父阶段出现后按原顺序补绘一次，避免把明细挂到错误的阶段或改变阶段顺序。

公开决策由两类事件表达。`decision_delta` 只携带同一 `stream_id` 的批次增量和 `decision_kind`，页面按 `decision_kind` 显示`算法决策：`、`检索决策：`或`最终决策：`前缀，并按码点逐字推进；完整 `decision` 到达时只结束该决策流，不会重复插入文本。同一工具的 `tool_call_start`/`tool_call_result` 在该决策的逐字展示追平之前只能暂存，追平后按原顺序补在决策文本后面；如果缺少完整 `decision` 结束事件，工具结果会强制放行，任务进入终态时同样放行所有未结束的决策，不允许永久挂起。历史回放只有完整 `decision`，因此直接显示带前缀的完整文本。

聊天草稿和公开决策共用同一套展示节奏：40 字/秒、25ms 步进推进展示游标，完整缓冲区始终以服务端内容为准，展示速度不影响工具执行。`final_result` 到达时如果已有文字草稿，终态文本校正到同一草稿，报告布局同样复用草稿而不做第二次渲染；没有草稿或结果不是文字时才新增一条结果消息。`prefers-reduced-motion` 和所有终态直接展示完整文本，暂停等待输入时展示继续推进。

聊天区滚动按 80px 阈值跟随最新内容：用户在阈值外主动上滑后停止自动跟随，回到底部后恢复；发送、切换或创建会话、新增消息和展示推进都会在跟随状态下滚动到最新内容。逐字推进、定时器和滚动容器由组件或 runtime controller 持有，不进入 Pinia。

## 开发与构建

在仓库根目录执行：

```powershell
Push-Location chat-frontend
npm ci
npm run dev
```

`npm run dev` 只启动 Vite；API 由 Vite 代理到 `http://127.0.0.1:5001`。完整代码质量门和构建命令为：

```powershell
npm run lint
npm run typecheck
npm run test:unit
npm run test:components
npm run test:e2e:mock
npm run build
npm run check
Pop-Location
```

`npm run check` 当前串联上述检查。构建时图形库通过动态 import 延迟加载，初始入口不静态包含 vis-network；`public/vendor/marked.min.js` 通过 `markdown-adapter.ts` 兼容现有 Markdown 行为。当前原始 HTML 输出行为是已接受的兼容风险，本阶段不偷偷增加清洗策略或 CSP 语义变化。

## Docker 与启动失败边界

`Dockerfile` 的 `chat-builder` 使用 Node 24 Alpine 执行 `npm ci` 和 `npm run build`，将产物复制到 `/opt/causalagent-chat`；最终 Python runtime 不包含 Node、npm 或 Vite。三个 Compose 文件只向 `app` 传递 `CHAT_FRONTEND_DIST_DIR` 和 `CHAT_VITE_DEV_SERVER_URL`，不再传递入口选择变量。

Vue 构建缺失属于运行期请求边界：`/`、`/chat-next` 和 `/chat-assets/...` 返回 503、`chat_frontend_missing` 与 request ID，不回退到旧静态入口或返回半成品资源。

## 验收、发布与回退

自动化检查只证明代码、协议夹具、组件、Mock 浏览器和部署静态契约；不证明真实 Flask、Cookie Session、MySQL/PostgreSQL、worker、文件上传、模型、Chrome/Edge 双浏览器或桌面壳。发布前必须由人工在 Vue 正式入口完成注册、登录/刷新/登出、管理员重定向、空 Session、消息成功/失败、Session 管理、文件、Web Search、普通 Job、Thinking、图、Markdown/图片、SSE 断线、active Job 恢复、waiting_input/resume、运行态停止对账、错误恢复、快速切换、四视口、Chrome、Edge 和桌面壳检查，并保留记录。

当前部署产物只包含 Vue 构建链。回退通过部署上一份经过验证的代码与镜像完成，不触碰 Session、Job、消息或数据库；不再依赖同一运行版本中的旧前端路由。

## 旧文件清理边界

下列文件已无运行时引用，但仍属于重要回滚文件，agent 不得直接删除。`app/static/js/` 中的脚本还包含 develop 在旧版普通聊天页面上新增的公开决策、假流式展示和滚动跟随改动，这些行为已经在本 Vue 工程按等价语义重新实现。用户确认当前代码、构建产物和人工验收记录均可接受后，应自行删除：

- `app/static/chat.html`
- `app/static/css/style.css`
- `app/static/js/script.js`
- `app/static/js/chat_layout_state.js`
- `app/static/js/execution_phase_state.js`
- `app/static/js/job_subscription_state.js`
- `app/static/js/stream_state.js`
- `app/static/js/marked.min.js`

配套的 Node 测试只验证上述静态文件，需要和它们一起删除，否则测试会指向不存在的文件：

- `tests/unit/frontend/chat_layout_state.test.cjs`
- `tests/unit/frontend/chat_stream_state.test.cjs`
- `tests/unit/frontend/execution_phase_state.test.cjs`
- `tests/unit/frontend/job_subscription_state.test.cjs`

不得删除 `app/static/rag_eval_app/`，它是独立的 RAG 工作台静态产物。物理删除完成后，应重新执行 `rg` 失效引用检查、普通端部署契约测试和 `git diff --check`；在用户实际删除前，变更日志和验收报告只能写“运行时已移除、物理文件待用户清理”。
