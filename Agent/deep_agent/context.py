"""Runtime-only dependencies for the isolated P2-U Deep Agent slice."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from Agent.deep_agent_tools.algorithm_executor import AlgorithmExecutor
from Agent.deep_agent_tools.models import McpInvocationContext


@dataclass(frozen=True)
class TrustedJobIdentity:
    """Worker-claimed identity; never comes from model-visible tool arguments."""

    job_id: str
    session_id: str
    user_id: int
    worker_id: str
    attempt_count: int
    lease_epoch: int


@dataclass(frozen=True)
class AgentRunContext:
    """Non-serializable graph dependencies and trusted execution identity."""

    execution_guard: Any
    trusted_identity: TrustedJobIdentity
    trusted_context: McpInvocationContext
    algorithm_executor: AlgorithmExecutor
    rag_executor: Any = None
    web_executor: Any = None

    def __post_init__(self) -> None:
        identity = self.trusted_identity
        context = self.trusted_context
        if (
            context.job_id != identity.job_id
            or context.session_id != identity.session_id
            or context.user_id != identity.user_id
            or context.worker_id != identity.worker_id
            or context.attempt_count != identity.attempt_count
            or context.lease_epoch != identity.lease_epoch
        ):
            raise ValueError("trusted identity and MCP context do not match")
