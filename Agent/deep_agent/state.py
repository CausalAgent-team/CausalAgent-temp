"""Explicit parent/Deep-Agent State projections for P2-U."""

from __future__ import annotations

from typing import Annotated, Any

from deepagents import DeepAgentState

from Agent.deep_agent_tools.models import (
    AlgorithmExecutionCommand,
    AlgorithmResult,
    DataProfile,
    EvidenceResult,
    FinalAnalysisDecision,
    InvocationRecord,
    WebEvidenceResult,
    merge_action_ledger,
    merge_algorithm_results,
    merge_evidence_results,
)


class ProjectDeepAgentState(DeepAgentState, total=False):
    """Official DeepAgentState plus project-owned, reducer-backed fields."""

    data_profile: DataProfile | None
    pending_command: AlgorithmExecutionCommand | None
    algorithm_results: Annotated[dict[str, AlgorithmResult], merge_algorithm_results]
    action_ledger: Annotated[dict[str, InvocationRecord], merge_action_ledger]
    rag_evidence: Annotated[dict[str, EvidenceResult], merge_evidence_results]
    web_evidence: Annotated[
        dict[str, WebEvidenceResult], merge_evidence_results
    ]
    structured_response: FinalAnalysisDecision | None


def project_parent_to_deep(parent_state: dict[str, Any]) -> ProjectDeepAgentState:
    """Project only durable business inputs; runtime dependencies stay out of State."""

    file_summary = parent_state.get("file_summary") or {}
    column_names = tuple(file_summary.get("columns") or ())
    row_count = file_summary.get("rows")
    if not isinstance(row_count, int) or row_count < 0:
        row_count = 0
    profile = DataProfile(
        row_count=row_count,
        column_count=len(column_names),
        column_names=column_names,
    )
    return {
        "messages": list(parent_state.get("messages") or []),
        "data_profile": profile,
        "pending_command": None,
        "algorithm_results": {},
        "action_ledger": {},
        "rag_evidence": {},
        "web_evidence": {},
        "structured_response": None,
    }


def project_deep_to_parent(
    deep_state: ProjectDeepAgentState,
) -> dict[str, Any]:
    """Return an explicit isolated payload for the legacy parent boundary."""

    results = deep_state.get("algorithm_results") or {}
    ledger = deep_state.get("action_ledger") or {}
    return {
        "causal_analysis_result": {
            "algorithm_results": {
                key: value.model_dump(mode="json")
                if isinstance(value, AlgorithmResult)
                else value
                for key, value in results.items()
            },
            "action_ledger": {
                key: value.model_dump(mode="json")
                if isinstance(value, InvocationRecord)
                else value
                for key, value in ledger.items()
            },
        },
    }
