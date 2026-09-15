"""P2-U fake-executor foundation tests."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from Agent.deep_agent.context import AgentRunContext, TrustedJobIdentity
from Agent.deep_agent.graph import build_fake_graph, run_fake_algorithm_step
from Agent.deep_agent.state import project_deep_to_parent, project_parent_to_deep
from Agent.deep_agent_tools.algorithm_specs import PC_SPEC
from Agent.deep_agent_tools.fake_algorithm_executor import FakeAlgorithmExecutor
from Agent.deep_agent_tools.models import AlgorithmExecutionCommand, McpInvocationContext
from langgraph.checkpoint.memory import MemorySaver


def _context() -> AgentRunContext:
    identity = TrustedJobIdentity(
        job_id="00000000-0000-0000-0000-000000000401",
        session_id="00000000-0000-0000-0000-000000000402",
        user_id=7,
        worker_id="worker-p2u",
        attempt_count=1,
        lease_epoch=2,
    )
    issued = datetime.now(timezone.utc)
    trusted_context = McpInvocationContext(
        invocation_id="00000000-0000-0000-0000-000000000403",
        job_id=identity.job_id,
        session_id=identity.session_id,
        user_id=identity.user_id,
        attempt_count=identity.attempt_count,
        lease_epoch=identity.lease_epoch,
        worker_id=identity.worker_id,
        input_snapshot_digest="snapshot",
        issued_at=issued,
        expires_at=issued + timedelta(minutes=5),
        key_id="current",
    )
    return AgentRunContext(
        execution_guard=None,
        trusted_identity=identity,
        trusted_context=trusted_context,
        algorithm_executor=FakeAlgorithmExecutor(),
    )


def _command(context: AgentRunContext) -> AlgorithmExecutionCommand:
    return AlgorithmExecutionCommand(
        invocation_id=context.trusted_context.invocation_id,
        capability_id=PC_SPEC.capability_id,
        capability_version=PC_SPEC.version,
        spec_digest=PC_SPEC.spec_digest,
        provider_call_id="p2u-call",
        input_identity="snapshot",
    )


def test_parent_projection_keeps_runtime_dependencies_out_of_state() -> None:
    deep = project_parent_to_deep(
        {
            "messages": [],
            "file_summary": {"rows": 10, "columns": ["A", "B"]},
            "algorithm_executor": object(),
        }
    )
    assert deep["data_profile"].row_count == 10
    assert deep["algorithm_results"] == {}
    assert "algorithm_executor" not in deep


def test_fake_executor_step_writes_result_and_ledger_then_projects_explicitly() -> None:
    async def scenario():
        context = _context()
        state = project_parent_to_deep({"messages": []})
        state["pending_command"] = _command(context)
        state.update(await run_fake_algorithm_step(state, context))
        return state

    state = asyncio.run(scenario())
    assert state["pending_command"] is None
    assert len(state["algorithm_results"]) == 1
    assert len(state["action_ledger"]) == 1
    parent = project_deep_to_parent(state)
    assert len(parent["causal_analysis_result"]["algorithm_results"]) == 1


def test_fake_graph_requires_checkpoint_and_restores_state() -> None:
    context = _context()
    command = _command(context)
    graph = build_fake_graph(MemorySaver())

    async def scenario():
        state = project_parent_to_deep({"messages": []})
        state["pending_command"] = command
        return await graph.ainvoke(
            state,
            {"configurable": {"thread_id": "p2u-fake"}},
            context=context,
        )

    result = asyncio.run(scenario())
    assert len(result["algorithm_results"]) == 1
    assert len(result["action_ledger"]) == 1

    with pytest.raises(RuntimeError):
        build_fake_graph(None)
