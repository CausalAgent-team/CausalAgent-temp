"""Deep Agent State、父子 State 显式投影和 checkpoint reducer 绑定。"""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Annotated, Any, TypedDict

from Agent.deep_agent_tools.models import (
    DataProfile,
    EvidenceResult,
    FinalAnalysisDecision,
    InvocationRecord,
    WebEvidenceResult,
    merge_action_ledger,
    merge_algorithm_results,
    merge_evidence_results,
)

try:  # pragma: no cover - 真实依赖在 Docker/Spike 环境中验证
    from deepagents.graph import DeepAgentState as _OfficialDeepAgentState
except (ImportError, ModuleNotFoundError):

    class _OfficialDeepAgentState(TypedDict, total=False):
        """没有安装 deepagents 时用于协议测试的最小兼容基类。"""

        messages: list[Any]


class DeepAgentState(_OfficialDeepAgentState, total=False):
    """保留官方 messages 字段，并扩展项目领域 State。"""

    data_profile: DataProfile
    analysis_question: str
    analysis_parameters: dict[str, Any]
    file_summary: dict[str, Any]
    missing_values_present: bool
    message_execution_id: str
    provider_response_id: str | None
    algorithm_results: Annotated[dict[str, Any], merge_algorithm_results]
    action_ledger: Annotated[dict[str, InvocationRecord], merge_action_ledger]
    rag_evidence: Annotated[dict[str, EvidenceResult], merge_evidence_results]
    web_evidence: Annotated[dict[str, WebEvidenceResult], merge_evidence_results]
    structured_response: FinalAnalysisDecision | None
    finalization_retry_count: int
    model_call_count: int
    tool_call_count: int


class ProjectDeepAgentState(DeepAgentState, total=False):
    """项目内层 State 的命名类型。

    ``algorithm_results`` 等字段的 reducer 通过 ``Annotated`` 绑定；初始状态
    始终显式放入空 map，保证没有工具调用时 Action Ledger 也存在。
    """


class ParentStateUpdate(TypedDict, total=False):
    """Deep Agent 能回写父图的白名单字段。"""

    deep_agent_algorithm_results: dict[str, Any]
    deep_agent_action_ledger: dict[str, InvocationRecord]
    deep_agent_rag_evidence: dict[str, EvidenceResult]
    deep_agent_web_evidence: dict[str, WebEvidenceResult]
    deep_agent_decision: FinalAnalysisDecision | None
    deep_agent_structured_response: FinalAnalysisDecision | None
    deep_agent_messages: list[Any]


def _as_data_profile(value: object, parent_state: Mapping[str, Any]) -> DataProfile:
    if isinstance(value, DataProfile):
        return value.model_copy(deep=True)
    if isinstance(value, Mapping):
        return DataProfile.model_validate(value)

    analysis_parameters = parent_state.get("analysis_parameters")
    if isinstance(analysis_parameters, Mapping):
        columns = tuple(
            str(column)
            for column in analysis_parameters.get("columns", ())
            if str(column)
        )
        column_profiles = analysis_parameters.get("column_profiles")
        if isinstance(column_profiles, Mapping):
            numeric_columns = tuple(
                column
                for column in columns
                if isinstance(column_profiles.get(column), Mapping)
                and column_profiles[column].get("inferred_type") == "continuous"
            )
            categorical_columns = tuple(
                column for column in columns if column not in numeric_columns
            )
        else:
            numeric_columns = ()
            categorical_columns = ()
        rows = analysis_parameters.get("n_rows") or 0
        if columns or rows:
            return DataProfile(
                row_count=max(0, int(rows)),
                column_count=len(columns),
                column_names=columns,
                numeric_columns=numeric_columns,
                categorical_columns=categorical_columns,
            )

    file_summary = parent_state.get("file_summary")
    if not isinstance(file_summary, Mapping):
        return DataProfile(row_count=0, column_count=0)
    columns = tuple(str(column) for column in file_summary.get("columns", ()) if str(column))
    rows = file_summary.get("rows") or 0
    return DataProfile(
        row_count=max(0, int(rows)),
        column_count=len(columns),
        column_names=columns,
    )


def initial_deep_agent_state(
    *,
    data_profile: DataProfile,
    analysis_question: str = "",
    analysis_parameters: Mapping[str, Any] | None = None,
    file_summary: Mapping[str, Any] | None = None,
    messages: list[Any] | None = None,
    message_execution_id: str | None = None,
    missing_values_present: bool = False,
    algorithm_results: Mapping[str, Any] | None = None,
    action_ledger: Mapping[str, Any] | None = None,
    rag_evidence: Mapping[str, Any] | None = None,
    web_evidence: Mapping[str, Any] | None = None,
    finalization_retry_count: int = 0,
) -> ProjectDeepAgentState:
    """创建可直接 checkpoint 的最小内层 State。"""

    return ProjectDeepAgentState(
        messages=list(messages or []),
        data_profile=data_profile.model_copy(deep=True),
        analysis_question=analysis_question,
        analysis_parameters=dict(analysis_parameters or {}),
        file_summary=dict(file_summary or {}),
        missing_values_present=missing_values_present,
        **({"message_execution_id": message_execution_id} if message_execution_id else {}),
        algorithm_results=dict(algorithm_results or {}),
        action_ledger=dict(action_ledger or {}),
        rag_evidence=dict(rag_evidence or {}),
        web_evidence=dict(web_evidence or {}),
        structured_response=None,
        finalization_retry_count=finalization_retry_count,
        model_call_count=0,
        tool_call_count=0,
    )


def _missing_values_from_parent(parent_state: Mapping[str, Any]) -> bool:
    explicit = parent_state.get("missing_values_present")
    if explicit is not None:
        return bool(explicit)
    analysis_parameters = parent_state.get("analysis_parameters")
    if not isinstance(analysis_parameters, Mapping):
        return False
    quality = analysis_parameters.get("quality_assessment")
    if isinstance(quality, Mapping) and float(quality.get("total_missing_ratio") or 0) > 0:
        return True
    profiles = analysis_parameters.get("column_profiles")
    if not isinstance(profiles, Mapping):
        return False
    return any(
        isinstance(profile, Mapping) and int(profile.get("missing_count") or 0) > 0
        for profile in profiles.values()
    )


def to_deep_agent_input(parent_state: Mapping[str, Any]) -> ProjectDeepAgentState:
    """只把 Deep Agent 所需字段投影到内层 State，不复制父状态。"""

    existing_child_messages = parent_state.get("deep_agent_messages")
    messages = existing_child_messages or parent_state.get("messages")
    if messages is None:
        messages = []
    if not isinstance(messages, list):
        messages = list(messages)
    analysis_parameters = parent_state.get("analysis_parameters")
    if not isinstance(analysis_parameters, Mapping):
        analysis_parameters = {}
    file_summary = parent_state.get("file_summary")
    if not isinstance(file_summary, Mapping):
        file_summary = {}
    data_profile = _as_data_profile(parent_state.get("data_profile"), parent_state)
    if not existing_child_messages:
        messages = [
            *messages,
            {
                "role": "system",
                "content": json.dumps(
                    {
                        "analysis_question": str(
                            parent_state.get("analysis_question")
                            or parent_state.get("user_question")
                            or ""
                        ),
                        "data_profile": data_profile.model_dump(mode="json"),
                        "analysis_parameters": dict(analysis_parameters),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            },
        ]
    retry_instruction = parent_state.get("deep_agent_retry_instruction")
    if isinstance(retry_instruction, str) and retry_instruction.strip():
        # 使用普通消息值而不是把 Runtime/异常对象放进 State；LangChain 会在
        # 真正模型调用前把标准 role/content mapping 转成 HumanMessage。
        messages = [
            *messages,
            {
                "role": "user",
                "content": retry_instruction.strip(),
            },
        ]
    return initial_deep_agent_state(
        data_profile=data_profile,
        analysis_question=str(
            parent_state.get("analysis_question")
            or parent_state.get("user_question")
            or ""
        ),
        analysis_parameters=analysis_parameters,
        file_summary=file_summary,
        messages=messages,
        message_execution_id=(
            str(parent_state["message_execution_id"])
            if parent_state.get("message_execution_id")
            else None
        ),
        missing_values_present=_missing_values_from_parent(parent_state),
        algorithm_results=parent_state.get("deep_agent_algorithm_results"),
        action_ledger=parent_state.get("deep_agent_action_ledger"),
        rag_evidence=parent_state.get("deep_agent_rag_evidence"),
        web_evidence=parent_state.get("deep_agent_web_evidence"),
        finalization_retry_count=int(parent_state.get("finalization_retry_count") or 0),
    )


def from_deep_agent_output(state: Mapping[str, Any]) -> ParentStateUpdate:
    """从内层输出投影固定白名单，禁止任意 key 覆盖父图 State。"""

    result: ParentStateUpdate = {
        "deep_agent_algorithm_results": dict(state.get("algorithm_results") or {}),
        "deep_agent_action_ledger": dict(state.get("action_ledger") or {}),
        "deep_agent_rag_evidence": dict(state.get("rag_evidence") or {}),
        "deep_agent_web_evidence": dict(state.get("web_evidence") or {}),
        "deep_agent_decision": state.get("structured_response"),
        "deep_agent_structured_response": state.get("structured_response"),
        "deep_agent_messages": list(state.get("messages") or []),
    }
    return result


def assert_checkpoint_state_safe(state: Mapping[str, Any]) -> None:
    """检查常见 runtime-only key 不会被写入 checkpoint。"""

    forbidden = {
        "execution_guard",
        "algorithm_executor",
        "rag_executor",
        "web_executor",
        "filesystem_backend",
        "trusted_identity",
        "store",
        "checkpointer",
    }
    leaked = forbidden.intersection(state)
    if leaked:
        raise TypeError(
            "runtime-only fields must not enter checkpoint state: "
            + ", ".join(sorted(leaked))
        )
