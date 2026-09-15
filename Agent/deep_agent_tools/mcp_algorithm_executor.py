"""AlgorithmExecutor implementation backed by the private causal-mcp client pool."""

from __future__ import annotations

import asyncio
from typing import Any

from Agent.deep_agent_tools.algorithm_executor import (
    AlgorithmExecutorError,
    validate_executor_result,
)
from Agent.deep_agent_tools.error_codes import SafeErrorCode
from Agent.deep_agent_tools.models import (
    AlgorithmExecutionCommand,
    AlgorithmResult,
    McpInvocationContext,
)

from app.agent.worker.mcp_client_pool import (
    McpClientPool,
    McpPoolError,
    McpTransportError,
)

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

    async def execute(
        self,
        command: AlgorithmExecutionCommand,
        trusted_context: McpInvocationContext,
    ) -> AlgorithmResult:
        if command.invocation_id != trusted_context.invocation_id:
            raise AlgorithmExecutorError(
                "command/context identity mismatch",
                safe_error_code=SafeErrorCode.MCP_CONTEXT_INVALID,
            )
        signature = sign_invocation(trusted_context, command, self.signing_key)
        arguments = {
            "command": command.model_dump(mode="json"),
            "trusted_context": trusted_context.model_dump(mode="json"),
            "signature": signature,
        }
        last_error: BaseException | None = None
        for retry_ordinal in range(self.max_retries + 1):
            try:
                response = await self.pool.call_tool(
                    {**arguments, "retry_ordinal": retry_ordinal},
                    invocation_id=command.invocation_id,
                    retry_ordinal=retry_ordinal,
                )
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
                    raise AlgorithmExecutorError(
                        "MCP call returned a safe error",
                        safe_error_code=safe_code,
                    )
                result = AlgorithmResult.model_validate(payload.get("result"))
                return validate_executor_result(
                    result,
                    command=command,
                    trusted_context=trusted_context,
                )
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
                await asyncio.sleep(self.retry_backoff_seconds * (2**retry_ordinal))
        raise AlgorithmExecutorError(
            "MCP execution failed after bounded retries",
            safe_error_code=(
                getattr(last_error, "safe_error_code", None)
                or SafeErrorCode.MCP_TRANSPORT_FAILED
            ),
        ) from last_error
