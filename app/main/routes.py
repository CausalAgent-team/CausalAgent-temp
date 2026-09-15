'''
app.main.routes - 主路由

- 根路由
- 普通端 Vue/legacy 双入口
- 普通端 Vue 静态资源
- 设置路由

'''
from pathlib import Path
import logging
import os

from flask import Blueprint, jsonify, redirect, request, send_from_directory

from app.request_context import get_request_id, log_request_failure
from config.settings import settings

main_bp = Blueprint('main', __name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SETTING_DIR = os.path.join(BASE_DIR, "setting")
PROJECT_ROOT = Path(BASE_DIR)
STATIC_DIR = PROJECT_ROOT / "app" / "static"
LOGGER = logging.getLogger(__name__)

## 设置
@main_bp.route('/api/setting')
def setting():
    topic = request.args.get('topic') # 从查询参数获取 topic
    request.args.get('topic')
    topic_to_file = {
            "userAgreement": "Userprivacy.md",
            "userManual": "manual.md"
        }
    filename = topic_to_file.get(topic)
    file_path = os.path.join(SETTING_DIR, filename)
    with open(file_path,'r',encoding = 'utf-8') as f:
        content = f.read()
        if not os.path.exists(file_path):
            # 返回更具体的错误信息给前端
            return jsonify({"success": False, "error": f"请求的内容文件 '{filename}' 未找到"}), 404 # 返回 404 Not Found

    return jsonify({"success": True, "messages": content})

def _chat_dist_dir() -> Path:
    """返回普通端 Vue 构建产物目录，不回退到旧版静态目录。"""
    configured = settings.CHAT_FRONTEND_DIST_DIR
    return Path(configured) if configured else PROJECT_ROOT / "chat-frontend" / "dist"


def _chat_frontend_missing_response():
    """构造稳定的 Vue 构建缺失响应，并记录不含路径细节的请求失败。"""
    log_request_failure(
        LOGGER,
        status_code=503,
        reason_code="unavailable",
    )
    return jsonify({
        "success": False,
        "error": "普通端 Vue 前端尚未构建",
        "code": "chat_frontend_missing",
        "request_id": get_request_id(),
    }), 503


def _serve_legacy_chat():
    """固定返回未迁移的普通端入口，不为尾斜杠建立别名。"""
    return send_from_directory(str(STATIC_DIR), "chat.html")


def _serve_chat_index(dist_dir: Path):
    """提供入口 HTML，并禁止入口缓存住旧的 hash 资源清单。"""
    response = send_from_directory(str(dist_dir), "index.html")
    response.cache_control.no_cache = True
    response.cache_control.max_age = 0
    return response


def _serve_vue_chat():
    """按显式开发配置跳转 Vite，否则同源提供完整 Vue 构建。"""
    if settings.CHAT_VITE_DEV_SERVER_URL:
        query = request.query_string.decode("ascii")
        suffix = f"?{query}" if query else ""
        return redirect(f"{settings.CHAT_VITE_DEV_SERVER_URL}/chat-assets/{suffix}")

    dist_dir = _chat_dist_dir()
    if not (dist_dir / "index.html").is_file():
        return _chat_frontend_missing_response()
    return _serve_chat_index(dist_dir)


# 根路由
@main_bp.route('/')
def index():
    """按配置选择根入口，默认保持旧版普通端行为。"""
    if settings.CHAT_FRONTEND_ENTRY == "vue":
        return _serve_vue_chat()
    return _serve_legacy_chat()


@main_bp.route('/chat-next')
def chat_next():
    """固定提供普通端 Vue 入口，不受根入口开关影响。"""
    return _serve_vue_chat()


@main_bp.route('/chat-legacy')
def chat_legacy():
    """固定提供旧版普通端入口，保留回滚路径。"""
    return _serve_legacy_chat()


@main_bp.route('/chat-assets/<path:filename>')
def chat_asset(filename: str):
    """从 Vue dist 提供同源资源；缺少完整构建时不返回半成品。"""
    dist_dir = _chat_dist_dir()
    if not (dist_dir / "index.html").is_file():
        return _chat_frontend_missing_response()
    response = send_from_directory(str(dist_dir), filename)
    if filename.startswith("assets/"):
        response.cache_control.public = True
        response.cache_control.max_age = 31536000
        response.cache_control.immutable = True
    else:
        response.cache_control.no_cache = True
        response.cache_control.max_age = 0
    return response


@main_bp.route('/rag_eval')
@main_bp.route('/rag-eval')
def rag_eval_page():
    """返回 Vue RAG 运行台页面。"""
    return send_from_directory("static/rag_eval_app", "index.html")
