"""P2-M causal-mcp Compose boundary checks."""

from __future__ import annotations

import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _service_block(text: str, service: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(service)}:\n.*?(?=^  [A-Za-z0-9_-]+:|\Z)",
        text,
    )
    assert match is not None, f"missing service: {service}"
    return match.group(0)


def _assert_mcp_does_not_receive_app_or_model_config(block: str) -> None:
    """MCP 只接收数据库和自身鉴权/算法配置，不接收应用或模型密钥。"""
    for name in ("API_KEY", "BASE_URL", "MODEL", "SECRET_KEY"):
        assert not re.search(rf"(?m)^\s*-?\s*{re.escape(name)}(?:=|:)", block)


def test_development_mcp_is_private_and_worker_waits_for_health() -> None:
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    mcp = _service_block(compose, "causal-mcp")
    worker = _service_block(compose, "worker")

    assert "dockerfile: Agent/CausalAgentMCP/Dockerfile" in mcp
    assert "ports:" not in mcp
    assert "healthcheck:" in mcp
    assert "http://127.0.0.1:8080/ready" in mcp
    assert 'causalagent_service: "mcp"' in mcp
    _assert_mcp_does_not_receive_app_or_model_config(mcp)
    assert "causal-mcp:" in worker
    assert "condition: service_healthy" in worker


def test_staging_and_production_mcp_keep_private_image_boundary() -> None:
    staging = (PROJECT_ROOT / "docker-compose.staging.yml").read_text(encoding="utf-8")
    production = (PROJECT_ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    staging_mcp = _service_block(staging, "causal-mcp")
    production_mcp = _service_block(production, "causal-mcp")

    assert "STAGING_MCP_IMAGE" in staging_mcp
    assert "CAUSAL_MCP_IMAGE" in production_mcp
    for block in (staging_mcp, production_mcp):
        assert "ports:" not in block
        assert "healthcheck:" in block
        assert "http://127.0.0.1:8080/ready" in block
        assert "CAUSAL_MCP_SERVICE_TOKEN" in block
        assert "CAUSAL_MCP_SIGNING_KEY_CURRENT" in block
        _assert_mcp_does_not_receive_app_or_model_config(block)
