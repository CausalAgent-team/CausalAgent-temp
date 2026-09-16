"""结构化终态的静态校验和一次性修正预算。"""

from __future__ import annotations

from collections.abc import Mapping, Set
from dataclasses import dataclass
from typing import Any

from Agent.deep_agent_tools.identity import build_invocation_id
from Agent.deep_agent_tools.models import (
    AlgorithmResult,
    FinalAnalysisDecision,
    InvocationRecord,
    validate_result_ref_for_invocation,
)


class StructuredResponseError(ValueError):
    """模型没有提交可验证的 ``structured_response``。"""


def validate_structured_response(value: Any) -> FinalAnalysisDecision:
    """只接受 ToolStrategy 产出的对象或等价 JSON mapping。"""

    if isinstance(value, FinalAnalysisDecision):
        return value.model_copy(deep=True)
    if isinstance(value, Mapping):
        try:
            return FinalAnalysisDecision.model_validate(value)
        except Exception as exc:  # Pydantic 的细节不能透传到公共输出
            raise StructuredResponseError("structured_response schema validation failed") from exc
    raise StructuredResponseError("structured_response is required")


def validate_decision_references(
    decision: FinalAnalysisDecision,
    *,
    algorithm_result_refs: Set[str],
    evidence_refs: Set[str] = frozenset(),
) -> FinalAnalysisDecision:
    """验证静态 schema 之外的引用闭包，不做科学判断。"""

    result_refs = set(algorithm_result_refs)
    assessment_refs = {item.result_ref for item in decision.result_assessments}
    if not assessment_refs.issubset(result_refs):
        raise StructuredResponseError("decision references an unknown algorithm result")
    if decision.primary_result_ref and decision.primary_result_ref not in result_refs:
        raise StructuredResponseError("primary_result_ref is not an available result")
    for proposal in decision.revision_proposals:
        if proposal.result_ref not in result_refs:
            raise StructuredResponseError("revision proposal references an unknown result")
        if not set(proposal.evidence_refs).issubset(evidence_refs):
            raise StructuredResponseError("revision proposal references unknown evidence")
    for conflict in decision.conflicts:
        if not set(conflict.result_refs).issubset(result_refs):
            raise StructuredResponseError("conflict references an unknown result")
    return decision.model_copy(deep=True)


class FinalizationGate:
    """只用程序事实校验 Deep Agent 的最终决策。

    Gate 不调用模型，也不修改结果、Ledger 或 graph。它只接受当前可信
    ``job/attempt/lease`` 的结果，并把 decision 中的动态引用与完整算法
    Action Ledger 对账；因此 stale worker 的结果不能通过最终报告入口。
    """

    def __init__(self, *, registry: Any | None = None) -> None:
        self.registry = registry
        self._algorithm_tool_names = frozenset(
            entry.spec.tool_name
            for entry in getattr(registry, "entries", ())
        )

    @staticmethod
    def _identity_value(identity: Any, name: str) -> Any:
        value = getattr(identity, name, None)
        if value is None:
            raise StructuredResponseError("trusted job identity is incomplete")
        return value

    @staticmethod
    def _coerce_results(value: Mapping[str, Any] | None) -> dict[str, AlgorithmResult]:
        results: dict[str, AlgorithmResult] = {}
        for key, raw_result in dict(value or {}).items():
            try:
                result = AlgorithmResult.model_validate(raw_result)
            except Exception as exc:
                raise StructuredResponseError("algorithm result state is invalid") from exc
            if key != result.result_ref:
                raise StructuredResponseError("algorithm result map key is invalid")
            results[key] = result
        return results

    @staticmethod
    def _coerce_ledger(value: Mapping[str, Any] | None) -> dict[str, InvocationRecord]:
        ledger: dict[str, InvocationRecord] = {}
        for key, raw_record in dict(value or {}).items():
            try:
                record = InvocationRecord.model_validate(raw_record)
            except Exception as exc:
                raise StructuredResponseError("action ledger state is invalid") from exc
            if key != record.invocation_id:
                raise StructuredResponseError("action ledger map key is invalid")
            ledger[key] = record
        return ledger

    @staticmethod
    def _expected_result_final_status(status: str) -> str:
        return {
            "valid": "succeeded",
            "not_ready": "not_ready",
            "timed_out": "timed_out",
            "invalid_input": "failed",
            "not_applicable": "failed",
            "execution_failed": "failed",
        }[status]

    def _is_algorithm_record(self, record: InvocationRecord) -> bool:
        if self._algorithm_tool_names:
            return record.tool_name in self._algorithm_tool_names
        return record.tool_name.startswith("causal_")

    def _current_ledger(
        self,
        ledger: Mapping[str, InvocationRecord],
        *,
        job_id: str,
    ) -> dict[str, InvocationRecord]:
        current: dict[str, InvocationRecord] = {}
        for record in ledger.values():
            try:
                expected_id = build_invocation_id(
                    job_id=job_id,
                    response_identity=record.response_identity,
                    provider_call_id=record.provider_call_id,
                )
            except (TypeError, ValueError) as exc:
                raise StructuredResponseError("action ledger identity is invalid") from exc
            if expected_id != record.invocation_id:
                if record.job_id == job_id:
                    # 当前 Job 上的记录却无法由其 response/provider identity
                    # 重建出 invocation_id，不能把它当作普通 stale 历史吞掉。
                    raise StructuredResponseError("action ledger identity is invalid")
                # 这不是一个当前 Job 的调用；stale/foreign 记录仍可保留在
                # checkpoint，但不得被当前 decision 引用或计入 no_valid。
                continue
            if (
                record.job_id is None
                or record.attempt_count is None
                or record.lease_epoch is None
                or record.worker_id is None
                or record.input_identity is None
            ):
                raise StructuredResponseError(
                    "action ledger ownership is incomplete"
                )
            if record.job_id != job_id:
                # invocation_id 已经指向当前 Job，却声明了另一个 Job 的所有权，
                # 这是跨 Job 污染而不是可忽略的 stale 记录。
                raise StructuredResponseError("action ledger Job ownership mismatch")
            if not self._is_algorithm_record(record):
                continue
            if record.final_status == "pending" or not record.attempts:
                raise StructuredResponseError("algorithm action ledger is not terminal")
            current[record.invocation_id] = record
        return current

    def _validate_result_ledger_pair(
        self,
        result: AlgorithmResult,
        record: InvocationRecord,
        *,
        identity: Any,
    ) -> None:
        try:
            validate_result_ref_for_invocation(
                result.result_ref,
                result.invocation_id,
            )
        except ValueError as exc:
            raise StructuredResponseError("algorithm result reference is invalid") from exc
        if record.provider_call_id != result.provider_call_id:
            raise StructuredResponseError("result and ledger provider call IDs differ")
        if record.tool_name != self._tool_name_for_result(result):
            raise StructuredResponseError("result and ledger tool names differ")
        expected_id = build_invocation_id(
            job_id=identity.job_id,
            response_identity=record.response_identity,
            provider_call_id=record.provider_call_id,
        )
        if expected_id != result.invocation_id or record.invocation_id != result.invocation_id:
            raise StructuredResponseError("result invocation identity is invalid")
        if record.result_ref not in (None, result.result_ref):
            raise StructuredResponseError("result and ledger result references differ")
        expected_status = self._expected_result_final_status(result.status)
        if record.final_status != expected_status:
            raise StructuredResponseError("result and ledger terminal status differ")
        provenance = result.provenance
        if provenance.job_id != str(identity.job_id):
            raise StructuredResponseError("result does not belong to the trusted Job")
        if provenance.attempt_count != int(identity.attempt_count):
            raise StructuredResponseError("result attempt does not match the trusted Job")
        if provenance.lease_epoch != int(identity.lease_epoch):
            raise StructuredResponseError("result lease does not match the trusted Job")
        if provenance.input_identity != identity.input_identity:
            raise StructuredResponseError("result input identity does not match the Job")
        latest_attempt = max(
            record.attempts.values(),
            key=lambda attempt: (attempt.retry_ordinal, attempt.revision),
        )
        expected_attempt_status = {
            "succeeded": "succeeded",
            "not_ready": "not_ready",
            "timed_out": "timed_out",
            "failed": "failed",
        }[expected_status]
        if latest_attempt.status != expected_attempt_status:
            raise StructuredResponseError("result and ledger attempt status differ")

    def _tool_name_for_result(self, result: AlgorithmResult) -> str:
        if self.registry is None:
            return {
                "causal.pc": "causal_pc",
                "causal.olc": "causal_olc",
                "causal.direct_lingam": "causal_direct_lingam",
            }.get(result.capability_id, result.capability_id)
        try:
            entry = self.registry.get(result.capability_id)
        except Exception as exc:
            raise StructuredResponseError("result capability is not registered") from exc
        if entry.spec.version != result.capability_version:
            raise StructuredResponseError("result capability version is not registered")
        if result.provenance.spec_digest != entry.spec.spec_digest:
            raise StructuredResponseError("result spec digest is not registered")
        return entry.spec.tool_name

    def validate(
        self,
        *,
        decision: Any,
        algorithm_results: Mapping[str, Any] | None,
        action_ledger: Mapping[str, Any] | None,
        trusted_identity: Any,
        rag_evidence: Mapping[str, Any] | None = None,
        web_evidence: Mapping[str, Any] | None = None,
    ) -> FinalAnalysisDecision:
        """校验并返回可安全交给 report 的 decision 副本。"""

        normalized_decision = validate_structured_response(decision)
        results = self._coerce_results(algorithm_results)
        ledger = self._coerce_ledger(action_ledger)
        job_id = str(self._identity_value(trusted_identity, "job_id"))
        current_attempt = int(self._identity_value(trusted_identity, "attempt_count"))
        current_lease = int(self._identity_value(trusted_identity, "lease_epoch"))
        current_worker = str(self._identity_value(trusted_identity, "worker_id"))
        current_input = str(self._identity_value(trusted_identity, "input_identity"))
        current_ledger = self._current_ledger(ledger, job_id=job_id)
        current_ledger = {
            key: record
            for key, record in current_ledger.items()
            if record.attempt_count == current_attempt
            and record.lease_epoch == current_lease
            and record.worker_id == current_worker
            and record.input_identity == current_input
        }

        eligible: dict[str, AlgorithmResult] = {}
        for result in results.values():
            provenance = result.provenance
            if (
                provenance.job_id == job_id
                and provenance.attempt_count
                == int(self._identity_value(trusted_identity, "attempt_count"))
                and provenance.lease_epoch
                == int(self._identity_value(trusted_identity, "lease_epoch"))
            ):
                eligible[result.result_ref] = result

        for result in eligible.values():
            record = current_ledger.get(result.invocation_id)
            if record is None:
                raise StructuredResponseError("eligible result has no matching ledger record")
            self._validate_result_ledger_pair(
                result,
                record,
                identity=trusted_identity,
            )

        evidence_refs = {
            *dict(rag_evidence or {}).keys(),
            *dict(web_evidence or {}).keys(),
        }
        normalized_decision = validate_decision_references(
            normalized_decision,
            algorithm_result_refs=set(eligible),
            evidence_refs=evidence_refs,
        )

        valid_refs = {
            result.result_ref
            for result in eligible.values()
            if result.status == "valid"
        }
        assessment_by_ref = {
            assessment.result_ref: assessment
            for assessment in normalized_decision.result_assessments
        }
        if not valid_refs.issubset(assessment_by_ref):
            raise StructuredResponseError("each eligible valid result needs one assessment")
        for assessment in normalized_decision.result_assessments:
            result = eligible[assessment.result_ref]
            if result.status != "valid" and assessment.disposition != "discarded":
                raise StructuredResponseError("non-valid results may only be discarded")

        if normalized_decision.outcome == "algorithm_supported":
            primary = normalized_decision.primary_result_ref
            if primary not in valid_refs:
                raise StructuredResponseError("primary result must be an eligible valid result")
        elif normalized_decision.outcome == "evidence_only":
            if any(
                assessment_by_ref[ref].disposition != "discarded"
                for ref in valid_refs
            ):
                raise StructuredResponseError(
                    "evidence_only must discard every eligible valid result"
                )
        elif normalized_decision.outcome == "no_valid_algorithm":
            if valid_refs:
                raise StructuredResponseError("no_valid_algorithm has an eligible valid result")
            if not current_ledger:
                raise StructuredResponseError(
                    "no_valid_algorithm requires a real algorithm invocation"
                )

        return normalized_decision


@dataclass
class FinalizationRetryController:
    """Gate 动态不一致后最多把修正机会交还 Deep Agent 一次。"""

    retry_limit: int = 1
    retries_used: int = 0

    def __post_init__(self) -> None:
        if self.retry_limit < 0:
            raise ValueError("retry_limit must be non-negative")
        if self.retries_used < 0 or self.retries_used > self.retry_limit:
            raise ValueError("retries_used is outside retry_limit")

    @property
    def can_retry(self) -> bool:
        return self.retries_used < self.retry_limit

    def consume(self) -> int:
        if not self.can_retry:
            raise StructuredResponseError("finalization retry budget exhausted")
        self.retries_used += 1
        return self.retries_used

