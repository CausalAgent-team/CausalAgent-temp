# Job 与文件生命周期

文档职责：记录 Session、analysis Job、输入账本、文件库、LangGraph checkpoint 以及删除清理之间的当前数据关系和状态转换。

适用范围：修改 `app/agent/job_service.py`、会话/文件路由、相关 Alembic migration、worker fencing 或跨库删除流程时使用；普通用户 API 入口见 [`../api/agent-jobs.md`](../api/agent-jobs.md) 与 [`../api/chat-files.md`](../api/chat-files.md)。

## 核心实体

| 实体 | 存储 | 作用 |
| --- | --- | --- |
| Session | MySQL `sessions` | 用户可见的会话容器，`id` 是 UUID 字符串；业务访问仍按 `session_id` 授权 |
| Job | MySQL `analysis_jobs` | 长任务队列、状态、lease、重试、冻结文件快照、终态摘要和创建请求关联 |
| Job 输入 | MySQL `analysis_job_inputs` | initial/resume 输入账本、顺序、问题 ID、幂等键和对应聊天消息 |
| Job 事件 | MySQL `analysis_job_events` | SSE 时间线、生命周期事件和内部执行摘要 |
| 文件对象 | MySQL `file_objects` | 按用户和 SHA-256 去重的不可变 BLOB |
| 用户文件 | MySQL `user_files` | 用户可见文件名、访问统计和对象引用 |
| 父图 checkpoint | PostgreSQL 官方 LangGraph 表 | Job 的外层恢复状态；`thread_id` 是 `analysis_jobs.job_id` |
| Deep Agent checkpoint | PostgreSQL 官方 LangGraph 表 | 内层消息、工具状态和 raw 文件；使用稳定的 `deep-agent:<uuid5(job_id)>` thread 与 `deep_agent_v1` namespace |
| 长期记忆 Store | PostgreSQL 官方 `AsyncPostgresStore` 表 | 按可信 `user_id` namespace 保存 Deep Agent 两份 memory 文件；不属于 Job checkpoint |
| cleanup outbox | MySQL `checkpoint_cleanup_outbox` | 跨库删除请求的可靠账本，按 `thread_id` 唯一 |

新建会话时，`POST /api/new_chat` 先在 MySQL 主库插入 `sessions` 记录再返回 ID。创建 Job、保存聊天、修改标题和上传文件都要求会话或用户文件真实存在且属于当前用户，不会根据未知 ID 自动重建对象。Job 创建时保存入口确定的原始 `X-Request-ID` 到 `analysis_jobs.request_id`；历史行可为 `NULL`，幂等重放不覆盖首次值。

## 文件库与冻结输入

文件上传进入文件库，不自动关联 Session 或 Job。相同用户相同 SHA-256 的内容复用 `file_objects`，不同文件名仍可以形成不同的 `user_files` 逻辑记录；浏览器中尚未提交的选择只是 composer 状态，不构成 Job 输入。

创建 Job 时，服务端在同一个 MySQL 事务中锁定并快照 `input_user_file_id`、对象 ID、文件 hash 和文件名，同时写入 initial `analysis_job_inputs` 和用户聊天消息。之后用户替换或清除浏览器草稿不会改变已创建 Job 的输入。

文件预览、下载以及 Agent 真正读取文件内容都在主库事务内更新 `last_accessed_at` 和 `access_count`；命中已有对象的重复上传不计为访问。CSV 预览最多读取 256 KiB、100 行、50 列，单元格最多 1000 字符，并且只按文本处理。

## Job 状态和并发

活动状态为 `queued`、`running`、`waiting_input`，终态为 `succeeded`、`failed`、`canceled`。同一 `user_id + session_id` 同时最多有一个活动 Job；`active_session_key` 是可空普通列，唯一键 `uq_analysis_jobs_active_session` 负责并发兜底。

领取时 worker 写入 `worker_id`、`attempt_count`、`lease_epoch`、锁定时间和心跳，并把 `execution_state` 置为 `leased`。运行中的业务取消会立即提交 `status=canceled`、取消事件和聊天投影，同时保留执行身份并转为 `execution_state=draining`；heartbeat 随后标记 invocation guard 撤销。LLM/RAG 继续合作式取消，MCP 算法调用额外通过签名控制面请求按 invocation 终止独立算法进程；取消失败或回执未知时仍保持 fencing，绝不接受迟到结果。worker cleanup 完成后以 `worker_confirmed` 释放，失联 lease 由 420 秒阈值以 `lease_expired` 回收。终态写入、事件写入和 assistant 消息提交前必须确认 worker、attempt、lease epoch 和 leased 状态仍匹配，旧 worker 不能覆盖新尝试。stale recovery 只在确认 PostgreSQL checkpoint 可读且未恢复的 interrupt 后进行；canceled Job 永不 resume 或 stale recovery，无法可靠读取恢复状态时禁止冒险重放。

## 等待输入、恢复与取消

Agent 产生 interrupt 后，Job 进入 `waiting_input`，保留 `active_session_key` 以阻止同一会话创建第二个 Job，但释放 worker lease并记录 `worker_confirmed`。服务端将问题 ID、公开提示和稳定 interrupt 事件写入 MySQL；恢复请求把输入追加为 `resume` 记录，随后重新排队同一个 Job，继续同一个 checkpoint。`queued`、`running`、`waiting_input` 都可以被即时逻辑取消；取消后的业务终态不可逆，旧 worker 的迟到结果会被 fencing 拒绝。

恢复输入只允许文本或受限 JSON，服务端限制长度、深度、字段/数组项数和 UTF-8 字节数。恢复与取消操作各自要求 UUID v4 `Idempotency-Key`，相同键重放相同请求时返回原结果，不同参数返回冲突。取消支持 `queued/running/waiting_input`，写入稳定 `canceled` 生命周期事件；运行中取消只释放业务活动锁，执行占用在 graph/EventWriter/heartbeat 和可能的 MCP 远端取消完成 cleanup 前保持 `draining`。

## 会话历史中的执行阶段

`ExecutionPhase` 是接口和前端展示概念，不新增表或字段。一个 `analysis_job_inputs` 记录对应至多一个阶段：initial 输入形成 sequence 0，后续 resume 依次形成 sequence 1、2 等。公开节点事件从上一个边界之后开始，归入下一个 `interrupt`、`final_result`、`error` 或 `canceled` 边界所关联的输入；活动 Job 最后尚无边界的区间归入最新输入。

用户消息通过 `chat_messages.analysis_job_input_id` 与输入账本精确关联；边界 assistant 消息同时通过 `source_event_id` 指向事件、通过 `analysis_job_input_id` 指向输入。同一输入先 interrupt 后取消时仍只有一个阶段，取消只把该阶段状态更新为 `canceled`。任一关系缺失、多义或与 `analysis_job_inputs.chat_message_id` 不一致时，该区间不进入历史展示。

Deep Agent 的算法公开决策、工具开始/结果和 Gate 后最终决策都作为阶段内公共事件保存，不依赖浏览器内存或 checkpoint 正文。会话刷新按 Job 事件 ID 顺序重建阶段；`step_id` 只负责把明细挂到对应父节点，不作为数据库实体或授权依据。

## Checkpoint 身份和跨库清理

父图 checkpoint 身份是：

```text
thread_id = analysis_jobs.job_id
checkpoint_ns = ""
```

业务 `session_id` 仍然是 MySQL `sessions.id`，不是 checkpoint thread。新 Job 从同一 Session 的 MySQL 聊天历史加载有界初始窗口；同一 Job 的 resume 和 stale recovery 才继续原 checkpoint。旧的 session-thread checkpoint 不迁移、不读取、不清理。管理员 checkpoint 摘要必须使用 `metadata.job_id` 精确关联，缺少该字段的记录不能按时间猜测归属。

Deep Agent 的 checkpoint 与长期记忆共用 PostgreSQL 实例但不是同一类数据：父图以
`thread_id=job_id` 保存外层 Job State；Deep Agent 子图以
`thread_id=deep-agent:<uuid5(job_id)>` 和 `checkpoint_ns=deep_agent_v1` 保存内部
messages、工具状态和短期 raw 文件。`AsyncPostgresStore` 另以
`("causalagent", "memory", str(user_id))` namespace 保存 `/memories/preferences.md`
和 `/memories/research_background.md`。worker 首次使用某个用户 namespace 时只做
create-if-absent 初始化，不覆盖已有内容；运行时对象与 MCP session 不会写入 Store。
子图 checkpoint 只保存由 Job、attempt、lease 和输入身份计算出的不可逆
`execution_scope` 摘要，不保存 execution guard、executor、数据库连接或签名材料。

删除 Session 或用户时，MySQL 事务先锁定并删除业务数据，同时为相关 Job 写入 `checkpoint_cleanup_outbox`。cleanup worker 用租约领取并调用 PostgreSQL `adelete_thread(job_id)`；租约过期可以恢复，失败按有限次数和退避重试。两个数据库之间没有伪造的分布式事务，后台清理状态必须可查询。

当前 outbox 只保存父图 `job_id`，cleanup worker 也只删除该 thread；它没有计算并删除
`deep-agent:<uuid5(job_id)>` 子图 thread。因此删除 Job/Session 后，Deep Agent 子图
checkpoint 及其中的短期 raw 文件可能继续保留。这是当前实现缺口，修复前不能把
checkpoint cleanup 描述为已覆盖完整父子图生命周期。

checkpoint cleanup 当前不删除 `store` 或 `store_migrations` 中的长期记忆。父子
checkpoint cleanup 应在同一 outbox attempt 内按可重试、幂等方式收敛；用户/合规删除长期
记忆仍需独立的 Store 删除流程，不能借用 Job cleanup 的表名过滤或顺手扩大清理范围。

删除逻辑文件时，如果仍有活动 Job 使用该 `user_file_id`，请求必须被阻断；删除 `user_files` 后只有在没有其他逻辑引用时才删除 `file_objects` BLOB，不提供回收站。
