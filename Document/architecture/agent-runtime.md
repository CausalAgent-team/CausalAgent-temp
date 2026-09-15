# Agent 运行时

文档职责：记录 Agent worker、LangGraph、MCP、RAG、联网搜索、结构化输出和执行事件的当前协作方式。

适用范围：修改 `Agent/`、`app/agent/worker/`、MCP server、RAG 初始化、联网搜索或用户可见事件协议时使用；Job 的持久化生命周期见 [`job-file-lifecycle.md`](job-file-lifecycle.md)，执行约束见 [`../../Agent/AGENTS.md`](../../Agent/AGENTS.md)。

## Worker 启动与 slot

`python -m app.agent.worker` 进入 `app/agent/worker/__main__.py`，再调用 bootstrap。当前新运行路径的启动顺序是：

```text
MySQL readiness
  → PostgreSQL checkpoint pool/schema
  → AsyncPostgresStore setup/readiness
  → 静态 Algorithm Registry
  → 进程级 MCP Client pool connect/handshake
  → RAG active release readiness
  → Deep Agent model/profile、内层 graph 和外层父图编译
  → worker ready
  → slots claim Job
```

`ProcessRuntime` 持有进程级 MCP pool、`McpAlgorithmExecutor`、静态 Registry、PostgreSQL Store/checkpointer、RAG readiness、领域 tools 和编译后的父图。`SlotRuntime` 只保存对这些对象的显式引用；生产新路径不会为 slot 创建 stdio MCP session，也不会重复编译 graph。每个 Job invocation 再由 slot 创建 `AgentRunContext`，绑定可信 Job/attempt/lease/input identity、execution guard、executor、filesystem backend 和 `web_search_enabled`；这些对象只进入 LangGraph runtime context，不进入 State 或 checkpoint。

因此，进程级 MCP Client pool 的成员容量和生命周期与 slot 数量分离，真实算法并发仍由 MCP 服务端进程池、Client pool、Tool 调度器和 Job 预算共同限制。启动失败会在 worker ready 前 fail closed，不领取 Job。

旧兼容构造器仍保留在 `runtime.py`，但只有显式走旧 `ProcessRuntime.graph is None` 的测试/兼容调用才会使用 slot stdio；`main_async()` 的新生产路径不会进入该分支。

## P2-M causal-mcp 过渡边界

P2-M 已新增独立的 `Agent/CausalAgentMCP/app.py`、固定 runner registry、有界 CPU 进程池和 `app/agent/worker/mcp_client_pool.py`。新服务使用 Streamable HTTP/HTTP/1.1、Bearer/HMAC、MySQL primary strong read、canonical UUID 和 lease 校验；`MCP session` 只承载传输，不保存 Job、checkpoint 或 Action Ledger。客户端池按 `N×K` 成员容量调度，成员 context 由 owner task 创建和关闭，以避免 MCP SDK/AnyIO cancel scope 跨任务清理。

这是 MCP 协作支线与 worker 新运行路径的共同边界。新路径在 bootstrap 中使用进程级长期 HTTP Client pool 和真实 `McpAlgorithmExecutor`；pool 的握手只确认 `execute_algorithm` capability，绝不使用远端 `list_tools()` 动态生成模型工具。服务协议、fake-authority HTTP smoke 和 pool 单测不能写成真实 MySQL 容量、完整 Job 或生产负载验收完成；这些仍属于 P5。

## P2-U 基础实现与协议边界

`Agent/deep_agent/` 保留 P2-U 的协议前置：`ProjectDeepAgentState` 继承官方 `DeepAgentState`，算法结果、Action Ledger 和证据使用显式 reducer；`AgentRunContext` 保存可信身份、执行守卫和真实/测试 executor，不进入 checkpoint；父 State 与 Deep Agent State 通过显式白名单投影连接。`build_fake_graph()` 仍只用于隔离 checkpointer/State 验收；生产构造器 `build_deep_agent()` 使用真实 Deep Agents graph，但本仓库当前只取得构造和 ToolNode 静态接线证据，真实 DeepSeek 调用、PostgreSQL Store 持久化和完整 Job 仍未验收。

## 父图与工具阶段

新 worker 父图的数据型路径是：

```text
agent → fold → preprocess → deep_agent → finalization_gate → report
```

普通聊天和报告追问仍由既有 `normal_chat`/`inquiry_answer` 路径结束。`deep_agent` 节点只把问题、数据画像、分析参数和必要的上一次内层消息显式投影给 Deep Agent；返回时只接收算法结果、Action Ledger、RAG/Web evidence、结构化决策和消息白名单。`finalization_gate` 不调用 LLM，只校验当前 Job/attempt/lease 的结果与 Ledger 对账；首次不一致回送同一 Deep Agent 一次，第二次仍不一致则以 `finalization_status=degraded` 进入报告，且不会展示未经 Gate 验证的主图。

Deep Agent 的模型可见算法 tools 由静态 `AlgorithmSpec`/Registry 生成。`AlgorithmDependencyDispatchMiddleware` 在 LangChain `ToolNode` 的调用边界收集同一响应中的 PC、OLC、DirectLiNGAM calls，使用 `requires/produces` 规划独立并行和依赖分层，之后才调用真实 `AlgorithmExecutor`；它不读取远端动态工具清单。内层工具结果不会把 raw payload 或 provider ID 带回父 State，事件适配器只在 `deep_agent` 父节点 update 中生成受控工具完成摘要。

旧 `build_graph()` 仍保留 `mcp`、`rag` 和 `web_search` 子图兼容路径：MCP 子图为 `mcp_planner -> mcp_tool_node -> mcp_result_parser`，RAG 子图为 `rag_question_planner -> rag_tool_node -> rag_result_parser -> rag_finalize`。该路径的中间字段仍隔离在子图内，不是新 worker 父图的生产入口。

### 新 Deep Agent 的 RAG/Web evidence 工具

`rag_evidence_search` 直接调用 `RagService.get_evidence()`，不调用旧 answer model；默认 Tool 绑定为延迟代理，worker 启动时只执行 active release/readiness，不加载 Chroma、BM25 或 embedding，首次实际查询才初始化进程内 RAG runtime。证据以 `evidence_ref`、snippet、来源定位、分数、release 和降级状态进入内层 State，父节点再投影为旧 report formatter 可消费的引用摘要。

`web_evidence_search` 直接返回 SearXNG 学术 snippet 和来源元数据，不读取正文；每次调用从 runtime context 读取可信的 `web_search_enabled`，显式关闭时返回 `WEB_SEARCH_DISABLED`，不会触网。Web evidence 与 RAG evidence 一样只通过白名单投影进入报告；真实 active release、SearXNG 网络和引用展示仍需 P5 验收。

#### RAG具体实现与异常处理

以下兼容子图行为仅适用于旧 `build_graph()` 路径；新 Deep Agent 使用上面的 evidence-only Tool。

RAG Planner 在调用 LLM 前检查进程级 `rag_available` 和已注册的 `rag_tools`。知识库目录未初始化、active release readiness 失败或工具列表为空时，Planner 写入私有 `rag_route=finish`、`rag_status=unavailable` 和统一降级中间结果，跳过 ToolNode，仍经 `rag_finalize` 回到父图的 Agent；进程 Runtime 同时保留内部 `rag_status=rag_unavailable`、安全错误码和可用时的 release id。正常 ToolNode 返回（包括 `success=False`）继续进入 Parser；ToolNode 或 Planner 的未捕获普通异常在重试结束后由 error handler 跳到 Finalize，Parser 异常标记为 `protocol_error` 后也进入 Finalize。

RAG 查询任务捕获普通查询、连接和目录异常时返回 `success=False`、`status=unavailable` 及 `error_type=RAGQueryError`，这表示知识库不可用，不表示 ToolMessage 协议错误。`parse_tool_message_json()` 遇到非法 JSON 时返回 `error_type=ToolMessageProtocolError`，RAG Parser 将其归类为 `protocol_error`；正常业务失败的 `success=False` 仍归类为 `unavailable`。所有路径最终由 Finalize 生成稳定的 `rag_output`，报告继续使用 `format_rag_summary_for_prompt()` 读取父图统一字段。

结构化输出统一通过 `Agent/llm_structured_output.py` 的同步/异步入口调用，固定使用普通 `function_calling`。结构化请求会关闭 thinking；MCP planner 仍使用原生 Tool Calls，并对关闭 thinking 的 LLM 副本设置 `tool_choice="required"`，确保 planner 必须选择一个已加载工具。`agent` 和 `fold` 的条件路由只读取显式 State 字段 `route_decision`、`fold_decision`，不使用展示消息猜测控制流。

RAG readiness 在 worker 启动时复用 `RagRuntimeConfig.from_environment()`，轻量校验 active pointer、相对路径、manifest 哈希、冻结正式来源身份、manifest 中的 embedding 配置、版本/collection、Chroma 内容摘要和必要索引产物；来源身份校验只读取受版本控制的 production defaults 和 manifest，不回读或解析原始 PDF。正式 embedding 当前由 API key 配置提供，本地 production embedding 开关关闭；embedding endpoint/凭据缺失仍只标记不可用。release 完整性或正式策略失败时尝试把唯一 fallback 提升为 active 并隔离失败 release；embedding API 请求故障不触发 pointer 回退。构建、evaluate、gate-check 和 publish 仍在受控目录内严格校验实际来源。readiness 不加载 embedding、Chroma、BM25 或回答模型。失败时 worker 继续运行并标记 `rag_unavailable`，对外仍使用 `status=unavailable`；缺失或非法 retrieval policy 仍按代码默认值回退并记录来源。完整 RagRuntime 继续按进程内 lazy singleton 在首次 RAG 查询时创建，active pointer 变化需通过 worker drain 与重启生效，不支持热切换或零停机切换。

worker 收到 SIGTERM/SIGINT 后停止领取新 Job，按 `JOB_DRAIN_TIMEOUT_SECONDS`（默认 60 秒）等待现有 slot。超时只取消本地执行任务并关闭资源，不把运行中的 Job 标记为 failed/cancelled；未完成 lease 由既有 stale recovery 接管。worker Compose 的 `stop_grace_period` 至少为 75 秒。DirectLiNGAM 作为 `causal_direct_lingam` MCP 工具提供连续数值 CSV 分析，输出的系数矩阵约定为 `target_to_source`，报告需要保留线性、非高斯、误差独立、DAG 和无潜在混杂等假设。

#### web_search具体实现与异常处理

以下兼容子图行为仅适用于旧 `build_graph()` 路径；新 Deep Agent 使用上面的 `web_evidence_search`。

`web_search` 子图内部路径为 `web_search_planner -> academic_search_node -> web_search_result_parser_node`。父图通过适配节点只向子图传入 `messages`、`analysis_parameters`、`causal_analysis_result` 和 `knowledge_base_result`，子图只投影 `web_search_result` 回父图；中间的 `planner`、`search` 私有字段不会进入父 State。

`web_search_planner` 与 RAG 不同，不在调用 LLM 前做进程级可用性检查，而是始终执行两步结构化输出：先 `generate_research_question` 提炼最需论证的具体问题，再 `get_web_search_query` 生成中英双语检索 query（`query` 面向报告展示、`query_en` 面向学术检索）。planner 捕获 `StructuredOutputError` 时写 `planner.success=False`，`academic_search_node` 据此短路、不再调用底层检索。

`academic_search_node` 单节点统一走 SearXNG 的 arxiv/crossref/openalex 三引擎，按引擎分组各取 top-3 后按 rank 轮转交错。`WEB_SEARCH_MAX_RESULTS` 的当前值为 9，搜索结果合并、报告/追问 prompt 注入和最终引用投影共用该上限，避免报告使用的资料超出公开引用范围。底层 `web_search()` 网络异常直接抛出，交 `tool_retry` 重试，重试耗尽后由 error handler 写 `search.success=False`。`web_search_result_parser_node` 是纯 snippet 出口（无 BM25、抓正文或 LLM 总结），把 `search.results` 投影为 `content`，产出稳定的 `web_search_result`。

三个节点都挂 error handler：planner 降级写 `planner.success=False`、academic_search 降级写 `search.success=False`，二者都让后续 `result_parser` 正常投影出 `success=False` 的结果；result_parser 注册 `degrade_web_search_parser_failure`，解析异常写入 `status=protocol_error` 的统一 `web_search_result`；父图 `web_search` 节点注册 `degrade_web_search_adapter_result`，子图整体失败时写入统一结果并 `goto="agent"`。统一结果由 `build_web_search_degradation_result` 构造，`WebSearchStatus` 只有 `available`、`unavailable`、`protocol_error` 三种值；异常对象经 `sanitize_error()` 归类，`asyncio.CancelledError` 和 `JobExecutionRevoked` 不会被错误转成普通搜索降级。是否进入子图由父图 `rag` 之后的 `web_search_router` 读 `context.web_search_enabled` 决定，关闭时直接回 `agent`——这是用户级事前短路，与 RAG 的进程级 `rag_available` 事前短路（在子图 planner 内）位置不同。

## 事件流与脱敏

worker 使用 LangGraph v2 的 `updates`、`messages`、`custom` 和 `tasks` 流，将内部执行事件转换为 `analysis_job_events`。根图 `tasks` 构成用户时间线，兼容子图工具事件折叠为 `mcp` 或 `rag` 阶段；新 Deep Agent 的内层 `ToolMessage` 不直接进入普通用户流，父 `deep_agent` update 只投影稳定工具名、完成状态和受控安全错误码。`finalization_gate` 作为独立阶段展示，最终 `finalization_status` 位于 `final_result.data`。普通用户 SSE 只允许 `normal_chat` 和 `inquiry_answer` 的公开文字进入 `text_delta`；原始 prompt、ToolMessage、完整工具结果、图状态、内部 attempt 和隐藏推理都不能进入普通用户协议。

事件写入由 Job 的 `lease_epoch`、worker、attempt、`execution_state=leased` 和稳定 `event_key` 共同保护。终态事件与 assistant 消息、Job 状态在同一个 MySQL 事务中落盘；旧 worker 失去 lease 或收到取消撤销后不能覆盖新执行结果。`JobExecutionGuard` 通过 LangGraph invocation runtime context 传递到父图、子图、ToolNode 包装器和 parser；节点开始、调用返回、异常处理、路由和事件持久化前均检查执行资格。`JobExecutionRevoked` 和 `asyncio.CancelledError` 是内部控制流，不进入 RetryPolicy、RAG 降级或公开 error 事件，必须继续向 worker 传播；普通 RAG 故障则在子图内收口并回到 Agent。前端断线恢复使用 Event ID 读取 MySQL 事件，不依赖 worker 内存。

普通异常的失败收敛会先在 Job 行锁内确认 worker、attempt、lease epoch 和 `leased` 状态；若锁住时发现业务取消，返回 `CANCELED_FENCED`，不再补写普通 `error` 事件。`OrderedEventWriter.abort()` 会丢弃未刷新的文字、结束排队 Future，并向调用方暴露消费协程的非预期异常；只有终态写入被接受后才设置 `terminal_seen`。worker 只有在 graph stream、EventWriter 和 heartbeat monitor 都完成 cleanup 后，才可以把 canceled/draining 执行占用标记为 `worker_confirmed`；cleanup 失败时保留 draining，交由租约回收路径处理。

普通用户历史与实时 SSE 共用字段白名单。历史阶段排除 `text_delta` 和所有边界事件，只重放节点、进度、决策、工具摘要、重试与节点结束；边界事件只在服务端用于阶段切分。页面刷新活动 Job 时，`load_session` 先重放已持久化节点事件并记录实际处理到的 `rendered_event_id`，随后活动 Job API 只补充状态，不能用数据库最新事件 ID 推进该游标；SSE 从 `rendered_event_id` 之后补发，避免加载与订阅之间的事件被跳过。

## 修改时的验证边界

- 修改图节点或路由时，必须核对显式 State 字段和失败路径，不能只验证成功样例。
- 修改事件适配器、结果展示或 SSE 时，必须确认公共 payload 没有内部字段和原始工具数据。
- 修改 worker 初始化时，必须同时检查 `runtime.py`、`bootstrap.py`、Docker Compose 的 worker 入口、进程级 MCP pool、PostgreSQL Store/checkpointer 和 slot 资源占用。
- 修改结构化输出或 MCP planner 时，必须分别验证普通 function calling、thinking 配置和原生 Tool Calls。
- 修改 RAG 或因果工具时，必须分别验证“知识库缺失可启动”和工具输入/输出契约。
- 新父图必须至少验证 `deep_agent → finalization_gate → report` 拓扑、首次 Gate 修正和二次 degraded；构造测试通过不能代替真实 MCP、DeepSeek、PostgreSQL、RAG/Web 或 MySQL Job 验收。
