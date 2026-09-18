import os
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


from app.main import routes  # noqa: E402
from app.request_context import register_request_context  # noqa: E402
from config.settings import AppConfig, settings  # noqa: E402


class ChatFrontendRouteTests(unittest.TestCase):
    """验证普通端唯一 Vue 入口、dist 托管和开发服务器边界。"""

    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = "chat-frontend-route-test-secret"
        register_request_context(self.app)
        self.app.register_blueprint(routes.main_bp)
        self.client = self.app.test_client()

    def test_root_and_chat_next_alias_serve_same_vue_index(self):
        """根路由是唯一正式入口，迁移期 Vue 地址只保留兼容别名。"""
        with TemporaryDirectory() as temp_dir:
            dist_dir = Path(temp_dir)
            (dist_dir / "index.html").write_text(
                "<!doctype html><html><body>vue-shell</body></html>",
                encoding="utf-8",
            )
            with patch.multiple(
                settings,
                CHAT_FRONTEND_DIST_DIR=str(dist_dir),
                CHAT_VITE_DEV_SERVER_URL="",
            ):
                root_response = self.client.get("/")
                alias_response = self.client.get("/chat-next")
                legacy_response = self.client.get("/chat-legacy")
                root_data = root_response.get_data()
                alias_data = alias_response.get_data()
                root_status = root_response.status_code
                alias_status = alias_response.status_code
                legacy_status = legacy_response.status_code
                root_response.close()
                alias_response.close()
                legacy_response.close()

        self.assertEqual(root_status, 200)
        self.assertEqual(alias_status, 200)
        self.assertEqual(root_data, alias_data)
        self.assertEqual(legacy_status, 404)

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

    def test_missing_vue_dist_returns_stable_503(self):
        """缺少 index.html 时所有 Vue 入口都失败关闭，不返回半成品。"""
        with TemporaryDirectory() as temp_dir:
            missing_dist = Path(temp_dir) / "missing-dist"
            with patch.multiple(
                settings,
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

    def test_explicit_vite_url_redirects_root_and_compatibility_alias(self):
        """显式开发服务器同时接管正式入口和兼容别名。"""
        with patch.multiple(
            settings,
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
        self.assertEqual(legacy_response.status_code, 404)


class ChatFrontendConfigTests(unittest.TestCase):
    """验证普通端 Vue 产物与开发服务器配置默认值。"""

    def test_vue_paths_default_to_local_dist_and_no_dev_server(self):
        with patch.dict(os.environ, TEST_ENV, clear=True):
            config = AppConfig()

        self.assertEqual(config.CHAT_FRONTEND_DIST_DIR, "")
        self.assertEqual(config.CHAT_VITE_DEV_SERVER_URL, "")


def _environment_dict(environment):
    """统一读取 Compose 的 list/mapping 两种 environment 写法。"""
    if isinstance(environment, dict):
        return environment
    return dict(item.split("=", 1) for item in environment)


class ChatFrontendDeploymentTests(unittest.TestCase):
    """验证 Vue 构建阶段、Compose 产物变量和无 Node runtime 边界。"""

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

                self.assertNotIn("CHAT_FRONTEND_ENTRY", environment)
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
