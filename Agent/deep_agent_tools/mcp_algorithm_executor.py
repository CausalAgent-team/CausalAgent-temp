"""AlgorithmExecutor implementation backed by the private causal-mcp client pool."""

from __future__ import annotations

import asyncio
from typing import Any

from Agent.deep_agent_tools.algorithm_executor import (
    AlgorithmExecutorError,
    validate_executor_command,
    validate_executor_result,
)
from Agent.deep_agent_tools.error_codes import SafeErrorCode
from Agent.deep_agent_tools.models import (
    AlgorithmExecutionCommand,
    AlgorithmResult,
    McpInvocationContext,
)
from Agent.execution_control import JobExecutionRevoked

from app.agent.worker.mcp_client_pool import (
    McpClientPool,
    McpPoolError,
    McpTransportError,
)
from app.agent.worker.execution_guard import current_execution_guard

from Agent.CausalAgentMCP.auth import sign_invocation


class McpAlgorithmExecutor:
    """Keep transport concerns out of the model-visible AlgorithmSpec tools."""

    def __init__(
        self,
        pool: McpClientPool,
        *,
        signing_key: str,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.05,
    ) -> None:
        self.pool = pool
        self.signing_key = signing_key
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds

    @staticmethod
    def _remote_lease_revoked(invocation_id: str) -> JobExecutionRevoked:
        """把 MCP 已确认的 stale lease 转回 worker 控制流。"""

        error = JobExecutionRevoked("MCP reported a stale execution lease")
        error.invocation_id = invocation_id
        error.remote_execution_status = "revoked"
        return error

    async def execute(
        self,
        command: AlgorithmExecutionCommand,
        trusted_context: McpInvocationContext,
    ) -> AlgorithmResult:
        validate_executor_command(command, trusted_context=trusted_context)
        signature = sign_invocation(trusted_context, command, self.signing_key)
        arguments = {
            "command": command.model_dump(mode="json"),
            "trusted_context": trusted_context.model_dump(mode="json"),
            "signature": signature,
        }
        last_error: BaseException | None = None
        for retry_ordinal in range(self.max_retries + 1):
            guard = current_execution_guard()
            if guard is not None:
                await guard.ensure_active()
            try:
                response = await self.pool.call_tool(
                    {**arguments, "retry_ordinal": retry_ordinal},
                    invocation_id=command.invocation_id,
                    retry_ordinal=retry_ordinal,
                )
                # 远端响应可能在本地 Job 被取消后才抵达；此时只能丢弃响应，
                # 不能把它标准化为 AlgorithmResult 或进入后续 Gate。
                guard = current_execution_guard()
                if guard is not None:
                    await guard.check_after_call()
                payload = getattr(response, "structured_content", None)
                if payload is None:
                    payload = getattr(response, "structuredContent", None)
                if not isinstance(payload, dict):
                    raise AlgorithmExecutorError(
                        "MCP response is not structured",
                        safe_error_code=SafeErrorCode.MCP_TRANSPORT_FAILED,
                    )
                if payload.get("ok") is not True:
                    error = payload.get("error") or {}
                    code = error.get("code", SafeErrorCode.MCP_TRANSPORT_FAILED.value)
                    try:
                        safe_code = SafeErrorCode(code)
                    except ValueError:
                        safe_code = SafeErrorCode.MCP_TRANSPORT_FAILED
                    if safe_code == SafeErrorCode.MCP_LEASE_STALE:
                        raise self._remote_lease_revoked(command.invocation_id)
                    raise AlgorithmExecutorError(
                        "MCP call returned a safe error",
                        safe_error_code=safe_code,
                    )
                result = AlgorithmResult.model_validate(payload.get("result"))
                result_safe_code = result.diagnostics.safe_error_code
                if (
                    str(getattr(result_safe_code, "value", result_safe_code) or "")
                    == SafeErrorCode.MCP_LEASE_STALE.value
                ):
                    raise self._remote_lease_revoked(command.invocation_id)
                return validate_executor_result(
                    result,
                    command=command,
                    trusted_context=trusted_context,
                )
            except asyncio.CancelledError as exc:
                # call_tool 可能已经把请求交给远端；CancelledError 只向上传播，
                # 并附带稳定 identity，供 cleanup/retry 审计按 pending/unknown
                # 处理，而不是生成新的失败调用。
                exc.invocation_id = command.invocation_id
                exc.remote_execution_status = "unknown"
                raise
            except McpTransportError as exc:
                last_error = exc
            except McpPoolError as exc:
                last_error = exc
                if exc.safe_error_code != SafeErrorCode.MCP_CAPACITY_EXHAUSTED:
                    break
            except AlgorithmExecutorError as exc:
                last_error = exc
                if exc.safe_error_code not in {
                    SafeErrorCode.MCP_CAPACITY_EXHAUSTED,
                    SafeErrorCode.MCP_TRANSPORT_FAILED,
                }:
                    break
            if retry_ordinal < self.max_retries:
                guard = current_execution_guard()
                if guard is not None:
                    await guard.check_after_call()
                await asyncio.sleep(self.retry_backoff_seconds * (2**retry_ordinal))
        raise AlgorithmExecutorError(
            "MCP execution failed after bounded retries",
            safe_error_code=(
                getattr(last_error, "safe_error_code", None)
                or SafeErrorCode.MCP_TRANSPORT_FAILED
            ),
        ) from last_error
