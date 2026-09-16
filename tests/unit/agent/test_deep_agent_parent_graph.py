"""P3/P4 父图构造与新路径拓扑合同测试。"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
import asyncio
from types import SimpleNamespace

from Agent.causal_agent.graph import (
    _deep_agent_parent_node,
    build_deep_agent_parent_graph,
)
from Agent.deep_agent.context import AgentRunContext, TrustedJobIdentity
from Agent.deep_agent_tools.identity import (
    build_deep_agent_execution_scope,
    build_deep_agent_run_id,
)


class _FakeLLM:
    """只满足父图编译所需的 model_copy，不发起模型调用。"""

    def model_copy(self, *, update):
        return self


def test_parent_graph_compiles_deep_agent_gate_and_report_path() -> None:
    graph = build_deep_agent_parent_graph(
        llm=_FakeLLM(),
        deep_agent=object(),
        registry=type("Registry", (), {"entries": ()})(),
        checkpointer=MemorySaver(),
    )

    nodes = set(graph.get_graph().nodes)
    assert {
        "agent",
        "fold",
        "preprocess",
        "deep_agent",
        "finalization_gate",
        "report",
    }.issubset(nodes)
    edges = {(edge.source, edge.target) for edge in graph.get_graph().edges}
    assert ("preprocess", "deep_agent") in edges
    assert ("deep_agent", "finalization_gate") in edges
    assert ("finalization_gate", "report") in edges


def test_parent_node_uses_stable_child_thread_id_and_minimal_projection() -> None:
    calls = []

    class Child:
        async def ainvoke(self, value, *, config, context):
            calls.append((value, config, context))
            return {
                "messages": [],
                "algorithm_results": {},
                "action_ledger": {},
                "rag_evidence": {},
                "web_evidence": {},
                "structured_response": None,
                "deep_agent_run_id": value["deep_agent_run_id"],
                "execution_scope": value["execution_scope"],
            }

    identity = TrustedJobIdentity(
        job_id="00000000-0000-0000-0000-000000000401",
        session_id="00000000-0000-0000-0000-000000000402",
        user_id=7,
        attempt_count=1,
        lease_epoch=2,
        worker_id="worker-1",
        input_identity="input-sha",
    )
    context = AgentRunContext(execution_guard=None, trusted_identity=identity)
    state = {
        "job_id": identity.job_id,
        "messages": [],
        "analysis_parameters": {},
        "file_summary": {},
    }

    update = asyncio.run(
        _deep_agent_parent_node(
            state,
            runtime=SimpleNamespace(context=context),
            config={"configurable": {"thread_id": identity.job_id}},
            deep_agent=Child(),
            store=None,
            memory_init_lock=asyncio.Lock(),
        )
    )

    expected = build_deep_agent_run_id(job_id=identity.job_id)
    assert update["deep_agent_run_id"] == expected
    assert update["deep_agent_status"] == "completed"
    assert calls[0][1]["configurable"]["thread_id"] == expected
    assert "execution_guard" not in calls[0][0]


def test_parent_node_reads_matching_child_checkpoint_instead_of_projecting_messages() -> None:
    calls = []

    identity = TrustedJobIdentity(
        job_id="00000000-0000-0000-0000-000000000411",
        session_id="00000000-0000-0000-0000-000000000412",
        user_id=7,
        attempt_count=1,
        lease_epoch=2,
        worker_id="worker-1",
        input_identity="input-sha",
    )
    child_values = {
        "messages": ["private child message"],
        "algorithm_results": {},
        "action_ledger": {},
        "rag_evidence": {},
        "web_evidence": {},
        "structured_response": None,
        "deep_agent_run_id": build_deep_agent_run_id(job_id=identity.job_id),
        "execution_scope": build_deep_agent_execution_scope(
            job_id=identity.job_id,
            attempt_count=identity.attempt_count,
            lease_epoch=identity.lease_epoch,
            input_identity=identity.input_identity,
        ),
    }

    class Child:
        async def aget_state(self, config):
            return SimpleNamespace(values=child_values)

        async def ainvoke(self, value, *, config, context):
            calls.append(value)
            return child_values

    update = asyncio.run(
        _deep_agent_parent_node(
            {
                "job_id": identity.job_id,
                "messages": ["parent message"],
                "analysis_parameters": {},
                "file_summary": {},
            },
            runtime=SimpleNamespace(
                context=AgentRunContext(execution_guard=None, trusted_identity=identity)
            ),
            config={"configurable": {"thread_id": identity.job_id}},
            deep_agent=Child(),
            store=None,
            memory_init_lock=asyncio.Lock(),
        )
    )

    assert calls == [None]
    assert "deep_agent_messages" not in update
