"""
Flask主应用 - 统一管理三个Streamlit应用
"""

import os
import sys
import json
import tempfile
import re

# 【修复】尽早设置环境变量，确保所有模块都使用无缓冲模式
os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONUTF8'] = '1'
os.environ['PYTHONUNBUFFERED'] = '1'  # 禁用Python输出缓冲，确保日志实时输出

import subprocess
import time
import threading
from dataclasses import replace
from datetime import datetime
from queue import Queue
from typing import Any, Mapping
from flask import Flask, render_template, request, jsonify, Response
from flask_socketio import SocketIO, emit
import atexit
import requests
from loguru import logger
import importlib
from pathlib import Path
import asyncio
from config import settings
from utils.crawl_tasks import CrawlTaskStore
from utils.data_readiness import check_data_readiness
from utils.weibo_data_prep import (
    build_weibo_collection_bundle,
    build_weibo_data_caps,
    evaluate_weibo_reportability,
    select_weibo_provider,
)
from utils.weibo_evidence_manifest import build_weibo_evidence_manifest
from utils.search_orchestrator import SearchOrchestrator
from utils.intake_web_search import (
    IntakeWebSearchConfigError,
    IntakeWebSearchRuntimeError,
    run_intake_web_search,
)
from downstream.mediacrawler.import_posts_to_bettafish import build_dsn as build_mediacrawler_dsn
from downstream.weibo_data.bundle_importer import import_weibo_bundle
from downstream.weibo_data.providers.base import WeiboCollectionBundle, WeiboDataCaps

# 导入ReportEngine
try:
    from ReportEngine.flask_interface import report_bp, initialize_report_engine
    REPORT_ENGINE_AVAILABLE = True
except ImportError as e:
    logger.error(f"ReportEngine导入失败: {e}")
    REPORT_ENGINE_AVAILABLE = False

app = Flask(__name__)
app.config['SECRET_KEY'] = settings.SECRET_KEY
socketio = SocketIO(app, cors_allowed_origins="*")
search_orchestrator = SearchOrchestrator()
crawl_tasks = CrawlTaskStore()

# eventlet 在客户端主动断开时偶尔会抛出 ConnectionAbortedError，这里做一次防御性包裹，
# 避免无意义的堆栈污染日志（仅在 eventlet 可用时启用）。
def _patch_eventlet_disconnect_logging():
    try:
        import eventlet.wsgi  # type: ignore
    except Exception as exc:  # pragma: no cover - 仅在生产环境有效
        logger.debug(f"eventlet 不可用，跳过断开补丁: {exc}")
        return

    try:
        original_finish = eventlet.wsgi.HttpProtocol.finish  # type: ignore[attr-defined]
    except Exception as exc:  # pragma: no cover
        logger.debug(f"eventlet 缺少 HttpProtocol.finish，跳过断开补丁: {exc}")
        return

    def _safe_finish(self, *args, **kwargs):  # pragma: no cover - 运行时才会触发
        try:
            return original_finish(self, *args, **kwargs)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError) as exc:
            try:
                environ = getattr(self, 'environ', {}) or {}
                method = environ.get('REQUEST_METHOD', '')
                path = environ.get('PATH_INFO', '')
                logger.warning(f"客户端已主动断开，忽略异常: {method} {path} ({exc})")
            except Exception:
                logger.warning(f"客户端已主动断开，忽略异常: {exc}")
            return

    eventlet.wsgi.HttpProtocol.finish = _safe_finish  # type: ignore[attr-defined]
    logger.info("已对 eventlet 连接中断进行安全防护")

_patch_eventlet_disconnect_logging()

# 注册ReportEngine Blueprint
if REPORT_ENGINE_AVAILABLE:
    app.register_blueprint(report_bp, url_prefix='/api/report')
    logger.info("ReportEngine接口已注册")
else:
    logger.info("ReportEngine不可用，跳过接口注册")

# 创建日志目录
LOG_DIR = Path('logs')
LOG_DIR.mkdir(exist_ok=True)

CONFIG_MODULE_NAME = 'config'
CONFIG_FILE_PATH = Path(__file__).resolve().parent / 'config.py'
CONFIG_KEYS = [
    'HOST',
    'PORT',
    'DB_DIALECT',
    'DB_HOST',
    'DB_PORT',
    'DB_USER',
    'DB_PASSWORD',
    'DB_NAME',
    'DB_CHARSET',
    'INSIGHT_ENGINE_API_KEY',
    'INSIGHT_ENGINE_BASE_URL',
    'INSIGHT_ENGINE_MODEL_NAME',
    'MEDIA_ENGINE_API_KEY',
    'MEDIA_ENGINE_BASE_URL',
    'MEDIA_ENGINE_MODEL_NAME',
    'QUERY_ENGINE_API_KEY',
    'QUERY_ENGINE_BASE_URL',
    'QUERY_ENGINE_MODEL_NAME',
    'REPORT_ENGINE_API_KEY',
    'REPORT_ENGINE_BASE_URL',
    'REPORT_ENGINE_MODEL_NAME',
    'FORUM_HOST_API_KEY',
    'FORUM_HOST_BASE_URL',
    'FORUM_HOST_MODEL_NAME',
    'KEYWORD_OPTIMIZER_API_KEY',
    'KEYWORD_OPTIMIZER_BASE_URL',
    'KEYWORD_OPTIMIZER_MODEL_NAME',
    'TAVILY_API_KEY',
    'SEARCH_TOOL_TYPE',
    'BOCHA_WEB_SEARCH_API_KEY',
    'ANSPIRE_API_KEY'
]


def _load_config_module():
    """Load or reload the config module to ensure latest values are available."""
    importlib.invalidate_caches()
    module = sys.modules.get(CONFIG_MODULE_NAME)
    try:
        if module is None:
            module = importlib.import_module(CONFIG_MODULE_NAME)
        else:
            module = importlib.reload(module)
    except ModuleNotFoundError:
        return None
    return module


def read_config_values():
    """Return the current configuration values that are exposed to the frontend."""
    try:
        # 重新加载配置以获取最新的 Settings 实例
        from config import reload_settings, settings
        reload_settings()
        
        values = {}
        for key in CONFIG_KEYS:
            # 从 Pydantic Settings 实例读取值
            value = getattr(settings, key, None)
            # Convert to string for uniform handling on the frontend.
            if value is None:
                values[key] = ''
            else:
                values[key] = str(value)
        return values
    except Exception as exc:
        logger.exception(f"读取配置失败: {exc}")
        return {}


def _serialize_config_value(value):
    """Serialize Python values back to a config.py assignment-friendly string."""
    if isinstance(value, bool):
        return 'True' if value else 'False'
    if isinstance(value, (int, float)):
        return str(value)
    if value is None:
        return 'None'

    value_str = str(value)
    escaped = value_str.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{escaped}"'


def write_config_values(updates):
    """Persist configuration updates to .env file (Pydantic Settings source)."""
    from pathlib import Path
    
    # 确定 .env 文件路径（与 config.py 中的逻辑一致）
    project_root = Path(__file__).resolve().parent
    cwd_env = Path.cwd() / ".env"
    env_file_path = cwd_env if cwd_env.exists() else (project_root / ".env")
    
    # 读取现有的 .env 文件内容
    env_lines = []
    env_key_indices = {}  # 记录每个键在文件中的索引位置
    if env_file_path.exists():
        env_lines = env_file_path.read_text(encoding='utf-8').splitlines()
        # 提取已存在的键及其索引
        for i, line in enumerate(env_lines):
            line_stripped = line.strip()
            if line_stripped and not line_stripped.startswith('#'):
                if '=' in line_stripped:
                    key = line_stripped.split('=')[0].strip()
                    env_key_indices[key] = i
    
    # 更新或添加配置项
    for key, raw_value in updates.items():
        # 格式化值用于 .env 文件（不需要引号，除非是字符串且包含空格）
        if raw_value is None or raw_value == '':
            env_value = ''
        elif isinstance(raw_value, (int, float)):
            env_value = str(raw_value)
        elif isinstance(raw_value, bool):
            env_value = 'True' if raw_value else 'False'
        else:
            value_str = str(raw_value)
            # 如果包含空格或特殊字符，需要引号
            if ' ' in value_str or '\n' in value_str or '#' in value_str:
                escaped = value_str.replace('\\', '\\\\').replace('"', '\\"')
                env_value = f'"{escaped}"'
            else:
                env_value = value_str
        
        # 更新或添加配置项
        if key in env_key_indices:
            # 更新现有行
            env_lines[env_key_indices[key]] = f'{key}={env_value}'
        else:
            # 添加新行到文件末尾
            env_lines.append(f'{key}={env_value}')
    
    # 写入 .env 文件
    env_file_path.parent.mkdir(parents=True, exist_ok=True)
    env_file_path.write_text('\n'.join(env_lines) + '\n', encoding='utf-8')
    
    # 重新加载配置模块（这会重新读取 .env 文件并创建新的 Settings 实例）
    _load_config_module()


system_state_lock = threading.Lock()
system_state = {
    'started': False,
    'starting': False,
    'shutdown_in_progress': False
}


def _set_system_state(*, started=None, starting=None):
    """Safely update the cached system state flags."""
    with system_state_lock:
        if started is not None:
            system_state['started'] = started
        if starting is not None:
            system_state['starting'] = starting


def _get_system_state():
    """Return a shallow copy of the system state flags."""
    with system_state_lock:
        return system_state.copy()


def _prepare_system_start():
    """Mark the system as starting if it is not already running or starting."""
    with system_state_lock:
        if system_state['started']:
            return False, '系统已启动'
        if system_state['starting']:
            return False, '系统正在启动'
        system_state['starting'] = True
        return True, None

def _mark_shutdown_requested():
    """标记关机已请求；若已有关机流程则返回 False。"""
    with system_state_lock:
        if system_state.get('shutdown_in_progress'):
            return False
        system_state['shutdown_in_progress'] = True
        return True


def initialize_system_components():
    """启动所有依赖组件（Streamlit 子应用、ForumEngine、ReportEngine）。"""
    logs = []
    errors = []
    
    message = "公开版本不内置 MindSpider 初始化；请通过数据导入或外部采集服务准备数据库。"
    logs.append(message)
    logger.info(message)

    try:
        stop_forum_engine()
        logs.append("已停止 ForumEngine 监控器以避免文件冲突")
    except Exception as exc:  # pragma: no cover - 安全捕获
        message = f"停止 ForumEngine 时发生异常: {exc}"
        logs.append(message)
        logger.exception(message)

    processes['forum']['status'] = 'stopped'

    for app_name, script_path in STREAMLIT_SCRIPTS.items():
        logs.append(f"检查文件: {script_path}")
        if os.path.exists(script_path):
            success, message = start_streamlit_app(app_name, script_path, processes[app_name]['port'])
            logs.append(f"{app_name}: {message}")
            if success:
                startup_success, startup_message = wait_for_app_startup(app_name, 30)
                logs.append(f"{app_name} 启动检查: {startup_message}")
                if not startup_success:
                    errors.append(f"{app_name} 启动失败: {startup_message}")
            else:
                errors.append(f"{app_name} 启动失败: {message}")
        else:
            msg = f"文件不存在: {script_path}"
            logs.append(f"错误: {msg}")
            errors.append(f"{app_name}: {msg}")

    forum_started = False
    try:
        start_forum_engine()
        processes['forum']['status'] = 'running'
        logs.append("ForumEngine 启动完成")
        forum_started = True
    except Exception as exc:  # pragma: no cover - 保底捕获
        error_msg = f"ForumEngine 启动失败: {exc}"
        logs.append(error_msg)
        errors.append(error_msg)

    if REPORT_ENGINE_AVAILABLE:
        try:
            if initialize_report_engine():
                logs.append("ReportEngine 初始化成功")
            else:
                msg = "ReportEngine 初始化失败"
                logs.append(msg)
                errors.append(msg)
        except Exception as exc:  # pragma: no cover
            msg = f"ReportEngine 初始化异常: {exc}"
            logs.append(msg)
            errors.append(msg)

    if errors:
        cleanup_processes()
        processes['forum']['status'] = 'stopped'
        if forum_started:
            try:
                stop_forum_engine()
            except Exception:  # pragma: no cover
                logger.exception("停止ForumEngine失败")
        return False, logs, errors

    return True, logs, []

# 初始化ForumEngine的forum.log文件
def init_forum_log():
    """初始化forum.log文件"""
    try:
        forum_log_file = LOG_DIR / "forum.log"
        # 检查文件不存在则创建并且写一个开始，存在就清空写一个开始
        if not forum_log_file.exists():
            with open(forum_log_file, 'w', encoding='utf-8') as f:
                start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                f.write(f"=== ForumEngine 系统初始化 - {start_time} ===\n")
            logger.info(f"ForumEngine: forum.log 已初始化")
        else:
            with open(forum_log_file, 'w', encoding='utf-8') as f:
                start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                f.write(f"=== ForumEngine 系统初始化 - {start_time} ===\n")
            logger.info(f"ForumEngine: forum.log 已初始化")
    except Exception as e:
        logger.exception(f"ForumEngine: 初始化forum.log失败: {e}")

# 初始化forum.log
init_forum_log()

# 启动ForumEngine智能监控
def start_forum_engine():
    """启动ForumEngine论坛"""
    try:
        from ForumEngine.monitor import start_forum_monitoring
        logger.info("ForumEngine: 启动论坛...")
        success = start_forum_monitoring()
        if not success:
            logger.info("ForumEngine: 论坛启动失败")
    except Exception as e:
        logger.exception(f"ForumEngine: 启动论坛失败: {e}")

# 停止ForumEngine智能监控
def stop_forum_engine():
    """停止ForumEngine论坛"""
    try:
        from ForumEngine.monitor import stop_forum_monitoring
        logger.info("ForumEngine: 停止论坛...")
        stop_forum_monitoring()
        logger.info("ForumEngine: 论坛已停止")
    except Exception as e:
        logger.exception(f"ForumEngine: 停止论坛失败: {e}")

def parse_forum_log_line(line):
    """解析forum.log行内容，提取对话信息"""
    import re
    
    # 匹配格式: [时间] [来源] 内容（来源允许大小写及空格）
    pattern = r'\[(\d{2}:\d{2}:\d{2})\]\s*\[([^\]]+)\]\s*(.*)'
    match = re.match(pattern, line)
    
    if not match:
        return None

    timestamp, raw_source, content = match.groups()
    source = raw_source.strip().upper()

    # 过滤掉系统消息和空内容
    if source == 'SYSTEM' or not content.strip():
        return None
    
    # 支持三个Agent和主持人
    if source not in ['QUERY', 'INSIGHT', 'MEDIA', 'HOST']:
        return None
    
    # 解码日志中的转义换行，保留多行格式
    cleaned_content = content.replace('\\n', '\n').replace('\\r', '').strip()
    
    # 根据来源确定消息类型和发送者
    if source == 'HOST':
        message_type = 'host'
        sender = 'Forum Host'
    else:
        message_type = 'agent'
        sender = f'{source.title()} Engine'
    
    return {
        'type': message_type,
        'sender': sender,
        'content': cleaned_content,
        'timestamp': timestamp,
        'source': source
    }

# Forum日志监听器
# 存储每个客户端的历史日志发送位置
forum_log_positions = {}

def monitor_forum_log():
    """监听forum.log文件变化并推送到前端"""
    import time
    from pathlib import Path

    forum_log_file = LOG_DIR / "forum.log"
    last_position = 0
    processed_lines = set()  # 用于跟踪已处理的行，避免重复

    # 如果文件存在，获取初始位置但不跳过内容
    if forum_log_file.exists():
        with open(forum_log_file, 'r', encoding='utf-8', errors='ignore') as f:
            # 记录文件大小，但不添加到processed_lines
            # 这样用户打开forum标签时可以获取历史
            f.seek(0, 2)  # 移到文件末尾
            last_position = f.tell()

    while True:
        try:
            if forum_log_file.exists():
                with open(forum_log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    f.seek(last_position)
                    new_lines = f.readlines()

                    if new_lines:
                        for line in new_lines:
                            line = line.rstrip('\n\r')
                            if line.strip():
                                line_hash = hash(line.strip())

                                # 避免重复处理同一行
                                if line_hash in processed_lines:
                                    continue

                                processed_lines.add(line_hash)

                                # 解析日志行并发送forum消息
                                parsed_message = parse_forum_log_line(line)
                                if parsed_message:
                                    socketio.emit('forum_message', parsed_message)

                                # 只有在控制台显示forum时才发送控制台消息
                                timestamp = datetime.now().strftime('%H:%M:%S')
                                formatted_line = f"[{timestamp}] {line}"
                                socketio.emit('console_output', {
                                    'app': 'forum',
                                    'line': formatted_line
                                })

                        last_position = f.tell()

                        # 清理processed_lines集合，避免内存泄漏（保留最近1000行的哈希）
                        if len(processed_lines) > 1000:
                            # 保留最近500行的哈希
                            recent_hashes = list(processed_lines)[-500:]
                            processed_lines = set(recent_hashes)

            time.sleep(1)  # 每秒检查一次
        except Exception as e:
            logger.error(f"Forum日志监听错误: {e}")
            time.sleep(5)

# 启动Forum日志监听线程
forum_monitor_thread = threading.Thread(target=monitor_forum_log, daemon=True)
forum_monitor_thread.start()

# 全局变量存储进程信息
processes = {
    'insight': {'process': None, 'port': 8501, 'status': 'stopped', 'output': [], 'log_file': None, 'healthcheck_started_at': None},
    'media': {'process': None, 'port': 8502, 'status': 'stopped', 'output': [], 'log_file': None, 'healthcheck_started_at': None},
    'query': {'process': None, 'port': 8503, 'status': 'stopped', 'output': [], 'log_file': None, 'healthcheck_started_at': None},
    'forum': {'process': None, 'port': None, 'status': 'stopped', 'output': [], 'log_file': None}  # 启动后标记为 running
}

STREAMLIT_SCRIPTS = {
    'insight': 'SingleEngineApp/insight_engine_streamlit_app.py',
    'media': 'SingleEngineApp/media_engine_streamlit_app.py',
    'query': 'SingleEngineApp/query_engine_streamlit_app.py'
}

def _log_shutdown_step(message: str):
    """统一记录关机步骤，便于排查。"""
    if 'pytest' in sys.modules:
        return
    logger.info(f"[Shutdown] {message}")


def _describe_running_children():
    """列出当前存活的子进程。"""
    running = []
    for name, info in processes.items():
        proc = info.get('process')
        if proc is not None and proc.poll() is None:
            port_desc = f", port={info.get('port')}" if info.get('port') else ""
            running.append(f"{name}(pid={proc.pid}{port_desc})")
    return running

# 输出队列
output_queues = {
    'insight': Queue(),
    'media': Queue(),
    'query': Queue(),
    'forum': Queue()
}

def write_log_to_file(app_name, line):
    """将日志写入文件"""
    try:
        log_file_path = LOG_DIR / f"{app_name}.log"
        with open(log_file_path, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
            f.flush()
    except Exception as e:
        logger.error(f"Error writing log for {app_name}: {e}")

def read_log_from_file(app_name, tail_lines=None):
    """从文件读取日志"""
    try:
        log_file_path = LOG_DIR / f"{app_name}.log"
        if not log_file_path.exists():
            return []
        
        with open(log_file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            lines = [line.rstrip('\n\r') for line in lines if line.strip()]
            
            if tail_lines:
                return lines[-tail_lines:]
            return lines
    except Exception as e:
        logger.exception(f"Error reading log for {app_name}: {e}")
        return []

def read_process_output(process, app_name):
    """读取进程输出并写入文件"""
    import select
    import sys
    
    while True:
        try:
            if process.poll() is not None:
                # 进程结束，读取剩余输出
                remaining_output = process.stdout.read()
                if remaining_output:
                    lines = remaining_output.decode('utf-8', errors='replace').split('\n')
                    for line in lines:
                        line = line.strip()
                        if line:
                            timestamp = datetime.now().strftime('%H:%M:%S')
                            formatted_line = f"[{timestamp}] {line}"
                            write_log_to_file(app_name, formatted_line)
                            socketio.emit('console_output', {
                                'app': app_name,
                                'line': formatted_line
                            })
                break
            
            # 使用非阻塞读取
            if sys.platform == 'win32':
                # Windows下使用不同的方法
                output = process.stdout.readline()
                if output:
                    line = output.decode('utf-8', errors='replace').strip()
                    if line:
                        timestamp = datetime.now().strftime('%H:%M:%S')
                        formatted_line = f"[{timestamp}] {line}"
                        
                        # 写入日志文件
                        write_log_to_file(app_name, formatted_line)
                        
                        # 发送到前端
                        socketio.emit('console_output', {
                            'app': app_name,
                            'line': formatted_line
                        })
                else:
                    # 没有输出时短暂休眠
                    time.sleep(0.1)
            else:
                # Unix系统使用select
                ready, _, _ = select.select([process.stdout], [], [], 0.1)
                if ready:
                    output = process.stdout.readline()
                    if output:
                        line = output.decode('utf-8', errors='replace').strip()
                        if line:
                            timestamp = datetime.now().strftime('%H:%M:%S')
                            formatted_line = f"[{timestamp}] {line}"
                            
                            # 写入日志文件
                            write_log_to_file(app_name, formatted_line)
                            
                            # 发送到前端
                            socketio.emit('console_output', {
                                'app': app_name,
                                'line': formatted_line
                            })
                            
        except Exception as e:
            error_msg = f"Error reading output for {app_name}: {e}"
            logger.exception(error_msg)
            write_log_to_file(app_name, f"[{datetime.now().strftime('%H:%M:%S')}] {error_msg}")
            break

def start_streamlit_app(app_name, script_path, port):
    """启动Streamlit应用"""
    try:
        if processes[app_name]['process'] is not None:
            return False, "应用已经在运行"
        
        # 检查文件是否存在
        if not os.path.exists(script_path):
            return False, f"文件不存在: {script_path}"
        
        # 清空之前的日志文件
        log_file_path = LOG_DIR / f"{app_name}.log"
        if log_file_path.exists():
            log_file_path.unlink()
        
        # 创建启动日志
        start_msg = f"[{datetime.now().strftime('%H:%M:%S')}] 启动 {app_name} 应用..."
        write_log_to_file(app_name, start_msg)
        
        cmd = [
            sys.executable, '-m', 'streamlit', 'run',
            script_path,
            '--server.port', str(port),
            '--server.headless', 'true',
            '--browser.gatherUsageStats', 'false',
            # '--logger.level', 'debug',  # 增加日志详细程度
            '--logger.level', 'info',
            '--server.enableCORS', 'false'
        ]
        
        # 设置环境变量确保UTF-8编码和减少缓冲
        env = os.environ.copy()
        env.update({
            'PYTHONIOENCODING': 'utf-8',
            'PYTHONUTF8': '1',
            'LANG': 'en_US.UTF-8',
            'LC_ALL': 'en_US.UTF-8',
            'PYTHONUNBUFFERED': '1',  # 禁用Python缓冲
            'STREAMLIT_BROWSER_GATHER_USAGE_STATS': 'false'
        })
        
        # 使用当前工作目录而不是脚本目录
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,  # 无缓冲
            universal_newlines=False,
            cwd=os.getcwd(),
            env=env,
            encoding=None,  # 让我们手动处理编码
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )
        
        processes[app_name]['process'] = process
        processes[app_name]['status'] = 'starting'
        processes[app_name]['output'] = []
        processes[app_name]['healthcheck_started_at'] = time.time()
        
        # 启动输出读取线程
        output_thread = threading.Thread(
            target=read_process_output,
            args=(process, app_name),
            daemon=True
        )
        output_thread.start()
        
        return True, f"{app_name} 应用启动中..."
        
    except Exception as e:
        error_msg = f"启动失败: {str(e)}"
        write_log_to_file(app_name, f"[{datetime.now().strftime('%H:%M:%S')}] {error_msg}")
        return False, error_msg

def stop_streamlit_app(app_name):
    """停止Streamlit应用"""
    try:
        process = processes[app_name]['process']
        if process is None:
            _log_shutdown_step(f"{app_name} 未运行，跳过停止")
            return False, "应用未运行"
        
        try:
            pid = process.pid
        except Exception:
            pid = 'unknown'

        _log_shutdown_step(f"正在停止 {app_name} (pid={pid})")
        process.terminate()
        
        # 等待进程结束
        try:
            process.wait(timeout=5)
            _log_shutdown_step(f"{app_name} 退出完成，returncode={process.returncode}")
        except subprocess.TimeoutExpired:
            _log_shutdown_step(f"{app_name} 终止超时，尝试强制结束 (pid={pid})")
            process.kill()
            process.wait()
            _log_shutdown_step(f"{app_name} 已强制结束，returncode={process.returncode}")
        
        processes[app_name]['process'] = None
        processes[app_name]['status'] = 'stopped'
        processes[app_name]['healthcheck_started_at'] = None
        
        return True, f"{app_name} 应用已停止"
        
    except Exception as e:
        _log_shutdown_step(f"{app_name} 停止失败: {e}")
        return False, f"停止失败: {str(e)}"

HEALTHCHECK_PATH = "/_stcore/health"
HEALTHCHECK_PROXIES = {'http': None, 'https': None}
HEALTHCHECK_GRACE_SECONDS = 15


def _build_healthcheck_url(port):
    return f"http://127.0.0.1:{port}{HEALTHCHECK_PATH}"


def _healthcheck_grace_active(app_name: str) -> bool:
    started_at = processes.get(app_name, {}).get('healthcheck_started_at')
    if not started_at:
        return False
    return (time.time() - started_at) < HEALTHCHECK_GRACE_SECONDS


def _log_healthcheck_failure(app_name: str, exc: Exception):
    if _healthcheck_grace_active(app_name):
        logger.debug(f"正在启动{app_name}，请等待")
        return
    logger.warning(f"{app_name} 健康检查失败: {exc}")


def check_app_status():
    """检查应用状态"""
    for app_name, info in processes.items():
        if info['process'] is not None:
            if info['process'].poll() is None:
                # 进程仍在运行，检查端口是否可访问
                try:
                    response = requests.get(
                        _build_healthcheck_url(info['port']),
                        timeout=2,
                        proxies=HEALTHCHECK_PROXIES
                    )
                    if response.status_code == 200:
                        info['status'] = 'running'
                    else:
                        info['status'] = 'starting'
                except Exception as exc:
                    _log_healthcheck_failure(app_name, exc)
                    info['status'] = 'starting'
            else:
                # 进程已结束
                info['process'] = None
                info['status'] = 'stopped'
                info['healthcheck_started_at'] = None

def wait_for_app_startup(app_name, max_wait_time=90):
    """等待应用启动完成"""
    import time
    start_time = time.time()
    while time.time() - start_time < max_wait_time:
        info = processes[app_name]
        if info['process'] is None:
            return False, "进程已停止"
        
        if info['process'].poll() is not None:
            return False, "进程启动失败"
        
        try:
            response = requests.get(
                _build_healthcheck_url(info['port']),
                timeout=2,
                proxies=HEALTHCHECK_PROXIES
            )
            if response.status_code == 200:
                info['status'] = 'running'
                return True, "启动成功"
        except Exception as exc:
            _log_healthcheck_failure(app_name, exc)

        time.sleep(1)

    return False, "启动超时"

def cleanup_processes():
    """清理所有进程"""
    if 'pytest' in sys.modules:
        return
    _log_shutdown_step("开始串行清理子进程")
    for app_name in STREAMLIT_SCRIPTS:
        stop_streamlit_app(app_name)

    processes['forum']['status'] = 'stopped'
    try:
        stop_forum_engine()
    except Exception:  # pragma: no cover
        logger.exception("停止ForumEngine失败")
    _log_shutdown_step("子进程清理完成")
    _set_system_state(started=False, starting=False)

def cleanup_processes_concurrent(timeout: float = 6.0):
    """并发清理所有子进程，超时后强制杀掉残留进程。"""
    _log_shutdown_step(f"开始并发清理子进程（超时 {timeout}s）")
    _log_shutdown_step("仅终止当前控制台启动并记录的子进程，不做端口扫描")
    running_before = _describe_running_children()
    if running_before:
        _log_shutdown_step("当前存活子进程: " + ", ".join(running_before))
    else:
        _log_shutdown_step("未检测到存活子进程，仍将发送关闭指令")

    threads = []

    # 并发关闭 Streamlit 子进程
    for app_name in STREAMLIT_SCRIPTS:
        t = threading.Thread(target=stop_streamlit_app, args=(app_name,), daemon=True)
        threads.append(t)
        t.start()

    # 并发关闭 ForumEngine
    forum_thread = threading.Thread(target=stop_forum_engine, daemon=True)
    threads.append(forum_thread)
    forum_thread.start()

    # 等待所有线程完成，最多 timeout 秒
    end_time = time.time() + timeout
    for t in threads:
        remaining = end_time - time.time()
        if remaining <= 0:
            break
        t.join(timeout=remaining)

    # 二次检查：强制杀掉仍存活的子进程
    for app_name in STREAMLIT_SCRIPTS:
        proc = processes[app_name]['process']
        if proc is not None and proc.poll() is None:
            try:
                _log_shutdown_step(f"{app_name} 进程仍存活，触发二次终止 (pid={proc.pid})")
                proc.terminate()
                proc.wait(timeout=1)
            except Exception:
                try:
                    _log_shutdown_step(f"{app_name} 二次终止失败，尝试kill (pid={proc.pid})")
                    proc.kill()
                    proc.wait(timeout=1)
                except Exception:
                    logger.warning(f"{app_name} 进程强制退出失败，继续关机")
            finally:
                processes[app_name]['process'] = None
                processes[app_name]['status'] = 'stopped'

    processes['forum']['status'] = 'stopped'
    _log_shutdown_step("并发清理结束，标记系统未启动")
    _set_system_state(started=False, starting=False)

def _schedule_server_shutdown(delay_seconds: float = 0.1):
    """在清理完成后尽快退出，避免阻塞当前请求。"""
    def _shutdown():
        time.sleep(delay_seconds)
        try:
            socketio.stop()
        except Exception as exc:  # pragma: no cover
            logger.warning(f"SocketIO 停止时异常，继续退出: {exc}")
        _log_shutdown_step("SocketIO 停止指令已发送，即将退出主进程")
        os._exit(0)

    threading.Thread(target=_shutdown, daemon=True).start()

def _start_async_shutdown(cleanup_timeout: float = 3.0):
    """异步触发清理并强制退出，避免HTTP请求阻塞。"""
    _log_shutdown_step(f"收到关机指令，启动异步清理（超时 {cleanup_timeout}s）")

    def _force_exit():
        _log_shutdown_step("关机超时，触发强制退出")
        os._exit(0)

    # 硬超时保护，即便清理线程异常也能退出
    hard_timeout = cleanup_timeout + 2.0
    force_timer = threading.Timer(hard_timeout, _force_exit)
    force_timer.daemon = True
    force_timer.start()

    def _cleanup_and_exit():
        try:
            cleanup_processes_concurrent(timeout=cleanup_timeout)
        except Exception as exc:  # pragma: no cover
            logger.exception(f"关机清理异常: {exc}")
        finally:
            _log_shutdown_step("清理线程结束，调度主进程退出")
            _schedule_server_shutdown(0.05)

    threading.Thread(target=_cleanup_and_exit, daemon=True).start()

# 注册清理函数
atexit.register(cleanup_processes)

@app.route('/')
def index():
    """主页"""
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    """获取所有应用状态"""
    check_app_status()
    return jsonify({
        app_name: {
            'status': info['status'],
            'port': info['port'],
            'output_lines': len(info['output'])
        }
        for app_name, info in processes.items()
    })

@app.route('/api/start/<app_name>')
def start_app(app_name):
    """启动指定应用"""
    if app_name not in processes:
        return jsonify({'success': False, 'message': '未知应用'})

    if app_name == 'forum':
        try:
            start_forum_engine()
            processes['forum']['status'] = 'running'
            return jsonify({'success': True, 'message': 'ForumEngine已启动'})
        except Exception as exc:  # pragma: no cover
            logger.exception("手动启动ForumEngine失败")
            return jsonify({'success': False, 'message': f'ForumEngine启动失败: {exc}'})

    script_path = STREAMLIT_SCRIPTS.get(app_name)
    if not script_path:
        return jsonify({'success': False, 'message': '该应用不支持启动操作'})

    success, message = start_streamlit_app(
        app_name,
        script_path,
        processes[app_name]['port']
    )

    if success:
        # 等待应用启动
        startup_success, startup_message = wait_for_app_startup(app_name, 15)
        if not startup_success:
            message += f" 但启动检查失败: {startup_message}"
    
    return jsonify({'success': success, 'message': message})

@app.route('/api/stop/<app_name>')
def stop_app(app_name):
    """停止指定应用"""
    if app_name not in processes:
        return jsonify({'success': False, 'message': '未知应用'})

    if app_name == 'forum':
        try:
            stop_forum_engine()
            processes['forum']['status'] = 'stopped'
            return jsonify({'success': True, 'message': 'ForumEngine已停止'})
        except Exception as exc:  # pragma: no cover
            logger.exception("手动停止ForumEngine失败")
            return jsonify({'success': False, 'message': f'ForumEngine停止失败: {exc}'})

    success, message = stop_streamlit_app(app_name)
    return jsonify({'success': success, 'message': message})

@app.route('/api/output/<app_name>')
def get_output(app_name):
    """获取应用输出"""
    if app_name not in processes:
        return jsonify({'success': False, 'message': '未知应用'})
    
    # 特殊处理Forum Engine
    if app_name == 'forum':
        try:
            forum_log_content = read_log_from_file('forum')
            return jsonify({
                'success': True,
                'output': forum_log_content,
                'total_lines': len(forum_log_content)
            })
        except Exception as e:
            return jsonify({'success': False, 'message': f'读取forum日志失败: {str(e)}'})
    
    # 从文件读取完整日志
    output_lines = read_log_from_file(app_name)
    
    return jsonify({
        'success': True,
        'output': output_lines
    })

@app.route('/api/test_log/<app_name>')
def test_log(app_name):
    """测试日志写入功能"""
    if app_name not in processes:
        return jsonify({'success': False, 'message': '未知应用'})
    
    # 写入测试消息
    test_msg = f"[{datetime.now().strftime('%H:%M:%S')}] 测试日志消息 - {datetime.now()}"
    write_log_to_file(app_name, test_msg)
    
    # 通过Socket.IO发送
    socketio.emit('console_output', {
        'app': app_name,
        'line': test_msg
    })
    
    return jsonify({
        'success': True,
        'message': f'测试消息已写入 {app_name} 日志'
    })

@app.route('/api/forum/start')
def start_forum_monitoring_api():
    """手动启动ForumEngine论坛"""
    try:
        from ForumEngine.monitor import start_forum_monitoring
        success = start_forum_monitoring()
        if success:
            return jsonify({'success': True, 'message': 'ForumEngine论坛已启动'})
        else:
            return jsonify({'success': False, 'message': 'ForumEngine论坛启动失败'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'启动论坛失败: {str(e)}'})

@app.route('/api/forum/stop')
def stop_forum_monitoring_api():
    """手动停止ForumEngine论坛"""
    try:
        from ForumEngine.monitor import stop_forum_monitoring
        stop_forum_monitoring()
        return jsonify({'success': True, 'message': 'ForumEngine论坛已停止'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'停止论坛失败: {str(e)}'})

@app.route('/api/forum/log')
def get_forum_log():
    """获取ForumEngine的forum.log内容"""
    try:
        forum_log_file = LOG_DIR / "forum.log"
        if not forum_log_file.exists():
            return jsonify({
                'success': True,
                'log_lines': [],
                'parsed_messages': [],
                'total_lines': 0
            })
        
        with open(forum_log_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            lines = [line.rstrip('\n\r') for line in lines if line.strip()]
        
        # 解析每一行日志并提取对话信息
        parsed_messages = []
        for line in lines:
            parsed_message = parse_forum_log_line(line)
            if parsed_message:
                parsed_messages.append(parsed_message)
        
        return jsonify({
            'success': True,
            'log_lines': lines,
            'parsed_messages': parsed_messages,
            'total_lines': len(lines)
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'读取forum.log失败: {str(e)}'})

@app.route('/api/forum/log/history', methods=['POST'])
def get_forum_log_history():
    """获取Forum历史日志（支持从指定位置开始）"""
    try:
        data = request.get_json()
        start_position = data.get('position', 0)  # 客户端上次接收的位置
        max_lines = data.get('max_lines', 1000)   # 最多返回的行数

        forum_log_file = LOG_DIR / "forum.log"
        if not forum_log_file.exists():
            return jsonify({
                'success': True,
                'log_lines': [],
                'position': 0,
                'has_more': False
            })

        with open(forum_log_file, 'r', encoding='utf-8', errors='ignore') as f:
            # 从指定位置开始读取
            f.seek(start_position)
            lines = []
            line_count = 0

            for line in f:
                if line_count >= max_lines:
                    break
                line = line.rstrip('\n\r')
                if line.strip():
                    # 添加时间戳
                    timestamp = datetime.now().strftime('%H:%M:%S')
                    formatted_line = f"[{timestamp}] {line}"
                    lines.append(formatted_line)
                    line_count += 1

            # 记录当前位置
            current_position = f.tell()

            # 检查是否还有更多内容
            f.seek(0, 2)  # 移到文件末尾
            end_position = f.tell()
            has_more = current_position < end_position

        return jsonify({
            'success': True,
            'log_lines': lines,
            'position': current_position,
            'has_more': has_more
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'读取forum历史失败: {str(e)}'})

@app.route('/api/search', methods=['POST'])
def search():
    """启动后端一键搜索编排任务。"""
    data = request.get_json(silent=True) or {}
    query = data.get('query', '').strip()
    
    if not query:
        return jsonify({'success': False, 'message': '搜索查询不能为空'}), 400

    engine_artifacts = data.get('engine_artifacts', {})
    if not isinstance(engine_artifacts, dict):
        return jsonify({'success': False, 'message': 'engine_artifacts must be an object'}), 400

    gate_result = _check_search_data_prep_gate(query, data.get('data_prep_task_id'))
    if gate_result is not None:
        return jsonify(gate_result), 409

    data_prep_task_id = str(data.get('data_prep_task_id') or '').strip()
    data_prep_task = crawl_tasks.get_task(data_prep_task_id) if data_prep_task_id else None
    if data_prep_task:
        result = search_orchestrator.start_search(
            query,
            research_request=_deserialize_weibo_data_request(data_prep_task.data_request),
            evidence_manifest=data_prep_task.evidence_manifest,
            data_prep_task_id=data_prep_task.task_id,
            engine_artifacts=engine_artifacts,
        )
    else:
        result = search_orchestrator.start_search(query, engine_artifacts=engine_artifacts)
    if data_prep_task_id:
        result['data_prep_task_id'] = data_prep_task_id
    status_code = 200 if result.get('success') else 400
    return jsonify(result), status_code


@app.route('/api/intake/web-search', methods=['POST'])
def intake_web_search():
    """Run a lightweight synchronous web search for chat intake clarification."""
    data = request.get_json(silent=True) or {}
    query = str(data.get('query', '')).strip()

    if not query:
        return jsonify({
            'success': False,
            'message': 'Search query cannot be empty.',
        }), 400

    try:
        result = run_intake_web_search(query, data.get('max_results'))
    except IntakeWebSearchConfigError:
        return jsonify({
            'success': False,
            'message': 'Search provider is not configured.',
        }), 503
    except IntakeWebSearchRuntimeError:
        return jsonify({
            'success': False,
            'message': 'Search provider request failed.',
        }), 502

    return jsonify(result)


@app.route('/api/search/status/<task_id>', methods=['GET'])
def search_status(task_id):
    """查询后端一键搜索编排任务状态。"""
    result = search_orchestrator.get_status(task_id)
    if not result:
        return jsonify({'success': False, 'message': '搜索任务不存在'}), 404
    return jsonify(result)


@app.route('/api/data/readiness', methods=['POST'])
def data_readiness():
    """Check whether imported MediaCrawler data can support a request."""
    data = request.get_json(silent=True) or {}
    query = data.get('query', '').strip()
    if not query:
        return jsonify({'success': False, 'message': '分析查询不能为空'}), 400

    minimum_total = int(data.get('minimum_total') or 1)
    minimum_tables = int(data.get('minimum_tables') or 1)
    platforms = _coerce_readiness_platforms(data.get('platforms'))
    result = asyncio.run(
        check_data_readiness(
            query,
            minimum_total=minimum_total,
            minimum_tables=minimum_tables,
            platforms=platforms,
        )
    )
    status_code = 200 if result.get('success') else 503
    return jsonify(result), status_code


@app.route('/api/crawl/tasks', methods=['POST'])
def create_crawl_task():
    """Create a crawl-preparation task contract without running MediaCrawler."""
    data = request.get_json(silent=True) or {}
    analysis_query = (data.get('analysis_query') or data.get('query') or '').strip()
    if not analysis_query:
        return jsonify({'success': False, 'message': 'analysis query is required'}), 400

    provider = select_weibo_provider(settings)
    caps = build_weibo_data_caps(settings)
    data_request_payload = _coerce_weibo_data_request(data.get('data_request'), analysis_query)
    task = crawl_tasks.create_task(
        analysis_query=analysis_query,
        data_request=_serialize_weibo_data_request(
            data_request_payload if isinstance(data.get('data_request'), dict) else data.get('data_request'),
            analysis_query,
        ),
        platforms=data.get('platforms') or None,
        provider=provider.name,
        caps=caps.to_dict(),
    )
    if provider.name == 'tikhub' and not _crawler_cloud_endpoint():
        try:
            _execute_tikhub_crawl_task(task, provider, caps, data_request_payload)
        except Exception as exc:
            message = _safe_error_message(exc)
            logger.error(f"TikHub Weibo data prep failed: {message}")
            task.mark_failed(message)
            return jsonify({'success': False, 'task': task.to_dict(), 'message': message}), 500
        return jsonify({'success': True, 'task': task.to_dict()}), 200

    if not _crawler_cloud_endpoint():
        task.mark_status(
            'manual_action_required',
            "请运行微博采集任务，导入结果后再检查数据是否足以进入分析。",
        )
    _submit_crawl_task_to_cloud_if_configured(task)
    return jsonify({'success': True, 'task': task.to_dict()}), 202


@app.route('/api/crawl/tasks/<task_id>', methods=['GET'])
def get_crawl_task(task_id):
    """Return crawl-preparation task status."""
    task = crawl_tasks.get_task(task_id)
    if not task:
        return jsonify({'success': False, 'message': 'crawl task not found'}), 404
    _refresh_crawl_task_from_cloud_if_needed(task)
    return jsonify({'success': True, 'task': task.to_dict()})


@app.route('/api/crawl/tasks/<task_id>/complete', methods=['POST'])
def complete_crawl_task(task_id):
    """Import completed crawler output and mark crawl-prep task imported."""
    task = crawl_tasks.get_task(task_id)
    if not task:
        return jsonify({'success': False, 'message': 'crawl task not found'}), 404

    data = request.get_json(silent=True) or {}
    raw_files = data.get('output_files') or data.get('files') or []
    output_files = [Path(str(path)) for path in raw_files if str(path).strip()]
    if not output_files:
        return jsonify({'success': False, 'message': 'output_files is required'}), 400

    try:
        _import_crawl_output(task, output_files, include_irrelevant=bool(data.get('include_irrelevant')))
    except Exception as exc:
        logger.exception(f"Weibo output import failed: {exc}")
        task.mark_failed(str(exc))
        return jsonify({'success': False, 'task': task.to_dict(), 'message': str(exc)}), 500

    return jsonify({'success': True, 'task': task.to_dict()})


def _import_crawl_output(task, output_files, *, include_irrelevant=False):
    import_result = asyncio.run(
        import_weibo_bundle(
            output_files,
            build_mediacrawler_dsn(),
            relevant_only=not include_irrelevant,
        )
    )
    caps = _caps_from_task(task)
    bundle = _load_crawl_output_bundle(task, output_files, caps)
    readiness = asyncio.run(
        check_data_readiness(_readiness_query_for_bundle(task.analysis_query, bundle), platforms=["weibo"])
    )
    reportability = evaluate_weibo_reportability(bundle, readiness=readiness)
    bundle_metadata = _bundle_metadata_for_task(bundle)
    evidence_manifest = _build_weibo_manifest_for_task(
        bundle,
        readiness,
        reportability.to_dict(),
        import_result,
        bundle_metadata,
    )

    if reportability.can_start_analysis:
        task.mark_reportable(
            import_result,
            readiness,
            reportability.to_dict(),
            bundle_metadata,
            evidence_manifest=evidence_manifest,
        )
    else:
        task.mark_insufficient(
            readiness,
            reportability.to_dict(),
            bundle_metadata,
            import_result=import_result,
            evidence_manifest=evidence_manifest,
        )


def _execute_tikhub_crawl_task(task, provider, caps, request_payload):
    task.mark_status(
        'compiling',
        '正在编译 TikHub 微博数据准备任务。',
    )

    accumulated_bundle = build_weibo_collection_bundle(
        provider.name,
        request_payload,
        caps,
    )
    collection_rounds: list[dict[str, Any]] = []
    import_result: dict[str, Any] = {}
    readiness: dict[str, Any] = {}
    reportability = evaluate_weibo_reportability(
        accumulated_bundle,
        readiness={'data_ready': False},
    )

    for round_index, round_spec in enumerate(
        _tikhub_collection_rounds(provider, caps, request_payload),
        start=1,
    ):
        strategy = str(round_spec['strategy'])
        task.mark_status(
            'collecting',
            f'正在使用 TikHub 采集微博帖子和一级评论（{strategy}）。',
        )
        round_bundle = round_spec['provider'].collect(
            round_spec['request'],
            round_spec['caps'],
        )
        collection_rounds.append(
            _summarize_collection_round(round_index, strategy, round_bundle)
        )
        accumulated_bundle = _merge_weibo_bundles(
            provider.name,
            request_payload,
            caps,
            accumulated_bundle,
            round_bundle,
            collection_rounds,
        )

        if not accumulated_bundle.posts and not accumulated_bundle.comments:
            reportability = evaluate_weibo_reportability(
                accumulated_bundle,
                readiness={'data_ready': False},
            )
            continue

        task.mark_status('normalizing', '正在整理 TikHub 微博数据，准备导入本地。')
        round_import_result = _import_tikhub_bundle(accumulated_bundle)
        import_result = _merge_import_results(import_result, round_import_result)
        task.mark_status('readiness_checking', '正在检查已导入微博数据是否足以分析。')
        readiness = asyncio.run(
            check_data_readiness(
                _readiness_query_for_bundle(task.analysis_query, accumulated_bundle),
                platforms=["weibo"],
            )
        )
        reportability = evaluate_weibo_reportability(
            accumulated_bundle,
            readiness=readiness,
        )
        if reportability.can_start_analysis:
            bundle_metadata = _bundle_metadata_for_task(
                accumulated_bundle,
                collection_rounds,
            )
            evidence_manifest = _build_weibo_manifest_for_task(
                accumulated_bundle,
                readiness,
                reportability.to_dict(),
                import_result,
                bundle_metadata,
            )
            task.mark_reportable(
                import_result,
                readiness,
                reportability.to_dict(),
                bundle_metadata,
                evidence_manifest=evidence_manifest,
            )
            return

    bundle_metadata = _bundle_metadata_for_task(accumulated_bundle, collection_rounds)
    bundle_metadata['fallback_stop_reason'] = (
        'zero_results'
        if not accumulated_bundle.posts and not accumulated_bundle.comments
        else 'insufficient_after_fallback'
    )
    evidence_manifest = _build_weibo_manifest_for_task(
        accumulated_bundle,
        readiness,
        reportability.to_dict(),
        import_result,
        bundle_metadata,
    )
    task.mark_insufficient(
        readiness,
        reportability.to_dict(),
        bundle_metadata,
        import_result=import_result,
        evidence_manifest=evidence_manifest,
    )


def _import_tikhub_bundle(bundle):
    bundle_path = _write_temp_weibo_bundle(bundle)
    try:
        return asyncio.run(
            import_weibo_bundle(
                [bundle_path],
                build_mediacrawler_dsn(),
                relevant_only=True,
            )
        )
    finally:
        try:
            bundle_path.unlink(missing_ok=True)
        except Exception as exc:  # pragma: no cover - cleanup only
            logger.warning(f"Temporary TikHub bundle cleanup failed: {exc}")


def _readiness_query_for_bundle(analysis_query, bundle):
    terms: list[str] = []
    for keyword in getattr(bundle, 'keywords', []) or []:
        text = str(keyword or '').strip()
        if text and text not in terms:
            terms.append(text)
    query_text = str(analysis_query or '').strip()
    if query_text and query_text not in terms:
        terms.append(query_text)
    return ' '.join(terms) or query_text


def _merge_import_results(current, next_result):
    if not current:
        merged = dict(next_result or {})
        if merged:
            merged['rounds'] = [dict(next_result or {})]
        return merged

    merged = dict(current or {})
    merged['provider'] = merged.get('provider') or (next_result or {}).get('provider')
    merged['inputs'] = list(merged.get('inputs') or []) + list((next_result or {}).get('inputs') or [])
    merged.setdefault('rounds', [])
    merged['rounds'] = list(merged['rounds']) + [dict(next_result or {})]

    current_counts = dict(merged.get('counts') or {})
    next_counts = dict((next_result or {}).get('counts') or {})
    table_total_keys = {'weibo_note', 'weibo_note_comment'}
    for key, value in next_counts.items():
        if key in table_total_keys:
            current_counts[key] = value
            continue
        if isinstance(value, int):
            current_counts[key] = int(current_counts.get(key) or 0) + value
        else:
            current_counts[key] = value
    merged['counts'] = current_counts
    return merged


def _tikhub_collection_rounds(provider, caps, request_payload):
    broadened_request = _broaden_weibo_request(request_payload)
    broadened_provider = _replace_provider(
        provider,
        pages_per_keyword=max(
            int(getattr(provider, 'pages_per_keyword', 1) or 1),
            min(3, int(getattr(provider, 'pages_per_keyword', 1) or 1) + 1),
        ),
    )
    comment_caps = replace(
        caps,
        max_comments_per_post=max(caps.max_comments_per_post, caps.max_comments_per_post_hard),
    )
    return (
        {
            'strategy': 'default',
            'provider': provider,
            'caps': caps,
            'request': request_payload,
        },
        {
            'strategy': 'broaden_keywords',
            'provider': broadened_provider,
            'caps': caps,
            'request': broadened_request,
        },
        {
            'strategy': 'expand_comments',
            'provider': broadened_provider,
            'caps': comment_caps,
            'request': broadened_request,
        },
    )


def _replace_provider(provider, **changes):
    provider_changes = {
        key: value
        for key, value in changes.items()
        if hasattr(provider, key)
    }
    if not provider_changes:
        return provider
    try:
        return replace(provider, **provider_changes)
    except Exception:
        return provider


def _broaden_weibo_request(request_payload):
    request = dict(request_payload or {})
    known_materials = request.get('knownMaterials') or []
    if isinstance(known_materials, str):
        materials = [known_materials]
    else:
        materials = [str(item) for item in known_materials if str(item).strip()]

    for value in (
        request.get('weiboClue'),
        request.get('eventOrIssue'),
        request.get('affectedSubject'),
        f"{request.get('affectedSubject') or ''} {request.get('eventOrIssue') or ''}",
    ):
        text = str(value or '').strip()
        if text and text not in materials:
            materials.append(text)

    request['knownMaterials'] = materials
    return request


def _merge_weibo_bundles(
    provider,
    request_payload,
    caps,
    current_bundle,
    next_bundle,
    collection_rounds,
):
    posts = _dedupe_records(
        list(current_bundle.posts or []) + list(next_bundle.posts or []),
        ('content_id', 'note_id', 'url', 'content'),
    )
    comments = _dedupe_records(
        list(current_bundle.comments or []) + list(next_bundle.comments or []),
        ('comment_id', 'note_id', 'content'),
    )
    metadata = dict(next_bundle.metadata or {})
    metadata['collection_rounds'] = collection_rounds
    return build_weibo_collection_bundle(
        provider,
        request_payload,
        caps,
        posts=posts,
        comments=comments,
        metadata=metadata,
        stop_reason=next_bundle.stop_reason,
    )


def _dedupe_records(records, keys):
    deduped = []
    seen = set()
    for record in records:
        if not isinstance(record, Mapping):
            continue
        identity = tuple(str(record.get(key) or '').strip() for key in keys)
        fallback = json.dumps(record, ensure_ascii=False, sort_keys=True)
        dedupe_key = identity if any(identity) else fallback
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped.append(dict(record))
    return deduped


def _summarize_collection_round(round_index, strategy, bundle):
    return {
        'round': round_index,
        'strategy': strategy,
        'keywords': list(bundle.keywords or []),
        'post_count': len(bundle.posts or []),
        'comment_count': len(bundle.comments or []),
        'stop_reason': bundle.stop_reason,
        'raw_post_count': (bundle.metadata or {}).get('raw_post_count'),
        'raw_comment_count': (bundle.metadata or {}).get('raw_comment_count'),
    }


def _bundle_metadata_for_task(bundle, collection_rounds=None):
    bundle_metadata = dict(bundle.metadata or {})
    bundle_metadata.setdefault('keywords', list(bundle.keywords or []))
    bundle_metadata.setdefault('stop_reason', bundle.stop_reason)
    bundle_metadata.setdefault('post_count', len(bundle.posts or []))
    bundle_metadata.setdefault('comment_count', len(bundle.comments or []))
    if collection_rounds is not None:
        bundle_metadata['collection_rounds'] = collection_rounds
    return bundle_metadata


def _build_weibo_manifest_for_task(
    bundle,
    readiness,
    reportability,
    import_result,
    bundle_metadata=None,
):
    metadata = dict(getattr(bundle, 'metadata', {}) or {})
    if bundle_metadata:
        metadata.update(dict(bundle_metadata or {}))
    bundle_for_manifest = replace(bundle, metadata=metadata)
    return build_weibo_evidence_manifest(
        bundle=bundle_for_manifest,
        readiness=readiness,
        reportability=reportability,
        import_result=import_result,
    )


def _caps_from_task(task) -> WeiboDataCaps:
    values = dict(task.caps or {})
    allowed = {
        'max_keywords',
        'max_posts_per_keyword',
        'max_selected_posts',
        'max_comments_per_post',
        'max_comments_per_post_hard',
        'allow_subcomments',
    }
    values = {key: value for key, value in values.items() if key in allowed}
    values['allow_subcomments'] = False
    return WeiboDataCaps(**values)


def _load_crawl_output_bundle(task, output_files, caps):
    posts: list[dict[str, Any]] = []
    comments: list[dict[str, Any]] = []
    provider = task.provider or 'mediacrawler'
    for output_file in output_files:
        payload = json.loads(Path(output_file).read_text(encoding='utf-8'))
        file_provider, file_posts, file_comments = _split_crawl_output_payload(payload)
        provider = file_provider or provider
        posts.extend(file_posts)
        comments.extend(file_comments)

    return build_weibo_collection_bundle(
        provider,
        {'eventOrIssue': task.analysis_query},
        caps,
        posts=posts,
        comments=comments,
        metadata={'inputs': [str(path) for path in output_files]},
    )


def _split_crawl_output_payload(payload):
    if isinstance(payload, list):
        posts, comments = _split_crawl_items(payload)
        return '', posts, comments
    if not isinstance(payload, Mapping):
        return '', [], []

    provider = str(payload.get('provider') or '')
    posts = [
        dict(item)
        for item in payload.get('posts') or []
        if isinstance(item, Mapping)
    ]
    comments = [
        dict(item)
        for item in payload.get('comments') or []
        if isinstance(item, Mapping)
    ]
    if posts or comments:
        return provider, posts, comments

    items = payload.get('items')
    if isinstance(items, list):
        split_posts, split_comments = _split_crawl_items(items)
        return provider, split_posts, split_comments

    if _is_comment_payload(payload):
        return provider, [], [dict(payload)]
    if _is_post_payload(payload):
        return provider, [dict(payload)], []
    return provider, [], []


def _split_crawl_items(items):
    posts: list[dict[str, Any]] = []
    comments: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        if _is_comment_payload(item):
            comments.append(dict(item))
        elif _is_post_payload(item):
            posts.append(dict(item))
    return posts, comments


def _is_comment_payload(item):
    return bool(item.get('comment_id') or item.get('parent_comment_id'))


def _is_post_payload(item):
    return bool(
        item.get('content_id')
        or item.get('note_id')
        or item.get('title')
        or item.get('content')
    )


def _write_temp_weibo_bundle(bundle):
    handle = tempfile.NamedTemporaryFile(
        mode='w',
        encoding='utf-8',
        suffix='.json',
        prefix='tikhub_weibo_bundle_',
        delete=False,
    )
    with handle:
        json.dump(bundle.to_dict(), handle, ensure_ascii=False)
    return Path(handle.name)


def _check_search_data_prep_gate(query, data_prep_task_id):
    provider_name = str(
        getattr(settings, 'WEIBO_DATA_PROVIDER', 'tikhub') or 'tikhub'
    ).strip().lower()
    if provider_name != 'tikhub':
        return None

    task_id = str(data_prep_task_id or '').strip()
    if not task_id:
        return {
            'success': False,
            'status': 'needs_weibo_data',
            'message': '正式分析前需要先完成可分析的 TikHub 微博数据准备。',
        }

    task = crawl_tasks.get_task(task_id)
    if not task:
        return {
            'success': False,
            'status': 'needs_weibo_data',
            'message': '未找到对应的微博数据准备任务。',
            'data_prep_task_id': task_id,
        }

    if task.analysis_query != query:
        return {
            'success': False,
            'status': 'needs_weibo_data',
            'message': '微博数据准备任务与当前分析查询不匹配。',
            'data_prep_task_id': task_id,
            'task': task.to_dict(),
        }

    reportability = task.reportability or {}
    if str(task.provider or '').strip().lower() != 'tikhub':
        return {
            'success': False,
            'status': 'needs_weibo_data',
            'message': '正式分析前需要使用 TikHub 微博数据准备任务。',
            'data_prep_task_id': task_id,
            'task': task.to_dict(),
        }

    if (
        task.status != 'reportable'
        or reportability.get('status') != 'reportable'
        or reportability.get('can_start_analysis') is not True
    ):
        return {
            'success': False,
            'status': 'needs_weibo_data',
            'message': '微博数据准备尚未达到可分析状态。',
            'data_prep_task_id': task_id,
            'task': task.to_dict(),
        }

    return None


def _coerce_weibo_data_request(raw_request, analysis_query):
    if isinstance(raw_request, dict):
        return _normalize_weibo_data_request_aliases(raw_request, analysis_query)
    text = str(raw_request or '').strip() or analysis_query
    return {'eventOrIssue': text}


def _normalize_weibo_data_request_aliases(raw_request, analysis_query):
    request_payload = dict(raw_request or {})
    event = (
        request_payload.get('eventOrIssue')
        or request_payload.get('event')
        or request_payload.get('event_or_issue')
        or request_payload.get('event_or_issue_name')
        or request_payload.get('issue')
        or request_payload.get('eventName')
        or request_payload.get('event_name')
        or request_payload.get('topic')
        or analysis_query
    )
    if event:
        request_payload['eventOrIssue'] = str(event).strip()

    subject = (
        request_payload.get('affectedSubject')
        or request_payload.get('affected_subject')
        or request_payload.get('subject')
        or request_payload.get('target')
    )
    if subject:
        request_payload['affectedSubject'] = str(subject).strip()

    time_window = (
        request_payload.get('timeWindow')
        or request_payload.get('time_window')
        or request_payload.get('window')
        or request_payload.get('date_range')
    )
    if time_window:
        request_payload['timeWindow'] = str(time_window).strip()

    profile_id = (
        request_payload.get('profileId')
        or request_payload.get('profile_id')
        or request_payload.get('profile')
    )
    if profile_id:
        request_payload['profileId'] = str(profile_id).strip()

    weibo_clue = request_payload.get('weiboClue') or request_payload.get('weibo_clue')
    if weibo_clue:
        request_payload['weiboClue'] = str(weibo_clue).strip()

    decision_goal = request_payload.get('decisionGoal') or request_payload.get('decision_goal')
    if decision_goal:
        request_payload['decisionGoal'] = str(decision_goal).strip()

    keyword_values = request_payload.get('keywords') or request_payload.get('searchKeywords') or []
    if isinstance(keyword_values, str):
        keywords = [
            value.strip()
            for value in re.split(r'[,，、|/\\\n]+', keyword_values)
            if value.strip()
        ]
    elif isinstance(keyword_values, list):
        keywords = [str(value).strip() for value in keyword_values if str(value).strip()]
    else:
        keywords = []

    if keywords:
        known_materials = request_payload.get('knownMaterials') or []
        if isinstance(known_materials, str):
            materials = [known_materials]
        elif isinstance(known_materials, list):
            materials = [str(item).strip() for item in known_materials if str(item).strip()]
        else:
            materials = []
        for keyword in keywords:
            if keyword not in materials:
                materials.append(keyword)
        request_payload['knownMaterials'] = materials

        existing_clue = str(request_payload.get('weiboClue') or '').strip()
        keyword_clue = '、'.join(keywords)
        request_payload['weiboClue'] = (
            f"{existing_clue}、{keyword_clue}" if existing_clue else keyword_clue
        )

    return request_payload


def _coerce_readiness_platforms(raw_platforms):
    if raw_platforms is None:
        return None
    if isinstance(raw_platforms, str):
        platforms = [raw_platforms]
    elif isinstance(raw_platforms, list):
        platforms = raw_platforms
    else:
        return None
    normalized = [
        str(platform).strip().lower()
        for platform in platforms
        if str(platform).strip()
    ]
    return normalized or None


def _serialize_weibo_data_request(raw_request, analysis_query):
    if isinstance(raw_request, dict):
        return json.dumps(raw_request, ensure_ascii=False)
    return str(raw_request or '').strip() or analysis_query


def _deserialize_weibo_data_request(value):
    try:
        payload = json.loads(str(value or '{}'))
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _safe_error_message(exc):
    message = str(exc)
    for secret in (
        getattr(settings, 'TIKHUB_API_KEY', None),
        getattr(settings, 'CRAWLER_CLOUD_API_KEY', None),
    ):
        secret_text = str(secret or '')
        if len(secret_text) >= 8:
            message = message.replace(secret_text, '[redacted]')
    return message


def _crawler_cloud_endpoint():
    return (getattr(settings, 'CRAWLER_CLOUD_ENDPOINT', None) or '').strip()


def _refresh_crawl_task_from_cloud_if_needed(task):
    if task.status != 'queued' or not task.cloud_status_url:
        return

    headers = {}
    api_key = (getattr(settings, 'CRAWLER_CLOUD_API_KEY', None) or '').strip()
    if api_key:
        headers['authorization'] = f'Bearer {api_key}'

    try:
        response = requests.get(
            task.cloud_status_url,
            timeout=int(getattr(settings, 'CRAWLER_CLOUD_TIMEOUT', 10) or 10),
            headers=headers or None,
        )
        response.raise_for_status()
        result = response.json()
    except Exception as exc:
        logger.warning(f"Cloud crawler status refresh failed: {exc}")
        return

    status = str(result.get('status') or '').lower()
    if status in {'completed', 'complete', 'succeeded', 'success'}:
        output_files = [
            Path(str(path))
            for path in (result.get('output_files') or result.get('files') or [])
            if str(path).strip()
        ]
        if not output_files:
            task.mark_failed('cloud crawler completed without output_files')
            return
        try:
            _import_crawl_output(
                task,
                output_files,
                include_irrelevant=bool(result.get('include_irrelevant')),
            )
        except Exception as exc:
            logger.exception(f"Cloud crawler output import failed: {exc}")
            task.mark_failed(str(exc))
    elif status in {'failed', 'error', 'cancelled', 'canceled'}:
        task.mark_failed(str(result.get('message') or result.get('error') or status))


def _submit_crawl_task_to_cloud_if_configured(task):
    endpoint = _crawler_cloud_endpoint()
    if not endpoint:
        return

    headers = {}
    api_key = (getattr(settings, 'CRAWLER_CLOUD_API_KEY', None) or '').strip()
    if api_key:
        headers['authorization'] = f'Bearer {api_key}'

    payload = {
        'task_id': task.task_id,
        'analysis_query': task.analysis_query,
        'data_request': task.data_request,
        'platforms': task.platforms,
        'provider': task.provider,
        'caps': task.caps,
    }
    try:
        response = requests.post(
            endpoint,
            json=payload,
            timeout=int(getattr(settings, 'CRAWLER_CLOUD_TIMEOUT', 10) or 10),
            headers=headers or None,
        )
        response.raise_for_status()
        try:
            result = response.json()
        except ValueError:
            result = {}
        task.mark_cloud_submitted(
            job_id=str(result.get('job_id') or result.get('task_id') or ''),
            status_url=str(result.get('status_url') or ''),
        )
    except Exception as exc:
        logger.exception(f"Cloud crawler submission failed: {exc}")
        task.mark_failed(str(exc))


@app.route('/api/config', methods=['GET'])
def get_config():
    """Expose selected configuration values to the frontend."""
    try:
        config_values = read_config_values()
        return jsonify({'success': True, 'config': config_values})
    except Exception as exc:
        logger.exception("读取配置失败")
        return jsonify({'success': False, 'message': f'读取配置失败: {exc}'}), 500


@app.route('/api/config', methods=['POST'])
def update_config():
    """Update configuration values and persist them to config.py."""
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict) or not payload:
        return jsonify({'success': False, 'message': '请求体不能为空'}), 400

    updates = {}
    for key, value in payload.items():
        if key in CONFIG_KEYS:
            updates[key] = value if value is not None else ''

    if not updates:
        return jsonify({'success': False, 'message': '没有可更新的配置项'}), 400

    try:
        write_config_values(updates)
        updated_config = read_config_values()
        return jsonify({'success': True, 'config': updated_config})
    except Exception as exc:
        logger.exception("更新配置失败")
        return jsonify({'success': False, 'message': f'更新配置失败: {exc}'}), 500


@app.route('/api/system/status')
def get_system_status():
    """返回系统启动状态。"""
    state = _get_system_state()
    return jsonify({
        'success': True,
        'started': state['started'],
        'starting': state['starting']
    })


@app.route('/api/system/start', methods=['POST'])
def start_system():
    """在接收到请求后启动完整系统。"""
    allowed, message = _prepare_system_start()
    if not allowed:
        return jsonify({'success': False, 'message': message}), 400

    try:
        success, logs, errors = initialize_system_components()
        if success:
            _set_system_state(started=True)
            return jsonify({'success': True, 'message': '系统启动成功', 'logs': logs})

        _set_system_state(started=False)
        return jsonify({
            'success': False,
            'message': '系统启动失败',
            'logs': logs,
            'errors': errors
        }), 500
    except Exception as exc:  # pragma: no cover - 保底捕获
        logger.exception("系统启动过程中出现异常")
        _set_system_state(started=False)
        return jsonify({'success': False, 'message': f'系统启动异常: {exc}'}), 500
    finally:
        _set_system_state(starting=False)

@app.route('/api/system/shutdown', methods=['POST'])
def shutdown_system():
    """优雅停止所有组件并关闭当前服务进程。"""
    state = _get_system_state()
    if state['starting']:
        return jsonify({'success': False, 'message': '系统正在启动/重启，请稍候'}), 400

    target_ports = [
        f"{name}:{info['port']}"
        for name, info in processes.items()
        if info.get('port')
    ]

    # 已有关机请求执行中时，返回当前存活的子进程，便于前端判断进度
    if not _mark_shutdown_requested():
        running = _describe_running_children()
        detail = '关机指令已下发，请稍等...'
        if running:
            detail = f"关机指令已下发，等待进程退出: {', '.join(running)}"
        if target_ports:
            detail = f"{detail}（端口: {', '.join(target_ports)}）"
        return jsonify({'success': True, 'message': detail, 'ports': target_ports})

    running = _describe_running_children()
    if running:
        _log_shutdown_step("开始关闭系统，正在等待子进程退出: " + ", ".join(running))
    else:
        _log_shutdown_step("开始关闭系统，未检测到存活子进程")

    try:
        _set_system_state(started=False, starting=False)
        _start_async_shutdown(cleanup_timeout=6.0)
        message = '关闭系统指令已下发，正在停止进程'
        if running:
            message = f"{message}: {', '.join(running)}"
        if target_ports:
            message = f"{message}（端口: {', '.join(target_ports)}）"
        return jsonify({'success': True, 'message': message, 'ports': target_ports})
    except Exception as exc:  # pragma: no cover - 兜底捕获
        logger.exception("系统关闭过程中出现异常")
        return jsonify({'success': False, 'message': f'系统关闭异常: {exc}'}), 500

@socketio.on('connect')
def handle_connect():
    """客户端连接"""
    emit('status', 'Connected to Flask server')

@socketio.on('request_status')
def handle_status_request():
    """请求状态更新"""
    check_app_status()
    emit('status_update', {
        app_name: {
            'status': info['status'],
            'port': info['port']
        }
        for app_name, info in processes.items()
    })


def run_flask_server():
    # 从配置文件读取 HOST 和 PORT
    from config import settings
    HOST = settings.HOST
    PORT = settings.PORT
    
    logger.info("等待配置确认，系统将在前端指令后启动组件...")
    logger.info(f"Flask服务器已启动，访问地址: http://{HOST}:{PORT}")
    
    socketio.run(app, host=HOST, port=PORT, debug=False, allow_unsafe_werkzeug=True)


if __name__ == '__main__':
    try:
        run_flask_server()
    except KeyboardInterrupt:
        logger.info("\n正在关闭应用...")
        cleanup_processes()
        
    
