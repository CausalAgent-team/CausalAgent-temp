import json
import os

import pytest


for key, value in {
    "SECRET_KEY": "test-secret",
    "API_KEY": "test-api-key",
    "BASE_URL": "https://example.test",
    "MODEL": "test-model",
    "MYSQL_HOST": "mysql",
    "MYSQL_USER": "app",
    "MYSQL_PASSWORD": "password",
    "MYSQL_DATABASE": "causalagent",
}.items():
    os.environ.setdefault(key, value)


from langchain_core.messages import AIMessage

from app.agent.worker.result_presenter import process_final_result
from app.chat.response_storage import (
    prepare_ai_response_for_storage,
    project_causal_graph,
)


ORIGINAL_GRAPH = {
    "graph_semantics": "dag_target_to_source",
    "nodes": ["A", "B"],
    "edges": [
        {"source": "A", "target": "B", "edge_type": "directed", "weight": 1.5},
    ],
}
PROJECTED_ORIGINAL_GRAPH = {
    "nodes": [{"id": "A", "label": "A"}, {"id": "B", "label": "B"}],
    "edges": [
        {
            "from": "A",
            "to": "B",
            "arrows": "to",
            "dashes": False,
            "weight": 1.5,
            "label": "1.5",
        }
    ],
}
REVISED_GRAPH = {
    "nodes": [{"id": "A", "label": "A"}, {"id": "B", "label": "B"}],
    "edges": [
        {"from": "B", "to": "A", "arrows": "to", "dashes": False, "label": ""}
    ],
}


def _final_state(postprocess_result, analysis_data=None):
    """构造报告完成时 process_final_result 所需的最小状态。"""
    return {
        "messages": [AIMessage(content="report ready", name="report")],
        "final_report": "report body",
        "causal_analysis_result": {
            "success": True,
            "data": ORIGINAL_GRAPH if analysis_data is None else analysis_data,
        },
        "postprocess_result": postprocess_result,
    }


def _assert_frontend_graph(graph):
    """前端 vis-network 只接受带 id 的节点和带 from/to 的边。"""
    assert graph["nodes"] and all(
        isinstance(node["id"], str) and node["label"] for node in graph["nodes"]
    )
    assert graph["edges"] and all(
        isinstance(edge["from"], str) and isinstance(edge["to"], str)
        for edge in graph["edges"]
    )


def test_final_result_projects_internal_graph_for_frontend():
    """没有修订图时，内部 StandardizedGraph 必须先投影再公开。"""
    result = process_final_result(_final_state(None))

    assert result["type"] == "causal_graph"
    assert result["data"] == PROJECTED_ORIGINAL_GRAPH
    assert result["graph_source"] == "original"
    _assert_frontend_graph(result["data"])

    _content, attachments = prepare_ai_response_for_storage(result)
    persisted = json.loads(attachments[0]["content"])
    assert persisted["data"] == PROJECTED_ORIGINAL_GRAPH


def test_final_result_falls_back_to_unprojectable_payload_instead_of_failing():
    """无法识别的图结构不能让最终结果整体失败。"""
    result = process_final_result(
        _final_state(None, analysis_data={"nodes": [1, 2], "edges": []})
    )

    assert result["type"] == "causal_graph"
    assert result["data"] == {"nodes": [1, 2], "edges": []}


def test_project_causal_graph_keeps_vis_network_payload_stable():
    """已转换过的载荷重复投影结果不变，旧附件与兼容链路才能继续使用。"""
    assert project_causal_graph(REVISED_GRAPH) == REVISED_GRAPH
    assert project_causal_graph(PROJECTED_ORIGINAL_GRAPH) == PROJECTED_ORIGINAL_GRAPH


def test_project_causal_graph_rejects_unknown_shapes():
    assert project_causal_graph(None) is None
    assert project_causal_graph("A -> B") is None
    assert project_causal_graph({"nodes": ["A"]}) is None
    assert project_causal_graph({"nodes": ["A"], "edges": [{"source": "A"}]}) is None


def test_final_result_uses_valid_revised_graph_and_history_persists_same_data():
    """最终 SSE 与历史附件必须保存同一份修订图。"""
    result = process_final_result(
        _final_state(
            {
                "revised_graph": REVISED_GRAPH,
                "revision_summary": "reversed A to B",
            }
        )
    )

    assert result["type"] == "causal_graph"
    assert result["data"] == REVISED_GRAPH
    assert result["graph_source"] == "postprocessed"
    assert result["revision_summary"] == "reversed A to B"
    _assert_frontend_graph(result["data"])

    _content, attachments = prepare_ai_response_for_storage(result)
    persisted = json.loads(attachments[0]["content"])
    assert persisted["data"] == REVISED_GRAPH
    assert persisted["graph_source"] == "postprocessed"


def test_final_result_exposes_only_finalization_status() -> None:
    state = _final_state(None)
    state["finalization_status"] = "degraded"
    result = process_final_result(state)

    assert result["finalization_status"] == "degraded"
    assert "finalization_error" not in result


@pytest.mark.parametrize(
    "postprocess_result",
    [
        None,
        {},
        {"revised_graph": []},
        {"revised_graph": {"nodes": [], "edges": "invalid"}},
        {"revised_graph": REVISED_GRAPH, "error": "postprocess failed"},
    ],
)
def test_final_result_falls_back_to_original_graph_when_revision_is_invalid(
    postprocess_result,
):
    """缺失、结构错误或带 error 的修订结果都必须安全回退原图。"""
    result = process_final_result(_final_state(postprocess_result))

    assert result["data"] == PROJECTED_ORIGINAL_GRAPH
    assert result["graph_source"] == "original"
