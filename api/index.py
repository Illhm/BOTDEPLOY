"""
Bot Deploy Manager - Vercel Serverless Edition

A Telegram bot for deploying and managing Python scripts remotely.
Features adapted for Vercel: Webhook-based, synchronous handlers.
"""

import os
import sys
import re
import ast
import logging
import tempfile
import subprocess
import venv
from threading import Lock
from typing import Dict, Optional, Set, List
from datetime import datetime
from pathlib import Path

import requests
import telebot
from telebot import types as tele_types
from telebot import util as tele_util
from flask import Flask, request, jsonify

# ============================================================================
# CONFIGURATION
# ============================================================================
class Config:
    def __init__(self):
        # Fallback to local config.py if exists, otherwise use environment variables
        try:
            import config as local_config
            self._use_local = True
            self.local_config = local_config
        except ImportError:
            self._use_local = False
            self.local_config = None

    def get(self, key, default=None):
        env_val = os.getenv(key)
        if env_val is not None:
            if env_val.lower() == 'true': return True
            if env_val.lower() == 'false': return False
            try: return int(env_val)
            except ValueError: pass
            return env_val

        if self._use_local and hasattr(self.local_config, key):
            return getattr(self.local_config, key)

        return default

config = Config()

BOT_TOKEN = config.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not configured in environment variables or config.py")

is_vercel = os.getenv("VERCEL") in ("1", "true", "True")

if is_vercel:
    TEMP_DIR = Path('/tmp/botdeploy')
    LOG_DIR = Path('/tmp/logs')
    VENV_DIR = Path('/tmp/venvs')
else:
    TEMP_DIR = Path(config.get('TEMP_DIR', '/tmp/botdeploy'))
    LOG_DIR = Path(config.get('LOG_DIR', '/tmp/logs'))
    VENV_DIR = Path(config.get('VENV_DIR', '/tmp/venvs'))

ALLOWED_USERS_RAW = config.get("ALLOWED_USERS", "")

# Initialize Bot (Synchronous for Serverless)
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# Initialize Flask
app = Flask(__name__)

# Set up temporary directories
TEMP_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
VENV_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# ============================================================================
# UTILITIES
# ============================================================================

def _parse_allowed_users(raw_value) -> List[int]:
    if raw_value in (None, False, ""):
        return []
    if isinstance(raw_value, (list, tuple, set)):
        return [int(u) for u in raw_value if str(u).isdigit()]
    if isinstance(raw_value, str):
        cleaned = raw_value.strip().strip("[]")
        if not cleaned: return []
        return [int(u.strip().strip("'\"")) for u in cleaned.split(',') if u.strip().strip("'\"").isdigit()]
    return []

ALLOWED_USERS = _parse_allowed_users(ALLOWED_USERS_RAW)

def is_authorized(message: tele_types.Message) -> bool:
    if not getattr(message, "from_user", None): return False
    if not ALLOWED_USERS: return True
    return message.from_user.id in ALLOWED_USERS

def _escape_markdown(text: str) -> str:
    text = str(text)
    escape_fn = getattr(tele_util, "escape_markdown", None)
    if callable(escape_fn): return escape_fn(text)
    return re.sub(r"([_*\\[`])", r"\\\1", text)

# Global storage for pending deployments (Since Vercel is stateless, this might be lost between cold starts, but it works for quick back-to-back requests if instance is kept warm)
pending_deployments: Dict[int, List[dict]] = {}

# ============================================================================
# DEPENDENCY MANAGER (Simplified for Serverless)
# ============================================================================
class DependencyManager:
    # Standard library modules (no need to install)
    STDLIB_MODULES = {
        'abc', 'aifc', 'argparse', 'array', 'ast', 'asynchat', 'asyncio', 'asyncore',
        'atexit', 'audioop', 'base64', 'bdb', 'binascii', 'binhex', 'bisect', 'builtins',
        'bz2', 'calendar', 'cgi', 'cgitb', 'chunk', 'cmath', 'cmd', 'code', 'codecs',
        'codeop', 'collections', 'colorsys', 'compileall', 'concurrent', 'configparser',
        'contextlib', 'copy', 'copyreg', 'cProfile', 'crypt', 'csv', 'ctypes', 'curses',
        'dataclasses', 'datetime', 'dbm', 'decimal', 'difflib', 'dis', 'distutils', 'doctest',
        'email', 'encodings', 'enum', 'errno', 'faulthandler', 'fcntl', 'filecmp', 'fileinput',
        'fnmatch', 'formatter', 'fractions', 'ftplib', 'functools', 'gc', 'getopt', 'getpass',
        'gettext', 'glob', 'grp', 'gzip', 'hashlib', 'heapq', 'hmac', 'html', 'http', 'imaplib',
        'imghdr', 'imp', 'importlib', 'inspect', 'io', 'ipaddress', 'itertools', 'json', 'keyword',
        'lib2to3', 'linecache', 'locale', 'logging', 'lzma', 'mailbox', 'mailcap', 'marshal',
        'math', 'mimetypes', 'mmap', 'modulefinder', 'multiprocessing', 'netrc', 'nis', 'nntplib',
        'numbers', 'operator', 'optparse', 'os', 'ossaudiodev', 'parser', 'pathlib', 'pdb',
        'pickle', 'pickletools', 'pipes', 'pkgutil', 'platform', 'plistlib', 'poplib', 'posix',
        'posixpath', 'pprint', 'profile', 'pstats', 'pty', 'pwd', 'py_compile', 'pyclbr', 'pydoc',
        'queue', 'quopri', 'random', 're', 'readline', 'reprlib', 'resource', 'rlcompleter',
        'runpy', 'sched', 'secrets', 'select', 'selectors', 'shelve', 'shlex', 'shutil', 'signal',
        'site', 'smtpd', 'smtplib', 'sndhdr', 'socket', 'socketserver', 'spwd', 'sqlite3', 'ssl',
        'stat', 'statistics', 'string', 'stringprep', 'struct', 'subprocess', 'sunau', 'symbol',
        'symtable', 'sys', 'sysconfig', 'syslog', 'tabnanny', 'tarfile', 'telnetlib', 'tempfile',
        'termios', 'test', 'textwrap', 'threading', 'time', 'timeit', 'tkinter', 'token',
        'tokenize', 'trace', 'traceback', 'tracemalloc', 'tty', 'turtle', 'turtledemo', 'types',
        'typing', 'unicodedata', 'unittest', 'urllib', 'uu', 'uuid', 'venv', 'warnings', 'wave',
        'weakref', 'webbrowser', 'winreg', 'winsound', 'wsgiref', 'xdrlib', 'xml', 'xmlrpc',
        'zipapp', 'zipfile', 'zipimport', 'zlib', '_thread'
    }

    PACKAGE_ALIASES = {"pil": "Pillow"}

    @staticmethod
    def extract_imports(script_path: Path) -> Set[str]:
        imports = set()
        try:
            with open(script_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names: imports.add(alias.name.split('.')[0])
                    elif isinstance(node, ast.ImportFrom):
                        if node.module: imports.add(node.module.split('.')[0])
            except SyntaxError:
                import_pattern = r'^\s*(?:from\s+(\S+)|import\s+(\S+))'
                for match in re.finditer(import_pattern, content, re.MULTILINE):
                    module = match.group(1) or match.group(2)
                    imports.add(module.split('.')[0].split(' ')[0])
            return imports - DependencyManager.STDLIB_MODULES
        except Exception:
            return set()

    @classmethod
    def resolve_packages(cls, imports: Set[str]) -> List[str]:
        resolved, seen = [], set()
        normalized_imports = {module.lower() for module in imports}
        for module in sorted(imports):
            package_name = cls.PACKAGE_ALIASES.get(module.lower(), module)
            if package_name in seen: continue
            seen.add(package_name)
            resolved.append(package_name)
        if "pyrogram" in normalized_imports and "tgcrypto" not in seen:
            seen.add("tgcrypto")
            resolved.append("tgcrypto")
        return resolved

    @staticmethod
    def create_venv(venv_path: Path) -> bool:
        try:
            venv.create(venv_path, with_pip=True, clear=True)
            return True
        except Exception as e:
            logger.error(f"Venv error: {e}")
            return False

    @staticmethod
    def install_packages(venv_path: Path, packages: List[str]) -> tuple[bool, str]:
        if not packages: return True, "No packages"
        pip_path = venv_path / "bin" / "pip"
        if not pip_path.exists(): return False, "pip not found"
        try:
            cmd = [str(pip_path), "install", "--no-cache-dir"] + packages
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            return res.returncode == 0, res.stdout if res.returncode == 0 else res.stderr
        except Exception as e: return False, str(e)

    @staticmethod
    def install_from_requirements(venv_path: Path, req_file: Path) -> tuple[bool, str]:
        pip_path = venv_path / "bin" / "pip"
        if not pip_path.exists(): return False, "pip not found"
        try:
            cmd = [str(pip_path), "install", "--no-cache-dir", "-r", str(req_file)]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            return res.returncode == 0, res.stdout if res.returncode == 0 else res.stderr
        except Exception as e: return False, str(e)

dependency_manager = DependencyManager()

# ============================================================================
# PROCESS MANAGER (Adapted for Serverless)
# ============================================================================
# Note: Vercel functions have a timeout (usually 10s on hobby, up to 60s/300s on pro).
# Processes started with subprocess.Popen might be killed when the HTTP request ends.
# To keep processes alive on Vercel is fundamentally against the serverless model,
# but we will start them in the background as best effort.

class ProcessInfo:
    def __init__(self, pid, process, file_path, log_path, chat_id):
        self.pid = pid
        self.process = process
        self.file_path = file_path
        self.log_path = log_path
        self.chat_id = chat_id
        self.created_at = datetime.now()

class ProcessManager:
    def __init__(self):
        self._processes: Dict[int, ProcessInfo] = {}

    def get_sanitized_env(self):
        safe_env = os.environ.copy()
        for key in {'BOT_TOKEN', 'API_ID', 'API_HASH', 'SHUTDOWN_TOKEN'}:
            safe_env.pop(key, None)
        return safe_env

    def setup_dependencies(self, script_path: Path, req_file: Optional[Path] = None):
        use_venv = config.get('USE_VENV', True)
        if not use_venv: return None, "Venv disabled"

        timestamp = datetime.now().timestamp()
        venv_path = VENV_DIR / f"venv_{timestamp}"

        messages = []
        if dependency_manager.create_venv(venv_path):
            messages.append("✅ Virtual environment created")
            if req_file and req_file.exists():
                succ, out = dependency_manager.install_from_requirements(venv_path, req_file)
                messages.append("✅ Requirements installed" if succ else f"⚠️ Install failed: {out[:100]}")
            else:
                imports = dependency_manager.extract_imports(script_path)
                packages = dependency_manager.resolve_packages(imports)
                if packages:
                    succ, out = dependency_manager.install_packages(venv_path, packages)
                    messages.append("✅ Dependencies installed" if succ else f"⚠️ Install failed: {out[:100]}")
                else:
                    messages.append("ℹ️ No external dependencies")
            return venv_path, "\\n".join(messages)
        return None, "Failed to create venv"

    def run_script(self, script_path: Path, log_path: Path, venv_path: Optional[Path], chat_id: int):
        try:
            python_path = venv_path / "bin" / "python" if venv_path else Path(sys.executable)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a") as log_file:
                # Start process detached (best effort for serverless)
                process = subprocess.Popen(
                    [str(python_path), str(script_path)],
                    stdout=log_file,
                    stderr=log_file,
                    cwd=script_path.parent,
                    env=self.get_sanitized_env(),
                    start_new_session=True # Detach from parent
                )
            return process
        except Exception as exc:
            logger.error(f"Start failed: {exc}")
            return None

process_manager = ProcessManager()

# ============================================================================
# BOT HANDLERS
# ============================================================================

@bot.message_handler(commands=["start", "help"])
def start_command(message: tele_types.Message):
    welcome_text = (
        "👋 **Welcome to Bot Deploy Manager (Vercel Edition)**\n\n"
        "**Available Commands:**\n"
        "• `/deploy <url>` - Deploy script from URL\n"
        "• Send Python file - Deploy uploaded script\n"
        "• `/status` - Check running processes\n"
        "• `/log <pid>` - Get log file\n"
        "• `/stop <pid>` - Stop process\n\n"
        "⚠️ **Note:** Vercel serverless functions have execution time limits. Long-running bots may be terminated by Vercel."
    )
    bot.reply_to(message, welcome_text)

@bot.message_handler(commands=["deploy"])
def deploy_command(message: tele_types.Message):
    if not is_authorized(message):
        return bot.reply_to(message, "❌ **Access Denied**")

    parts = message.text.split()
    if len(parts) < 2:
        return bot.reply_to(message, "❌ **Invalid Command**\n\nUsage: `/deploy <url>`")

    url = parts[1]
    if not re.match(r'^https?://', url):
        return bot.reply_to(message, "❌ **Invalid URL**")

    bot.reply_to(message, "🌐 **Downloading script from URL...**")
    file_path = TEMP_DIR / f"script_{datetime.now().timestamp()}.py"

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        file_path.write_text(resp.text, encoding='utf-8')
        _handle_deploy(message, file_path, None)
    except Exception as e:
        bot.reply_to(message, f"❌ **Download Failed**: `{str(e)}`")

@bot.message_handler(content_types=['document'])
def deploy_document(message: tele_types.Message):
    if not is_authorized(message):
        return bot.reply_to(message, "❌ Access Denied")

    if message.document.file_name.endswith('.py'):
        bot.reply_to(message, "📥 **Downloading script file...**")
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        script_path = TEMP_DIR / f"script_{datetime.now().timestamp()}_{message.document.file_name}"
        script_path.write_bytes(downloaded_file)

        _handle_deploy(message, script_path, None)
    else:
        bot.reply_to(message, "❌ Only Python files (.py) are supported.")

def _handle_deploy(message, file_path: Path, req_file: Optional[Path]):
    log_path = LOG_DIR / f"log_{datetime.now().timestamp()}.txt"
    bot.reply_to(message, "⚙️ **Preparing environment...**")

    venv_path, status = process_manager.setup_dependencies(file_path, req_file)
    bot.send_message(message.chat.id, _escape_markdown(status), parse_mode="Markdown")

    process = process_manager.run_script(file_path, log_path, venv_path, message.chat.id)
    if not process:
        return bot.send_message(message.chat.id, "❌ Failed to start process")

    pinfo = ProcessInfo(process.pid, process, file_path, log_path, message.chat.id)
    process_manager._processes[process.pid] = pinfo

    bot.send_message(
        message.chat.id,
        f"✅ **Deployment Started**\n\n**PID:** `{process.pid}`\n**Log:** `{log_path.name}`",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=["status"])
def status_command(message: tele_types.Message):
    if not is_authorized(message): return bot.reply_to(message, "❌ Access Denied")

    if not process_manager._processes:
        return bot.reply_to(message, "ℹ️ No active processes at the moment.")

    msg = ["📊 **Process Status**\n"]
    for pid, p in list(process_manager._processes.items()):
        status = "✅ Running" if p.process.poll() is None else "❌ Stopped"
        msg.append(f"PID: `{pid}`\nStatus: {status}\nLog: `{p.log_path.name}`\n---")

    bot.reply_to(message, "\n".join(msg))

@bot.message_handler(commands=["stop"])
def stop_command(message: tele_types.Message):
    if not is_authorized(message): return bot.reply_to(message, "❌ Access Denied")
    parts = message.text.split()
    if len(parts) < 2: return bot.reply_to(message, "Usage: `/stop <pid>`")

    try:
        pid = int(parts[1])
        p = process_manager._processes.pop(pid, None)
        if p:
            try: p.process.terminate()
            except: pass
            bot.reply_to(message, f"✅ Process {pid} stopped.")
        else:
            bot.reply_to(message, "❌ Process not found.")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")

@bot.message_handler(commands=["log"])
def log_command(message: tele_types.Message):
    if not is_authorized(message): return bot.reply_to(message, "❌ Access Denied")
    parts = message.text.split()
    if len(parts) < 2: return bot.reply_to(message, "Usage: `/log <pid>`")

    try:
        pid = int(parts[1])
        # Find log by PID if in memory, else search log dir
        log_file = None
        if pid in process_manager._processes:
            log_file = process_manager._processes[pid].log_path
        else:
            # Fallback search in /tmp/logs if process died and was removed from memory
            bot.reply_to(message, "⚠️ Process not active in memory, log might be missing.")
            return

        if log_file and log_file.exists():
            with open(log_file, "rb") as f:
                bot.send_document(message.chat.id, f)
        else:
            bot.reply_to(message, "❌ Log file not found.")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")

# ============================================================================
# FLASK ROUTES FOR VERCEL
# ============================================================================

@app.route('/')
def home():
    return jsonify({"status": "Bot Deploy Manager (Vercel) is running!"})

@app.route('/api/webhook', methods=['POST'])
def webhook():
    """Endpoint for Telegram to send updates"""
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = tele_types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    return 'Forbidden', 403

@app.route('/api/set_webhook', methods=['GET'])
def set_webhook():
    """Helper endpoint to set the webhook URL"""
    host_url = request.host_url.rstrip('/')
    webhook_url = f"{host_url}/api/webhook"

    bot.remove_webhook()
    success = bot.set_webhook(url=webhook_url)

    if success:
        return jsonify({"status": "success", "webhook_url": webhook_url})
    return jsonify({"status": "failed"}), 500

# Vercel requires the app variable to be exposed
if __name__ == '__main__':
    app.run(debug=True, port=5000)
