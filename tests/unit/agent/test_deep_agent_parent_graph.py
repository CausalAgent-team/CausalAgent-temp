"""P3/P4 父图构造与新路径拓扑合同测试。"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver

from Agent.causal_agent.graph import build_deep_agent_parent_graph


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
