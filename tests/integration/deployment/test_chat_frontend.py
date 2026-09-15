import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml
from flask import Flask


TEST_ENV = {
    "SECRET_KEY": "chat-frontend-test-secret",
    "API_KEY": "chat-frontend-test-api-key",
    "BASE_URL": "https://example.test",
    "MODEL": "chat-frontend-test-model",
    "MYSQL_HOST": "chat-frontend-test-mysql",
    "MYSQL_USER": "chat-frontend-test-user",
    "MYSQL_PASSWORD": "chat-frontend-test-password",
    "MYSQL_DATABASE": "chat-frontend-test-database",
}
for key, value in TEST_ENV.items():
    os.environ.setdefault(key, value)
os.environ.setdefault("CHAT_FRONTEND_ENTRY", "legacy")


from app.main import routes  # noqa: E402
from app.request_context import register_request_context  # noqa: E402
from config.settings import AppConfig, settings  # noqa: E402


class ChatFrontendRouteTests(unittest.TestCase):
    """验证普通端双入口、dist 托管和开发服务器边界。"""

    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = "chat-frontend-route-test-secret"
        register_request_context(self.app)
        self.app.register_blueprint(routes.main_bp)
        self.client = self.app.test_client()

    def test_root_and_legacy_route_keep_legacy_html_without_trailing_slash(self):
        """迁移期根路由默认是旧版，旧版入口没有尾斜杠别名。"""
        with patch.multiple(
            settings,
            CHAT_FRONTEND_ENTRY="legacy",
            CHAT_FRONTEND_DIST_DIR="",
            CHAT_VITE_DEV_SERVER_URL="",
        ):
            root_response = self.client.get("/")
            legacy_response = self.client.get("/chat-legacy")
            trailing_response = self.client.get("/chat-legacy/")

        self.assertEqual(root_response.status_code, 200)
        self.assertEqual(legacy_response.status_code, 200)
        self.assertEqual(root_response.data, legacy_response.data)
        self.assertEqual(trailing_response.status_code, 404)

    def test_vue_dist_and_assets_are_served_from_configured_directory(self):
        """完整 dist 由 Vue 入口和稳定资源前缀同源提供。"""
        with TemporaryDirectory() as temp_dir:
            dist_dir = Path(temp_dir)
            (dist_dir / "index.html").write_text(
                "<!doctype html><html><body>vue-shell</body></html>",
                encoding="utf-8",
            )
            (dist_dir / "assets").mkdir()
            (dist_dir / "assets" / "app.js").write_text(
                "console.log('vue');",
                encoding="utf-8",
            )

            with patch.multiple(
                settings,
                CHAT_FRONTEND_ENTRY="legacy",
                CHAT_FRONTEND_DIST_DIR=str(dist_dir),
                CHAT_VITE_DEV_SERVER_URL="",
            ):
                page_response = self.client.get("/chat-next")
                asset_response = self.client.get("/chat-assets/assets/app.js")
                missing_asset_response = self.client.get("/chat-assets/assets/missing.js")
                page_data = page_response.get_data()
                asset_data = asset_response.get_data()
                page_status = page_response.status_code
                asset_status = asset_response.status_code
                missing_asset_status = missing_asset_response.status_code
                page_cache_control = page_response.headers["Cache-Control"]
                asset_cache_control = asset_response.headers["Cache-Control"]
                page_response.close()
                asset_response.close()
                missing_asset_response.close()

        self.assertEqual(page_status, 200)
        self.assertIn(b"vue-shell", page_data)
        self.assertIn("no-cache", page_cache_control)
        self.assertEqual(asset_status, 200)
        self.assertEqual(asset_data, b"console.log('vue');")
        self.assertIn("public", asset_cache_control)
        self.assertIn("max-age=31536000", asset_cache_control)
        self.assertIn("immutable", asset_cache_control)
        self.assertEqual(missing_asset_status, 404)

    def test_missing_vue_dist_returns_stable_503_without_legacy_fallback(self):
        """缺少 index.html 时所有 Vue 入口都失败关闭，不返回旧版或半成品。"""
        with TemporaryDirectory() as temp_dir:
            missing_dist = Path(temp_dir) / "missing-dist"
            with patch.multiple(
                settings,
                CHAT_FRONTEND_ENTRY="vue",
                CHAT_FRONTEND_DIST_DIR=str(missing_dist),
                CHAT_VITE_DEV_SERVER_URL="",
            ):
                responses = [
                    self.client.get("/"),
                    self.client.get("/chat-next"),
                    self.client.get("/chat-assets/assets/app.js"),
                ]

        for response in responses:
            with self.subTest(path=response.request.path):
                self.assertEqual(response.status_code, 503)
                payload = response.get_json()
                self.assertEqual(payload["code"], "chat_frontend_missing")
                self.assertEqual(payload["request_id"], response.headers["X-Request-ID"])

    def test_explicit_vite_url_redirects_vue_only_and_legacy_stays_local(self):
        """显式开发服务器只接管 Vue 入口，旧版回滚入口始终同源。"""
        with patch.multiple(
            settings,
            CHAT_FRONTEND_ENTRY="vue",
            CHAT_FRONTEND_DIST_DIR="",
            CHAT_VITE_DEV_SERVER_URL="http://127.0.0.1:5174",
        ):
            root_response = self.client.get("/")
            next_response = self.client.get("/chat-next")
            next_with_query_response = self.client.get("/chat-next?next=%2Fadmin%2Fdatabase")
            legacy_response = self.client.get("/chat-legacy")

        self.assertEqual(root_response.status_code, 302)
        self.assertEqual(root_response.headers["Location"], "http://127.0.0.1:5174/chat-assets/")
        self.assertEqual(next_response.status_code, 302)
        self.assertEqual(
            next_response.headers["Location"],
            "http://127.0.0.1:5174/chat-assets/",
        )
        self.assertEqual(
            next_with_query_response.headers["Location"],
            "http://127.0.0.1:5174/chat-assets/?next=%2Fadmin%2Fdatabase",
        )
        self.assertEqual(legacy_response.status_code, 200)


class ChatFrontendConfigTests(unittest.TestCase):
    """验证普通端入口配置的默认值和导入阶段 fail-closed 行为。"""

    def test_entry_defaults_to_legacy_when_missing(self):
        with patch.dict(os.environ, TEST_ENV, clear=True):
            config = AppConfig()

        self.assertEqual(config.CHAT_FRONTEND_ENTRY, "legacy")
        self.assertEqual(config.CHAT_FRONTEND_DIST_DIR, "")
        self.assertEqual(config.CHAT_VITE_DEV_SERVER_URL, "")

    def test_invalid_entry_raises_during_configuration_loading(self):
        invalid_env = {
            **TEST_ENV,
            "CHAT_FRONTEND_ENTRY": "react",
        }
        with patch.dict(os.environ, invalid_env, clear=True):
            with self.assertRaisesRegex(
                ValueError,
                r"CHAT_FRONTEND_ENTRY.*legacy.*vue",
            ):
                AppConfig()

    def test_invalid_entry_logs_startup_failure_and_exits_nonzero(self):
        """启动失败以固定事件日志和非零进程退出共同构成明确错误。"""
        project_root = Path(__file__).resolve().parents[3]
        environment = {**TEST_ENV, "CHECKPOINT_POSTGRES_PASSWORD": "chat-frontend-test-checkpoint-password"}
        environment.update({
            "CHAT_FRONTEND_ENTRY": "react",
            "PYTHONPATH": str(project_root),
        })
        result = subprocess.run(
            [sys.executable, "CausalAgent.py"],
            cwd=project_root,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )

        output = f"{result.stdout}\n{result.stderr}"
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('"event_code":"web.startup.failed"', output)
        self.assertIn('"phase":"configuration"', output)


def _environment_dict(environment):
    """统一读取 Compose 的 list/mapping 两种 environment 写法。"""
    if isinstance(environment, dict):
        return environment
    return dict(item.split("=", 1) for item in environment)


class ChatFrontendDeploymentTests(unittest.TestCase):
    """验证 Vue 构建阶段、Compose 入口变量和无 Node runtime 边界。"""

    def test_dockerfile_builds_chat_dist_and_runtime_has_no_node_commands(self):
        dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

        self.assertIn("FROM node:24-alpine AS chat-builder", dockerfile)
        self.assertIn(
            "COPY chat-frontend/package.json chat-frontend/package-lock.json ./",
            dockerfile,
        )
        self.assertIn("COPY chat-frontend/ ./", dockerfile)
        self.assertIn("COPY --from=chat-builder /frontend/dist /opt/causalagent-chat", dockerfile)
        self.assertIn("CHAT_FRONTEND_DIST_DIR=/opt/causalagent-chat", dockerfile)

        runtime_stage = dockerfile.split("FROM python-deps AS runtime", 1)[1]
        self.assertNotIn("npm ", runtime_stage)
        self.assertNotIn("node:", runtime_stage)
        self.assertNotIn("vite", runtime_stage.lower())

    def test_compose_app_keeps_chat_dist_outside_source_mount(self):
        for filename in (
            "docker-compose.yml",
            "docker-compose.staging.yml",
            "docker-compose.prod.yml",
        ):
            with self.subTest(filename=filename):
                compose = yaml.safe_load(Path(filename).read_text(encoding="utf-8"))
                app = compose["services"]["app"]
                environment = _environment_dict(app["environment"])

                self.assertEqual(environment["CHAT_FRONTEND_ENTRY"], "${CHAT_FRONTEND_ENTRY:-legacy}")
                self.assertEqual(
                    environment["CHAT_FRONTEND_DIST_DIR"],
                    "${CHAT_FRONTEND_DIST_DIR:-/opt/causalagent-chat}",
                )
                self.assertEqual(
                    environment["CHAT_VITE_DEV_SERVER_URL"],
                    "${CHAT_VITE_DEV_SERVER_URL:-}",
                )
                self.assertFalse(
                    any("/opt/causalagent-chat" in str(volume) for volume in app.get("volumes", []))
                )

    def test_ignores_do_not_send_local_chat_build_outputs(self):
        dockerignore = Path(".dockerignore").read_text(encoding="utf-8")
        gitignore = Path(".gitignore").read_text(encoding="utf-8")

        for text in (dockerignore, gitignore):
            self.assertIn("chat-frontend/node_modules/", text)
            self.assertIn("chat-frontend/dist/", text)
            self.assertIn("chat-frontend/test-results/", text)
            self.assertIn("chat-frontend/playwright-report/", text)


if __name__ == "__main__":
    unittest.main()
