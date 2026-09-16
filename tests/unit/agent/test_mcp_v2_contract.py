"""P2-M MCP v2 contracts and bounded-resource behavior."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import time
from unittest.mock import patch

import pytest

from Agent.CausalAgentMCP.auth import McpAuthError, sign_invocation, verify_invocation
from Agent.CausalAgentMCP.config import McpServerConfig
from Agent.CausalAgentMCP.executor_pool import (
    BoundedProcessPool,
    ExecutionOutcome,
    PoolExecutionError,
)
from Agent.CausalAgentMCP.runner_registry import _pc, build_default_registry
from Agent.CausalAgentMCP.service import CausalMcpService, McpServiceError
from Agent.deep_agent_tools.algorithm_specs import PC_SPEC
from Agent.deep_agent_tools.error_codes import SafeErrorCode
from Agent.deep_agent_tools.identity import build_result_ref
from Agent.deep_agent_tools.models import (
    AlgorithmExecutionCommand,
    AlgorithmResult,
    AlgorithmResultProvenance,
    McpInvocationContext,
    StandardizedGraph,
)
from Agent.deep_agent_tools.mcp_algorithm_executor import McpAlgorithmExecutor
from app.agent.worker.mcp_client_pool import (
    McpClientPool,
    McpClientPoolConfig,
    McpPoolError,
    McpTransportError,
)
from app.agent.worker.execution_guard import JobExecutionGuard, JobExecutionRevoked
from observability.logging_runtime import current_log_context


def _context() -> McpInvocationContext:
    issued = datetime.now(timezone.utc)
    return McpInvocationContext(
        invocation_id="00000000-0000-0000-0000-000000000001",
        job_id="00000000-0000-0000-0000-000000000002",
        session_id="00000000-0000-0000-0000-000000000003",
        user_id=7,
        attempt_count=1,
        lease_epoch=4,
        worker_id="worker-1",
        input_snapshot_digest="file-hash",
        issued_at=issued,
        expires_at=issued + timedelta(minutes=5),
        key_id="current",
    )


def _command(context: McpInvocationContext) -> AlgorithmExecutionCommand:
    return AlgorithmExecutionCommand(
        invocation_id=context.invocation_id,
        capability_id=PC_SPEC.capability_id,
        capability_version=PC_SPEC.version,
        spec_digest=PC_SPEC.spec_digest,
        provider_call_id="call-1",
        input_identity="file-hash",
        parameters={"alpha": 0.05},
    )


def _config() -> McpServerConfig:
    return McpServerConfig(
        service_token="service-token",
        signing_key_current="secret",
        signing_key_previous=None,
        signing_key_id="current",
        signing_key_previous_id="previous",
    )


def _sleep_runner(_csv_data, parameters):
    time.sleep(parameters["delay"])
    return {"ok": True, "delay": parameters["delay"]}


def test_hmac_binds_command_and_rejects_expired_context() -> None:
    context = _context()
    command = _command(context)
    signature = sign_invocation(context, command, "secret")
    verify_invocation(
        context,
        command,
        signature,
        keys={"current": "secret"},
    )

    changed = command.model_copy(update={"parameters": {"alpha": 0.1}})
    with pytest.raises(McpAuthError):
        verify_invocation(context, changed, signature, keys={"current": "secret"})

    expired = context.model_copy(
        update={
            "issued_at": datetime.now(timezone.utc) - timedelta(minutes=5),
            "expires_at": datetime.now(timezone.utc) - timedelta(minutes=4),
        }
    )
    with pytest.raises(McpAuthError):
        verify_invocation(expired, command, signature, keys={"current": "secret"})


def test_service_returns_normalized_result_without_raw_runner_text() -> None:
    class FakePool:
        def ready(self) -> bool:
            return True

        async def execute(self, **kwargs):
            await kwargs["before_start"](0.01)
            return ExecutionOutcome(
                value={
                    "success": True,
                    "data": {
                        "nodes": [{"id": "A"}, {"id": "B"}],
                        "edges": [{"from": "A", "to": "B", "arrows": "to"}],
                    },
                    "diagnostics": {"n_samples": 10, "n_features": 2},
                },
                executor_slot_id="process-0",
            )

    async def scenario():
        context = _context()
        command = _command(context)
        service = CausalMcpService(
            config=_config(),
            registry=build_default_registry(),
            executor_pool=FakePool(),
            authority_reader=lambda _context: "A,B\n1,2\n3,4\n",
            database_probe=lambda: True,
        )
        payload = await service.execute_payload(
            {
                "command": command.model_dump(mode="json"),
                "trusted_context": context.model_dump(mode="json"),
                "signature": sign_invocation(context, command, "secret"),
            }
        )
        return payload

    payload = asyncio.run(scenario())
    assert payload["ok"] is True
    assert payload["result"]["status"] == "valid"
    assert payload["result"]["standardized_graph"]["edges"][0]["source"] == "A"
    assert "runner" not in payload["result"]


def test_service_logs_job_invocation_timeline_and_slow_threshold() -> None:
    class SlowPool:
        def ready(self) -> bool:
            return True

        async def execute(self, **kwargs):
            await kwargs["before_start"](0.01)
            await asyncio.sleep(0.03)
            return ExecutionOutcome(
                value={"success": True, "data": {"nodes": [], "edges": []}},
                executor_slot_id="process-0",
            )

    async def scenario():
        context = _context()
        command = _command(context)
        service = CausalMcpService(
            config=replace(_config(), slow_log_seconds=0.01),
            registry=build_default_registry(),
            executor_pool=SlowPool(),
            authority_reader=lambda _context: "A,B\n1,2\n3,4\n",
            database_probe=lambda: True,
        )
        observed = []

        def capture(_logger, event_code, **kwargs):
            observed.append((event_code, kwargs.get("details"), current_log_context()))

        with patch("Agent.CausalAgentMCP.service.log_event", side_effect=capture):
            payload = await service.execute_payload(
                {
                    "command": command.model_dump(mode="json"),
                    "trusted_context": context.model_dump(mode="json"),
                    "signature": sign_invocation(context, command, "secret"),
                }
            )
        return payload, observed

    payload, observed = asyncio.run(scenario())
    assert payload["ok"] is True
    assert [item[0] for item in observed] == [
        "mcp.request.received",
        "mcp.request.accepted",
        "mcp.tool.slow",
        "mcp.tool.finished",
    ]
    for _event, _details, context_fields in observed:
        assert context_fields["job_id"] == _context().job_id
        assert context_fields["invocation_id"] == _context().invocation_id
        assert context_fields["tool"] == PC_SPEC.capability_id


def test_bounded_pool_times_out_before_returning_late_result() -> None:
    def slow_runner(_csv_data, _parameters):
        import time

        time.sleep(0.12)
        return {"ok": True}

    async def scenario():
        pool = BoundedProcessPool(
            process_workers=1,
            queue_capacity=0,
            enqueue_timeout_seconds=0.02,
            executor_factory=ThreadPoolExecutor,
        )
        await pool.start()
        try:
            with pytest.raises(PoolExecutionError) as error:
                await pool.execute(
                    capability_id="test",
                    runner=slow_runner,
                    csv_data="A,B\n1,2\n",
                    parameters={},
                    timeout_seconds=0.01,
                    concurrency=1,
                )
            assert error.value.safe_error_code.value == "ALGORITHM_TIMED_OUT"
            await asyncio.sleep(0.15)
            result = await pool.execute(
                capability_id="test",
                runner=slow_runner,
                csv_data="A,B\n1,2\n",
                parameters={},
                timeout_seconds=1,
                concurrency=1,
            )
            assert result.value["ok"] is True
        finally:
            await pool.close()

    asyncio.run(scenario())


def test_bounded_pool_releases_capability_after_global_admission_timeout() -> None:
    def slow_runner(_csv_data, _parameters):
        import time

        time.sleep(0.08)
        return {"ok": True}

    def quick_runner(_csv_data, _parameters):
        return {"ok": True}

    async def scenario():
        pool = BoundedProcessPool(
            process_workers=1,
            queue_capacity=0,
            enqueue_timeout_seconds=0.01,
            executor_factory=ThreadPoolExecutor,
        )
        await pool.start()
        try:
            occupied = asyncio.create_task(
                pool.execute(
                    capability_id="capability.a",
                    runner=slow_runner,
                    csv_data="A\n1\n",
                    parameters={},
                    timeout_seconds=1,
                    concurrency=1,
                )
            )
            await asyncio.sleep(0.01)
            with pytest.raises(PoolExecutionError):
                await pool.execute(
                    capability_id="capability.b",
                    runner=quick_runner,
                    csv_data="A\n1\n",
                    parameters={},
                    timeout_seconds=1,
                    concurrency=1,
                )
            await occupied
            recovered = await pool.execute(
                capability_id="capability.b",
                runner=quick_runner,
                csv_data="A\n1\n",
                parameters={},
                timeout_seconds=1,
                concurrency=1,
            )
            assert recovered.value["ok"] is True
        finally:
            await pool.close()

    asyncio.run(scenario())


def test_cancel_terminates_only_the_target_invocation_process() -> None:
    async def scenario():
        pool = BoundedProcessPool(
            process_workers=2,
            queue_capacity=1,
        )
        await pool.start()
        identity = ("job-1", 1, 1, "worker-1")
        canceled = asyncio.create_task(
            pool.execute(
                capability_id="test.cancel",
                runner=_sleep_runner,
                csv_data="A\n1\n",
                parameters={"delay": 2.0},
                timeout_seconds=5,
                concurrency=2,
                invocation_id="inv-cancel",
                execution_identity=identity,
            )
        )
        sibling = asyncio.create_task(
            pool.execute(
                capability_id="test.cancel",
                runner=_sleep_runner,
                csv_data="A\n1\n",
                parameters={"delay": 0.1},
                timeout_seconds=5,
                concurrency=2,
                invocation_id="inv-sibling",
                execution_identity=identity,
            )
        )
        await asyncio.sleep(0.05)
        cancellation = await pool.cancel(
            "inv-cancel",
            execution_identity=identity,
        )
        assert cancellation.status == "canceled"
        with pytest.raises(PoolExecutionError) as error:
            await canceled
        assert error.value.safe_error_code == SafeErrorCode.ALGORITHM_CANCELED
        assert (await sibling).value["ok"] is True
        assert (
            await pool.cancel("inv-cancel", execution_identity=identity)
        ).status == "already_canceled"
        assert (
            await pool.cancel(
                "inv-cancel",
                execution_identity=("job-other", 1, 1, "worker-1"),
            )
        ).status == "identity_mismatch"
        await pool.close()

    asyncio.run(scenario())


def test_authority_reader_failure_is_mapped_to_safe_transport_error() -> None:
    class FakePool:
        def ready(self) -> bool:
            return True

    def broken_reader(_context):
        raise RuntimeError("driver connection details")

    async def scenario():
        context = _context()
        command = _command(context)
        service = CausalMcpService(
            config=_config(),
            registry=build_default_registry(),
            executor_pool=FakePool(),
            authority_reader=broken_reader,
            database_probe=lambda: True,
        )
        return await service.execute_payload(
            {
                "command": command.model_dump(mode="json"),
                "trusted_context": context.model_dump(mode="json"),
                "signature": sign_invocation(context, command, "secret"),
            }
        )

    payload = asyncio.run(scenario())
    assert payload["ok"] is True
    assert payload["result"]["status"] == "execution_failed"
    assert payload["result"]["diagnostics"]["safe_error_code"] == "MCP_TRANSPORT_FAILED"


def test_service_rechecks_lease_before_process_start_and_after_result() -> None:
    class FakePool:
        def ready(self) -> bool:
            return True

        async def execute(self, **kwargs):
            await kwargs["before_start"](0.01)
            return ExecutionOutcome(
                value={"success": True, "data": {"nodes": [], "edges": []}},
                executor_slot_id="process-0",
            )

    calls = 0

    def authority_reader(_context):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise McpServiceError(SafeErrorCode.MCP_LEASE_STALE)
        return "A,B\n1,2\n3,4\n"

    async def scenario():
        context = _context()
        command = _command(context)
        service = CausalMcpService(
            config=_config(),
            registry=build_default_registry(),
            executor_pool=FakePool(),
            authority_reader=authority_reader,
            database_probe=lambda: True,
        )
        return await service.execute_payload(
            {
                "command": command.model_dump(mode="json"),
                "trusted_context": context.model_dump(mode="json"),
                "signature": sign_invocation(context, command, "secret"),
            }
        )

    payload = asyncio.run(scenario())
    assert calls == 3
    assert payload["result"]["status"] == "execution_failed"
    assert payload["result"]["diagnostics"]["safe_error_code"] == "MCP_LEASE_STALE"


def test_pc_runner_forwards_spec_alpha(monkeypatch) -> None:
    observed = {}

    def fake_runner(csv_data, *, alpha):
        observed.update(csv_data=csv_data, alpha=alpha)
        return {"success": True}

    monkeypatch.setattr("Agent.causal.causalachieve.run_pc_analysis", fake_runner)
    assert _pc("A,B\n1,2\n", {"alpha": 0.2})["success"] is True
    assert observed == {"csv_data": "A,B\n1,2\n", "alpha": 0.2}


def test_service_exposes_algorithm_timeout_as_result_status() -> None:
    class TimeoutPool:
        def ready(self) -> bool:
            return True

        async def execute(self, **kwargs):
            await kwargs["before_start"](0.01)
            raise PoolExecutionError(SafeErrorCode.ALGORITHM_TIMED_OUT)

    async def scenario():
        context = _context()
        command = _command(context)
        service = CausalMcpService(
            config=_config(),
            registry=build_default_registry(),
            executor_pool=TimeoutPool(),
            authority_reader=lambda _context: "A,B\n1,2\n3,4\n",
            database_probe=lambda: True,
        )
        return await service.execute_payload(
            {
                "command": command.model_dump(mode="json"),
                "trusted_context": context.model_dump(mode="json"),
                "signature": sign_invocation(context, command, "secret"),
            }
        )

    payload = asyncio.run(scenario())
    assert payload["ok"] is True
    assert payload["result"]["status"] == "timed_out"


def test_service_cancel_is_identity_bound_and_idempotent() -> None:
    class CancelPool:
        def ready(self) -> bool:
            return True

        async def cancel(self, invocation_id, *, execution_identity):
            assert invocation_id == _context().invocation_id
            assert execution_identity == (
                _context().job_id,
                1,
                4,
                "worker-1",
            )
            return SimpleNamespace(status="canceled", invocation_id=invocation_id)

    async def scenario():
        context = _context()
        command = _command(context)
        service = CausalMcpService(
            config=_config(),
            registry=build_default_registry(),
            executor_pool=CancelPool(),
            authority_reader=lambda _context: "A,B\n1,2\n",
            database_probe=lambda: True,
        )
        return await service.cancel_payload(
            {
                "command": command.model_dump(mode="json"),
                "trusted_context": context.model_dump(mode="json"),
                "signature": sign_invocation(context, command, "secret"),
            }
        )

    payload = asyncio.run(scenario())
    assert payload["ok"] is True
    assert payload["cancellation"]["status"] == "canceled"


class _FakeClient:
    def __init__(self, _transport, **_kwargs):
        self.session = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def list_tools(self):
        return SimpleNamespace(
            tools=[
                SimpleNamespace(name="execute_algorithm"),
                SimpleNamespace(name="cancel_algorithm"),
            ]
        )

    async def call_tool(self, _name, arguments):
        return SimpleNamespace(structured_content={"ok": True, "arguments": arguments})


class _FakeHttpClient:
    async def __aexit__(self, *_args):
        return None


def test_client_pool_uses_one_scheduler_for_a_and_b_modes() -> None:
    async def scenario():
        for max_in_flight in (1, 2):
            pool = McpClientPool(
                McpClientPoolConfig(
                    url="http://causal-mcp:8080/mcp",
                    service_token="token",
                    pool_size=2,
                    max_in_flight_per_client=max_in_flight,
                    acquire_timeout_seconds=0.01,
                    max_connections=4,
                    max_keepalive_connections=4,
                ),
                http_client=_FakeHttpClient(),
                client_factory=_FakeClient,
                transport_factory=lambda *_args, **_kwargs: object(),
            )
            await pool.start()
            leases = [await pool.acquire() for _ in range(2 * max_in_flight)]
            try:
                with pytest.raises(McpPoolError):
                    await pool.acquire()
            finally:
                await asyncio.gather(*(lease.release() for lease in leases))
                await pool.close()

    asyncio.run(scenario())


def test_executor_reuses_invocation_id_for_structured_mcp_result() -> None:
    context = _context()
    command = _command(context)
    result = AlgorithmResult(
        result_ref=build_result_ref(invocation_id=context.invocation_id),
        invocation_id=context.invocation_id,
        provider_call_id=command.provider_call_id,
        capability_id=command.capability_id,
        capability_version=command.capability_version,
        status="valid",
        standardized_graph=StandardizedGraph(graph_semantics="dag"),
        provenance=AlgorithmResultProvenance(
            job_id=context.job_id,
            attempt_count=context.attempt_count,
            lease_epoch=context.lease_epoch,
            input_identity=command.input_identity,
            spec_digest=command.spec_digest,
            invocation_id=context.invocation_id,
            capability_id=command.capability_id,
            capability_version=command.capability_version,
        ),
    )

    class FakePool:
        async def call_tool(self, arguments, **_kwargs):
            assert arguments["trusted_context"]["job_id"] == context.job_id
            return SimpleNamespace(
                structured_content={"ok": True, "result": result.model_dump(mode="json")}
            )

    output = asyncio.run(
        McpAlgorithmExecutor(FakePool(), signing_key="secret").execute(
            command, context
        )
    )
    assert output.invocation_id == context.invocation_id
    assert output.result_ref == result.result_ref


def test_executor_checks_guard_after_remote_response_and_propagates_revocation() -> None:
    context = _context()
    command = _command(context)
    guard = JobExecutionGuard("job", "worker", 1, 1)
    calls = []

    async def ensure_active():
        calls.append("ensure")

    async def check_after_call():
        calls.append("after")
        raise JobExecutionRevoked("revoked after MCP response")

    guard.ensure_active = ensure_active
    guard.check_after_call = check_after_call

    class FakePool:
        async def call_tool(self, *_args, **_kwargs):
            return SimpleNamespace(structured_content={"ok": True, "result": {}})

    token = guard.install()
    try:
        with pytest.raises(JobExecutionRevoked):
            asyncio.run(
                McpAlgorithmExecutor(FakePool(), signing_key="secret").execute(
                    command, context
                )
            )
    finally:
        JobExecutionGuard.reset(token)
    assert calls == ["ensure", "after"]


def test_executor_maps_remote_stale_lease_to_job_execution_revoked() -> None:
    context = _context()
    command = _command(context)

    class FakePool:
        async def call_tool(self, *_args, **_kwargs):
            return SimpleNamespace(
                structured_content={
                    "ok": False,
                    "error": {"code": SafeErrorCode.MCP_LEASE_STALE.value},
                }
            )

    with pytest.raises(JobExecutionRevoked) as error:
        asyncio.run(
            McpAlgorithmExecutor(FakePool(), signing_key="secret").execute(
                command, context
            )
        )
    assert error.value.invocation_id == command.invocation_id
    assert error.value.remote_execution_status == "revoked"


def test_executor_stops_before_retry_backoff_when_guard_is_revoked() -> None:
    context = _context()
    command = _command(context)
    guard = JobExecutionGuard("job", "worker", 1, 1)
    calls = []

    async def ensure_active():
        calls.append("ensure")

    async def check_after_call():
        calls.append("after")
        raise JobExecutionRevoked("revoked before retry")

    guard.ensure_active = ensure_active
    guard.check_after_call = check_after_call

    class FakePool:
        call_count = 0

        async def call_tool(self, *_args, **_kwargs):
            self.call_count += 1
            raise McpTransportError("mcp-1", 0)

    pool = FakePool()
    token = guard.install()
    try:
        with pytest.raises(JobExecutionRevoked):
            asyncio.run(
                McpAlgorithmExecutor(
                    pool,
                    signing_key="secret",
                    retry_backoff_seconds=0,
                ).execute(command, context)
            )
    finally:
        JobExecutionGuard.reset(token)
    assert pool.call_count == 1
    assert calls == ["ensure", "after"]


def test_executor_marks_canceled_remote_call_with_same_invocation_identity() -> None:
    context = _context()
    command = _command(context)

    class FakePool:
        async def call_tool(self, *_args, **_kwargs):
            raise asyncio.CancelledError()

        async def cancel_tool(self, *_args, **_kwargs):
            return SimpleNamespace(
                structured_content={
                    "ok": True,
                    "cancellation": {
                        "status": "canceled",
                        "invocation_id": command.invocation_id,
                    },
                }
            )

    with pytest.raises(asyncio.CancelledError) as error:
        asyncio.run(
            McpAlgorithmExecutor(FakePool(), signing_key="secret").execute(
                command, context
            )
        )
    assert error.value.invocation_id == command.invocation_id
    assert error.value.remote_execution_status == "canceled"


def test_executor_guard_revocation_cancels_the_remote_invocation() -> None:
    context = _context()
    command = _command(context)
    guard = JobExecutionGuard(context.job_id, context.worker_id, 1, 4)

    async def ensure_active():
        if guard.revoked:
            raise JobExecutionRevoked("revoked")

    guard.ensure_active = ensure_active
    guard.check_after_call = ensure_active

    class FakePool:
        cancel_calls = 0

        async def call_tool(self, *_args, **_kwargs):
            await asyncio.Event().wait()

        async def cancel_tool(self, *_args, **_kwargs):
            self.cancel_calls += 1
            return SimpleNamespace(
                structured_content={
                    "ok": True,
                    "cancellation": {
                        "status": "canceled",
                        "invocation_id": command.invocation_id,
                    },
                }
            )

    async def scenario():
        pool = FakePool()
        token = guard.install()
        try:
            task = asyncio.create_task(
                McpAlgorithmExecutor(pool, signing_key="secret").execute(
                    command, context
                )
            )
            await asyncio.sleep(0.01)
            guard.mark_revoked(status="canceled", execution_state="draining")
            with pytest.raises(JobExecutionRevoked) as error:
                await task
            assert error.value.remote_execution_status == "canceled"
            assert pool.cancel_calls == 1
        finally:
            JobExecutionGuard.reset(token)

    asyncio.run(scenario())
