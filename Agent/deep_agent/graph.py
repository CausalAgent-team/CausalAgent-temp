"""Minimal fake-executor graph used before real P2-U adapters are connected."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from Agent.deep_agent_tools.models import ActionAttempt, InvocationRecord

from .context import AgentRunContext
from .state import ProjectDeepAgentState


async def run_fake_algorithm_step(
    state: ProjectDeepAgentState,
    context: AgentRunContext,
) -> dict[str, Any]:
    """Execute one pending command through the injected fake executor."""

    command = state.get("pending_command")
    if command is None:
        return {
            "algorithm_results": {},
            "action_ledger": {},
        }
    if context.execution_guard is not None:
        await context.execution_guard.ensure_active()
    result = await context.algorithm_executor.execute(
        command,
        context.trusted_context,
    )
    finished_at = datetime.now(timezone.utc)
    invocation = InvocationRecord(
        invocation_id=command.invocation_id,
        response_identity=f"fake:{command.provider_call_id}",
        response_identity_source="message_execution_id",
        provider_call_id=command.provider_call_id,
        tool_name=command.capability_id,
        final_status="succeeded" if result.status == "valid" else "failed",
        result_ref=result.result_ref,
        attempts={
            0: ActionAttempt(
                retry_ordinal=0,
                revision=2,
                status="succeeded" if result.status == "valid" else "failed",
                started_at=finished_at,
                finished_at=finished_at,
                safe_error_code=(
                    None
                    if result.status == "valid"
                    else str(result.diagnostics.safe_error_code)
                ),
            )
        },
    )
    if context.execution_guard is not None:
        await context.execution_guard.check_after_call()
    return {
        "pending_command": None,
        "algorithm_results": {result.result_ref: result},
        "action_ledger": {invocation.invocation_id: invocation},
    }


async def _fake_algorithm_node(
    state: ProjectDeepAgentState,
    runtime: Runtime[AgentRunContext],
) -> dict[str, Any]:
    return await run_fake_algorithm_step(state, runtime.context)


def build_fake_graph(checkpointer: Any):
    """Compile a one-step graph with explicit checkpoint support."""

    if checkpointer is None or checkpointer is False:
        raise RuntimeError("fake Deep Agent graph requires a checkpointer")
    workflow = StateGraph(ProjectDeepAgentState, context_schema=AgentRunContext)
    workflow.add_node("fake_algorithm", _fake_algorithm_node)
    workflow.add_edge(START, "fake_algorithm")
    workflow.add_edge("fake_algorithm", END)
    return workflow.compile(checkpointer=checkpointer)
