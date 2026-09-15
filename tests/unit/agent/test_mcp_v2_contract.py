"""P2-M MCP v2 contracts and bounded-resource behavior."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from Agent.CausalAgentMCP.auth import McpAuthError, sign_invocation, verify_invocation
from Agent.CausalAgentMCP.config import McpServerConfig
from Agent.CausalAgentMCP.executor_pool import (
    BoundedProcessPool,
    ExecutionOutcome,
    PoolExecutionError,
)
from Agent.CausalAgentMCP.runner_registry import build_default_registry
from Agent.CausalAgentMCP.service import CausalMcpService
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
)


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

        async def execute(self, **_kwargs):
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


def test_service_exposes_algorithm_timeout_as_result_status() -> None:
    class TimeoutPool:
        def ready(self) -> bool:
            return True

        async def execute(self, **_kwargs):
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


class _FakeClient:
    def __init__(self, _transport, **_kwargs):
        self.session = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def list_tools(self):
        return SimpleNamespace(tools=[SimpleNamespace(name="execute_algorithm")])

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
