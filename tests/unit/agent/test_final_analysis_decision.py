"""P2-U ToolStrategy 终态和 finalization retry 预算测试。"""

import asyncio
import pytest

from Agent.deep_agent import AgentRunContext, FinalizationGate, TrustedJobIdentity
from Agent.deep_agent.memory import build_in_memory_backend
from Agent.deep_agent_tools import (
    DataProfile,
    FakeAlgorithmExecutor,
    SafeErrorCode,
    build_algorithm_tools,
    build_default_registry,
)
from Agent.deep_agent_tools.adapters import build_default_adapters

from Agent.deep_agent.finalization import (
    FinalizationRetryController,
    StructuredResponseError,
    validate_decision_references,
    validate_structured_response,
)
from Agent.causal_agent.graph import (
    _legacy_rag_evidence_result,
    _legacy_web_evidence_result,
)
from Agent.deep_agent_tools.models import EvidenceResult, WebEvidenceResult


def _decision():
    return {
        "outcome": "algorithm_supported",
        "primary_result_ref": "result-1",
        "result_assessments": [
            {"result_ref": "result-1", "disposition": "primary", "rationale": "valid"}
        ],
        "conflict_status": "none",
        "conflicts": [],
        "revision_proposals": [],
        "selection_rationale": "selected by evidence",
        "confidence": "medium",
        "confidence_basis": ["diagnostics"],
    }


def test_structured_response_and_reference_closure_are_required() -> None:
    decision = validate_structured_response(_decision())
    assert decision.primary_result_ref == "result-1"
    validate_decision_references(decision, algorithm_result_refs={"result-1"})
    with pytest.raises(StructuredResponseError, match="unknown algorithm result"):
        validate_decision_references(decision, algorithm_result_refs=set())


def test_retry_budget_allows_exactly_one_retry() -> None:
    controller = FinalizationRetryController()
    assert controller.can_retry
    assert controller.consume() == 1
    assert not controller.can_retry
    with pytest.raises(StructuredResponseError, match="exhausted"):
        controller.consume()


def _algorithm_execution(*, failure: bool = False):
    identity = TrustedJobIdentity(
        job_id="00000000-0000-0000-0000-000000000201",
        session_id="00000000-0000-0000-0000-000000000202",
        user_id=7,
        attempt_count=0,
        lease_epoch=1,
        worker_id="worker-1",
        input_identity="input-sha",
    )
    executor = FakeAlgorithmExecutor(
        failures={"causal.pc": SafeErrorCode.ALGORITHM_EXECUTION_FAILED}
        if failure
        else {}
    )
    backend = build_in_memory_backend(user_id=7)
    context = AgentRunContext(
        execution_guard=None,
        trusted_identity=identity,
        algorithm_executor=executor,
        filesystem_backend=backend,
    )
    registry = build_default_registry(
        build_default_adapters(executor=executor, raw_backend=backend)
    )
    tool = next(
        item
        for item in build_algorithm_tools(
            registry,
            runtime_context=context,
            data_profile=DataProfile(
                row_count=100,
                column_count=2,
                column_names=("x", "y"),
                numeric_columns=("x", "y"),
            ),
        )
        if item.name == "causal_pc"
    ).to_langchain_tool()
    command = asyncio.run(
        tool.coroutine(
            runtime=type(
                "Runtime",
                (),
                {
                    "tool_call_id": "gate-call-1",
                    "state": {"message_execution_id": "gate-response-1"},
                    "context": context,
                },
            )(),
            alpha=0.05,
        )
    )
    result = next(iter(command.update["algorithm_results"].values()))
    ledger = next(iter(command.update["action_ledger"].values()))
    return identity, registry, result, ledger


def test_finalization_gate_accepts_only_ledger_backed_primary_result() -> None:
    identity, registry, result, ledger = _algorithm_execution()
    decision = validate_structured_response(
        {
            **_decision(),
            "primary_result_ref": result.result_ref,
            "result_assessments": [
                {
                    "result_ref": result.result_ref,
                    "disposition": "primary",
                    "rationale": "the validated result is selected",
                }
            ],
        }
    )

    accepted = FinalizationGate(registry=registry).validate(
        decision=decision,
        algorithm_results={result.result_ref: result},
        action_ledger={ledger.invocation_id: ledger},
        trusted_identity=identity,
    )

    assert accepted.primary_result_ref == result.result_ref


def test_finalization_gate_requires_every_valid_result_assessment() -> None:
    identity, registry, result, ledger = _algorithm_execution()
    decision = validate_structured_response(
        {
            **_decision(),
            "outcome": "evidence_only",
            "primary_result_ref": None,
            "result_assessments": [],
        }
    )

    with pytest.raises(StructuredResponseError, match="each eligible valid result"):
        FinalizationGate(registry=registry).validate(
            decision=decision,
            algorithm_results={result.result_ref: result},
            action_ledger={ledger.invocation_id: ledger},
            trusted_identity=identity,
        )


def test_finalization_gate_accepts_no_valid_algorithm_only_after_a_failed_call() -> None:
    identity, registry, result, ledger = _algorithm_execution(failure=True)
    decision = validate_structured_response(
        {
            "outcome": "no_valid_algorithm",
            "primary_result_ref": None,
            "result_assessments": [],
            "conflict_status": "none",
            "conflicts": [],
            "revision_proposals": [],
            "selection_rationale": "the algorithm call did not produce a valid result",
            "confidence": "low",
            "confidence_basis": ["execution ledger"],
        }
    )

    accepted = FinalizationGate(registry=registry).validate(
        decision=decision,
        algorithm_results={result.result_ref: result},
        action_ledger={ledger.invocation_id: ledger},
        trusted_identity=identity,
    )

    assert accepted.outcome == "no_valid_algorithm"


def test_deep_agent_evidence_projection_keeps_report_snippets_and_sources() -> None:
    rag = EvidenceResult(
        evidence_ref="rag:1",
        snippet="RAG snippet",
        source_title="Knowledge source",
        source_url="https://example.invalid/rag",
        release_id="mm_" + "a" * 20,
    )
    web = WebEvidenceResult(
        evidence_ref="web:1",
        snippet="Web snippet",
        source_title="Web source",
        source_url="https://example.invalid/web",
        provider_status="available",
        fetched_at="2026-09-15T00:00:00Z",
    )

    rag_result = _legacy_rag_evidence_result({"rag:1": rag})
    web_result = _legacy_web_evidence_result({"web:1": web})

    assert rag_result["success"] is True
    assert "RAG snippet" in rag_result["questions"][0]["answer"]
    assert rag_result["questions"][0]["citations"] == ["rag:1"]
    assert web_result["success"] is True
    assert web_result["content"][0]["text"] == "Web snippet"
    assert web_result["content"][0]["url"] == "https://example.invalid/web"

