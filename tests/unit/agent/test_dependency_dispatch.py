"""验证同一 AIMessage 的算法调用经过统一 DependencyPlan dispatch。"""

from __future__ import annotations

import asyncio

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from Agent.deep_agent import AgentRunContext, TrustedJobIdentity
from Agent.deep_agent.memory import build_in_memory_backend
from Agent.deep_agent.state import ProjectDeepAgentState
from Agent.deep_agent_tools import (
    DataProfile,
    FakeAlgorithmExecutor,
    build_algorithm_tools,
    build_default_registry,
)
from Agent.deep_agent_tools.adapters import build_default_adapters
from Agent.deep_agent_tools.dependency_dispatch import (
    build_algorithm_dependency_middleware,
)


IDENTITY = TrustedJobIdentity(
    job_id="00000000-0000-0000-0000-000000000101",
    session_id="00000000-0000-0000-0000-000000000102",
    user_id=7,
    attempt_count=0,
    lease_epoch=1,
    worker_id="worker-1",
    input_identity="input-sha",
)


def test_tool_node_dispatches_each_algorithm_call_once() -> None:
    executor = FakeAlgorithmExecutor()
    context = AgentRunContext(
        execution_guard=None,
        trusted_identity=IDENTITY,
        algorithm_executor=executor,
        filesystem_backend=build_in_memory_backend(user_id=7),
    )
    registry = build_default_registry(
        build_default_adapters(
            executor=executor,
            raw_backend=context.filesystem_backend,
        )
    )
    profile = DataProfile(
        row_count=300,
        column_count=2,
        column_names=("x", "y"),
        numeric_columns=("x", "y"),
    )
    tools = [
        tool.to_langchain_tool()
        for tool in build_algorithm_tools(
            registry,
            runtime_context=context,
            data_profile=profile,
        )
    ]
    middleware = build_algorithm_dependency_middleware(registry=registry)

    builder = StateGraph(ProjectDeepAgentState, context_schema=AgentRunContext)
    builder.add_node(
        "tools",
        ToolNode(
            tools,
            handle_tool_errors=False,
            awrap_tool_call=middleware.awrap_tool_call,
        ),
    )
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)
    graph = builder.compile()

    state = asyncio.run(
        graph.ainvoke(
            {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "causal_pc",
                                "args": {"alpha": 0.05},
                                "id": "dispatch-pc-1",
                                "type": "tool_call",
                            },
                            {
                                "name": "causal_olc",
                                "args": {"alpha": 0.05, "beta": 0.01},
                                "id": "dispatch-olc-1",
                                "type": "tool_call",
                            },
                        ],
                    )
                ],
                "message_execution_id": "message-execution-dispatch-1",
                "data_profile": profile,
                "algorithm_results": {},
                "action_ledger": {},
                "rag_evidence": {},
                "web_evidence": {},
            },
            context=context,
        )
    )

    assert len(executor.calls) == 2
    assert {call.command.capability_id for call in executor.calls} == {
        "causal.pc",
        "causal.olc",
    }
    assert len(state["algorithm_results"]) == 2
    assert all(result.status == "valid" for result in state["algorithm_results"].values())
    assert {
        record.provider_call_id for record in state["action_ledger"].values()
    } == {"dispatch-pc-1", "dispatch-olc-1"}
