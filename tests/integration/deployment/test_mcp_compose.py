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


def test_development_mcp_is_private_and_worker_waits_for_health() -> None:
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    mcp = _service_block(compose, "causal-mcp")
    worker = _service_block(compose, "worker")

    assert "dockerfile: Agent/CausalAgentMCP/Dockerfile" in mcp
    assert "ports:" not in mcp
    assert "healthcheck:" in mcp
    assert "http://127.0.0.1:8080/ready" in mcp
    assert 'causalagent_service: "mcp"' in mcp
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
